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

- **FastMCP** for MCP protocol implementation

## Pipeline Stages

Applications flow through these stages:

1. **saved** - Job saved for later review
2. **applied** - Application submitted
3. **interviewing** - In interview process
4. **rejected** - Application rejected
5. **offer** - Offer received
6. **accepted** - Offer accepted

## How Vector Search Works

1. **Embedding Generation**: User profile text is converted to a **384-dim vector** using `sentence-transformers/all-MiniLM-L6-v2` (same model as `ingest_profile_embeddings.py`)
2. Vector search user's profile against job postings
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
- `app.yaml` - Databricks App configuration
- `requirements.txt` - Python dependencies
