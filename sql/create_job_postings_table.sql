-- Job Postings Table for AI Job Hunting Copilot
-- Stores raw job posting data from Adzuna API

-- Create job_postings table
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
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- When we fetched it from Adzuna
    is_active BOOLEAN DEFAULT TRUE,  -- Whether the job is still active
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_job_postings_external_id 
    ON job_postings(external_id);

CREATE INDEX IF NOT EXISTS idx_job_postings_is_active 
    ON job_postings(is_active) 
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_job_postings_company 
    ON job_postings(company);

CREATE INDEX IF NOT EXISTS idx_job_postings_location 
    ON job_postings(location);

CREATE INDEX IF NOT EXISTS idx_job_postings_category 
    ON job_postings(category);

CREATE INDEX IF NOT EXISTS idx_job_postings_posted_date 
    ON job_postings(posted_date DESC);

CREATE INDEX IF NOT EXISTS idx_job_postings_fetched_at 
    ON job_postings(fetched_at DESC);

-- Full-text search index on title and description
CREATE INDEX IF NOT EXISTS idx_job_postings_search 
    ON job_postings 
    USING gin(to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '')));

-- Trigger to update updated_at timestamp
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

COMMENT ON TABLE job_postings IS 'Raw job posting data fetched from Adzuna API';
COMMENT ON COLUMN job_postings.external_id IS 'Unique job ID from Adzuna API';
COMMENT ON COLUMN job_postings.is_active IS 'Whether the job is still active (for soft deletes)';
COMMENT ON COLUMN job_postings.fetched_at IS 'Timestamp when the job was last fetched from Adzuna';
COMMENT ON COLUMN job_postings.posted_date IS 'Original posting date from Adzuna';