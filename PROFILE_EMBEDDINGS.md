# Profile Embeddings - AI Job Hunting Copilot

## Overview

This module generates vector embeddings for user profiles (resume text) to enable personalized job matching and recommendations using semantic similarity search.

## Architecture

```
User Profile (resume text) 
    ↓
[sentence-transformers/all-MiniLM-L6-v2]
    ↓
384-dimensional embedding vector
    ↓
Stored in profile_embeddings table
    ↓
Vector similarity search (pgvector)
    ↓
Matches to job_embeddings → Personalized job recommendations
```

## Components

### 1. Database Schema
**File:** `sql/create_profile_embeddings_table.sql`

Creates the `profile_embeddings` table:
- `profile_id` - Foreign key to profiles table
- `user_id` - Quick user lookup
- `resume_text` - Snapshot of resume at embedding time
- `embedding` - 384-dim vector (pgvector type)
- `model_name` - Embedding model used
- `embedded_at` - Timestamp

**Indexes:**
- IVFFlat index for fast vector similarity search
- B-tree indexes on profile_id, user_id, embedded_at

### 2. Ingestion Notebook
**File:** `dashboard/notebooks/ingest_profile_embeddings`

**What it does:**
1. Reads profiles from `profiles` table (only those with `resume_text`)
2. Computes embeddings using `sentence-transformers/all-MiniLM-L6-v2` (same as jobs)
3. Writes to `profile_embeddings` table
4. Tests profile-to-job matching

**Key features:**
- ✅ Incremental processing (only NEW profiles without embeddings)
- ✅ Batch processing for efficiency
- ✅ Reprocess all mode (`process_all=true` widget)
- ✅ Compatible with job embeddings (same model, same dimension)

### 3. Flask Integration
**File:** `dashboard/app.py`

**(TODO - Not yet implemented)**
- Auto-generate embeddings when user uploads CV
- Regenerate when resume_text changes
- Personalized job recommendations endpoint

## Setup Instructions

### Step 1: Create the Table

Connect to your Lakebase Postgres database and run:

```bash
psql -h <your-lakebase-host> -U <user> -d <database> -f sql/create_profile_embeddings_table.sql
```

Or manually execute the SQL:
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS profile_embeddings (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    resume_text TEXT,
    embedding vector(384),
    model_name TEXT DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
    embedded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_profile FOREIGN KEY (profile_id) 
        REFERENCES profiles(profile_id) ON DELETE CASCADE
);

CREATE INDEX idx_profile_embeddings_vector 
    ON profile_embeddings 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100);
```

### Step 2: Run the Ingestion Notebook

Open and run the notebook:
```
dashboard/notebooks/ingest_profile_embeddings
```

**First run (process all existing profiles):**
- Set widget `process_all = true`
- Click "Run All"

**Subsequent runs (incremental):**
- Set widget `process_all = false` (default)
- Only processes NEW profiles without embeddings

### Step 3: Verify Embeddings

```sql
-- Check how many profiles have embeddings
SELECT COUNT(*) FROM profile_embeddings;

-- Sample profile-to-job matching
SELECT 
    j.title,
    j.company,
    j.location,
    1 - (j.embedding <=> p.embedding) AS similarity_score
FROM profile_embeddings p
CROSS JOIN job_embeddings j
WHERE p.profile_id = <your_profile_id>
ORDER BY p.embedding <=> j.embedding
LIMIT 10;
```

## Usage Examples

### 1. Personalized Job Recommendations

**Query:** "Show me the top 10 jobs that match my profile"

```python
# Flask endpoint (to be implemented)
@app.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    user_id = get_current_user_id()
    
    # Get user's profile embedding
    profile = lakebase.run_query(
        "SELECT embedding FROM profile_embeddings WHERE user_id = %s",
        (user_id,)
    )
    
    if not profile:
        return jsonify({'error': 'Profile not found'}), 404
    
    profile_embedding = profile[0]['embedding']
    
    # Find similar jobs
    jobs = lakebase.run_query(
        """
        SELECT 
            j.title,
            j.company,
            j.location,
            p.salary_min,
            p.salary_max,
            p.url,
            1 - (j.embedding <=> %s::vector) AS match_score
        FROM job_embeddings j
        JOIN job_postings p ON j.job_id = p.job_id
        WHERE p.is_active = TRUE
        ORDER BY j.embedding <=> %s::vector
        LIMIT 10
        """,
        (profile_embedding, profile_embedding)
    )
    
    return jsonify({'jobs': jobs})
```

### 2. Hybrid Search (Query + Profile)

**Query:** "Find Python backend jobs that also match my profile"

```python
# Combine semantic search query with profile matching
# 1. Generate embedding for search query
query_embedding = model.encode(["Python backend developer"])[0]

# 2. Weight: 70% search query, 30% profile match
results = lakebase.run_query(
    """
    SELECT 
        j.title,
        j.company,
        j.location,
        (0.7 * (1 - (j.embedding <=> %s::vector))) +
        (0.3 * (1 - (j.embedding <=> %s::vector))) AS combined_score
    FROM job_embeddings j
    JOIN job_postings p ON j.job_id = p.job_id
    WHERE p.is_active = TRUE
    ORDER BY combined_score DESC
    LIMIT 20
    """,
    (query_embedding.tolist(), profile_embedding)
)
```

### 3. Auto-Generate on Profile Update

**When user updates resume in Flask:**

```python
@app.route('/profile/save', methods=['POST'])
def save_profile():
    # ... existing save logic ...
    
    # Generate embedding if resume text changed
    if resume_text and (not existing_profile or existing_profile['resume_text'] != resume_text):
        # Compute embedding
        embedding = embedding_model.encode([resume_text])[0]
        
        # Upsert to profile_embeddings
        lakebase.run_write(
            """
            INSERT INTO profile_embeddings (
                profile_id, user_id, resume_text, embedding, model_name
            ) VALUES (%s, %s, %s, %s::double precision[], %s)
            ON CONFLICT (profile_id) DO UPDATE SET
                resume_text = EXCLUDED.resume_text,
                embedding = EXCLUDED.embedding::vector,
                embedded_at = CURRENT_TIMESTAMP
            """,
            (profile_id, user_id, resume_text, 
             '{' + ','.join(str(float(x)) for x in embedding) + '}',
             'sentence-transformers/all-MiniLM-L6-v2')
        )
```

## Scheduling

### Option 1: Databricks Job (Recommended)

Schedule the notebook to run daily/hourly to process new profiles:

```yaml
# databricks.yml
resources:
  jobs:
    profile_embeddings_daily:
      name: "Profile Embeddings - Daily Sync"
      tasks:
        - task_key: ingest_profile_embeddings
          notebook_task:
            notebook_path: dashboard/notebooks/ingest_profile_embeddings
            base_parameters:
              process_all: "false"  # Incremental only
          new_cluster:
            spark_version: "14.3.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 0  # Single-node
      schedule:
        quartz_cron_expression: "0 0 2 * * ?"  # 2 AM daily
        timezone_id: "America/Los_Angeles"
```

### Option 2: Real-time (Flask)

Generate embeddings immediately when user uploads CV - see example above.

## Performance Considerations

### Batch Size
- Default: 32 profiles per batch
- Adjust based on cluster memory

### Index Tuning
- IVFFlat `lists` parameter: Default 100
- Increase for larger datasets (e.g., 1000 lists for 10K+ profiles)
- Trade-off: higher lists = faster search, slower index build

### Model Caching
- Model is loaded once per notebook run
- Cached in `/tmp/.cache/huggingface`

## Troubleshooting

### Issue: No profiles to process
**Cause:** All profiles already have embeddings  
**Solution:** Set `process_all=true` widget to recompute

### Issue: pgvector extension not found
**Cause:** Extension not enabled  
**Solution:** Run `CREATE EXTENSION IF NOT EXISTS vector;`

### Issue: Embeddings don't match jobs
**Cause:** Different embedding models used  
**Solution:** Both tables MUST use `sentence-transformers/all-MiniLM-L6-v2`

### Issue: Out of memory
**Cause:** Too many profiles, batch size too large  
**Solution:** Reduce batch_size in notebook (line ~235)

## Future Enhancements

1. **Skills extraction** - Generate separate embeddings for skills section
2. **Weighted embeddings** - Different weights for title, experience, skills
3. **Multi-vector** - Store multiple embeddings per profile (experience, education, skills)
4. **LLM augmentation** - Use LLM to enhance resume text before embedding
5. **Feedback loop** - Update embeddings based on which jobs users apply to
6. **Real-time updates** - Auto-regenerate on profile save in Flask

## Related Files

- `sql/create_tables.sql` - Main schema (includes profiles table)
- `sql/create_job_embeddings_table.sql` - Job embeddings schema
- `dashboard/notebooks/ingest_job_embeddings` - Job embeddings notebook
- `dashboard/app.py` - Flask application
- `EMBEDDINGS_NOTEBOOK.md` - Job embeddings documentation

## Questions?

Check:
1. Database connection in `lakebase.py`
2. Notebook execution logs
3. pgvector extension status: `SELECT * FROM pg_extension WHERE extname = 'vector';`