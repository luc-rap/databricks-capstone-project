"""
Adzuna API Adapter for Job Search

Provides Python functions to interact with the Adzuna Job Search API.
See: https://developer.adzuna.com/docs/search

All functions return structured dicts suitable for MCP tool responses.
"""

import os
import requests
from typing import Optional, Dict, List, Any

_BASE_URL = "https://api.adzuna.com/v1/api"
_DEFAULT_TIMEOUT = 30
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    """Get or create a requests session for connection pooling."""
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


def _get(endpoint: str, params: Optional[Dict] = None) -> dict:
    """
    Make a GET request to the Adzuna API.
    
    Args:
        endpoint: API endpoint path (e.g., "/jobs/us/search/1")
        params: Query parameters
    
    Returns:
        JSON response as a dict
    """
    session = _get_session()
    url = f"{_BASE_URL}{endpoint}"
    
    # Add API credentials from environment
    # These should be set from Databricks secrets in production
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    
    if not app_id or not app_key:
        raise ValueError(
            "ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables must be set. "
            "Configure them in app.yaml from Databricks secrets."
        )
    
    # Add credentials to params
    params = params or {}
    params["app_id"] = app_id
    params["app_key"] = app_key
    
    resp = session.get(url, params=params, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def search_jobs(
    country: str = "us",
    what: Optional[str] = None,
    where: Optional[str] = None,
    page: int = 1,
    results_per_page: int = 20,
    sort_by: str = "relevance",
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    contract_type: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search for jobs using the Adzuna API.
    
    Args:
        country: Country code (e.g., "us", "uk", "ca")
        what: Keywords/job title to search for
        where: Location to search in
        page: Page number (1-indexed)
        results_per_page: Number of results per page (max 50)
        sort_by: Sort order - "relevance", "date", "salary"
        salary_min: Minimum salary filter
        salary_max: Maximum salary filter
        contract_type: Contract type filter - "permanent", "contract", "part_time"
        category: Job category filter
    
    Returns:
        Dict with:
        - count: Total number of results
        - results: List of job postings
        - page: Current page number
    """
    endpoint = f"/jobs/{country}/search/{page}"
    
    params = {
        "results_per_page": min(results_per_page, 50),
        "sort_by": sort_by,
    }
    
    if what:
        params["what"] = what
    if where:
        params["where"] = where
    if salary_min:
        params["salary_min"] = salary_min
    if salary_max:
        params["salary_max"] = salary_max
    if contract_type:
        params["contract_type"] = contract_type
    if category:
        params["category"] = category
    
    data = _get(endpoint, params)
    
    return {
        "count": data.get("count", 0),
        "results": [
            {
                "id": job.get("id"),
                "title": job.get("title"),
                "company": job.get("company", {}).get("display_name"),
                "location": job.get("location", {}).get("display_name"),
                "description": job.get("description"),
                "created": job.get("created"),
                "redirect_url": job.get("redirect_url"),
                "salary_min": job.get("salary_min"),
                "salary_max": job.get("salary_max"),
                "contract_type": job.get("contract_type"),
                "category": job.get("category", {}).get("label"),
            }
            for job in data.get("results", [])
        ],
        "page": page,
    }


def get_job_details(country: str, job_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific job posting.
    
    Args:
        country: Country code (e.g., "us", "uk")
        job_id: Adzuna job ID
    
    Returns:
        Dict with full job details
    """
    endpoint = f"/jobs/{country}/{job_id}"
    data = _get(endpoint)
    
    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "company": data.get("company", {}).get("display_name"),
        "location": data.get("location", {}).get("display_name"),
        "description": data.get("description"),
        "created": data.get("created"),
        "redirect_url": data.get("redirect_url"),
        "salary_min": data.get("salary_min"),
        "salary_max": data.get("salary_max"),
        "contract_type": data.get("contract_type"),
        "category": data.get("category", {}).get("label"),
    }


def get_job_categories(country: str = "us") -> List[Dict[str, Any]]:
    """
    Get available job categories for a country.
    
    Args:
        country: Country code (e.g., "us", "uk")
    
    Returns:
        List of category dicts with label and tag
    """
    endpoint = f"/jobs/{country}/categories"
    data = _get(endpoint)
    
    return [
        {
            "label": cat.get("label"),
            "tag": cat.get("tag"),
        }
        for cat in data.get("results", [])
    ]


# TODO: Add more Adzuna API functions as needed:
# - get_histogram: Get salary histogram data
# - get_top_companies: Get top hiring companies
# - get_geodata: Get location-based job data
