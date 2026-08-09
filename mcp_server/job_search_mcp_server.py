"""Job Search MCP Server.

Exposes job search and application management tools over MCP 
(Model Context Protocol) so a Databricks Agent can:
    - Search for jobs via Adzuna API
    - Rank jobs against user profile using semantic similarity
    - Save/apply to jobs and track application pipeline
    - Generate personalized cover letters using Foundation Model API
    - Manage interview notes
    - Explain job match scores with detailed reasoning

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

import adzuna_adapter as lakebase_adapter  # Renamed from adzuna_adapter

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
        return '<>'
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
    Search for job postings in Lakebase database using keyword filters.
    For semantic search with your profile, use search_jobs_semantic instead.
    
    Args:
        keywords: Job title or keywords (e.g., "Python developer", "data engineer")
        location: Location to search in (e.g., "San Francisco", "Remote")
        remote_only: Filter for remote-only positions
        salary_min: Minimum salary requirement
        results_per_page: Number of results to return
    
    Returns:
        Dict with count and list of job results
    """
    user_email = _get_end_user_email()
    logger.info(f"search_jobs called by {user_email}: keywords={keywords}, location={location}")
    
    try:
        # Handle remote filtering
        search_location = "remote" if remote_only else location
        
        results = lakebase_adapter.search_jobs(
            keywords=keywords,
            location=search_location,
            salary_min=salary_min,
            limit=results_per_page,
        )
        
        return results
    except Exception as e:
        logger.exception(f"Failed to search jobs")
        return {
            "status": "error",
            "message": f"Failed to search jobs: {str(e)}",
        }


@mcp.tool
def search_jobs_semantic(
    query: str,
    use_profile: bool = True,
    location: str = None,
    top_k: int = 10
) -> dict:
    """
    Search jobs using natural language query with semantic matching against stored user profile.
    This uses embeddings for intelligent ranking based on skill and experience alignment.
    
    Args:
        query: Natural language search query (e.g., "find remote data engineering roles")
        use_profile: Whether to combine query with user's stored profile for better ranking (default True)
        location: Optional location filter
        top_k: Number of top matches to return (default 10)
    
    Returns:
        Dict with ranked job results including match scores (query_similarity, profile_similarity, overall match_score)
    """
    user_email = _get_end_user_email()
    logger.info(f"search_jobs_semantic called by {user_email}: query={query}, use_profile={use_profile}")
    
    try:
        results = lakebase_adapter.search_jobs_by_query(
            user_email=user_email,
            query=query,
            use_profile=use_profile,
            location=location,
            top_k=top_k,
        )
        return results
    except Exception as e:
        logger.exception(f"Failed to search jobs semantically")
        return {
            "status": "error",
            "message": f"Failed to search jobs semantically: {str(e)}",
        }


@mcp.tool
def rank_jobs_by_profile(
    user_profile_text: str,
    keywords: str = "",
    location: str = "",
    top_k: int = 10
) -> dict:
    """
    Rank job postings by match to user's profile using semantic similarity.
    
    Args:
        user_profile_text: User's resume/profile text (skills, experience, preferences)
        keywords: Optional keyword filter
        location: Optional location filter
        top_k: Number of top matches to return (default 10)
    
    Returns:
        Dict with ranked job results and match scores
    """
    user_email = _get_end_user_email()
    logger.info(f"rank_jobs_by_profile called by {user_email}")
    
    try:
        results = lakebase_adapter.rank_jobs_by_profile(
            user_profile_text=user_profile_text,
            keywords=keywords,
            location=location,
            top_k=top_k,
        )
        return results
    except Exception as e:
        logger.exception(f"Failed to rank jobs")
        return {
            "status": "error",
            "message": f"Failed to rank jobs: {str(e)}",
        }


@mcp.tool
def explain_job_match(
    job_id: int
) -> dict:
    """
    Explain why a specific job is or isn't a good match for the user.
    Uses stored user profile (resume, preferences, target roles) for comprehensive analysis.
    
    The explanation includes:
    - Overall match score (0-100)
    - Semantic similarity between user's resume and job description
    - Match analysis for: target roles, location/remote, salary, and job preferences
    - Detailed list of strengths (what matches well)
    - Detailed list of gaps (what's missing or misaligned)
    - Actionable recommendation (Strong Apply, Apply, Consider, or Skip)
    
    Args:
        job_id: Job posting ID (internal job_id from database, not external_id)
    
    Returns:
        Dict with:
        - overall_match_score: 0-100 score
        - recommendation: "Strong Apply", "Apply", "Consider", or "Skip"
        - action: Suggested next step
        - strengths: List of why this is a good match
        - gaps: List of misalignments or missing qualifications
        - score_breakdown: Individual scores for semantic, role, location, salary
        - reasoning: Natural language explanation
        - job_details: Job description snippet and basic info
    """
    user_email = _get_end_user_email()
    logger.info(f"explain_job_match called by {user_email} for job {job_id}")
    
    try:
        explanation = lakebase_adapter.explain_job_match(
            user_email=user_email,
            job_id=job_id,
        )
        return explanation
    except Exception as e:
        logger.exception(f"Failed to explain job match")
        return {
            "status": "error",
            "message": f"Failed to explain job match: {str(e)}",
        }


@mcp.tool
def save_job(job_id: str, match_score: float = None, notes: str = "") -> dict:
    """
    Save a job posting to the user's 'saved' pipeline stage.
    
    Args:
        job_id: Job ID to save
        match_score: Optional match score (0-100)
        notes: Optional notes about why this job is interesting
    
    Returns:
        Confirmation dict with application_id
    """
    user_email = _get_end_user_email()
    logger.info(f"save_job called by {user_email} for job {job_id}")
    
    try:
        result = lakebase_adapter.save_job_to_pipeline(
            user_email=user_email,
            job_id=job_id,
            stage="saved",
            notes=notes,
            match_score=match_score,
        )
        return result
    except Exception as e:
        logger.exception(f"Failed to save job")
        return {
            "status": "error",
            "message": f"Failed to save job: {str(e)}",
        }


@mcp.tool
def update_application_status(
    job_id: str,
    status: str,
    notes: str = ""
) -> dict:
    """
    Update the pipeline stage of a job application.
    
    Args:
        job_id: Job ID for this application
        status: New stage - saved, applied, interviewing, rejected, offer, accepted
        notes: Optional notes about the status change
    
    Returns:
        Confirmation dict
    """
    user_email = _get_end_user_email()
    logger.info(f"update_application_status called by {user_email} for job {job_id} to {status}")
    
    try:
        result = lakebase_adapter.save_job_to_pipeline(
            user_email=user_email,
            job_id=job_id,
            stage=status,
            notes=notes,
        )
        return result
    except Exception as e:
        logger.exception(f"Failed to update application status")
        return {
            "status": "error",
            "message": f"Failed to update application status: {str(e)}",
        }


@mcp.tool
def get_my_applications(stage: str = None) -> dict:
    """
    Get all of the user's job applications, optionally filtered by stage.
    
    Args:
        stage: Optional stage filter - saved, applied, interviewing, rejected, offer, accepted
    
    Returns:
        Dict with list of applications and job details
    """
    user_email = _get_end_user_email()
    logger.info(f"get_my_applications called by {user_email}, stage={stage}")
    
    try:
        applications = lakebase_adapter.get_user_applications(
            user_email=user_email,
            stage=stage,
        )
        return {
            "status": "success",
            "count": len(applications),
            "applications": applications,
        }
    except Exception as e:
        logger.exception(f"Failed to get applications")
        return {
            "status": "error",
            "message": f"Failed to get applications: {str(e)}",
        }


@mcp.tool
def get_user_info() -> dict:
    """
    Get the current user's profile information including resume, target roles, and job preferences.
    
    Returns:
        Dict with user info including:
        - user: Basic user info (id, email, created_at)
        - profile: Profile details (resume_text, target_roles, location_preferences, 
                   remote_preference, salary_min, salary_max)
    """
    user_email = _get_end_user_email()
    logger.info(f"get_user_info called by {user_email}")
    
    try:
        user_info = lakebase_adapter.get_user_info(user_email=user_email)
        return user_info
    except Exception as e:
        logger.exception(f"Failed to get user info")
        return {
            "status": "error",
            "message": f"Failed to get user info: {str(e)}",
        }


@mcp.tool
def store_user_profile(
    profile_text: str,
    target_roles: str = None,
    location_preferences: str = None,
    remote_preference: str = None,
    job_preferences: str = None
) -> dict:
    """
    Store or update the user's profile/resume with preferences.
    This will automatically generate embeddings for semantic job matching.
    
    Args:
        profile_text: User's resume or profile text describing skills, experience, etc.
        target_roles: Comma-separated target roles (e.g., "Data Engineer, ML Engineer")
        location_preferences: Preferred locations (e.g., "San Francisco, Remote")
        remote_preference: Remote work preference (remote, hybrid, onsite)
        job_preferences: Job preferences (work authorization, visa requirements, etc.)
    
    Returns:
        Confirmation dict with profile_id and embedding dimensions
    """
    user_email = _get_end_user_email()
    logger.info(f"store_user_profile called by {user_email}")
    
    try:
        result = lakebase_adapter.store_user_profile(
            user_email=user_email,
            profile_text=profile_text,
            target_roles=target_roles,
            location_preferences=location_preferences,
            remote_preference=remote_preference,
            job_preferences=job_preferences,
        )
        return result
    except Exception as e:
        logger.exception(f"Failed to store user profile")
        return {
            "status": "error",
            "message": f"Failed to store user profile: {str(e)}",
        }


@mcp.tool
def get_cover_letter_context(job_id: int) -> dict:
    """
    Get context data for drafting a personalized cover letter for a job posting.
    
    Returns the user's profile (resume, target roles, experience) and job details
    (title, company, description) that you can use to draft a tailored cover letter.
    
    Use this information to write a compelling 2-3 paragraph cover letter that:
    - Highlights relevant skills and experience matching the job requirements
    - Expresses genuine interest in the role and company
    - Is concise and ready to use in an application
    - Avoids generic statements and focuses on specific qualifications
    
    Args:
        job_id: Job posting ID (internal job_id from database)
    
    Returns:
        Dict with:
        - status: "success" or "error"
        - job: Job details (title, company, location, description, url)
        - profile: User profile (resume_text, target_roles, years_experience, location_preferences, remote_preference)
        - error: Error message (if status is "error")
    """
    user_email = _get_end_user_email()
    logger.info(f"get_cover_letter_context called by {user_email} for job {job_id}")
    
    try:
        result = lakebase_adapter.generate_cover_letter(
            user_email=user_email,
            job_id=job_id,
        )
        return result
    except Exception as e:
        logger.exception(f"Failed to get cover letter context")
        return {
            "status": "error",
            "error": f"Failed to get cover letter context: {str(e)}",
        }


if __name__ == "__main__":
    # Add middleware to capture request headers for end-user identity
    # This must be done before mcp.run() is called
    if hasattr(mcp, 'app') and mcp.app is not None:
        mcp.app.add_middleware(RequestContextMiddleware)
    
    # Databricks Apps route external HTTP traffic to this port via app.yaml;
    # streamable-http is the transport Databricks' MCP client/gateway expects
    # (see the "Host your own MCP" doc linked in the module docstring above).
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", 8000)))
    mcp.run(transport="http", host="0.0.0.0", port=port)
