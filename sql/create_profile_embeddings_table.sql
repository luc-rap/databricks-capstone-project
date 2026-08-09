-- Profile Embeddings Table for AI Job Hunting Copilot
-- Stores vector embeddings of resume chunks for detailed job matching

-- Enable pgvector extension (run once per database)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create profile_embeddings table
CREATE TABLE IF NOT EXISTS profile_embeddings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(384),  -- 384 dimensions for sentence-transformers/all-MiniLM-L6-v2
    model_name TEXT DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
    embedded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key to profiles table
    CONSTRAINT fk_profile 
        FOREIGN KEY (user_id) 
        REFERENCES profiles(user_id) 
        ON DELETE CASCADE,
    
    -- Unique constraint: one embedding per user + chunk_index combination
    CONSTRAINT unique_user_chunk UNIQUE (user_id, chunk_index)
);

-- Create index for fast vector similarity search (IVFFlat)
-- This is the recommended index for pgvector with cosine distance
CREATE INDEX IF NOT EXISTS idx_profile_embeddings_vector 
    ON profile_embeddings 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100);

-- Alternative: HNSW index (better for high-dimensional data, requires pgvector 0.5.0+)
-- CREATE INDEX IF NOT EXISTS idx_profile_embeddings_vector_hnsw 
--     ON profile_embeddings 
--     USING hnsw (embedding vector_cosine_ops);

-- Create index on user_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_profile_embeddings_user_id 
    ON profile_embeddings(user_id);

-- Create index on chunk_index for ordered retrieval
CREATE INDEX IF NOT EXISTS idx_profile_embeddings_chunk_index 
    ON profile_embeddings(chunk_index);

-- Create index on embedded_at for time-based queries
CREATE INDEX IF NOT EXISTS idx_profile_embeddings_embedded_at 
    ON profile_embeddings(embedded_at DESC);

COMMENT ON TABLE profile_embeddings IS 'Vector embeddings for profile resume chunks using sentence-transformers/all-MiniLM-L6-v2 (384 dimensions). Stores individual chunk embeddings for detailed section-by-section job matching.';
COMMENT ON COLUMN profile_embeddings.user_id IS 'Foreign key to profiles table';
COMMENT ON COLUMN profile_embeddings.chunk_index IS 'Sequential chunk number (0-based) for this resume';
COMMENT ON COLUMN profile_embeddings.chunk_text IS 'Text content of this resume chunk (500 chars with 100 overlap)';
COMMENT ON COLUMN profile_embeddings.embedding IS '384-dimensional vector embedding of this chunk';
COMMENT ON COLUMN profile_embeddings.model_name IS 'Name of the embedding model used';
COMMENT ON COLUMN profile_embeddings.embedded_at IS 'Timestamp when the embedding was computed';