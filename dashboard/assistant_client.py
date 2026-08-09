"""
AI Job Hunting Assistant using Databricks Foundation Models + MCP Tools

Uses Databricks Foundation Model APIs (authenticated via Unity Catalog)
with intelligent function calling to use your job search MCP tools.
"""

import os
import json
import time
import uuid
from typing import Optional, Dict, Any, List
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
import sys

# Add MCP server to path
mcp_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'mcp_server')
if mcp_path not in sys.path:
    sys.path.insert(0, mcp_path)


class DatabricksAssistantClient:
    """AI Assistant using Databricks Foundation Models with Unity Catalog auth."""
    
    def __init__(self, token: Optional[str] = None, workspace_url: Optional[str] = None):
        """Initialize with authentication token (from app request headers or WorkspaceClient).
        
        Args:
            token: OAuth token from X-Forwarded-Access-Token header (in Databricks Apps)
            workspace_url: Workspace URL (in Databricks Apps)
        """
        try:
            # Create WorkspaceClient with proper authentication
            if token and workspace_url:
                # Databricks App context - create client with explicit token
                # Ensure workspace URL has https:// scheme
                if workspace_url and not workspace_url.startswith(('http://', 'https://')):
                    workspace_url = f"https://{workspace_url}"
                
                self.w = WorkspaceClient(
                    host=workspace_url,
                    token=token
                )
                self.workspace_url = workspace_url
                self.token = token
            else:
                # Notebook context - use default authentication
                try:
                    self.w = WorkspaceClient()
                    self.workspace_url = self.w.config.host
                    self.token = self.w.config.token
                    
                    # Ensure workspace URL has https:// scheme
                    if self.workspace_url and not self.workspace_url.startswith(('http://', 'https://')):
                        self.workspace_url = f"https://{self.workspace_url}"
                except Exception as e:
                    raise Exception(f"No authentication available. In Databricks Apps, pass token from request headers. In notebooks, ensure WorkspaceClient can authenticate. Error: {e}")
            
            # Validate
            if not self.token or not self.workspace_url:
                raise Exception("No authentication token or workspace URL available.")
            
            # Use Meta Llama 3.3 70B - available in this workspace
            self.model_endpoint = "databricks-meta-llama-3-3-70b-instruct"
            
            # Conversation state
            self.conversation_id = None
            self.message_history = []
            
            # Load MCP tools
            self._load_mcp_tools()
            
            print(f"✓ Initialized with Databricks Foundation Model: {self.model_endpoint}")
            print(f"✓ Workspace: {self.workspace_url}")
            print(f"✓ Token: {'Present' if self.token else 'Missing'}")
            print(f"✓ Using SDK serving endpoint client for proper authentication")
            
        except Exception as e:
            print(f"❌ Failed to initialize assistant client: {e}")
            raise
    
    def _load_mcp_tools(self):
        """Load MCP tool functions by importing adapter directly (avoids fastmcp dependency)."""
        try:
            # Import the adapter directly - no fastmcp needed
            import adzuna_adapter
            
            # Create wrapper functions that match expected signatures
            def search_jobs(keywords, location=None, salary_min=None, salary_max=None, remote_only=False, limit=10):
                return adzuna_adapter.search_jobs(
                    keywords=keywords,
                    location=location,
                    salary_min=salary_min,
                    limit=limit
                )
            
            def search_jobs_by_query(query, user_email=None, location=None, limit=10):
                return adzuna_adapter.search_jobs_by_query(
                    query=query,
                    user_email=user_email,
                    location=location,
                    top_k=limit
                )
            
            def explain_job_match(job_id, user_email):
                # Get user info first
                user_info = adzuna_adapter.get_user_info(user_email)
                return adzuna_adapter.explain_job_match(
                    job_id=job_id,
                    user_profile=user_info
                )
            
            def get_user_info(user_email):
                return adzuna_adapter.get_user_info(user_email)
            
            def save_job_to_pipeline(job_id, user_email, status):
                return adzuna_adapter.save_job_to_pipeline(
                    user_email=user_email,
                    job_id=job_id,
                    status=status
                )
            
            def get_user_applications(user_email):
                return adzuna_adapter.get_user_applications(user_email)
            
            def store_user_profile(user_email, profile_text, target_roles=None, location_preferences=None, remote_preference=None, job_preferences=None):
                return adzuna_adapter.store_user_profile(
                    user_email=user_email,
                    profile_text=profile_text,
                    target_roles=target_roles,
                    location_preferences=location_preferences,
                    remote_preference=remote_preference,
                    job_preferences=job_preferences
                )
            
            def get_cover_letter_context(job_id, user_email):
                return adzuna_adapter.generate_cover_letter(
                    user_email=user_email,
                    job_id=job_id
                )
            
            # Store wrapper functions
            self.tools_map = {
                'search_jobs': search_jobs,
                'search_jobs_by_query': search_jobs_by_query,
                'explain_job_match': explain_job_match,
                'get_user_info': get_user_info,
                'save_job_to_pipeline': save_job_to_pipeline,
                'get_user_applications': get_user_applications,
                'store_user_profile': store_user_profile,
                'get_cover_letter_context': get_cover_letter_context
            }
            
            # Define tool schemas for function calling
            self.tool_descriptions = """
Available Tools:
1. search_jobs(keywords, location=None, salary_min=None, salary_max=None, remote_only=False, limit=10)
   - Search for jobs by keywords, location, and filters
   
2. search_jobs_by_query(query, user_email=None, location=None, limit=10)
   - Semantic search using natural language, can match against user profile
   
3. explain_job_match(job_id, user_email)
   - Get detailed explanation of why a job matches the user's profile
   
4. get_user_info(user_email)
   - Get user's profile, skills, and preferences
   
5. save_job_to_pipeline(job_id, user_email, status)
   - Save job to application pipeline (status: saved, applied, interviewing, offer, rejected)
   
6. get_user_applications(user_email)
   - Get user's job applications and their status
   
7. store_user_profile(user_email, profile_text, target_roles=None, location_preferences=None, remote_preference=None, job_preferences=None)
   - Manage user profile with resume text and job search preferences
   
8. get_cover_letter_context(job_id, user_email)
   - Retrieve job and profile data for cover letter drafting
"""
            
            print(f"✓ Loaded {len(self.tools_map)} MCP tools")
            
        except Exception as e:
            print(f"Warning: Could not load MCP tools: {e}")
            self.tools_map = {}
            self.tool_descriptions = ""
    
    def create_conversation(
        self,
        user_email: Optional[str] = None,
        **kwargs  # Accept and ignore other args for compatibility
    ) -> str:
        """Create a new conversation.
        
        Args:
            user_email: User's email for context
        
        Returns:
            Conversation ID
        """
        # Generate unique conversation ID
        self.conversation_id = str(uuid.uuid4())
        
        # Initialize with system prompt
        system_prompt = f"""You are an AI career coach and job search assistant.

You help users find jobs, understand job matches, and track their applications.

{self.tool_descriptions}

When users ask about jobs:
1. Use search_jobs or search_jobs_by_query to find relevant positions
2. Provide specific details (title, company, salary, location)
3. Use explain_job_match when users want to know why a job fits
4. Use save_job_to_pipeline when users want to track a job
5. Use get_user_applications to show their pipeline
6. Use store_user_profile to help users set up or update their profile
7. Use get_cover_letter_context when users want help drafting a cover letter

Be conversational and helpful. When calling tools, format your response as:
TOOL_CALL: tool_name(arg1="value1", arg2="value2")

User context: {user_email or 'unknown'}"""
        
        self.message_history = [{
            'role': 'system',
            'content': system_prompt
        }]
        
        print(f"Created conversation: {self.conversation_id}")
        return self.conversation_id
    
    def send_message(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Send a message and get AI response with tool calling.
        
        Args:
            message: User's message
            conversation_id: Optional conversation ID
        
        Returns:
            Response with reply text and metadata
        """
        import re
        
        conv_id = conversation_id or self.conversation_id
        
        if not conv_id:
            raise Exception("No conversation ID. Call create_conversation() first.")
        
        # Validate prerequisites
        if not self.token:
            error_msg = "No authentication token available. Cannot make API calls."
            return {
                'success': False,
                'error': error_msg,
                'reply': error_msg
            }
        
        if not self.workspace_url:
            error_msg = "No workspace URL available. Cannot make API calls."
            return {
                'success': False,
                'error': error_msg,
                'reply': error_msg
            }
        
        try:
            # Add user message to history
            self.message_history.append({
                'role': 'user',
                'content': message
            })
            
            # Call Databricks Foundation Model using SDK (handles token scopes automatically)
            print(f"Calling Foundation Model API via SDK: {self.model_endpoint}")
            print(f"Message count: {len(self.message_history)}")
            
            # Convert message history to SDK format
            sdk_messages = []
            for msg in self.message_history:
                role_str = msg['role']
                if role_str == 'system':
                    role = ChatMessageRole.SYSTEM
                elif role_str == 'user':
                    role = ChatMessageRole.USER
                elif role_str == 'assistant':
                    role = ChatMessageRole.ASSISTANT
                else:
                    continue
                
                sdk_messages.append(ChatMessage(
                    role=role,
                    content=msg['content']
                ))
            
            try:
                # Use SDK to call serving endpoint with proper authentication
                response = self.w.serving_endpoints.query(
                    name=self.model_endpoint,
                    messages=sdk_messages,
                    max_tokens=1024,
                    temperature=0.7
                )
                
                # Extract response from SDK result
                if response.choices and len(response.choices) > 0:
                    assistant_reply = response.choices[0].message.content
                else:
                    error_msg = "No response choices returned from model"
                    print(error_msg)
                    return {
                        'success': False,
                        'error': error_msg,
                        'reply': error_msg
                    }
                
            except Exception as api_error:
                error_msg = f"""Foundation Model API Error:

Error: {str(api_error)}

Possible causes:
- Foundation Model endpoint not accessible in this workspace
- Model endpoint name incorrect: {self.model_endpoint}
- Workspace permissions

Try checking available endpoints with: databricks serving-endpoints list"""
                
                print(f"API Error: {error_msg}")
                import traceback
                traceback.print_exc()
                return {
                    'success': False,
                    'error': error_msg,
                    'reply': error_msg
                }
            
            print(f"Assistant reply: {assistant_reply[:200]}...")
            
            # Check if assistant wants to call a tool
            tool_calls = self._extract_tool_calls(assistant_reply)
            
            if tool_calls:
                # Execute tools and get final response
                tool_results = []
                for tool_name, tool_args in tool_calls:
                    print(f"Calling tool: {tool_name}({tool_args})")
                    result = self._execute_tool(tool_name, tool_args)
                    tool_results.append(f"{tool_name} returned: {json.dumps(result, indent=2)}")
                
                # Add tool results to history and get final response
                tool_context = "\n\n".join(tool_results)
                self.message_history.append({
                    'role': 'assistant',
                    'content': f"[Used tools]\n{tool_context}"
                })
                
                # Get final conversational response using SDK
                final_messages_list = self.message_history + [{
                    'role': 'user',
                    'content': 'Based on the tool results above, provide a helpful response to the user.'
                }]
                
                final_sdk_messages = []
                for msg in final_messages_list:
                    role_str = msg['role']
                    if role_str == 'system':
                        role = ChatMessageRole.SYSTEM
                    elif role_str == 'user':
                        role = ChatMessageRole.USER
                    elif role_str == 'assistant':
                        role = ChatMessageRole.ASSISTANT
                    else:
                        continue
                    
                    final_sdk_messages.append(ChatMessage(
                        role=role,
                        content=msg['content']
                    ))
                
                try:
                    final_response = self.w.serving_endpoints.query(
                        name=self.model_endpoint,
                        messages=final_sdk_messages,
                        max_tokens=512,
                        temperature=0.7
                    )
                    
                    if final_response.choices and len(final_response.choices) > 0:
                        reply = final_response.choices[0].message.content
                    else:
                        reply = assistant_reply
                except Exception as e:
                    print(f"Warning: Final response call failed: {e}")
                    reply = assistant_reply
            else:
                reply = assistant_reply
            
            # Add final response to history
            self.message_history.append({
                'role': 'assistant',
                'content': reply
            })
            
            return {
                'success': True,
                'reply': reply,
                'conversation_id': conv_id,
                'message_id': str(uuid.uuid4())
            }
            
        except Exception as e:
            print(f"Error in send_message: {e}")
            import traceback
            tb = traceback.format_exc()
            print(tb)
            
            error_msg = f"""Unexpected Error:

Error Type: {type(e).__name__}
Error Message: {str(e)}

Full Traceback:
{tb}

Please check the application logs for more details."""
            
            return {
                'success': False,
                'error': error_msg,
                'reply': error_msg
            }
    
    def _format_messages_for_llama(self) -> str:
        """Format message history for Llama model."""
        formatted = []
        for msg in self.message_history:
            role = msg['role']
            content = msg['content']
            if role == 'system':
                formatted.append(f"System: {content}")
            elif role == 'user':
                formatted.append(f"User: {content}")
            elif role == 'assistant':
                formatted.append(f"Assistant: {content}")
        return "\n\n".join(formatted)
    
    def _extract_tool_calls(self, text: str) -> List[tuple]:
        """Extract tool calls from assistant response.
        
        Looks for patterns like: TOOL_CALL: search_jobs(keywords="python", location="remote")
        """
        import re
        
        pattern = r'TOOL_CALL:\s*(\w+)\(([^)]*)\)'
        matches = re.findall(pattern, text)
        
        tool_calls = []
        for tool_name, args_str in matches:
            # Parse arguments
            args = {}
            if args_str.strip():
                # Simple parsing: key="value" or key=value
                arg_pattern = r'(\w+)\s*=\s*(?:"([^"]*)"|([^,\s]+))'
                for arg_match in re.finditer(arg_pattern, args_str):
                    key = arg_match.group(1)
                    value = arg_match.group(2) or arg_match.group(3)
                    # Try to convert to appropriate type
                    if value.lower() == 'true':
                        value = True
                    elif value.lower() == 'false':
                        value = False
                    elif value.isdigit():
                        value = int(value)
                    args[key] = value
            
            tool_calls.append((tool_name, args))
        
        return tool_calls
    
    def _execute_tool(self, tool_name: str, args: Dict) -> Any:
        """Execute an MCP tool with given arguments."""
        if tool_name not in self.tools_map:
            return {"error": f"Tool '{tool_name}' not found"}
        
        try:
            tool_func = self.tools_map[tool_name]
            result = tool_func(**args)
            return result
        except Exception as e:
            return {"error": str(e)}
    
    def get_conversation_history(self, conversation_id: Optional[str] = None) -> List[Dict]:
        """Get the message history for a conversation."""
        return self.message_history
