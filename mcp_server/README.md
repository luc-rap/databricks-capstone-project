# Job Search MCP Server

This is a standalone MCP (Model Context Protocol) server that exposes job search and application management tools to AI agents.

Instead of calling external APIs, this server connects to **Lakebase Postgres** to search and manage job postings stored locally, enabling semantic search, profile-based ranking, and application pipeline tracking.

## Features

### 🧠 **Semantic Search with Embeddings**
* Vector search using Databricks BGE embeddings for job-to-profile matching
* Cosine similarity ranking - finds jobs semantically similar to your skills
* Works beyond keyword matching - understands context and relationships

### 🎯 **Intelligent Job Matching**
* **Profile Ranking**: Rank jobs by semantic similarity to user resume/profile
* **Match Explanation**: AI-powered breakdown of why each job matches
* **Multi-factor Scoring**: Combines semantic similarity (50%), skills (20%), location (15%), salary (15%)
* **Smart Recommendations**: "Strong Apply" / "Apply" / "Consider" / "Skip" based on match score

### 📊 **Application Pipeline Tracking**
* Save jobs to pipeline stages: saved → applied → interviewing → offer → accepted
* Track match scores and personal notes for each application
* Query all applications by stage

### 📝 **Interview & Follow-up Management**
* Track interview notes with dates, types, and follow-up reminders
* Identify stale applications that need attention
* Get structured context for AI-powered cover letter generation

## Setup

### 1. **Set up Lakebase Database**

Run the schema setup SQL in your Lakebase database:

```bash
# Connect to your Lakebase instance and run:
psql -h <lakebase-host> -d databricks_postgres -f schema.sql
```

Or run it from a Databricks notebook (see `schema.sql`).

### 2. **Configure Secrets**

Ensure these secrets exist in your Databricks workspace:

```python
# In Databricks notebook:
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

# Create secret scope if it doesn't exist
# databricks secrets create-scope database

# Add Lakebase connection URL
w.secrets.put_secret(
    scope="database",
    key="lakebase-url",
    string_value="postgresql://student@<host>:5432/databricks_postgres"
)

# Optionally add endpoint name (auto-discovered if omitted)
w.secrets.put_secret(
    scope="database",
    key="lakebase-endpoint",
    string_value="projects/<project_id>/branches/<branch_id>/endpoints/<endpoint_id>"
)
```

### 3. **Deploy as Databricks App**

```bash
databricks apps deploy job-search-mcp --source-dir mcp_server/
```

### 4. **Register with AI Agent**

- Get the app URL from deployment
- Register as MCP server in your AI agent configuration

## MCP Tools

### Job Search & Ranking

- **`search_jobs(keywords, location, remote_only, salary_min, results_per_page)`**  
  Search job postings with filters

- **`rank_jobs_by_profile(user_profile_text, keywords, location, top_k)`**  
  Rank jobs by semantic match to user's profile (uses embeddings)

- **`explain_job_match(job_id, user_skills, user_location, salary_min)`**  
  Get AI explanation of why a job matches or doesn't match user preferences

### Application Pipeline Management

- **`save_job(job_id, match_score, notes)`**  
  Save a job to the 'saved' pipeline stage

- **`update_application_status(job_id, status, notes)`**  
  Move job through pipeline: saved → applied → interviewing → rejected/offer/accepted

- **`get_my_applications(stage)`**  
  Get all applications for current user, optionally filtered by stage

### Interview & Follow-up Management

- **`add_interview_note(job_id, interview_date, interview_type, notes, follow_up_date)`**  
  Record interview details, feedback, and set follow-up dates  
  Interview types: phone_screen, technical, behavioral, onsite, final

- **`get_stale_applications(days_threshold)`**  
  Find applications not updated in X days (default 14) for follow-up  
  Excludes terminal statuses (rejected, accepted)

- **`get_cover_letter_context(job_id)`**  
  Get structured job and profile data for AI-generated cover letters  
  Returns: job details, user resume, skills, experience for agent to use

## Architecture

The MCP server connects to:

- **Lakebase Postgres** for job postings and application tracking  
  - `job_postings` table (created by ingest notebook)
  - `user_applications` table (application pipeline)
  - `interview_notes` table (interview tracking)
  - `users` and `user_profiles` tables (profile management)

- **Databricks SDK** for OAuth token generation and authentication

- **FastMCP** for MCP protocol implementation

## Pipeline Stages

Applications flow through these stages:

1. **saved** - Job saved for later review
2. **applied** - Application submitted
3. **interviewing** - In interview process
4. **rejected** - Application rejected
5. **offer** - Offer received
6. **accepted** - Offer accepted

## Testing Vector Search

Test the semantic matching locally before deploying:

```python
# Run in a Databricks notebook
%run /Workspace/Users/lucia.woollett@proton.me/databricks-capstone-project/mcp_server/test_vector_search.py
```

Or test individual functions:

```python
import sys
sys.path.append('/Workspace/Users/lucia.woollett@proton.me/databricks-capstone-project/mcp_server')
import adzuna_adapter as lakebase_adapter

# 1. Semantic ranking
user_profile = """
Data Engineer with 5+ years experience.
Skills: Python, SQL, Spark, AWS, Databricks.
Looking for remote roles in data engineering.
"""

results = lakebase_adapter.rank_jobs_by_profile(
    user_profile_text=user_profile,
    location="Florida",
    top_k=10
)

for job in results['results']:
    print(f"{job['title']} - Match: {job['match_score']}%")

# 2. Explain a specific match
explanation = lakebase_adapter.explain_job_match(
    job_id=results['results'][0]['id'],
    user_profile={
        "skills": ["Python", "SQL", "Spark"],
        "location": "Florida",
        "salary_min": 100000
    }
)

print(f"Match: {explanation['match_score']}%")
print(f"Recommendation: {explanation['recommendation']}")
print(f"Reasoning: {explanation['reasoning']}")
```

## How Vector Search Works

1. **Embedding Generation**: User profile text is converted to a **384-dim vector** using `sentence-transformers/all-MiniLM-L6-v2` (same model as `ingest_profile_embeddings.py`)
2. **Similarity Calculation**: Cosine similarity computed between user embedding and all job embeddings
3. **Ranking**: Jobs sorted by similarity score (0-1 scale, shown as 0-100%)
4. **Explanation**: Multi-factor analysis combining:
   - **Semantic similarity** (50% weight) - from vector embeddings
   - **Keyword skill matches** (20% weight) - exact text matching
   - **Location match** (15% weight) - geography alignment
   - **Salary match** (15% weight) - compensation expectations

**Important**: The MCP server uses the **same embedding model** as your notebooks to ensure consistency in semantic search results.

## Files

- `adzuna_adapter.py` - Lakebase job adapter with vector search
- `job_search_mcp_server.py` - FastMCP server with tool definitions
- `schema.sql` - Database schema for user_applications table
- `test_vector_search.py` - Test script for semantic matching
- `app.yaml` - Databricks App configuration
- `requirements.txt` - Python dependencies
