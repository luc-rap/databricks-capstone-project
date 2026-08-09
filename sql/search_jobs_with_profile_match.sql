-- Job Search with Profile Match Scores
-- Use these queries in your search page backend to show job matches for logged-in users

-- =============================================================================
-- QUERY 1: Basic Job Search with Match Score
-- Returns all active jobs with match score for a given user
-- Match score = MAX similarity across all resume chunks (best matching section)
-- =============================================================================

-- Replace $1 with the user_id parameter in your backend
SELECT 
    jp.job_id,
    jp.title,
    jp.company,
    jp.location,
    jp.job_type,
    jp.salary_min,
    jp.salary_max,
    jp.is_remote,
    jp.description,
    jp.requirements,
    jp.posted_at,
    jp.url,
    MAX(1 - (pe.embedding <=> je.embedding)) AS match_score
FROM job_postings jp
JOIN job_embeddings je ON jp.job_id = je.job_id
CROSS JOIN profile_embeddings pe
WHERE jp.is_active = TRUE
  AND pe.user_id = $1  -- User ID parameter
GROUP BY 
    jp.job_id, jp.title, jp.company, jp.location, jp.job_type,
    jp.salary_min, jp.salary_max, jp.is_remote, jp.description,
    jp.requirements, jp.posted_at, jp.url
ORDER BY match_score DESC
LIMIT 50;


-- =============================================================================
-- QUERY 2: Job Search with Filters + Match Score
-- Add location, remote, salary, and keyword filters
-- =============================================================================

SELECT 
    jp.job_id,
    jp.title,
    jp.company,
    jp.location,
    jp.job_type,
    jp.salary_min,
    jp.salary_max,
    jp.is_remote,
    jp.posted_at,
    jp.url,
    MAX(1 - (pe.embedding <=> je.embedding)) AS match_score
FROM job_postings jp
JOIN job_embeddings je ON jp.job_id = je.job_id
CROSS JOIN profile_embeddings pe
WHERE jp.is_active = TRUE
  AND pe.user_id = $1  -- User ID
  -- Optional filters (set to NULL in backend if not used)
  AND (jp.location ILIKE $2 OR $2 IS NULL)  -- e.g., '%San Francisco%'
  AND (jp.is_remote = $3 OR $3 IS NULL)  -- TRUE/FALSE
  AND (jp.salary_max >= $4 OR $4 IS NULL)  -- Minimum salary requirement
  AND (
    LOWER(jp.title) LIKE LOWER($5) OR 
    LOWER(jp.description) LIKE LOWER($5) OR 
    LOWER(jp.requirements) LIKE LOWER($5) OR 
    $5 IS NULL
  )  -- Keyword search (e.g., '%python%')
GROUP BY 
    jp.job_id, jp.title, jp.company, jp.location, jp.job_type,
    jp.salary_min, jp.salary_max, jp.is_remote, jp.posted_at, jp.url
HAVING MAX(1 - (pe.embedding <=> je.embedding)) >= 0.5  -- Only show jobs with >50% match
ORDER BY match_score DESC
LIMIT 50;


-- =============================================================================
-- QUERY 3: Job Search with Pagination
-- Add OFFSET for pagination support
-- =============================================================================

SELECT 
    jp.job_id,
    jp.title,
    jp.company,
    jp.location,
    jp.job_type,
    jp.salary_min,
    jp.salary_max,
    jp.is_remote,
    jp.posted_at,
    MAX(1 - (pe.embedding <=> je.embedding)) AS match_score
FROM job_postings jp
JOIN job_embeddings je ON jp.job_id = je.job_id
CROSS JOIN profile_embeddings pe
WHERE jp.is_active = TRUE
  AND pe.user_id = $1
GROUP BY 
    jp.job_id, jp.title, jp.company, jp.location, jp.job_type,
    jp.salary_min, jp.salary_max, jp.is_remote, jp.posted_at
ORDER BY match_score DESC
LIMIT $2  -- Page size (e.g., 20)
OFFSET $3;  -- (page_number - 1) * page_size


-- =============================================================================
-- QUERY 4: Job Details with Best Matching Resume Section
-- Show which part of the resume matched this job best
-- Use this for the job detail page to explain WHY it's a good match
-- =============================================================================

WITH chunk_matches AS (
    SELECT 
        pe.chunk_index,
        pe.chunk_text,
        1 - (pe.embedding <=> je.embedding) AS similarity
    FROM profile_embeddings pe
    CROSS JOIN job_embeddings je
    WHERE pe.user_id = $1  -- User ID
      AND je.job_id = $2   -- Job ID
    ORDER BY similarity DESC
    LIMIT 3  -- Top 3 matching chunks
)
SELECT 
    jp.job_id,
    jp.title,
    jp.company,
    jp.location,
    jp.description,
    jp.requirements,
    jp.salary_min,
    jp.salary_max,
    jp.is_remote,
    cm.chunk_index,
    cm.chunk_text AS matching_resume_section,
    cm.similarity AS section_match_score
FROM job_postings jp
JOIN job_embeddings je ON jp.job_id = je.job_id
CROSS JOIN chunk_matches cm
WHERE jp.job_id = $2
ORDER BY cm.similarity DESC;


-- =============================================================================
-- QUERY 5: Match Score Distribution (Analytics)
-- Show how many jobs fall into each match score bucket
-- Useful for UI insights like "You're a strong match for 12 jobs!"
-- =============================================================================

WITH match_scores AS (
    SELECT 
        jp.job_id,
        MAX(1 - (pe.embedding <=> je.embedding)) AS match_score
    FROM job_postings jp
    JOIN job_embeddings je ON jp.job_id = je.job_id
    CROSS JOIN profile_embeddings pe
    WHERE jp.is_active = TRUE
      AND pe.user_id = $1
    GROUP BY jp.job_id
)
SELECT 
    CASE 
        WHEN match_score >= 0.8 THEN 'Excellent Match (80%+)'
        WHEN match_score >= 0.7 THEN 'Strong Match (70-79%)'
        WHEN match_score >= 0.6 THEN 'Good Match (60-69%)'
        WHEN match_score >= 0.5 THEN 'Fair Match (50-59%)'
        ELSE 'Low Match (<50%)'
    END AS match_category,
    COUNT(*) AS job_count
FROM match_scores
GROUP BY match_category
ORDER BY MIN(match_score) DESC;


-- =============================================================================
-- PERFORMANCE NOTES
-- =============================================================================

-- 1. The CROSS JOIN with profile_embeddings can be expensive for users with many chunks
--    Consider adding an index on profile_embeddings(user_id) if not already present
--
-- 2. The vector similarity calculation (<=>) uses the IVFFlat index on job_embeddings
--    Make sure this index exists for fast similarity search
--
-- 3. For very active searches, consider caching match scores in a materialized view
--    that refreshes periodically (e.g., every hour)
--
-- 4. Alternative scoring strategies you can try:
--    - AVG(similarity) instead of MAX for overall fit
--    - AVG of top-3 chunks for "best sections" fit
--    - Weighted average (e.g., weight recent experience chunks higher)

-- =============================================================================
-- EXAMPLE BACKEND USAGE (Python/Flask)
-- =============================================================================

/*
import psycopg2
from flask import request

@app.route('/api/search/jobs')
def search_jobs():
    user_id = request.user.id  # From session
    location = request.args.get('location')
    is_remote = request.args.get('remote')
    min_salary = request.args.get('min_salary')
    keyword = request.args.get('q')
    page = int(request.args.get('page', 1))
    page_size = 20
    
    conn = psycopg2.connect(...)
    cursor = conn.cursor()
    
    cursor.execute('''
        -- Use QUERY 2 from above
        SELECT job_id, title, company, location, ..., match_score
        FROM ...
        WHERE pe.user_id = %s
          AND (jp.location ILIKE %s OR %s IS NULL)
          ...
        ORDER BY match_score DESC
        LIMIT %s OFFSET %s
    ''', (user_id, location, location, is_remote, is_remote, 
          min_salary, min_salary, keyword, keyword, keyword, keyword,
          page_size, (page - 1) * page_size))
    
    jobs = cursor.fetchall()
    return jsonify(jobs)
*/
