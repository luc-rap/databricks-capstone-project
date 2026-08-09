# Job Search MCP Server

This is a standalone MCP (Model Context Protocol) server that exposes job search and application management tools to AI agents.

## Features

* **Job Search**: Search Adzuna API for job postings with filters
* **Application Tracking**: Save jobs, update application status, track pipeline
* **Interview Management**: Add interview notes, track follow-ups
* **Content Generation**: Draft tailored cover letters (TODO: integrate LLM)

## Setup

1. **Get Adzuna API Credentials**
   - Sign up at https://developer.adzuna.com/
   - Get your App ID and App Key

2. **Store Secrets**
   ```bash
   python setup_secrets.py
   ```
   This will prompt for your Adzuna credentials and store them in Databricks secrets.

3. **Deploy as Databricks App**
   ```bash
   databricks apps deploy job-search-mcp --source-dir mcp_server/
   ```

4. **Register with AI Agent**
   - Get the app URL from deployment
   - Register as MCP server in your AI agent configuration

## MCP Tools

### Job Search
- `search_jobs(keywords, location, remote_only, salary_min, results_per_page)`
- `get_job_categories()`

### Application Management
- `save_job(job_id, match_score, reasoning)`
- `update_application_status(job_id, status, notes)`
- `add_interview_note(job_id, interview_date, interview_type, notes, follow_up_date)`
- `get_stale_applications(days_threshold)`
- `draft_cover_letter(job_id, job_description, user_profile)`

## Architecture

The MCP server is stateless and relies on:
- **Adzuna API** for job search data
- **Lakebase** (optional) for persistent application tracking
- **Databricks Foundation Model API** (TODO) for AI-generated content
