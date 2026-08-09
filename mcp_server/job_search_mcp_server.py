"""Job Search MCP Server.

Exposes job search and application management tools over MCP 
(Model Context Protocol) so a Databricks Agent can:
    - Search for jobs via Adzuna API
    - Rank jobs against user profile
    - Save/apply to jobs
    - Track application pipeline
    - Draft cover letters
    - Manage interview notes

Deploy this as a separate Databricks App from the main dashboard,
so an AI agent can register its URL as an external MCP server.

Run locally:
    python job_search_mcp_server.py
"""

import os
import logging
from contextvars import ContextVar

from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

import adzuna_adapter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("job-search-mcp-server")

# Context variable to store request headers for accessing end-user identity
_request_context: ContextVar[dict] = ContextVar('request_context', default={})


def _get_end_user_email() -> str:
    """Get the actual end user's email from request headers."""
    headers = _request_context.get()
    forwarded_user = headers.get('x-forwarded-user')
    if forwarded_user:
        return forwarded_user
    
    # Fallback: use service principal
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        return w.current_user.me().user_name or 'unknown@databricks.com'
    except Exception:
        return 'unknown@databricks.com'


mcp = FastMCP("job-search-service")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware to capture HTTP headers containing end-user identity."""
    async def dispatch(self, request: Request, call_next):
        headers = {
            'x-forwarded-user': request.headers.get('x-forwarded-user'),
            'x-forwarded-email': request.headers.get('x-forwarded-email'),
        }
        _request_context.set(headers)
        response = await call_next(request)
        return response


# ============================================================================
# MCP Tools - Job Search
# ============================================================================

@mcp.tool
def search_jobs(
    keywords: str = "",
    location: str = "",
    remote_only: bool = False,
    salary_min: int = None,
    results_per_page: int = 20
) -> dict:
    """
    Search for job postings using the Adzuna API.
    
    Args:
        keywords: Job title or keywords (e.g., "Python developer", "data engineer")
        location: Location to search in (e.g., "San Francisco", "Remote")
        remote_only: Filter for remote-only positions
        salary_min: Minimum salary requirement
        results_per_page: Number of results to return (max 50)
    
    Returns:
        Dict with count and list of job results
    """
    user_email = _get_end_user_email()
    logger.info(f"search_jobs called by {user_email}: keywords={keywords}, location={location}")
    
    try:
        # Handle remote filtering
        what = keywords
        where = location if not remote_only else "remote"
        
        results = adzuna_adapter.search_jobs(
            country="us",
            what=what,
            where=where,
            results_per_page=results_per_page,
            salary_min=salary_min,
        )
        
        return results
    except Exception as e:
        logger.exception(f"Failed to search jobs")
        return {
            "status": "error",
            "message": f"Failed to search jobs: {str(e)}",
        }


@mcp.tool
def get_job_categories() -> list:
    """
    Get list of available job categories from Adzuna.
    
    Useful for filtering job searches by category.
    
    Returns:
        List of category dicts with label and tag
    """
    user_email = _get_end_user_email()
    logger.info(f"get_job_categories called by {user_email}")
    
    try:
        return adzuna_adapter.get_job_categories(country="us")
    except Exception as e:
        logger.exception(f"Failed to get job categories")
        return [{"status": "error", "message": str(e)}]


# ============================================================================
# MCP Tools - Application Management (TODO: Implement with Lakebase)
# ============================================================================

@mcp.tool
def save_job(job_id: str, match_score: float = None, reasoning: str = "") -> dict:
    """
    Save a job posting to the user's saved jobs list.
    
    Args:
        job_id: Adzuna job ID to save
        match_score: Optional match score (0-100)
        reasoning: AI-generated explanation of why this job matches
    
    Returns:
        Confirmation dict with saved_job_id
    """
    user_email = _get_end_user_email()
    logger.info(f"save_job called by {user_email} for job {job_id}")
    
    # TODO: Implement with Lakebase connection
    # Insert into saved_jobs table
    return {
        "status": "success",
        "message": f"Job {job_id} saved successfully",
        "job_id": job_id,
        "match_score": match_score,
    }


@mcp.tool
def update_application_status(
    job_id: str,
    status: str,
    notes: str = ""
) -> dict:
    """
    Update the status of a job application.
    
    Args:
        job_id: Job ID for this application
        status: New status - saved, applied, interviewing, rejected, offer, accepted
        notes: Optional notes about the status change
    
    Returns:
        Confirmation dict
    """
    user_email = _get_end_user_email()
    logger.info(f"update_application_status called by {user_email} for job {job_id} to {status}")
    
    # TODO: Implement with Lakebase connection
    # Update applications table
    return {
        "status": "success",
        "message": f"Application status updated to {status}",
        "job_id": job_id,
        "new_status": status,
    }


@mcp.tool
def add_interview_note(
    job_id: str,
    interview_date: str,
    interview_type: str,
    notes: str,
    follow_up_date: str = None
) -> dict:
    """
    Add interview notes for a job application.
    
    Args:
        job_id: Job ID for this application
        interview_date: Date of interview (YYYY-MM-DD)
        interview_type: Type - phone_screen, technical, behavioral, onsite, final
        notes: Interview notes and feedback
        follow_up_date: Optional follow-up date (YYYY-MM-DD)
    
    Returns:
        Confirmation dict with interview_id
    """
    user_email = _get_end_user_email()
    logger.info(f"add_interview_note called by {user_email} for job {job_id}")
    
    # TODO: Implement with Lakebase connection
    # Insert into interview_notes table
    return {
        "status": "success",
        "message": "Interview note added successfully",
        "job_id": job_id,
        "interview_type": interview_type,
    }


@mcp.tool
def get_stale_applications(days_threshold: int = 14) -> list:
    """
    Get applications that haven't been updated in a while.
    
    Args:
        days_threshold: Number of days without update to consider stale (default 14)
    
    Returns:
        List of stale application dicts
    """
    user_email = _get_end_user_email()
    logger.info(f"get_stale_applications called by {user_email}, threshold={days_threshold} days")
    
    # TODO: Implement with Lakebase connection
    # Query applications with updated_at older than threshold
    return []


@mcp.tool
def draft_cover_letter(job_id: str, job_description: str, user_profile: str) -> dict:
    """
    Generate a tailored cover letter snippet for a job posting.
    
    This is a template - you'll want to integrate with an LLM
    (e.g., Databricks Foundation Model API) to generate the actual content.
    
    Args:
        job_id: Job ID
        job_description: Full job description
        user_profile: User's resume/profile text
    
    Returns:
        Dict with draft cover letter text
    """
    user_email = _get_end_user_email()
    logger.info(f"draft_cover_letter called by {user_email} for job {job_id}")
    
    # TODO: Implement with LLM API
    # Use job_description + user_profile to generate personalized cover letter
    return {
        "status": "success",
        "job_id": job_id,
        "cover_letter": "TODO: Generate personalized cover letter using LLM",
    }


# Add middleware and run
mcp.app.add_middleware(RequestContextMiddleware)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(mcp.app, host="0.0.0.0", port=port)
