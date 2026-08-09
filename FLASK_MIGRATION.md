# Flask Migration - AI Job Hunting Copilot

## ✅ Conversion Complete!

Your project has been successfully converted from Streamlit to Flask with HTML templates, following the pattern from your day-2 homework.

## What Changed

### 1. **Application Framework**
- **Before:** Streamlit (Python-only, component-based)
- **After:** Flask (Python backend + HTML templates)

### 2. **File Structure**
```
dashboard/
├── app.py                     # Flask app with routes (was Streamlit app)
├── app.yaml                   # Updated to run Flask
├── requirements.txt           # Flask instead of Streamlit
├── lakebase.py               # Database helper (unchanged)
├── templates/                 # NEW - HTML templates
│   ├── base.html             # Base template with sidebar navigation
│   ├── index.html            # Home page with stats dashboard
│   ├── profile.html          # Profile management form
│   ├── search.html           # Job search interface
│   ├── pipeline.html         # Application tracking kanban
│   ├── interviews.html       # Interview notes (placeholder)
│   └── assistant.html        # AI chat interface
├── static/                    # NEW - CSS/JS assets
│   └── css/
│       └── styles.css        # Custom styles
└── notebooks/
    └── ingest_job_embeddings.py
```

### 3. **Routes (URL Structure)**
| Route | Purpose |
|-------|---------|
| `/` | Home page with stats |
| `/profile` | View profile |
| `/profile/save` | Save profile (POST) |
| `/search` | Job search |
| `/pipeline` | Application pipeline |
| `/interviews` | Interview tracking |
| `/assistant` | AI chat |
| `/api/chat` | Chat API endpoint (POST) |

### 4. **UI Framework**
- **Bootstrap 5** for responsive design
- **Bootstrap Icons** for icons
- **Custom CSS** for Databricks branding (red sidebar)
- **Vanilla JavaScript** for form handling and chat

## How to Run

### Local Development
```bash
cd dashboard
pip install -r requirements.txt
python app.py
```

Open browser: `http://localhost:8080`

### Deploy to Databricks
Use Databricks Apps deployment:
1. Ensure Lakebase database is set up
2. Configure secrets via `setup_secrets.py`
3. Deploy using Databricks UI or CLI

## Key Features

### ✅ Fully Functional
- **User Management** - Auto-creates users from Databricks identity
- **Profile Management** - Save career preferences with AJAX form submission
- **Application Pipeline** - View applications grouped by status
- **Navigation** - Sidebar with active page highlighting
- **Responsive Design** - Mobile-friendly Bootstrap layout

### 🚧 TODO (Same as before)
- Job search integration with Adzuna API via MCP server
- AI chat integration with Databricks Agent
- Interview notes management
- Embedding generation for resume matching
- Cover letter drafting with LLM

## Architecture

### Backend (Flask)
```python
# app.py structure
Flask(__name__)
  ├── Routes (view functions)
  ├── Database helpers (via lakebase.py)
  └── Databricks SDK integration

# Each route:
1. Gets current user from Databricks
2. Queries Lakebase database
3. Renders HTML template with data
```

### Frontend (HTML + Bootstrap)
```html
<!-- Template inheritance -->
base.html (sidebar + layout)
  ├── index.html (home page)
  ├── profile.html (form with AJAX)
  ├── search.html (search UI)
  ├── pipeline.html (status cards)
  ├── interviews.html (placeholder)
  └── assistant.html (chat interface)
```

### Database (Lakebase)
- Same schema as before (8 tables)
- Accessed via `lakebase.run_query()` and `lakebase.run_write()`
- PostgreSQL with psycopg2-binary driver

## Comparison: Streamlit vs Flask

| Feature | Streamlit | Flask |
|---------|-----------|-------|
| **Code Style** | Python-only, imperative | Python backend + HTML templates |
| **UI Components** | Built-in (st.button, st.form) | Custom HTML + Bootstrap |
| **State Management** | st.session_state | Flask sessions or client-side |
| **Real-time Updates** | Auto-rerun on change | Manual AJAX or page reload |
| **Customization** | Limited CSS control | Full HTML/CSS/JS control |
| **Learning Curve** | Easier for data scientists | Requires web dev knowledge |
| **Best For** | Rapid prototyping, dashboards | Production apps, full control |

## Next Steps

1. **Test Locally**
   ```bash
   cd dashboard
   python app.py
   # Visit http://localhost:8080
   ```

2. **Customize Styling**
   - Edit `static/css/styles.css`
   - Modify templates in `templates/`

3. **Implement TODOs**
   - Connect job search to Adzuna API
   - Integrate AI chat with Databricks Agent
   - Add interview notes CRUD operations

4. **Deploy**
   - Follow deployment instructions in `README.md`

## Troubleshooting

### Port Already in Use
```bash
# Change port in app.py or set PORT env var
export PORT=8081
python app.py
```

### Database Connection Error
- Check Lakebase URL in secrets
- Verify LAKEBASE_SECRET_SCOPE and LAKEBASE_SECRET_KEY in app.yaml

### Templates Not Found
- Ensure templates/ folder is in same directory as app.py
- Check Flask template_folder configuration

## Migration Benefits

✅ **More Control** - Full access to HTML/CSS/JS
✅ **Production Ready** - Standard web framework pattern
✅ **Familiarity** - Matches your day-2 homework structure
✅ **Extensibility** - Easy to add REST APIs, webhooks, etc.
✅ **Debugging** - Standard Flask debugging tools
✅ **Deployment** - Works with any WSGI server

---

**You now have a Flask app with HTML templates, just like your previous projects!** 🎉
