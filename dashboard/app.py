"""
AI Job Hunting Copilot - Flask Application

A Databricks App that provides:
- User profile management
- AI-powered job search and recommendations
- Application pipeline tracking
- Interview notes and follow-ups
"""

import os
import re
import io
import json
from decimal import Decimal
from datetime import datetime, date
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask.json.provider import DefaultJSONProvider
from databricks.sdk import WorkspaceClient
from sentence_transformers import SentenceTransformer
from PyPDF2 import PdfReader

import lakebase
from assistant_client import DatabricksAssistantClient


class DecimalJSONProvider(DefaultJSONProvider):
    """Custom JSON provider that handles Decimal and datetime types from database results."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management
app.json = DecimalJSONProvider(app)  # Use custom JSON encoder for all jsonify() calls

# Initialize Assistant client (singleton pattern)
assistant_client = None

def get_assistant_client():
    global assistant_client
    
    token = request.headers.get('X-Forwarded-Access-Token')
    
    # Use the actual Databricks workspace URL, not the app URL
    workspace_url = '<workspace_url>'
    
    print(f"Token present: {bool(token)}")
    print(f"Workspace URL: {workspace_url}")
    
    if not assistant_client:
        assistant_client = DatabricksAssistantClient(
            token=token,
            workspace_url=workspace_url
        )
    
    return assistant_client

# Initialize Databricks SDK
w = WorkspaceClient()

# Initialize embedding model (same as used in notebook)
print("Loading embedding model...")
embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
print("Embedding model loaded!")


def get_current_user():
    """Get current user from session or Databricks context."""
    # Check if a profile is selected in the session
    if 'selected_profile' in session:
        return session['selected_profile']
    
    # Otherwise, use the authenticated Databricks user
    try:
        current_user = w.current_user.me()
        return {
            'email': current_user.user_name,
            'name': current_user.display_name or current_user.user_name.split('@')[0]
        }
    except Exception as e:
        print(f"Error getting current user: {e}")
        return {'email': 'unknown@databricks.com', 'name': 'Unknown User'}


def get_or_create_user(email, full_name):
    """Get or create user in database."""
    try:
        users = lakebase.run_query(
            "SELECT user_id FROM users WHERE email = %s",
            (email,)
        )
        if users:
            return users[0]['user_id']
        else:
            lakebase.run_write(
                "INSERT INTO users (email, full_name) VALUES (%s, %s)",
                (email, full_name)
            )
            users = lakebase.run_query(
                "SELECT user_id FROM users WHERE email = %s",
                (email,)
            )
            return users[0]['user_id']
    except Exception as e:
        print(f"Error getting/creating user: {e}")
        return None


def parse_pg_array(value):
    """Convert PostgreSQL array string to Python list.
    
    PostgreSQL arrays are returned as strings like '{val1,val2}' by psycopg2.
    This function converts them to proper Python lists.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value  # Already a list
    if isinstance(value, str):
        # Remove curly braces and split by comma
        if value.startswith('{') and value.endswith('}'):
            value = value[1:-1]
        if not value:
            return []
        return [item.strip('"').strip() for item in value.split(',')]
    return []


@app.route('/')
def index():
    """Home page with overview and stats."""
    user = get_current_user()
    user_id = get_or_create_user(user['email'], user['name'])
    
    stats = {
        'saved': 0,
        'applied': 0,
        'interviewing': 0,
        'offers': 0
    }
    
    if user_id:
        try:
            stats['saved'] = lakebase.run_query(
                "SELECT COUNT(*) as count FROM applications WHERE user_id = %s",
                (user_id,)
            )[0]['count']
            
            stats['applied'] = lakebase.run_query(
                "SELECT COUNT(*) as count FROM applications WHERE user_id = %s AND status = 'applied'",
                (user_id,)
            )[0]['count']
            
            stats['interviewing'] = lakebase.run_query(
                "SELECT COUNT(*) as count FROM applications WHERE user_id = %s AND status = 'interviewing'",
                (user_id,)
            )[0]['count']
            
            stats['offers'] = lakebase.run_query(
                "SELECT COUNT(*) as count FROM applications WHERE user_id = %s AND status = 'offer'",
                (user_id,)
            )[0]['count']
        except Exception as e:
            print(f"Error loading stats: {e}")
    
    return render_template('index.html', user=user, stats=stats)


@app.route('/profile')
def profile():
    """User profile management page."""
    user = get_current_user()
    user_id = get_or_create_user(user['email'], user['name'])
    
    profile_data = {}
    if user_id:
        try:
            profiles = lakebase.run_query(
                "SELECT * FROM profiles WHERE user_id = %s",
                (user_id,)
            )
            if profiles:
                profile_data = profiles[0]
                # Convert PostgreSQL arrays to Python lists for template
                if 'target_roles' in profile_data:
                    profile_data['target_roles'] = parse_pg_array(profile_data['target_roles'])
                if 'location_preferences' in profile_data:
                    profile_data['location_preferences'] = parse_pg_array(profile_data['location_preferences'])
        except Exception as e:
            print(f"Error loading profile: {e}")
            import traceback
            traceback.print_exc()
    
    return render_template('profile.html', user=user, profile=profile_data)


@app.route('/profile/save', methods=['POST'])
def save_profile():
    """Save user profile."""
    user = get_current_user()
    user_id = get_or_create_user(user['email'], user['name'])
    
    if not user_id:
        return jsonify({'success': False, 'error': 'User not found'}), 400
    
    # Parse form data
    target_roles = [r.strip() for r in request.form.get('target_roles', '').split(',') if r.strip()]
    location_prefs = [l.strip() for l in request.form.get('location_prefs', '').split(',') if l.strip()]
    remote_pref = request.form.get('remote_pref', 'flexible')
    salary_min = int(request.form.get('salary_min', 0))
    salary_max = int(request.form.get('salary_max', 200000))
    years_exp = int(request.form.get('years_exp', 0))
    resume_text = request.form.get('resume_text', '')
    job_preferences = request.form.get('job_preferences', '')
    
    try:
        # Check if profile exists
        existing = lakebase.run_query(
            "SELECT profile_id FROM profiles WHERE user_id = %s",
            (user_id,)
        )
        
        if existing:
            # Update
            lakebase.run_write(
                """
                UPDATE profiles SET
                    target_roles = %s,
                    location_preferences = %s,
                    remote_preference = %s,
                    salary_min = %s,
                    salary_max = %s,
                    years_experience = %s,
                    resume_text = %s,
                    job_preferences = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
                """,
                (target_roles, location_prefs, remote_pref, salary_min,
                 salary_max, years_exp, resume_text, job_preferences, user_id)
            )
        else:
            # Insert
            lakebase.run_write(
                """
                INSERT INTO profiles (
                    user_id, target_roles, location_preferences,
                    remote_preference, salary_min, salary_max,
                    years_experience, resume_text, job_preferences
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, target_roles, location_prefs, remote_pref,
                 salary_min, salary_max, years_exp, resume_text, job_preferences)
            )
        
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error saving profile: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/parse-cv', methods=['POST'])
def parse_cv():
    """Parse CV PDF and extract text + structured fields."""
    if 'cv_file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400
    
    file = request.files['cv_file']
    
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'success': False, 'error': 'Only PDF files are supported'}), 400
    
    try:
        # Read PDF and extract text
        pdf_bytes = file.read()
        pdf_file = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_file)
        
        # Extract text from all pages
        full_text = ''
        for page in reader.pages:
            full_text += page.extract_text() + '\n'
        
        if not full_text.strip():
            return jsonify({'success': False, 'error': 'Could not extract text from PDF'}), 400
        
        # Parse structured fields using simple regex patterns
        parsed_data = {
            'resume_text': full_text.strip(),
            'target_roles': extract_roles(full_text),
            'years_experience': extract_years_experience(full_text),
            'location_preferences': extract_locations(full_text),
            'job_preferences': extract_job_preferences(full_text)
        }
        
        return jsonify({
            'success': True,
            'data': parsed_data
        })
        
    except Exception as e:
        print(f"Error parsing CV: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def extract_roles(text):
    """Extract likely job roles from CV text."""
    # Common role keywords
    role_patterns = [
        r'(?:^|\s)(Software Engineer|Data Scientist|ML Engineer|Data Engineer|'
        r'Full Stack Developer|Backend Developer|Frontend Developer|DevOps Engineer|'
        r'Cloud Architect|Product Manager|Data Analyst|Business Analyst|'
        r'Senior Engineer|Lead Engineer|Principal Engineer|Engineering Manager)(?:\s|$|,)',
    ]
    
    roles = set()
    for pattern in role_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            roles.add(match.group(1).strip())
    
    return ', '.join(sorted(roles)) if roles else ''


def extract_years_experience(text):
    """Extract years of experience from CV text."""
    # Look for patterns like "X years of experience" or "X+ years"
    patterns = [
        r'(\d+)\+?\s*years?\s+(?:of\s+)?experience',
        r'(\d+)\+?\s*yrs?\s+(?:of\s+)?experience',
    ]
    
    years = []
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            years.append(int(match.group(1)))
    
    # Return the maximum years found (most likely total experience)
    return max(years) if years else 0


def extract_locations(text):
    """Extract location preferences from CV text."""
    # Common US cities and states
    locations = [
        'San Francisco', 'New York', 'Seattle', 'Austin', 'Boston',
        'Los Angeles', 'Chicago', 'Denver', 'Portland', 'Remote',
        'California', 'New York', 'Washington', 'Texas', 'Massachusetts'
    ]
    
    found = set()
    for location in locations:
        if re.search(r'\b' + re.escape(location) + r'\b', text, re.IGNORECASE):
            found.add(location)
    
    return ', '.join(sorted(found)) if found else ''


def extract_job_preferences(text):
    """Extract work authorization and job preferences from CV text."""
    preferences = []
    
    # Work authorization patterns
    if re.search(r'(US|United States)\s+(citizen|citizenship)', text, re.IGNORECASE):
        preferences.append('US Citizen')
    
    if re.search(r'green\s*card', text, re.IGNORECASE):
        preferences.append('Green Card holder')
    
    if re.search(r'work\s+authorization', text, re.IGNORECASE):
        preferences.append('Has work authorization')
    
    if re.search(r'(no|does not|doesn\'t)\s+require\s+(visa|sponsorship)', text, re.IGNORECASE):
        preferences.append('No visa sponsorship needed')
    
    if re.search(r'(require|need)s?\s+(visa|sponsorship|H-?1B)', text, re.IGNORECASE):
        preferences.append('Requires visa sponsorship')
    
    if re.search(r'authorized\s+to\s+work\s+in\s+(US|United States)', text, re.IGNORECASE):
        preferences.append('Authorized to work in US')
    
    if re.search(r'(eligible|authorized)\s+to\s+work', text, re.IGNORECASE):
        preferences.append('Eligible to work')
    
    if re.search(r'security\s+clearance', text, re.IGNORECASE):
        preferences.append('Has security clearance')
    
    return ', '.join(preferences) if preferences else ''


def add_profile_match_scores(jobs, user_id):
    """
    Add profile_match_score to each job based on user's profile embeddings.
    Computes max similarity across all resume chunks.
    """
    if not jobs:
        return jobs
    
    try:
        job_ids = [job['job_id'] for job in jobs]
        
        # Query to get max similarity across all profile chunks for each job
        sql = """
            SELECT 
                je.job_id,
                MAX(1 - (pe.embedding <=> je.embedding)) AS profile_match_score
            FROM job_embeddings je
            CROSS JOIN profile_embeddings pe
            WHERE pe.user_id = %s
              AND je.job_id = ANY(%s)
            GROUP BY je.job_id
        """
        
        results = lakebase.run_query(sql, (user_id, job_ids))
        match_scores = {row['job_id']: float(row['profile_match_score']) for row in results}
        
        # Add match scores to jobs
        for job in jobs:
            job['profile_match_score'] = match_scores.get(job['job_id'])
        
        return jobs
        
    except Exception as e:
        print(f"Error adding profile match scores: {e}")
        import traceback
        traceback.print_exc()
        # Return jobs without profile scores on error (graceful degradation)
        return jobs


@app.route('/search')
def search():
    """Job search page."""
    user = get_current_user()
    return render_template('search.html', user=user)


@app.route('/api/search', methods=['POST'])
def api_search():
    """Semantic job search API endpoint."""
    data = request.json
    query = data.get('query', '').strip()
    location = data.get('location', '').strip()
    remote_only = data.get('remote_only', False)
    limit = data.get('limit', 20)
    include_profile_match = data.get('include_profile_match', False)
    
    if not query:
        return jsonify({'success': False, 'error': 'Query is required'}), 400
    
    try:
        # Generate embedding for the search query
        query_embedding = embedding_model.encode(query).tolist()
        
        # Build the SQL query
        # Use cosine distance (<=> operator) for vector similarity
        sql = """
            SELECT 
                p.job_id,
                p.title,
                p.company,
                p.location,
                p.salary_min,
                p.salary_max,
                p.description,
                p.url,
                p.posted_date,
                e.embedding <=> %s::vector as distance
            FROM job_embeddings e
            JOIN job_postings p ON e.job_id = p.job_id
            WHERE p.is_active = TRUE
        """
        
        params = [query_embedding]
        
        # Add location filter if provided
        if location:
            sql += " AND p.location ILIKE %s"
            params.append(f"%{location}%")
        
        # Add remote filter if requested
        if remote_only:
            sql += " AND LOWER(p.location) LIKE '%remote%'"
        
        # Order by similarity (lowest distance = most similar)
        sql += " ORDER BY distance ASC LIMIT %s"
        params.append(limit)
        
        # Execute query
        results = lakebase.run_query(sql, tuple(params))
        
        # Format results
        jobs = []
        for row in results:
            jobs.append({
                'job_id': row['job_id'],
                'title': row['title'],
                'company': row['company'],
                'location': row['location'],
                'salary_min': row['salary_min'],
                'salary_max': row['salary_max'],
                'description': row['description'],
                'url': row['url'],
                'posted_date': row['posted_date'].isoformat() if row['posted_date'] else None,
                'similarity': float(1 - row['distance'])  # Convert distance to similarity score (0-1)
            })
        
        # Add profile match scores if requested
        if include_profile_match:
            user = get_current_user()
            user_id = get_or_create_user(user['email'], user['name'])
            if user_id:
                jobs = add_profile_match_scores(jobs, user_id)
        
        return jsonify({
            'success': True,
            'query': query,
            'count': len(jobs),
            'jobs': jobs
        })
        
    except Exception as e:
        print(f"Error in semantic search: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/market-stats')
def market_stats():
    """Job market statistics page."""
    user = get_current_user()
    return render_template('market_stats.html', user=user)


@app.route('/api/market-stats', methods=['GET'])
def api_market_stats():
    """API endpoint for job market statistics."""
    import time
    try:
        print("[MARKET-STATS] API endpoint called")
        start_time = time.time()
        
        # Summary stats - optimized single query
        print("[MARKET-STATS] Executing summary stats query...")
        summary_stats = lakebase.run_query("""
            SELECT 
                COUNT(*) as total_jobs,
                COUNT(*) FILTER (WHERE LOWER(location) LIKE '%remote%') as remote_jobs,
                AVG((salary_min + salary_max) / 2.0) FILTER (WHERE salary_min IS NOT NULL AND salary_max IS NOT NULL) as avg_salary,
                MIN(salary_min) FILTER (WHERE salary_min IS NOT NULL) as min_salary,
                MAX(salary_max) FILTER (WHERE salary_max IS NOT NULL) as max_salary
            FROM job_postings
            WHERE is_active = TRUE
        """)
        
        stats = summary_stats[0] if summary_stats else {}
        total_jobs = stats.get('total_jobs', 0)
        remote_jobs = stats.get('remote_jobs', 0)
        avg_salary = float(stats.get('avg_salary', 0) or 0)
        min_salary = float(stats.get('min_salary', 0) or 0)
        max_salary = float(stats.get('max_salary', 0) or 0)
        remote_percentage = round((remote_jobs / total_jobs * 100), 1) if total_jobs > 0 else 0
        
        # Top locations
        print("[MARKET-STATS] Executing top locations query...")
        top_locations = lakebase.run_query("""
            SELECT location, COUNT(*) as count
            FROM job_postings
            WHERE is_active = TRUE
            GROUP BY location
            ORDER BY count DESC
            LIMIT 10
        """)
        
        # Salary distribution
        print("[MARKET-STATS] Executing salary distribution query...")
        salary_distribution = lakebase.run_query("""
            SELECT 
                CASE 
                    WHEN (salary_min + salary_max) / 2 < 50000 THEN '< $50k'
                    WHEN (salary_min + salary_max) / 2 < 75000 THEN '$50k-$75k'
                    WHEN (salary_min + salary_max) / 2 < 100000 THEN '$75k-$100k'
                    WHEN (salary_min + salary_max) / 2 < 125000 THEN '$100k-$125k'
                    WHEN (salary_min + salary_max) / 2 < 150000 THEN '$125k-$150k'
                    WHEN (salary_min + salary_max) / 2 < 200000 THEN '$150k-$200k'
                    ELSE '$200k+'
                END as range,
                COUNT(*) as count
            FROM job_postings
            WHERE is_active = TRUE AND salary_min IS NOT NULL AND salary_max IS NOT NULL
            GROUP BY range
            ORDER BY MIN(salary_min)
        """)
        
        # Top companies
        print("[MARKET-STATS] Executing top companies query...")
        top_companies = lakebase.run_query("""
            SELECT company, COUNT(*) as count
            FROM job_postings
            WHERE is_active = TRUE
            GROUP BY company
            ORDER BY count DESC
            LIMIT 10
        """)
        
        # Top titles
        print("[MARKET-STATS] Executing top titles query...")
        top_titles = lakebase.run_query("""
            SELECT title, COUNT(*) as count
            FROM job_postings
            WHERE is_active = TRUE
            GROUP BY title
            ORDER BY count DESC
            LIMIT 10
        """)
        
        query_time = time.time() - start_time
        print(f"[MARKET-STATS] All queries completed in {query_time:.2f} seconds")
        
        return jsonify({
            'success': True,
            'stats': {
                'total_jobs': total_jobs,
                'avg_salary': avg_salary,
                'min_salary': min_salary,
                'max_salary': max_salary,
                'remote_jobs': remote_jobs,
                'remote_percentage': remote_percentage,
                'top_locations': [{'location': row['location'], 'count': row['count']} for row in top_locations],
                'salary_distribution': [{'range': row['range'], 'count': row['count']} for row in salary_distribution],
                'top_companies': [{'company': row['company'], 'count': row['count']} for row in top_companies],
                'top_titles': [{'title': row['title'], 'count': row['count']} for row in top_titles]
            },
            'query_time': query_time
        })
        
    except Exception as e:
        print(f"Error loading market stats: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/pipeline')
def pipeline():
    """Application pipeline tracking page."""
    user = get_current_user()
    user_id = get_or_create_user(user['email'], user['name'])
    
    applications = []
    if user_id:
        try:
            applications = lakebase.run_query(
                """
                SELECT a.*, j.title, j.company, j.location
                FROM applications a
                JOIN job_postings j ON a.job_id = j.job_id
                WHERE a.user_id = %s
                ORDER BY a.updated_at DESC
                """,
                (user_id,)
            )
        except Exception as e:
            print(f"Error loading applications: {e}")
    
    # Group by status
    grouped = {
        'saved': [],
        'applied': [],
        'interviewing': [],
        'offer': [],
        'rejected': []
    }
    for app in applications:
        status = app.get('status', 'saved')
        if status in grouped:
            grouped[status].append(app)
    
    return render_template('pipeline.html', user=user, applications=grouped)


@app.route('/api/save_job', methods=['POST'])
def save_job():
    """API endpoint to save a job to the pipeline."""
    try:
        data = request.json
        job_id = data.get('job_id')
        status = data.get('status', 'saved')
        notes = data.get('notes', '')
        
        if not job_id:
            return jsonify({'success': False, 'error': 'Job ID is required'}), 400
        
        # Get current user
        user = get_current_user()
        user_id = get_or_create_user(user['email'], user['name'])
        
        if not user_id:
            return jsonify({'success': False, 'error': 'User not found'}), 400
        
        # Check if application already exists
        existing = lakebase.run_query(
            "SELECT application_id FROM applications WHERE user_id = %s AND job_id = %s",
            (user_id, job_id)
        )
        
        if existing:
            # Update existing application
            lakebase.run_write(
                "UPDATE applications SET status = %s, notes = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s AND job_id = %s",
                (status, notes, user_id, job_id)
            )
            application_id = existing[0]['application_id']
        else:
            # Insert new application
            lakebase.run_write(
                "INSERT INTO applications (user_id, job_id, status, notes, created_at, updated_at) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (user_id, job_id, status, notes)
            )
            # Get the new application_id
            result = lakebase.run_query(
                "SELECT application_id FROM applications WHERE user_id = %s AND job_id = %s",
                (user_id, job_id)
            )
            application_id = result[0]['application_id'] if result else None
        
        return jsonify({
            'success': True,
            'message': f'Job saved to {status} stage',
            'application_id': application_id
        })
    
    except Exception as e:
        print(f"Error saving job: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/update_job_status', methods=['POST'])
def update_job_status():
    """API endpoint to update job status in the pipeline."""
    try:
        data = request.json
        job_id = data.get('job_id')
        new_status = data.get('status')
        notes = data.get('notes', '')
        
        if not job_id or not new_status:
            return jsonify({'success': False, 'error': 'Job ID and status are required'}), 400
        
        # Validate status
        valid_statuses = ['saved', 'applied', 'interviewing', 'offer', 'rejected', 'accepted']
        if new_status not in valid_statuses:
            return jsonify({
                'success': False,
                'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }), 400
        
        # Get current user
        user = get_current_user()
        user_id = get_or_create_user(user['email'], user['name'])
        
        if not user_id:
            return jsonify({'success': False, 'error': 'User not found'}), 400
        
        # Check if application exists
        existing = lakebase.run_query(
            "SELECT application_id FROM applications WHERE user_id = %s AND job_id = %s",
            (user_id, job_id)
        )
        
        if existing:
            # Update existing application status
            lakebase.run_write(
                "UPDATE applications SET status = %s, notes = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s AND job_id = %s",
                (new_status, notes, user_id, job_id)
            )
            return jsonify({
                'success': True,
                'message': f'Job moved to {new_status}'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Application not found'
            }), 404
    
    except Exception as e:
        print(f"Error updating job status: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/interviews')
def interviews():
    """Interview tracking page."""
    user = get_current_user()
    user_id = get_or_create_user(user['email'], user['name'])
    
    interviewing_apps = []
    if user_id:
        try:
            interviewing_apps = lakebase.run_query(
                """
                SELECT a.*, j.title, j.company, j.location, j.url
                FROM applications a
                JOIN job_postings j ON a.job_id = j.job_id
                WHERE a.user_id = %s AND a.status = 'interviewing'
                ORDER BY a.updated_at DESC
                """,
                (user_id,)
            )
        except Exception as e:
            print(f"Error loading interviewing applications: {e}")
    
    return render_template('interviews.html', user=user, applications=interviewing_apps)


@app.route('/assistant')
def assistant():
    """AI assistant chat interface."""
    user = get_current_user()
    return render_template('assistant.html', user=user)


@app.route('/api/chat', methods=['POST'])
def chat():
    """API endpoint for chat messages - integrated with Databricks Assistant API."""
    data = request.json
    message = data.get('message', '').strip()
    conversation_id = data.get('conversation_id')  # Optional: reuse existing conversation
    
    if not message:
        return jsonify({'success': False, 'error': 'Message is required'}), 400
    
    try:
        # Get current user for context
        user = get_current_user()
        user_email = user['email']
        
        # Get or create Assistant client
        client = get_assistant_client()
        
        # Create a new conversation if needed (with auto MCP discovery)
        if not conversation_id and not client.conversation_id:
            try:
                conversation_id = client.create_conversation(
                    user_email=user_email,
                    auto_discover_mcp=True  # Automatically discover and attach MCP servers
                )
            except Exception as conv_error:
                print(f"Warning: Could not create conversation with MCP: {conv_error}")
                # Fallback: create conversation without MCP
                conversation_id = client.create_conversation(
                    user_email=user_email,
                    auto_discover_mcp=False
                )
        
        # Send message to Assistant
        result = client.send_message(message, conversation_id=conversation_id)
        
        if result['success']:
            return jsonify({
                'success': True,
                'reply': result['reply'],
                'conversation_id': result['conversation_id'],
                'message_id': result.get('message_id')
            })
        else:
            return jsonify({
                'success': False,
                'reply': result['reply'],
                'error': result.get('error', 'Unknown error')
            }), 500
    
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'reply': 'Sorry, I encountered an unexpected error. Please try again.'
        }), 500


@app.route('/api/profiles', methods=['GET'])
def get_profiles():
    """Get all user profiles."""
    try:
        profiles = lakebase.run_query(
            "SELECT email, full_name FROM users ORDER BY full_name"
        )
        return jsonify({
            'success': True,
            'profiles': profiles
        })
    except Exception as e:
        print(f"Error fetching profiles: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/profiles/current', methods=['GET'])
def get_current_profile():
    """Get currently selected profile."""
    user = get_current_user()
    return jsonify({
        'success': True,
        'profile': user
    })


@app.route('/api/profiles/switch', methods=['POST'])
def switch_profile():
    """Switch to a different profile."""
    data = request.json
    email = data.get('email')
    name = data.get('name')
    
    if not email or not name:
        return jsonify({'success': False, 'error': 'Email and name are required'}), 400
    
    # Store selected profile in session
    session['selected_profile'] = {
        'email': email,
        'name': name
    }
    
    return jsonify({
        'success': True,
        'profile': session['selected_profile']
    })


@app.route('/api/profiles/create', methods=['POST'])
def create_profile():
    """Create a new profile."""
    data = request.json
    email = data.get('email')
    name = data.get('name')
    
    if not email or not name:
        return jsonify({'success': False, 'error': 'Email and name are required'}), 400
    
    try:
        # Create user in database
        user_id = get_or_create_user(email, name)
        
        if user_id:
            # Switch to the new profile
            session['selected_profile'] = {
                'email': email,
                'name': name
            }
            return jsonify({
                'success': True,
                'profile': session['selected_profile']
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to create profile'}), 500
    except Exception as e:
        print(f"Error creating profile: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/profiles/clear', methods=['POST'])
def clear_profile():
    """Clear selected profile and return to authenticated user."""
    if 'selected_profile' in session:
        session.pop('selected_profile')
    return jsonify({'success': True})


if __name__ == '__main__':
    host = os.getenv('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_RUN_PORT', 8000))
    app.run(debug=True, host=host, port=port)
    print(f"Flask app running on http://{host}:{port}")
