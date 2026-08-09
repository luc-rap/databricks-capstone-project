"""
Lakebase Job Adapter for Job Search and Matching

Provides Python functions to interact with job postings stored in Lakebase Postgres.
Supports semantic search, ranking against user profiles, and application pipeline management.

All functions return structured dicts suitable for MCP tool responses.
"""

import os
import base64
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from typing import Optional, Dict, List, Any
from datetime import datetime

# Database connection singleton
_db_connection = None


def _get_db_connection():
    """Get or create a database connection using password from secret (same as notebooks)."""
    global _db_connection
    
    if _db_connection is None or _db_connection.closed:
        from databricks.sdk import WorkspaceClient
        from urllib.parse import urlparse
        
        w = WorkspaceClient()
        
        # Get Lakebase URL from secret (same as notebook cell 7)
        secret = w.secrets.get_secret(scope="database", key="lakebase-url")
        lakebase_url = base64.b64decode(secret.value).decode("utf-8")
        parsed = urlparse(lakebase_url)
        
        # Extract connection components
        db_host = parsed.hostname
        db_port = parsed.port or 5432
        db_name = parsed.path.lstrip('/')
        db_user = parsed.username
        
        # Use password from URL (not OAuth)
        if parsed.password:
            db_password = parsed.password
        else:
            # Fallback: try to get token from separate secret
            token_secret = w.secrets.get_secret(scope="database", key="lakebase-token")
            db_password = base64.b64decode(token_secret.value).decode("utf-8")
        
        # Connect with psycopg2 (same as notebook cell 8)
        _db_connection = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password,
            sslmode='require',
            cursor_factory=RealDictCursor
        )
    
    return _db_connection



def search_jobs(
    keywords: Optional[str] = None,
    location: Optional[str] = None,
    salary_min: Optional[int] = None,
    salary_max: Optional[int] = None,
    contract_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Search for jobs in Lakebase using SQL filters.
    
    Args:
        keywords: Keywords to search in title/description (case-insensitive)
        location: Location filter (case-insensitive, partial match)
        salary_min: Minimum salary requirement
        salary_max: Maximum salary cap
        contract_type: Contract type filter
        limit: Number of results to return
        offset: Pagination offset
    
    Returns:
        Dict with count and list of job results
    """
    conn = _get_db_connection()
    cursor = conn.cursor()
    
    # Build dynamic SQL query
    conditions = ["is_active = TRUE"]
    params = []
    
    if keywords:
        conditions.append("(title ILIKE %s OR description ILIKE %s)" )
        keyword_pattern = f"%{keywords}%"
        params.extend([keyword_pattern, keyword_pattern])
    
    if location:
        conditions.append("location ILIKE %s")
        params.append(f"%{location}%")
    
    if salary_min:
        conditions.append("(salary_max >= %s OR salary_min >= %s)")
        params.extend([salary_min, salary_min])
    
    if salary_max:
        conditions.append("(salary_min <= %s OR salary_max <= %s)")
        params.extend([salary_max, salary_max])
    
    if contract_type:
        conditions.append("contract_type = %s")
        params.append(contract_type)
    
    where_clause = " AND ".join(conditions)
    
    # Count total results
    count_sql = f"SELECT COUNT(*) as total FROM job_postings WHERE {where_clause}"
    cursor.execute(count_sql, params)
    total_count = cursor.fetchone()['total']
    
    # Fetch results
    sql = f"""
        SELECT 
            job_id,
            external_id,
            title,
            company,
            location,
            description,
            url,
            salary_min,
            salary_max,
            contract_type,
            category,
            posted_date as created,
            fetched_at
        FROM job_postings
        WHERE {where_clause}
        ORDER BY fetched_at DESC
        LIMIT %s OFFSET %s
    """
    
    cursor.execute(sql, params + [limit, offset])
    results = cursor.fetchall()
    
    return {
        "count": total_count,
        "results": [dict(row) for row in results],
        "page": (offset // limit) + 1,
        "limit": limit,
    }


# Global embedding model singleton
_embedding_model = None

def _get_embedding_model():
    """Get or load the sentence-transformers model (singleton pattern)."""
    global _embedding_model
    
    if _embedding_model is None:
        import os
        from sentence_transformers import SentenceTransformer
        
        # Same model as ingest_profile_embeddings.py
        MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
        
        # Use same cache location as notebooks
        os.environ["HF_HOME"] = "/tmp/.cache/huggingface"
        os.environ["TRANSFORMERS_CACHE"] = "/tmp/.cache/huggingface"
        os.environ["HF_HUB_CACHE"] = "/tmp/.cache/huggingface"
        
        _embedding_model = SentenceTransformer(MODEL_NAME, cache_folder="/tmp/.cache/huggingface")
    
    return _embedding_model


def _generate_embedding(text: str) -> List[float]:
    """
    Generate embedding vector for text using sentence-transformers.
    Uses the SAME model as ingest_profile_embeddings.py: all-MiniLM-L6-v2 (384-dim).
    
    Args:
        text: Input text to embed
    
    Returns:
        Embedding vector as list of floats (384 dimensions)
    """
    model = _get_embedding_model()
    
    # Encode the text (returns numpy array)
    embedding = model.encode(text, show_progress_bar=False)
    
    # Convert to list for JSON serialization
    return embedding.tolist()


def store_user_profile(
    user_email: str,
    profile_text: str,
    target_roles: Optional[str] = None,
    location_preferences: Optional[str] = None,
    remote_preference: Optional[str] = None,
    job_preferences: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store user profile/resume with chunked embeddings.
    Stores profile metadata in profiles table and embeddings in profile_embeddings table.
    
    Args:
        user_email: User's email
        profile_text: Resume text to embed
        target_roles: Comma-separated target roles
        location_preferences: Preferred locations
        remote_preference: Remote work preference (remote, hybrid, onsite)
        job_preferences: Job preferences (work authorization, visa requirements, etc.)
    
    Returns:
        Confirmation dict with profile_id
    """
    conn = _get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Step 1: Get or create user in users table
        cursor.execute(
            "INSERT INTO users (email, full_name) VALUES (%s, %s) ON CONFLICT (email) DO NOTHING RETURNING user_id",
            (user_email, user_email.split('@')[0])  # Use email prefix as default name
        )
        result = cursor.fetchone()
        
        if result:
            user_id = result['user_id']
        else:
            # User already exists, get their ID
            cursor.execute("SELECT user_id FROM users WHERE email = %s", (user_email,))
            user_id = cursor.fetchone()['user_id']
        
        # Step 2: Insert or update profile (without embedding - that goes in profile_embeddings)
        cursor.execute(
            """
            INSERT INTO profiles (
                user_id, resume_text, target_roles, 
                location_preferences, remote_preference, job_preferences, created_at, updated_at
            ) VALUES (%s, %s, %s::text[], %s::text[], %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id)
            DO UPDATE SET
                resume_text = EXCLUDED.resume_text,
                target_roles = EXCLUDED.target_roles,
                location_preferences = EXCLUDED.location_preferences,
                remote_preference = EXCLUDED.remote_preference,
                job_preferences = EXCLUDED.job_preferences,
                updated_at = CURRENT_TIMESTAMP
            RETURNING profile_id, user_id
            """,
            (user_id, profile_text, 
             [target_roles] if target_roles else [],
             [location_preferences] if location_preferences else [],
             remote_preference,
             job_preferences)
        )
        profile_result = cursor.fetchone()
        profile_id = profile_result['profile_id']
        profile_user_id = profile_result['user_id']
        
        # Step 3: Generate embedding for full resume text (as single chunk for now)
        try:
            embedding = _generate_embedding(profile_text)
        except Exception as e:
            conn.rollback()
            return {
                "status": "error",
                "message": f"Failed to generate embedding: {str(e)}"
            }
        
        # Step 4: Store embedding in profile_embeddings table (upsert using ON CONFLICT)
        cursor.execute(
            """
            INSERT INTO profile_embeddings (
                user_id, chunk_index, chunk_text, embedding, model_name, embedded_at
            ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, chunk_index)
            DO UPDATE SET
                chunk_text = EXCLUDED.chunk_text,
                embedding = EXCLUDED.embedding,
                embedded_at = CURRENT_TIMESTAMP
            """,
            (profile_user_id, 0, profile_text, embedding, 'sentence-transformers/all-MiniLM-L6-v2')
        )
        
        conn.commit()
        
        return {
            "status": "success",
            "message": f"Profile stored with embeddings",
            "profile_id": profile_id,
            "user_id": profile_user_id,
            "embedding_dim": len(embedding)
        }
    except Exception as e:
        conn.rollback()
        return {
            "status": "error",
            "message": f"Failed to store profile: {str(e)}"
        }


def search_jobs_by_query(
    user_email: str,
    query: str,
    use_profile: bool = True,
    location: Optional[str] = None,
    top_k: int = 10,
) -> Dict[str, Any]:
    """
    Search jobs using natural language query + stored user profile embeddings.
    Uses PostgreSQL vector search with <=> operator for fast similarity computation.
    
    Args:
        user_email: User's email to load their profile embedding
        query: Natural language search query
        use_profile: Whether to combine query with user's stored profile
        location: Optional location filter
        top_k: Number of top matches to return
    
    Returns:
        Dict with ranked job results, match scores, and explanations
    """
    conn = _get_db_connection()
    cursor = conn.cursor()
    
    # Step 1: Embed the user's query
    try:
        query_embedding = _generate_embedding(query)
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to embed query: {str(e)}"
        }
    
    # Step 2: Check if user has a profile embedding
    profile_user_id = None
    has_profile = False
    
    if use_profile:
        cursor.execute(
            """
            SELECT p.user_id
            FROM users u
            JOIN profiles p ON u.user_id = p.user_id
            WHERE u.email = %s
            LIMIT 1
            """,
            (user_email,)
        )
        profile_lookup = cursor.fetchone()
        
        if profile_lookup:
            profile_user_id = profile_lookup['user_id']
            # Check if embeddings exist
            cursor.execute(
                "SELECT COUNT(*) as count FROM profile_embeddings WHERE user_id = %s",
                (profile_user_id,)
            )
            count_result = cursor.fetchone()
            has_profile = count_result['count'] > 0
    
    # Step 3: Build filter conditions
    filter_conditions = ["je.embedding IS NOT NULL", "jp.is_active = TRUE"]
    filter_params = []
    
    if location:
        filter_conditions.append("jp.location ILIKE %s")
        filter_params.append(f"%{location}%")
    
    filter_clause = " AND ".join(filter_conditions)
    
    # Step 4: Use vector search with <=> operator
    # If profile exists, combine query + profile similarity; otherwise just query
    if has_profile and profile_user_id:
        # Combined search: 40% query similarity + 60% profile similarity
        # Use subquery to get profile embedding (first chunk)
        sql = f"""
            WITH profile_emb AS (
                SELECT embedding
                FROM profile_embeddings
                WHERE user_id = %s
                ORDER BY chunk_index
                LIMIT 1
            )
            SELECT 
                jp.job_id,
                jp.external_id,
                jp.title,
                jp.company,
                jp.location,
                jp.description,
                jp.url,
                jp.salary_min,
                jp.salary_max,
                jp.contract_type,
                jp.category,
                jp.posted_date as created,
                jp.fetched_at,
                (1 - (je.embedding <=> %s::vector)) AS query_similarity,
                (1 - (je.embedding <=> (SELECT embedding FROM profile_emb))) AS profile_similarity,
                ((1 - (je.embedding <=> %s::vector)) * 0.4 + 
                 (1 - (je.embedding <=> (SELECT embedding FROM profile_emb))) * 0.6) AS match_score
            FROM job_postings jp
            JOIN job_embeddings je ON jp.job_id = je.job_id
            WHERE {filter_clause}
            ORDER BY match_score DESC
            LIMIT %s
        """
        cursor.execute(sql, [profile_user_id, query_embedding, query_embedding] + filter_params + [top_k])
    else:
        # Query-only search (no profile)
        sql = f"""
            SELECT 
                jp.job_id,
                jp.external_id,
                jp.title,
                jp.company,
                jp.location,
                jp.description,
                jp.url,
                jp.salary_min,
                jp.salary_max,
                jp.contract_type,
                jp.category,
                jp.posted_date as created,
                jp.fetched_at,
                (1 - (je.embedding <=> %s::vector)) AS query_similarity,
                NULL AS profile_similarity,
                (1 - (je.embedding <=> %s::vector)) AS match_score
            FROM job_postings jp
            JOIN job_embeddings je ON jp.job_id = je.job_id
            WHERE {filter_clause}
            ORDER BY match_score DESC
            LIMIT %s
        """
        cursor.execute(sql, [query_embedding, query_embedding] + filter_params + [top_k])
    
    results = cursor.fetchall()
    
    # Convert to list of dicts and scale scores to 0-100
    formatted_results = []
    for row in results:
        job_dict = dict(row)
        job_dict['match_score'] = round(job_dict['match_score'] * 100, 1)
        job_dict['query_similarity'] = round(job_dict['query_similarity'] * 100, 1)
        if job_dict['profile_similarity'] is not None:
            job_dict['profile_similarity'] = round(job_dict['profile_similarity'] * 100, 1)
        formatted_results.append(job_dict)
    
    return {
        "count": len(formatted_results),
        "results": formatted_results,
        "page": 1,
        "limit": top_k,
        "query": query,
        "used_profile": has_profile,
    }


def rank_jobs_by_profile(
    user_profile_text: str,
    keywords: Optional[str] = None,
    location: Optional[str] = None,
    top_k: int = 10,
) -> Dict[str, Any]:
    """
    DEPRECATED: Use search_jobs_by_query() with stored profiles instead.
    
    Rank jobs by semantic similarity to user profile using embeddings.
    Now uses PostgreSQL vector search with <=> operator.
    
    Args:
        user_profile_text: User's resume/profile text for semantic matching
        keywords: Optional keyword filter
        location: Optional location filter
        top_k: Number of top matches to return
    
    Returns:
        Dict with ranked job results and match scores
    """
    conn = _get_db_connection()
    cursor = conn.cursor()
    
    # Step 1: Generate embedding for user profile
    try:
        user_embedding = _generate_embedding(user_profile_text)
    except Exception as e:
        # Fallback to keyword search if embedding generation fails
        print(f"Warning: Embedding generation failed ({e}), falling back to keyword search")
        results = search_jobs(keywords=keywords, location=location, limit=top_k)
        for job in results['results']:
            job['match_score'] = 50.0
            job['match_reasoning'] = "Keyword-based match (embeddings unavailable)"
        return results
    
    # Step 2: Build filter conditions for optional keywords/location
    filter_conditions = ["je.embedding IS NOT NULL", "jp.is_active = TRUE"]
    filter_params = []
    
    if keywords:
        filter_conditions.append("(jp.title ILIKE %s OR jp.description ILIKE %s)")
        keyword_pattern = f"%{keywords}%"
        filter_params.extend([keyword_pattern, keyword_pattern])
    
    if location:
        filter_conditions.append("jp.location ILIKE %s")
        filter_params.append(f"%{location}%")
    
    filter_clause = " AND ".join(filter_conditions)
    
    # Step 3: Use vector search with <=> operator to compute similarity in database
    sql = f"""
        SELECT 
            jp.external_id as id,
            jp.title,
            jp.company,
            jp.location,
            jp.description,
            jp.url,
            jp.salary_min,
            jp.salary_max,
            jp.contract_type,
            jp.category,
            jp.posted_date as created,
            jp.fetched_at,
            (1 - (je.embedding <=> %s::vector)) AS similarity
        FROM job_postings jp
        JOIN job_embeddings je ON jp.job_id = je.job_id
        WHERE {filter_clause}
        ORDER BY similarity DESC
        LIMIT %s
    """
    
    cursor.execute(sql, [user_embedding] + filter_params + [top_k])
    results = cursor.fetchall()
    
    # Format results
    ranked_jobs = []
    for job in results:
        job_dict = dict(job)
        similarity = job_dict.pop('similarity')
        job_dict['match_score'] = round(similarity * 100, 1)
        job_dict['match_reasoning'] = (
            f"Semantic similarity: {similarity:.3f}. "
            f"Profile keywords align with job requirements."
        )
        ranked_jobs.append(job_dict)
    
    return {
        "count": len(ranked_jobs),
        "results": ranked_jobs,
        "page": 1,
        "limit": top_k,
    }


def explain_job_match(
    user_email: str,
    job_id: int,
) -> Dict[str, Any]:
    """
    Explain why a job is or isn't a good match for the user.
    Uses PostgreSQL vector similarity, stored profile data, and rule-based matching.
    
    Args:
        user_email: User's email to load their profile
        job_id: Job posting ID (internal job_id, not external_id)
    
    Returns:
        Dict with detailed match explanation, score breakdown, strengths, and gaps
    """
    conn = _get_db_connection()
    cursor = conn.cursor()
    
    # Step 1: Get user profile and check if they have embeddings
    cursor.execute(
        """
        SELECT 
            u.user_id,
            p.profile_id,
            p.resume_text,
            p.target_roles,
            p.location_preferences,
            p.remote_preference,
            p.job_preferences,
            p.years_experience,
            p.salary_min,
            p.salary_max
        FROM users u
        LEFT JOIN profiles p ON u.user_id = p.user_id
        WHERE u.email = %s
        LIMIT 1
        """,
        (user_email,)
    )
    user_data = cursor.fetchone()
    
    if not user_data:
        return {
            "status": "error",
            "message": f"User {user_email} not found"
        }
    
    if not user_data['profile_id']:
        return {
            "status": "error",
            "message": "No profile found. Please create a profile first using store_user_profile."
        }
    
    user_id = user_data['user_id']
    
    # Step 2: Get job details and compute semantic similarity using vector search
    cursor.execute(
        """
        WITH profile_emb AS (
            SELECT embedding
            FROM profile_embeddings
            WHERE user_id = %s
            ORDER BY chunk_index
            LIMIT 1
        )
        SELECT 
            jp.job_id,
            jp.external_id,
            jp.title,
            jp.company,
            jp.location,
            jp.description,
            jp.salary_min,
            jp.salary_max,
            jp.contract_type,
            jp.is_remote,
            jp.url,
            CASE 
                WHEN je.embedding IS NOT NULL AND (SELECT embedding FROM profile_emb) IS NOT NULL
                THEN (1 - (je.embedding <=> (SELECT embedding FROM profile_emb)))
                ELSE NULL
            END AS semantic_similarity
        FROM job_postings jp
        LEFT JOIN job_embeddings je ON jp.job_id = je.job_id
        WHERE jp.job_id = %s
        """,
        (user_id, job_id)
    )
    job = cursor.fetchone()
    
    if not job:
        return {
            "status": "error",
            "message": f"Job {job_id} not found"
        }
    
    # Step 3: Analyze matches and gaps
    matches = []
    gaps = []
    scores = {}
    
    # 1. Semantic similarity score
    semantic_score = job['semantic_similarity'] or 0.0
    scores['semantic_match'] = round(semantic_score * 100, 1)
    
    if semantic_score > 0.75:
        matches.append(f"🟢 Excellent semantic match ({semantic_score:.2f}) - Your profile strongly aligns with this role's requirements")
    elif semantic_score > 0.6:
        matches.append(f"🟡 Good semantic match ({semantic_score:.2f}) - Solid alignment with some areas to develop")
    elif semantic_score > 0.45:
        matches.append(f"🟠 Moderate match ({semantic_score:.2f}) - Some relevant experience but notable gaps")
    else:
        gaps.append(f"🔴 Low semantic similarity ({semantic_score:.2f}) - This role requires significantly different skills/experience")
    
    # 2. Target roles matching
    target_roles = user_data['target_roles'] or []
    job_title_lower = job['title'].lower()
    
    matched_roles = [role for role in target_roles if role.lower() in job_title_lower]
    if matched_roles:
        scores['role_match'] = 100
        matches.append(f"✓ Title matches your target roles: {', '.join(matched_roles)}")
    else:
        scores['role_match'] = 50 if target_roles else 75  # Lower score if they have specific targets
        if target_roles:
            gaps.append(f"✗ Job title '{job['title']}' doesn't match your target roles: {', '.join(target_roles)}")
    
    # 3. Location/Remote matching
    location_prefs = user_data['location_preferences'] or []
    remote_pref = user_data['remote_preference']
    
    location_match = False
    if job['is_remote']:
        if remote_pref in ['remote', 'flexible']:
            scores['location_match'] = 100
            matches.append(f"✓ Remote position aligns with your '{remote_pref}' preference")
            location_match = True
        else:
            scores['location_match'] = 50
            gaps.append(f"⚠ Remote position (you prefer '{remote_pref}' work)")
    elif location_prefs:
        job_location_lower = job['location'].lower()
        matching_locations = [loc for loc in location_prefs if loc.lower() in job_location_lower]
        
        if matching_locations:
            scores['location_match'] = 100
            matches.append(f"✓ Location matches your preferences: {', '.join(matching_locations)}")
            location_match = True
        else:
            scores['location_match'] = 30
            gaps.append(f"✗ Location '{job['location']}' not in your preferences: {', '.join(location_prefs)}")
    else:
        scores['location_match'] = 75  # Neutral if no preference
    
    # 4. Salary matching
    user_salary_min = user_data['salary_min']
    user_salary_max = user_data['salary_max']
    
    if job['salary_min'] and user_salary_min:
        if job['salary_min'] >= user_salary_min:
            salary_diff = ((job['salary_min'] - user_salary_min) / user_salary_min) * 100
            scores['salary_match'] = 100
            matches.append(f"✓ Salary ${job['salary_min']:,}+ meets your ${user_salary_min:,}+ requirement (+{salary_diff:.0f}%)")
        else:
            salary_gap = user_salary_min - job['salary_min']
            gap_pct = (salary_gap / user_salary_min) * 100
            scores['salary_match'] = max(0, 100 - gap_pct)
            gaps.append(f"✗ Salary ${job['salary_min']:,} is ${salary_gap:,} below your ${user_salary_min:,} minimum (-{gap_pct:.0f}%)")
    elif not job['salary_min']:
        scores['salary_match'] = 50
        gaps.append("⚠ Salary not disclosed - recommend discussing during interview")
    else:
        scores['salary_match'] = 75  # Neutral if user didn't specify
    
    # 5. Job preferences matching (work authorization, etc.)
    job_prefs = user_data['job_preferences']
    if job_prefs:
        # This is informational - include in the response
        matches.append(f"ℹ️  Your requirements: {job_prefs}")
        scores['preferences_noted'] = 100
    
    # Calculate overall match score with weighted factors
    # Semantic similarity is most important (50%), then role (20%), location (15%), salary (15%)
    overall_score = (
        scores.get('semantic_match', 0) * 0.50 +
        scores.get('role_match', 75) * 0.20 +
        scores.get('location_match', 75) * 0.15 +
        scores.get('salary_match', 75) * 0.15
    )
    
    # Determine recommendation
    if overall_score >= 75:
        recommendation = "🎯 Strong Apply"
        action = "This is an excellent match. Apply soon!"
    elif overall_score >= 60:
        recommendation = "✅ Apply"
        action = "Good fit overall. Review the gaps and apply if you're comfortable addressing them."
    elif overall_score >= 45:
        recommendation = "⚠️  Consider"
        action = "Mixed signals. Carefully evaluate whether the gaps are dealbreakers or growth opportunities."
    else:
        recommendation = "❌ Skip"
        action = "Significant misalignment. Focus on better-matched opportunities."
    
    # Generate detailed reasoning
    reasoning_parts = []
    
    if semantic_score > 0.7:
        reasoning_parts.append("Your background shows strong alignment with this role's core requirements.")
    elif semantic_score > 0.5:
        reasoning_parts.append("You have relevant experience, though some skill development may be needed.")
    elif semantic_score > 0:
        reasoning_parts.append("This role stretches beyond your current profile - significant ramp-up expected.")
    
    if len(matches) > len(gaps):
        reasoning_parts.append(f"The role matches {len(matches)} of your criteria with {len(gaps)} potential gaps.")
    elif len(gaps) > 0:
        reasoning_parts.append(f"Consider the {len(gaps)} gaps carefully before applying.")
    
    return {
        "status": "success",
        "job_id": job['job_id'],
        "external_id": job['external_id'],
        "job_title": job['title'],
        "company": job['company'],
        "location": job['location'],
        "url": job['url'],
        "overall_match_score": round(overall_score, 1),
        "recommendation": recommendation,
        "action": action,
        "score_breakdown": scores,
        "strengths": matches,
        "gaps": gaps,
        "reasoning": " ".join(reasoning_parts),
        "job_details": {
            "description": job['description'][:500] + "..." if len(job['description']) > 500 else job['description'],
            "salary_range": f"${job['salary_min']:,} - ${job['salary_max']:,}" if job['salary_min'] and job['salary_max'] else "Not disclosed",
            "contract_type": job['contract_type'],
            "is_remote": job['is_remote']
        }
    }


def save_job_to_pipeline(
    user_email: str,
    job_id: str,
    stage: str,
    notes: Optional[str] = None,
    match_score: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Save a job to the user's application pipeline.
    
    Args:
        user_email: User's email (from request context)
        job_id: External job ID
        stage: Pipeline stage - saved, applied, interviewing, rejected, offer, accepted
        notes: Optional notes about this application
        match_score: Optional match score
    
    Returns:
        Confirmation dict
    """
    conn = _get_db_connection()
    cursor = conn.cursor()
    
    # Get user_id from email
    try:
        cursor.execute("SELECT user_id FROM users WHERE email = %s", (user_email,))
        user_result = cursor.fetchone()
        
        if not user_result:
            return {
                "status": "error",
                "message": f"User {user_email} not found"
            }
        
        user_id = user_result['user_id']
        
        # Insert or update application
        sql = """
            INSERT INTO applications (
                user_id, job_id, status, notes, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, job_id) 
            DO UPDATE SET
                status = EXCLUDED.status,
                notes = EXCLUDED.notes,
                updated_at = CURRENT_TIMESTAMP
            RETURNING application_id
        """
        
        cursor.execute(sql, (user_id, job_id, stage, notes))
        conn.commit()
        application_id = cursor.fetchone()['application_id']
        
        return {
            "status": "success",
            "message": f"Job saved to {stage} stage",
            "application_id": application_id,
            "job_id": job_id,
            "stage": stage,
        }
    except Exception as e:
        conn.rollback()
        return {
            "status": "error",
            "message": f"Failed to save job: {str(e)}"
        }


def get_user_applications(user_email: str, stage: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get all applications for a user, optionally filtered by stage.
    
    Args:
        user_email: User's email
        stage: Optional stage filter
    
    Returns:
        List of application dicts with job details
    """
    conn = _get_db_connection()
    cursor = conn.cursor()
    
    # First get user_id from email
    cursor.execute("SELECT user_id FROM users WHERE email = %s", (user_email,))
    user_result = cursor.fetchone()
    
    if not user_result:
        return []
    
    user_id = user_result['user_id']
    
    # Query applications with job details
    if stage:
        sql = """
            SELECT 
                a.application_id,
                a.status,
                a.applied_date,
                a.notes,
                a.created_at,
                a.updated_at,
                jp.job_id,
                jp.external_id,
                jp.title,
                jp.company,
                jp.location,
                jp.salary_min,
                jp.salary_max,
                jp.url
            FROM applications a
            JOIN job_postings jp ON a.job_id = jp.job_id
            WHERE a.user_id = %s AND a.status = %s
            ORDER BY a.updated_at DESC
        """
        cursor.execute(sql, (user_id, stage))
    else:
        sql = """
            SELECT 
                a.application_id,
                a.status,
                a.applied_date,
                a.notes,
                a.created_at,
                a.updated_at,
                jp.job_id,
                jp.external_id,
                jp.title,
                jp.company,
                jp.location,
                jp.salary_min,
                jp.salary_max,
                jp.url
            FROM applications a
            JOIN job_postings jp ON a.job_id = jp.job_id
            WHERE a.user_id = %s
            ORDER BY a.updated_at DESC
        """
        cursor.execute(sql, (user_id,))
    
    results = cursor.fetchall()
    return [dict(row) for row in results]


def get_user_info(user_email: str) -> Dict[str, Any]:
    """
    Get user profile information including resume, preferences, and settings.
    
    Args:
        user_email: User's email
    
    Returns:
        Dict with user info and profile details, or error if user not found
    """
    conn = _get_db_connection()
    cursor = conn.cursor()
    
    # Join users and profiles tables to get complete user info
    sql = """
        SELECT 
            u.user_id,
            u.email,
            u.full_name,
            u.created_at as user_created_at,
            p.profile_id,
            p.resume_text,
            p.target_roles,
            p.location_preferences,
            p.remote_preference,
            p.job_preferences,
            p.years_experience,
            p.salary_min,
            p.salary_max,
            p.created_at as profile_created_at,
            p.updated_at as profile_updated_at
        FROM users u
        LEFT JOIN profiles p ON u.user_id = p.user_id
        WHERE u.email = %s
        LIMIT 1
    """
    
    cursor.execute(sql, (user_email,))
    result = cursor.fetchone()
    
    if not result:
        return {
            "status": "error",
            "message": f"User {user_email} not found"
        }
    
    user_info = dict(result)
    
    # Check if user has a profile
    if not user_info['profile_id']:
        return {
            "status": "success",
            "message": "User found but no profile created yet",
            "user": {
                "user_id": user_info['user_id'],
                "email": user_info['email'],
                "full_name": user_info['full_name'],
                "created_at": user_info['user_created_at'],
            },
            "profile": None
        }
    
    return {
        "status": "success",
        "user": {
            "user_id": user_info['user_id'],
            "email": user_info['email'],
            "full_name": user_info['full_name'],
            "created_at": user_info['user_created_at'],
        },
        "profile": {
            "profile_id": user_info['profile_id'],
            "resume_text": user_info['resume_text'],
            "target_roles": user_info['target_roles'],
            "location_preferences": user_info['location_preferences'],
            "remote_preference": user_info['remote_preference'],
            "job_preferences": user_info['job_preferences'],
            "years_experience": user_info['years_experience'],
            "salary_min": user_info['salary_min'],
            "salary_max": user_info['salary_max'],
            "created_at": user_info['profile_created_at'],
            "updated_at": user_info['profile_updated_at'],
        }
    }


def generate_cover_letter(
    user_email: str,
    job_id: int,
) -> Dict[str, Any]:
    """
    Get context data for generating a personalized cover letter.
    Returns user profile and job details that the agent can use to generate the cover letter.
    
    Args:
        user_email: User's email address
        job_id: Job posting ID from job_postings table
    
    Returns:
        Dict with:
        - status: "success" or "error"
        - job: Job details (title, company, location, description)
        - profile: User profile (resume_text, target_roles, years_experience)
        - error: Error message (if status is "error")
    """
    conn = _get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get user info and profile
        user_info_result = get_user_info(user_email)
        
        if user_info_result.get('status') != 'success':
            return {
                "status": "error",
                "error": "User not found"
            }
        
        profile = user_info_result.get('profile')
        if not profile or not profile.get('resume_text'):
            return {
                "status": "error",
                "error": "Please complete your profile with resume text first"
            }
        
        # Get job details
        cur.execute(
            "SELECT * FROM job_postings WHERE job_id = %s",
            (job_id,)
        )
        job = cur.fetchone()
        
        if not job:
            return {
                "status": "error",
                "error": "Job not found"
            }
        
        # Return context for agent to generate cover letter
        return {
            "status": "success",
            "job": {
                "job_id": job['job_id'],
                "title": job['title'],
                "company": job['company'],
                "location": job['location'],
                "description": job['description'],
                "url": job.get('url')
            },
            "profile": {
                "resume_text": profile.get('resume_text', ''),
                "target_roles": profile.get('target_roles', []),
                "years_experience": profile.get('years_experience', 0),
                "location_preferences": profile.get('location_preferences', []),
                "remote_preference": profile.get('remote_preference')
            }
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
    finally:
        cur.close()


def add_interview_note(
    user_email: str,
    job_id: int,
    interview_date: str,
    interview_type: str,
    notes: str,
    follow_up_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add interview notes for a job application.
    Creates interview_notes table if it doesn't exist.
    
    Args:
        user_email: User's email address
        job_id: Job posting ID from job_postings table
        interview_date: Date of interview (YYYY-MM-DD)
        interview_type: Type of interview (phone_screen, technical, behavioral, onsite, final)
        notes: Interview notes and feedback
        follow_up_date: Optional follow-up date (YYYY-MM-DD)
    
    Returns:
        Dict with:
        - status: "success" or "error"
        - interview_id: ID of the created interview note
        - message: Success/error message
    """
    conn = _get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # First get user_id from email
        cur.execute("SELECT user_id FROM users WHERE email = %s", (user_email,))
        user_result = cur.fetchone()
        
        if not user_result:
            return {
                "status": "error",
                "message": "User not found"
            }
        
        user_id = user_result['user_id']
        
        # Verify job exists
        cur.execute("SELECT job_id FROM job_postings WHERE job_id = %s", (job_id,))
        job_result = cur.fetchone()
        
        if not job_result:
            return {
                "status": "error",
                "message": "Job not found"
            }
        
        # Create interview_notes table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS interview_notes (
                interview_id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                job_id INTEGER NOT NULL,
                interview_date DATE NOT NULL,
                interview_type VARCHAR(50) NOT NULL,
                notes TEXT,
                follow_up_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (job_id) REFERENCES job_postings(job_id)
            )
        """)
        
        # Insert interview note
        cur.execute("""
            INSERT INTO interview_notes 
                (user_id, job_id, interview_date, interview_type, notes, follow_up_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING interview_id
        """, (user_id, job_id, interview_date, interview_type, notes, follow_up_date))
        
        result = cur.fetchone()
        interview_id = result['interview_id']
        
        conn.commit()
        
        return {
            "status": "success",
            "interview_id": interview_id,
            "message": "Interview note added successfully",
            "job_id": job_id,
            "interview_type": interview_type
        }
    
    except Exception as e:
        conn.rollback()
        return {
            "status": "error",
            "message": f"Failed to add interview note: {str(e)}"
        }
    finally:
        cur.close()


def get_stale_applications(
    user_email: str,
    days_threshold: int = 14
) -> List[Dict[str, Any]]:
    """
    Get applications that haven't been updated in a while.
    Useful for following up on pending applications.
    
    Args:
        user_email: User's email address
        days_threshold: Number of days without update to consider stale (default 14)
    
    Returns:
        List of stale application dicts with job details
    """
    conn = _get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # First get user_id from email
        cur.execute("SELECT user_id FROM users WHERE email = %s", (user_email,))
        user_result = cur.fetchone()
        
        if not user_result:
            return []
        
        user_id = user_result['user_id']
        
        # Query applications that haven't been updated in days_threshold days
        # Exclude rejected and accepted statuses since they're terminal
        sql = """
            SELECT 
                a.application_id,
                a.status,
                a.applied_date,
                a.notes,
                a.created_at,
                a.updated_at,
                CURRENT_DATE - DATE(a.updated_at) as days_stale,
                jp.job_id,
                jp.external_id,
                jp.title,
                jp.company,
                jp.location,
                jp.salary_min,
                jp.salary_max,
                jp.url,
                jp.description
            FROM applications a
            JOIN job_postings jp ON a.job_id = jp.job_id
            WHERE a.user_id = %s 
                AND a.status NOT IN ('rejected', 'accepted')
                AND a.updated_at < (CURRENT_TIMESTAMP - INTERVAL '%s days')
            ORDER BY a.updated_at ASC
        """
        
        cur.execute(sql, (user_id, days_threshold))
        results = cur.fetchall()
        
        return [dict(row) for row in results]
    
    except Exception as e:
        print(f"Error getting stale applications: {e}")
        return []
    finally:
        cur.close()
