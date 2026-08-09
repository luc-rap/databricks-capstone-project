# Databricks Assistant API Integration

This document explains how the AI Job Hunting Copilot integrates with the Databricks Assistant API to provide conversational AI capabilities.

## Architecture Overview

```
┌─────────────────┐
│  Web Browser    │
│  (assistant.html)│
└────────┬────────┘
         │ HTTP POST /api/chat
         ▼
┌─────────────────┐
│  Flask Backend  │
│    (app.py)     │
└────────┬────────┘
         │ Uses
         ▼
┌──────────────────────┐
│ DatabricksAssistant  │
│      Client          │
│ (assistant_client.py)│
└────────┬─────────────┘
         │ REST API
         ▼
┌──────────────────────┐
│  Databricks          │
│  Assistant API       │
│  + MCP Server        │
└──────────────────────┘
```

## Components

### 1. `assistant_client.py` - Python Client SDK

Provides a simple Python interface to the Databricks Assistant API:

```python
from assistant_client import DatabricksAssistantClient

# Initialize client
client = DatabricksAssistantClient()

# Create a conversation (with automatic MCP server discovery)
conversation_id = client.create_conversation(
    user_email="user@example.com",
    auto_discover_mcp=True
)

# Send a message
result = client.send_message(
    "Find me data engineering jobs in San Francisco",
    conversation_id=conversation_id
)

print(result['reply'])
```

**Key Features:**
- Automatic MCP server discovery and attachment
- Conversation state management
- Message history tracking
- Error handling with fallbacks

### 2. `app.py` - Flask Backend Integration

The `/api/chat` endpoint handles chat messages:

```python
@app.route('/api/chat', methods=['POST'])
def chat():
    # Get user message
    message = request.json.get('message')
    
    # Get Assistant client
    client = get_assistant_client()
    
    # Create conversation if needed (with MCP auto-discovery)
    if not client.conversation_id:
        client.create_conversation(
            user_email=get_current_user()['email'],
            auto_discover_mcp=True
        )
    
    # Send message and return response
    result = client.send_message(message)
    return jsonify(result)
```

**Features:**
- Singleton Assistant client pattern (reuses connection)
- Automatic conversation creation
- User context injection
- Comprehensive error handling

### 3. `assistant.html` - Chat UI

Provides a clean chat interface with:
- User/assistant message bubbles
- "Thinking..." indicator while waiting
- Conversation continuity (tracks conversation_id)
- Basic markdown formatting support
- Error handling and retry

## How It Works

### First Message Flow

1. **User sends message** via the web UI
2. **Frontend POSTs** to `/api/chat` with `{ message: "..." }`
3. **Backend creates conversation**:
   - Calls `client.create_conversation(auto_discover_mcp=True)`
   - Assistant API discovers MCP servers (like your job search MCP server)
   - Attaches discovered servers to the conversation
   - Returns `conversation_id`
4. **Backend sends message** to Assistant API
5. **Assistant processes** the message:
   - Uses natural language understanding
   - Calls MCP tools if needed (e.g., `search_jobs`, `explain_job_match`)
   - Generates response
6. **Backend returns** `{ reply: "...", conversation_id: "..." }`
7. **Frontend displays** response and stores `conversation_id`

### Subsequent Messages

1. User sends another message
2. Frontend includes `conversation_id` in request
3. Backend reuses existing conversation
4. Assistant maintains context from previous messages
5. Response is returned and displayed

## MCP Server Integration

The system automatically discovers and attaches your MCP server:

### MCP Server Discovery

```python
# In assistant_client.py
def discover_mcp_servers(self) -> List[str]:
    """Discover available MCP servers in the workspace."""
    response = requests.get(
        f"{self.api_base}/mcp/servers",
        headers=self.headers
    )
    return [server['name'] for server in response.json()['servers']]
```

### Conversation Creation with MCP

```python
# Automatically attach discovered MCP servers
conversation_id = client.create_conversation(
    user_email=user_email,
    auto_discover_mcp=True  # <-- Key flag
)
```

When `auto_discover_mcp=True`, the client:
1. Calls the MCP discovery API
2. Gets list of available MCP servers
3. Attaches them to the conversation
4. Assistant can now call MCP tools

## Available MCP Tools

Your job search MCP server exposes these tools to the Assistant:

- `search_jobs` - Find jobs by keywords/location/filters
- `search_jobs_by_query` - Semantic search using embeddings
- `explain_job_match` - Detailed explanation of job match
- `store_user_profile` - Save user resume/profile
- `save_job_to_pipeline` - Track application
- `get_user_applications` - View pipeline status
- `get_user_info` - Retrieve user profile

The Assistant automatically decides which tools to call based on the user's message.

## Testing the Integration

### 1. Start Your MCP Server

```bash
cd mcp_server
python job_search_mcp_server.py
```

### 2. Deploy Your Flask App

The app should be deployed as a Databricks App or running locally.

### 3. Test Conversation Flow

**User:** "Find me data engineering jobs in San Francisco"

**Behind the scenes:**
- Assistant sees user intent: job search
- Calls MCP tool: `search_jobs(keywords="data engineering", location="San Francisco")`
- Formats results into natural language

**Assistant:** "I found 15 data engineering jobs in San Francisco. Here are the top matches: ..."

**User:** "Tell me more about the first one"

**Behind the scenes:**
- Assistant maintains context (remembers the job list)
- May call `explain_job_match` for detailed analysis

**Assistant:** "This Senior Data Engineer role at [Company] is a strong match (87% score) because..."

## Error Handling

### MCP Server Unavailable

If MCP servers aren't discovered:
```python
try:
    conversation_id = client.create_conversation(auto_discover_mcp=True)
except Exception as e:
    # Fallback: create conversation without MCP
    conversation_id = client.create_conversation(auto_discover_mcp=False)
```

The Assistant still responds, but can't use job search tools.

### API Timeout

```python
try:
    result = client.send_message(message, timeout=120)
except requests.Timeout:
    return {"reply": "Request timed out. Please try again."}
```

### Connection Errors

```python
except Exception as e:
    return {
        "reply": "Sorry, I encountered an error. Please try again.",
        "error": str(e)
    }
```

## Configuration

### Environment Variables

```bash
# Databricks workspace (auto-configured by SDK)
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi...

# Flask settings
FLASK_RUN_HOST=0.0.0.0
FLASK_RUN_PORT=8000
```

### Assistant API Endpoints

The client uses these Databricks Assistant API endpoints:

- `POST /api/2.0/assistant/conversations` - Create conversation
- `POST /api/2.0/assistant/messages` - Send message
- `GET /api/2.0/assistant/conversations/{id}/messages` - Get history
- `GET /api/2.0/assistant/mcp/servers` - Discover MCP servers

## Advanced Usage

### Custom MCP Server List

If you know which MCP servers to use:

```python
conversation_id = client.create_conversation(
    user_email=user_email,
    mcp_servers=["job-search-server", "resume-parser"],
    auto_discover_mcp=False
)
```

### Streaming Responses

```python
# Not yet implemented - future enhancement
for chunk in client.send_message_stream(message):
    print(chunk, end='', flush=True)
```

### Access Message History

```python
history = client.get_conversation_history(conversation_id)
for msg in history:
    print(f"{msg['role']}: {msg['content']}")
```

## Troubleshooting

### "No MCP servers discovered"

- Ensure your MCP server is running
- Check MCP server registration in workspace
- Verify workspace permissions

### "Conversation creation failed"

- Check Databricks token validity
- Verify workspace URL is correct
- Check network connectivity

### "Assistant isn't using MCP tools"

- Verify MCP servers were attached (check logs)
- Ensure tool descriptions are clear
- Try more explicit prompts

### "Timeout errors"

- Increase timeout in `send_message()` call
- Check MCP tool performance
- Verify database connectivity

## Next Steps

1. **Add streaming responses** for real-time feedback
2. **Implement conversation persistence** to restore past conversations
3. **Add file upload** for resume parsing
4. **Create analytics dashboard** to track assistant usage
5. **Add feedback mechanism** to improve responses

## Resources

- [Databricks Assistant API Docs](https://docs.databricks.com/assistant/api.html)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Flask Documentation](https://flask.palletsprojects.com/)
