# AI Job Hunting Copilot - Databricks AI Capstone project

An AI-powered job search assistant built on Databricks, combining:
- **Lakebase** (Postgres) for structured data storage
- **MCP Server** for AI agent tool integration
- **Flask** for user interaction
- **Adzuna API** for job search data
-- CDF and data pipeline requirements were dropped as per intructions (not supported in free edition)

## Features

### 🔍 Intelligent Job Search
- Search jobs via Adzuna API with natural language
- Semantic search using embeddings (job descriptions + user profile)
- AI-powered job ranking and match scoring

### 📊 Application Pipeline Tracking
- Track jobs through stages: saved → applied → interviewing → offer
- Interview notes and follow-up reminders
- Identify stale applications

### 💬 AI Assistant
- Ask questions in natural language
- Get job recommendations tailored to your profile
- Draft cover letters and resume bullets
- Prepare for interviews

### 👤 User Profile Management
- Upload CV and store resume and skills
- Add target roles, preferred locations, salary range, job preferences

## Architecture

```
databricks-capstone-project/
├── sql/                      # Lakebase table schemas
│   ├── create_tables.sql     # Main table definitions
│   └── sample_data.sql       # Test data
│
├── mcp_server/               # MCP Server (separate Databricks App)
│   ├── adzuna_adapter.py     # Adzuna API wrapper
│   ├── job_search_mcp_server.py  # FastMCP server with tools
│   ├── app.yaml              # MCP server app config
│   └── requirements.txt
│
├── dashboard/                # Main Streamlit App
│   ├── app.py                # Streamlit frontend
│   ├── lakebase.py           # Lakebase connection helper
│   ├── app.yaml              # Dashboard app config
│   ├── requirements.txt
│   └── notebooks/
│       └── ingest_job_embeddings.py  # Periodic job ingestion
│
├── setup_secrets.py          # One-time secret setup
└── databricks.yml            # DAB configuration
```

## Setup Instructions

### 1. Get Adzuna API Credentials
1. Sign up at https://developer.adzuna.com/
2. Create an app to get App ID and App Key

### 2. Set up Lakebase
1. Create a Lakebase Postgres database in your Databricks workspace
2. Get the connection URL
3. Run the SQL

### 3. Configure Secrets
```bash
python setup_secrets.py
```

This will prompt for:
- Adzuna App ID and App Key
- Lakebase connection URL

### 4. Deploy Apps

- Deploy MCP Server in Databricks
- Deploy Dashboard in Databricks


### 5. Ingest Job Postings
Run the `dashboard/notebooks/ingest_job_embeddings` notebook to:
- Fetch jobs from Adzuna API
- Generate embeddings
- Store in Lakebase

Schedule this to run daily/weekly to refresh job listings.

### 6. Connect AI Agent
Register the MCP server URL with your Databricks AI Agent to enable tool calling.

**📚 For detailed integration guidance**, see [mcp_server/ASSISTANT_INTEGRATION.md](mcp_server/ASSISTANT_INTEGRATION.md) for:
- Complete tool reference with examples
- Conversational workflow patterns
- Best practices for semantic search and matching
- Error handling and multi-profile support

## Database Schema

### Core Tables
- **users** - User accounts
- **profiles** - Career preferences, resume, embeddings
- **skills** - User skills with proficiency levels
- **job_postings** - Jobs from Adzuna with embeddings
- **applications** - Application pipeline tracking
- **saved_jobs** - Saved jobs with match scores
- **interview_notes** - Interview tracking and follow-ups
- **contacts** - Networking and referral contacts

## MCP Tools

The MCP server exposes these tools to AI agents:

### Job Search
- `search_jobs(keywords, location, remote_only, salary_min, results_per_page)`
- `get_job_categories()`

### Application Management
- `save_job(job_id, match_score, reasoning)` - Save a job to your pipeline
- `update_application_status(job_id, status, notes)` - Move jobs through stages (saved → applied → interviewing → rejected/offer)
- `get_my_applications(stage)` - Query all applications, optionally filtered by stage

### Interview & Follow-up
- `add_interview_note(job_id, interview_date, interview_type, notes, follow_up_date)` - Track interviews with notes and reminders
  - Interview types: `phone_screen`, `technical`, `behavioral`, `onsite`, `final`
- `get_stale_applications(days_threshold)` - Find applications not updated in X days (default 14)
  - Excludes terminal stages (rejected, accepted)
- `get_cover_letter_context(job_id)` - Get structured job + profile data for AI-generated cover letters

### Profile Management
- `store_user_profile(resume_text, target_roles, skills, ...)` - Create/update user profile
- `get_user_info()` - Retrieve current user's profile and preferences

## TODO / Future Enhancements

### Completed ✅
- [x] Interview notes and follow-up tracking with `add_interview_note()`
- [x] Stale application detection with `get_stale_applications()`
- [x] Cover letter context API with `get_cover_letter_context()`
- [x] Multi-profile support (session-based profile switching)
- [x] Profile management tools (`store_user_profile`, `get_user_info`)

### In Progress 🚧
- [ ] Implement semantic search with embeddings
- [ ] Integrate Databricks Foundation Model API for:
  - Resume/job description embeddings
  - AI-generated cover letter drafting (context API ready)
  - Interview preparation suggestions

### Future Ideas 🔮
- [ ] Add analytics dashboard (application funnel, success metrics)
- [ ] Email integration for application tracking
- [ ] Calendar integration for interview scheduling
- [ ] Chrome extension for quick job saves
- [ ] Mobile app

## Development

### Run Locally

#### Dashboard
```bash
cd dashboard
pip install -r requirements.txt
streamlit run app.py --server.port=8080
```

#### MCP Server
```bash
cd mcp_server
pip install -r requirements.txt
python job_search_mcp_server.py
```

### Testing
```bash
# Run tests (TODO: add test suite)
pytest tests/
```

## Contributing

This is a capstone project. Suggestions and improvements welcome!

## License

MIT License - see LICENSE file for details
