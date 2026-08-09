-- Job Embeddings Table for AI Job Hunting Copilot
-- Stores vector embeddings of job postings for semantic search

-- Enable pgvector extension (run once per database)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create job_embeddings table
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

-- Create index for fast vector similarity search (IVFFlat)
-- This is the recommended index for pgvector with cosine distance
CREATE INDEX IF NOT EXISTS idx_job_embeddings_vector 
    ON job_embeddings 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100);

-- Alternative: HNSW index (better for high-dimensional data, requires pgvector 0.5.0+)
-- CREATE INDEX IF NOT EXISTS idx_job_embeddings_vector_hnsw 
--     ON job_embeddings 
--     USING hnsw (embedding vector_cosine_ops);

-- Create index on job_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_job_embeddings_job_id 
    ON job_embeddings(job_id);

-- Create index on external_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_job_embeddings_external_id 
    ON job_embeddings(external_id);

-- Create index on embedded_at for time-based queries
CREATE INDEX IF NOT EXISTS idx_job_embeddings_embedded_at 
    ON job_embeddings(embedded_at DESC);

COMMENT ON TABLE job_embeddings IS 'Vector embeddings for job postings using sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)';
COMMENT ON COLUMN job_embeddings.job_id IS 'Foreign key to job_postings table';
COMMENT ON COLUMN job_embeddings.embedding IS '384-dimensional vector embedding of job title + description';
COMMENT ON COLUMN job_embeddings.model_name IS 'Name of the embedding model used';
COMMENT ON COLUMN job_embeddings.embedded_at IS 'Timestamp when the embedding was computed';