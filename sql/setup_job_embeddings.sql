-- ==============================================================================
-- COMPLETE SETUP: Job Embeddings for AI Job Hunting Copilot
-- ==============================================================================
-- This script sets up both the job_postings and job_embeddings tables
-- for storing job data and their vector embeddings for semantic search.
--
-- Run this in your Lakebase Postgres database.
-- ==============================================================================

-- Enable pgvector extension (required for vector similarity search)
CREATE EXTENSION IF NOT EXISTS vector;

-- ==============================================================================
-- TABLE 1: job_postings (raw job data from Adzuna API)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS job_postings (
    job_id SERIAL PRIMARY KEY,
    external_id TEXT UNIQUE NOT NULL,  -- Adzuna job ID
    title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    description TEXT,
    url TEXT,  -- redirect_url from Adzuna
    salary_min NUMERIC(12, 2),
    salary_max NUMERIC(12, 2),
    contract_type TEXT,  -- e.g., 'full_time', 'part_time', 'contract'
    category TEXT,  -- Job category from Adzuna
    posted_date TIMESTAMP,  -- When the job was originally posted
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- When we fetched it
    is_active BOOLEAN DEFAULT TRUE,  -- Whether the job is still active
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for job_postings
CREATE INDEX IF NOT EXISTS idx_job_postings_external_id ON job_postings(external_id);
CREATE INDEX IF NOT EXISTS idx_job_postings_is_active ON job_postings(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_job_postings_company ON job_postings(company);
CREATE INDEX IF NOT EXISTS idx_job_postings_location ON job_postings(location);
CREATE INDEX IF NOT EXISTS idx_job_postings_category ON job_postings(category);
CREATE INDEX IF NOT EXISTS idx_job_postings_posted_date ON job_postings(posted_date DESC);
CREATE INDEX IF NOT EXISTS idx_job_postings_fetched_at ON job_postings(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_postings_search ON job_postings USING gin(to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '')));

-- Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_job_postings_updated_at()
RETURNS TRIGGER AS $
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_job_postings_updated_at
    BEFORE UPDATE ON job_postings
    FOR EACH ROW
    EXECUTE FUNCTION update_job_postings_updated_at();

-- ==============================================================================
-- TABLE 2: job_embeddings (vector embeddings for semantic search)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS job_embeddings (
    id SERIAL PRIMARY KEY,
    job_id INTEGER UNIQUE NOT NULL,
    external_id TEXT,
    title TEXT,
    company TEXT,
    location TEXT,
    embedding vector(384),  -- 384 dimensions for sentence-transformers/all-MiniLM-L6-v2
    model_name TEXT DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
    embedded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key to job_postings table
    CONSTRAINT fk_job_posting 
        FOREIGN KEY (job_id) 
        REFERENCES job_postings(job_id) 
        ON DELETE CASCADE
);

-- Vector similarity search index (IVFFlat - fast for cosine distance)
CREATE INDEX IF NOT EXISTS idx_job_embeddings_vector 
    ON job_embeddings 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100);

-- Standard indexes for lookups
CREATE INDEX IF NOT EXISTS idx_job_embeddings_job_id ON job_embeddings(job_id);
CREATE INDEX IF NOT EXISTS idx_job_embeddings_external_id ON job_embeddings(external_id);
CREATE INDEX IF NOT EXISTS idx_job_embeddings_embedded_at ON job_embeddings(embedded_at DESC);

-- ==============================================================================
-- EXAMPLE QUERIES
-- ==============================================================================

-- 1. Check table setup
-- SELECT COUNT(*) FROM job_postings;
-- SELECT COUNT(*) FROM job_embeddings;

-- 2. View recent job postings
-- SELECT job_id, title, company, location, posted_date 
-- FROM job_postings 
-- WHERE is_active = TRUE 
-- ORDER BY posted_date DESC 
-- LIMIT 10;

-- 3. Find similar jobs using vector similarity (cosine distance)
-- Replace [your_embedding_vector] with actual 384-dim vector
/*
SELECT 
    e.title,
    e.company,
    e.location,
    p.salary_min,
    p.salary_max,
    p.url,
    1 - (e.embedding <=> '[your_embedding_vector]'::vector) AS similarity_score
FROM job_embeddings e
JOIN job_postings p ON e.job_id = p.job_id
WHERE p.is_active = TRUE
ORDER BY e.embedding <=> '[your_embedding_vector]'::vector
LIMIT 20;
*/

-- 4. Find jobs similar to a specific job (by job_id)
/*
WITH reference_job AS (
    SELECT embedding 
    FROM job_embeddings 
    WHERE job_id = 1  -- Replace with actual job_id
)
SELECT 
    e.title,
    e.company,
    e.location,
    1 - (e.embedding <=> (SELECT embedding FROM reference_job)) AS similarity
FROM job_embeddings e
JOIN job_postings p ON e.job_id = p.job_id
WHERE p.is_active = TRUE
  AND e.job_id != 1  -- Exclude the reference job itself
ORDER BY e.embedding <=> (SELECT embedding FROM reference_job)
LIMIT 10;
*/

-- 5. Filter by location AND similarity
/*
SELECT 
    e.title,
    e.company,
    e.location,
    p.salary_max,
    1 - (e.embedding <=> '[your_embedding_vector]'::vector) AS match_score
FROM job_embeddings e
JOIN job_postings p ON e.job_id = p.job_id
WHERE p.is_active = TRUE
  AND (e.location ILIKE '%San Francisco%' OR e.location ILIKE '%Remote%')
ORDER BY e.embedding <=> '[your_embedding_vector]'::vector
LIMIT 20;
*/

-- 6. Get embedding statistics
/*
SELECT 
    COUNT(*) as total_embeddings,
    COUNT(DISTINCT model_name) as unique_models,
    MIN(embedded_at) as oldest_embedding,
    MAX(embedded_at) as newest_embedding
FROM job_embeddings;
*/

-- ==============================================================================
-- MAINTENANCE QUERIES
-- ==============================================================================

-- Delete old job postings (older than 30 days)
-- DELETE FROM job_postings WHERE fetched_at < NOW() - INTERVAL '30 days';

-- Mark inactive jobs (not fetched in 7 days)
-- UPDATE job_postings SET is_active = FALSE WHERE fetched_at < NOW() - INTERVAL '7 days';

-- Rebuild vector index (if needed after bulk inserts)
-- REINDEX INDEX idx_job_embeddings_vector;

-- ==============================================================================
-- NOTES
-- ==============================================================================
-- 1. The embedding dimension (384) matches sentence-transformers/all-MiniLM-L6-v2
-- 2. Cosine distance (<=> operator) is used for similarity (0 = identical, 2 = opposite)
-- 3. IVFFlat index trades accuracy for speed (good for >10K vectors)
-- 4. For <10K vectors, consider HNSW index (requires pgvector 0.5.0+):
--    CREATE INDEX ... USING hnsw (embedding vector_cosine_ops);
-- 5. Run ANALYZE after bulk inserts to update query planner statistics:
--    ANALYZE job_postings; ANALYZE job_embeddings;

-- ==============================================================================
-- READY! Run the ingest_job_embeddings notebook to populate these tables.
-- ==============================================================================