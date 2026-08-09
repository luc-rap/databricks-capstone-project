# SQL Schema for Job Embeddings

## 📁 Files Created

| File | Purpose |
|------|---------|
| **setup_job_embeddings.sql** | 🎯 **START HERE** - Complete setup with both tables |
| create_job_postings_table.sql | Raw job data table schema |
| create_job_embeddings_table.sql | Vector embeddings table schema |

## 🚀 Quick Start

### 1. Run the Complete Setup

Connect to your Lakebase Postgres database and run:

```bash
psql $LAKEBASE_URL -f setup_job_embeddings.sql
```

This creates:
* ✅ `job_postings` table (raw job data)
* ✅ `job_embeddings` table (384-dim vectors)
* ✅ All indexes and triggers
* ✅ pgvector extension

### 2. Verify Setup

```sql
-- Check tables were created
\dt job_*

-- Check pgvector extension
\dx vector

-- Count rows (should be 0 initially)
SELECT COUNT(*) FROM job_postings;
SELECT COUNT(*) FROM job_embeddings;
```

## 📊 Table Schemas

### `job_postings` (Raw Job Data)

Stores job postings fetched from Adzuna API.

```sql
CREATE TABLE job_postings (
    job_id SERIAL PRIMARY KEY,
    external_id TEXT UNIQUE NOT NULL,  -- Adzuna job ID
    title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    description TEXT,
    url TEXT,
    salary_min NUMERIC(12, 2),
    salary_max NUMERIC(12, 2),
    contract_type TEXT,
    category TEXT,
    posted_date TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Key Features:**
* Unique constraint on `external_id` (prevents duplicates)
* Soft deletes via `is_active` flag
* Auto-updating `updated_at` timestamp
* Full-text search index on title + description
* Indexes on common query fields (company, location, category)

### `job_embeddings` (Vector Embeddings)

Stores 384-dimensional embeddings for semantic search.

```sql
CREATE TABLE job_embeddings (
    id SERIAL PRIMARY KEY,
    job_id INTEGER UNIQUE NOT NULL,  -- FK to job_postings
    external_id TEXT,
    title TEXT,
    company TEXT,
    location TEXT,
    embedding vector(384),  -- all-MiniLM-L6-v2
    model_name TEXT DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
    embedded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES job_postings(job_id) ON DELETE CASCADE
);
```

**Key Features:**
* IVFFlat index for fast cosine similarity search
* Foreign key cascade deletes (deleting job also deletes embedding)
* Tracks model name and embedding timestamp
* 384 dimensions (matches all-MiniLM-L6-v2 output)

## 🔍 Example Queries

### Find Similar Jobs (Semantic Search)

```sql
-- Given a user's profile embedding, find matching jobs
SELECT 
    e.title,
    e.company,
    e.location,
    p.salary_min,
    p.salary_max,
    p.url,
    1 - (e.embedding <=> '[0.1,0.2,0.3,...]'::vector) AS similarity_score
FROM job_embeddings e
JOIN job_postings p ON e.job_id = p.job_id
WHERE p.is_active = TRUE
ORDER BY e.embedding <=> '[0.1,0.2,0.3,...]'::vector
LIMIT 20;
```

**Note:** The `<=>` operator computes **cosine distance** (0 = identical, 2 = opposite).
To get similarity score (0-1), use: `1 - (embedding <=> query_vector)`

### Find Jobs Similar to Another Job

```sql
-- Find jobs similar to job_id = 42
WITH reference_job AS (
    SELECT embedding FROM job_embeddings WHERE job_id = 42
)
SELECT 
    e.title,
    e.company,
    e.location,
    1 - (e.embedding <=> (SELECT embedding FROM reference_job)) AS similarity
FROM job_embeddings e
JOIN job_postings p ON e.job_id = p.job_id
WHERE p.is_active = TRUE
  AND e.job_id != 42
ORDER BY e.embedding <=> (SELECT embedding FROM reference_job)
LIMIT 10;
```

### Filter by Location + Semantic Match

```sql
-- Remote jobs matching user profile
SELECT 
    e.title,
    e.company,
    e.location,
    p.salary_max,
    1 - (e.embedding <=> '[...]'::vector) AS match_score
FROM job_embeddings e
JOIN job_postings p ON e.job_id = p.job_id
WHERE p.is_active = TRUE
  AND (e.location ILIKE '%Remote%' OR e.location ILIKE '%San Francisco%')
  AND p.salary_min >= 100000
ORDER BY e.embedding <=> '[...]'::vector
LIMIT 20;
```

### Get Embedding Statistics

```sql
SELECT 
    COUNT(*) as total_embeddings,
    COUNT(DISTINCT model_name) as unique_models,
    MIN(embedded_at) as oldest_embedding,
    MAX(embedded_at) as newest_embedding,
    COUNT(DISTINCT e.company) as unique_companies
FROM job_embeddings e;
```

## 🔧 Maintenance

### Clean Up Old Jobs

```sql
-- Delete jobs older than 30 days
DELETE FROM job_postings 
WHERE fetched_at < NOW() - INTERVAL '30 days';

-- Mark stale jobs as inactive
UPDATE job_postings 
SET is_active = FALSE 
WHERE fetched_at < NOW() - INTERVAL '7 days';
```

### Rebuild Vector Index

After bulk inserts (1000+ rows), rebuild the index:

```sql
REINDEX INDEX idx_job_embeddings_vector;
ANALYZE job_embeddings;
```

### Check Index Health

```sql
-- Check index size
SELECT 
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE tablename IN ('job_postings', 'job_embeddings')
ORDER BY pg_relation_size(indexrelid) DESC;
```

## 🎯 Integration with Notebook

Your [ingest_job_embeddings](#notebook-1196080723430297) notebook will:

1. **Fetch jobs** from Adzuna API → `job_postings` table
2. **Read jobs** via Spark JDBC
3. **Compute embeddings** with pandas UDF (distributed)
4. **Write embeddings** to `job_embeddings` table

The notebook handles:
* ✅ ON CONFLICT upserts (deduplication)
* ✅ Batch inserts (100 rows at a time)
* ✅ Array → vector casting
* ✅ Distributed embedding computation

## 📚 pgvector Reference

### Distance Operators

| Operator | Distance Type | Range | Best For |
|----------|--------------|-------|----------|
| `<=>` | Cosine | 0-2 | Text embeddings (our use case) |
| `<->` | L2 (Euclidean) | 0-∞ | Spatial data |
| `<#>` | Inner product | -∞ to ∞ | Normalized vectors |

**We use cosine (`<=>`) because:**
* sentence-transformers embeddings are normalized
* Robust to vector magnitude differences
* Standard for semantic similarity

### Index Types

| Index | Speed | Accuracy | Build Time | Memory |
|-------|-------|----------|-----------|---------|
| **IVFFlat** | Fast | ~95% | Fast | Low |
| HNSW | Very Fast | ~99% | Slow | High |

**We use IVFFlat because:**
* Good accuracy for 10K-1M vectors
* Fast build time (important for frequent updates)
* Lower memory footprint

## ✅ Next Steps

1. ✅ Tables created
2. ▶️ Run [ingest_job_embeddings notebook](#notebook-1196080723430297)
3. ▶️ Verify embeddings: `SELECT COUNT(*) FROM job_embeddings;`
4. ▶️ Test semantic search with example queries above
5. ▶️ Integrate with Flask app for user recommendations

## 🔗 Related Files

* [ingest_job_embeddings notebook](#notebook-1196080723430297)
* [Flask app](#file-1983587163160146)
* [FLASK_MIGRATION.md](#file-1196080723430295)

---

**Ready to populate the tables!** Run the notebook to fetch jobs and generate embeddings. 🚀
