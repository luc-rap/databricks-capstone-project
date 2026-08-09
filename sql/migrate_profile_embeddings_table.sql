-- Migration SQL for Profile Embeddings Table
-- Migrates from single-vector-per-profile to chunk-based schema

-- OPTION 1: DROP AND RECREATE (if you don't need to preserve existing data)
-- Safest approach if you're still in development

DROP TABLE IF EXISTS profile_embeddings CASCADE;

CREATE TABLE profile_embeddings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(384),
    model_name TEXT DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
    embedded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_profile 
        FOREIGN KEY (user_id) 
        REFERENCES profiles(user_id) 
        ON DELETE CASCADE,
    
    CONSTRAINT unique_user_chunk UNIQUE (user_id, chunk_index)
);

CREATE INDEX idx_profile_embeddings_vector 
    ON profile_embeddings 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100);

CREATE INDEX idx_profile_embeddings_user_id 
    ON profile_embeddings(user_id);

CREATE INDEX idx_profile_embeddings_chunk_index 
    ON profile_embeddings(chunk_index);

CREATE INDEX idx_profile_embeddings_embedded_at 
    ON profile_embeddings(embedded_at DESC);

COMMENT ON TABLE profile_embeddings IS 'Vector embeddings for profile resume chunks using sentence-transformers/all-MiniLM-L6-v2 (384 dimensions). Stores individual chunk embeddings for detailed section-by-section job matching.';
COMMENT ON COLUMN profile_embeddings.user_id IS 'Foreign key to profiles table';
COMMENT ON COLUMN profile_embeddings.chunk_index IS 'Sequential chunk number (0-based) for this resume';
COMMENT ON COLUMN profile_embeddings.chunk_text IS 'Text content of this resume chunk (500 chars with 100 overlap)';
COMMENT ON COLUMN profile_embeddings.embedding IS '384-dimensional vector embedding of this chunk';


-- OPTION 2: RENAME OLD TABLE AND CREATE NEW (if you want to preserve old data temporarily)
-- Use this if you want to compare old vs new embeddings or have a backup

/*
ALTER TABLE profile_embeddings RENAME TO profile_embeddings_old;

CREATE TABLE profile_embeddings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(384),
    model_name TEXT DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
    embedded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_profile 
        FOREIGN KEY (user_id) 
        REFERENCES profiles(user_id) 
        ON DELETE CASCADE,
    
    CONSTRAINT unique_user_chunk UNIQUE (user_id, chunk_index)
);

-- Create indexes
CREATE INDEX idx_profile_embeddings_vector 
    ON profile_embeddings 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100);

CREATE INDEX idx_profile_embeddings_user_id 
    ON profile_embeddings(user_id);

CREATE INDEX idx_profile_embeddings_chunk_index 
    ON profile_embeddings(chunk_index);

CREATE INDEX idx_profile_embeddings_embedded_at 
    ON profile_embeddings(embedded_at DESC);

-- After verifying the new table works, drop the old one:
-- DROP TABLE profile_embeddings_old CASCADE;
*/


-- VERIFICATION QUERIES (run after migration)

-- Check table structure
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'profile_embeddings'
ORDER BY ordinal_position;

-- Check indexes
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'profile_embeddings';

-- Check row count (should be 0 after fresh creation)
SELECT COUNT(*) FROM profile_embeddings;
