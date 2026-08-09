# Quick Start Guide - AI Job Hunting Copilot

## What You Have

Your project template is ready with:

✅ **SQL Schema** - 8 Lakebase tables for users, profiles, skills, jobs, applications, interviews, contacts  
✅ **MCP Server** - FastMCP server with Adzuna API adapter and 7+ tools  
✅ **Streamlit Dashboard** - Frontend with profile management, job search, pipeline tracking, AI chat  
✅ **Ingestion Script** - Notebook/script to fetch and embed job postings  
✅ **Secret Management** - Setup script for API credentials  
✅ **DAB Config** - Declarative automation bundle for deployment  

## Setup Checklist

### 1️⃣ Get API Credentials

**Adzuna API** (Required)
- Sign up: https://developer.adzuna.com/
- Create app → Get App ID and App Key

**Databricks Foundation Model API** (Optional, for embeddings)
- Already available in your workspace
- No additional setup needed

### 2️⃣ Create Lakebase Database

```sql
-- In Databricks SQL Editor or notebook:
-- Create your Lakebase Postgres database
-- Save the connection URL (postgresql://...)
```

### 3️⃣ Store Secrets

```bash
# Run from local machine or notebook:
python setup_secrets.py

# You'll be prompted for:
# - Adzuna App ID
# - Adzuna App Key  
# - Lakebase connection URL
```

### 4️⃣ Create Tables

```sql
-- Connect to your Lakebase database
-- Run: sql/create_tables.sql
-- Optional: Run sql/sample_data.sql for test data
```

### 5️⃣ What to Implement Next

The template has placeholders (marked with TODO) for:

#### In `mcp_server/adzuna_adapter.py`:
- Additional API endpoints (histogram, top companies, geodata)

#### In `mcp_server/job_search_mcp_server.py`:
- Lakebase connections for application management tools
- LLM integration for cover letter generation

#### In `dashboard/app.py`:
- Job search integration with MCP server
- AI chat interface with Databricks Agent
- Analytics/metrics dashboard

#### In `dashboard/notebooks/ingest_job_embeddings.py`:
- Embedding generation using Foundation Model API
- Example code provided as comment

## File Reference

### Core Files

| File | Purpose |
|------|---------|
| `sql/create_tables.sql` | Lakebase schema definitions |
| `sql/sample_data.sql` | Test data for development |
| `setup_secrets.py` | One-time credential setup |
| `README.md` | Full documentation |

### MCP Server (Tools for AI Agent)

| File | Purpose |
|------|---------|
| `mcp_server/adzuna_adapter.py` | Adzuna API wrapper |
| `mcp_server/job_search_mcp_server.py` | FastMCP server with tools |
| `mcp_server/app.yaml` | App deployment config |
| `mcp_server/README.md` | MCP server documentation |

### Dashboard (User Interface)

| File | Purpose |
|------|---------|
| `dashboard/app.py` | Streamlit frontend |
| `dashboard/lakebase.py` | Database connection helper |
| `dashboard/app.yaml` | App deployment config |
| `dashboard/notebooks/ingest_job_embeddings.py` | Job ingestion script |

## Development Workflow

### Local Testing

**Dashboard:**
```bash
cd dashboard
pip install -r requirements.txt
streamlit run app.py --server.port=8080
```

**MCP Server:**
```bash
cd mcp_server
pip install -r requirements.txt
python job_search_mcp_server.py
```

### Deployment

Use Databricks Apps CLI or the Databricks UI to deploy:
1. Deploy MCP server first
2. Deploy dashboard
3. Register MCP server URL with AI agent

## Key Concepts

### MCP (Model Context Protocol)
- Exposes tools that AI agents can call
- Your MCP server provides job search and application management tools
- Deploy as separate app so agents can access it

### Embeddings for Semantic Search
- Generate embeddings for job descriptions
- Generate embeddings for user profiles/resumes
- Use vector similarity to find matching jobs beyond keyword search

### Application Pipeline
- Track jobs through stages: saved → applied → interviewing → offer
- AI helps prioritize, draft materials, schedule follow-ups

## Need Help?

Check:
- `README.md` - Full documentation
- `mcp_server/README.md` - MCP server details
- Adzuna API docs: https://developer.adzuna.com/docs/search
- FastMCP docs: https://github.com/jlowin/fastmcp
- Databricks Apps: https://docs.databricks.com/aws/en/apps/

## What's Different From Day 1-3?

- **Day 1**: Basic Lakebase tables → Now: 8-table schema with relationships
- **Day 2**: Simple MCP server → Now: 7+ tools + Adzuna integration
- **Day 3**: Basic app → Now: Full Streamlit UI with AI chat

This combines all concepts into one production-ready application!
