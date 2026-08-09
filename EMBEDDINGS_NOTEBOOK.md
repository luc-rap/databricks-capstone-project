# Job Embeddings Notebook - Complete! 

## ✅ Conversion Complete

Your job embeddings script has been converted from a Python file to a **proper Jupyter notebook** following the same pattern as `ingest_ticker_news_embeddings.ipynb`.

## What Was Created

**New Notebook:** `dashboard/notebooks/ingest_job_embeddings.ipynb`

### Notebook Structure (14 cells)

| Cell # | Type | Title | Purpose |
|--------|------|-------|---------|
| 1 | Markdown | Job Posting Embeddings Ingestion | Overview and use case |
| 2 | Python | Install Dependencies | `pip install sentence-transformers requests psycopg2-binary` |
| 3 | Python | Restart Python | `dbutils.library.restartPython()` |
| 4 | Markdown | Configuration | Explains widget usage |
| 5 | Python | Setup Widgets | Configurable parameters (model, tables, search query) |
| 6 | Markdown | Lakebase Connection | Connection setup explanation |
| 7 | Python | Parse Lakebase URL | Parse JDBC URL and credentials |
| 8 | Markdown | Fetch Jobs from Adzuna | API integration overview |
| 9 | Python | Fetch and Store Jobs | Call Adzuna API, batch insert to Lakebase |
| 10 | Markdown | Load Jobs into Spark | Distributed processing |
| 11 | Python | Read Jobs from Lakebase | Load jobs via JDBC |
| 12 | Markdown | Compute Embeddings | Pandas UDF explanation |
| 13 | Python | Generate Embeddings with Pandas UDF | Distributed embedding generation |
| 14 | Markdown | Write Embeddings | Batch write strategy |
| 15 | Python | Batch Insert Embeddings | psycopg2 batch insert to Lakebase |
| 16 | Markdown | Summary | Next steps and example queries |

## Key Features

### 🎯 Same Model as Ticker News
- **Model:** `sentence-transformers/all-MiniLM-L6-v2`
- **Dimensions:** 384
- **Quality:** Proven model for semantic search
- **Performance:** Fast inference, efficient for batch processing

### 🔧 Configurable via Widgets
```python
dbutils.widgets.text("job_postings_table", "job_postings", ...)
dbutils.widgets.text("job_embeddings_table", "job_embeddings", ...)
dbutils.widgets.text("embedding_model", "sentence-transformers/all-MiniLM-L6-v2", ...)
dbutils.widgets.text("search_query", "data engineer", ...)
dbutils.widgets.text("results_per_page", "50", ...)
```

Override parameters without editing the notebook - perfect for scheduled jobs!

### ⚡ Distributed Processing
```python
def embed_partitions(iterator: Iterator[pd.DataFrame]) -> Iterator[pd.DataFrame]:
    """Load model once per partition, then embed all rows in that partition."""
    model = SentenceTransformer(EMBEDDING_MODEL_NAME, ...)
    for batch in iterator:
        vectors = model.encode(batch["embedding_text"].tolist())
        yield pd.DataFrame({...})

embeddings_df = jobs_df.mapInPandas(embed_partitions, schema=embeddings_schema)
```

Scales automatically across your cluster!

### 💾 Efficient Batch Writes
```python
# PostgreSQL array format: {val1,val2,...}
insert_data = [(
    row.job_id,
    row.title,
    '{' + ','.join(str(float(x)) for x in row.embedding) + '}',
    ...
) for row in embeddings_rows]

# Batch insert with ON CONFLICT for upserts
execute_values(cursor, insert_sql, insert_data, template=template, page_size=100)
```

## How It Works

### 1. **Fetch Jobs from Adzuna**
```
Adzuna API → job_postings table (Lakebase)
- external_id, title, company, location, description
- salary_min/max, contract_type, category
- ON CONFLICT DO UPDATE for deduplication
```

### 2. **Load into Spark**
```
Lakebase → Spark DataFrame (via JDBC)
- Distributed across cluster
- Concatenate title + description for embedding text
- Filter out empty descriptions
```

### 3. **Compute Embeddings**
```
Spark DataFrame → mapInPandas UDF → Embeddings DataFrame
- Load model once per partition (not per row!)
- Encode in batches for efficiency
- Returns 384-dim vector per job
```

### 4. **Write to Lakebase**
```
Embeddings DataFrame → Lakebase job_embeddings table
- Batch insert via psycopg2
- Format as PostgreSQL arrays
- Cast to pgvector type
```

## Database Schema

### Required Tables

#### `job_postings` (raw job data)
```sql
CREATE TABLE job_postings (
    job_id SERIAL PRIMARY KEY,
    external_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    description TEXT,
    url TEXT,
    salary_min NUMERIC,
    salary_max NUMERIC,
    contract_type TEXT,
    category TEXT,
    posted_date TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
```

#### `job_embeddings` (vector embeddings)
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE job_embeddings (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES job_postings(job_id) UNIQUE,
    external_id TEXT,
    title TEXT,
    company TEXT,
    location TEXT,
    embedding vector(384),  -- all-MiniLM-L6-v2 dimension
    model_name TEXT,
    embedded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for similarity search
CREATE INDEX ON job_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

## Running the Notebook

### Manual Run
1. Open the notebook in Databricks
2. Attach to a cluster (serverless or all-purpose)
3. Run all cells sequentially
4. Check the output - it will show:
   - ✅ Jobs fetched
   - ✅ Jobs inserted/updated
   - ✅ Embeddings computed
   - ✅ Embeddings written

### Scheduled Run (TODO)
Create a Databricks Job:
```yaml
# resources/ingest_job_embeddings_job.yml
resources:
  jobs:
    ingest_job_embeddings:
      name: "Ingest Job Embeddings"
      tasks:
        - task_key: ingest_embeddings
          notebook_task:
            notebook_path: ../dashboard/notebooks/ingest_job_embeddings
          new_cluster:
            spark_version: "15.4.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 2
      schedule:
        quartz_cron_expression: "0 0 2 * * ?"  # Daily at 2 AM
        timezone_id: "America/Los_Angeles"
```

Deploy with:
```bash
databricks bundle deploy -t dev
```

## Using the Embeddings

### Semantic Job Search
```python
# In your Flask app or another notebook:
from openai import OpenAI

# Generate embedding for user query
client = OpenAI(
    api_key=os.environ.get("DATABRICKS_TOKEN"),
    base_url=f"{os.environ.get('DATABRICKS_HOST')}/serving-endpoints"
)

query = "senior data engineer with python and spark"
response = client.embeddings.create(
    input=query,
    model="databricks-bge-large-en"  # or use sentence-transformers locally
)
query_embedding = response.data[0].embedding

# Find similar jobs in Lakebase
conn = psycopg2.connect(lakebase_url)
cursor = conn.cursor()

cursor.execute("""
    SELECT 
        title, company, location,
        1 - (embedding <=> %s::vector) AS similarity
    FROM job_embeddings
    ORDER BY embedding <=> %s::vector
    LIMIT 10
""", (query_embedding, query_embedding))

results = cursor.fetchall()
for title, company, location, similarity in results:
    print(f"{title} at {company} ({location}) - {similarity:.2%} match")
```

### Match User Profile to Jobs
```python
# Generate embedding for user's resume
resume_text = user.resume_text
resume_embedding = model.encode(resume_text)

# Find best matching jobs
cursor.execute("""
    SELECT 
        j.title, j.company, j.location, j.salary_min, j.salary_max,
        1 - (e.embedding <=> %s::vector) AS match_score
    FROM job_embeddings e
    JOIN job_postings j ON e.job_id = j.job_id
    WHERE j.is_active = TRUE
    ORDER BY e.embedding <=> %s::vector
    LIMIT 20
""", (resume_embedding, resume_embedding))

recommendations = cursor.fetchall()
```

## Comparison: Old vs New

| Aspect | Old (.py file) | New (Jupyter notebook) |
|--------|---------------|------------------------|
| **Format** | Plain Python with "Cell" comments | Proper Jupyter notebook cells |
| **Execution** | Run as script or copy-paste | Run cell-by-cell in UI |
| **Widgets** | ❌ No widgets | ✅ Configurable via widgets |
| **Embeddings** | ⚠️ Placeholder function | ✅ Full implementation with pandas UDF |
| **Model** | Not specified | ✅ sentence-transformers/all-MiniLM-L6-v2 (384-dim) |
| **Distribution** | Single-threaded | ✅ Distributed via mapInPandas |
| **Batch Writes** | Row-by-row | ✅ Batch inserts with execute_values |
| **Scheduling** | Manual | ✅ Ready for Databricks Jobs |
| **Documentation** | Comments only | ✅ Markdown cells with explanations |

## Next Steps

1. **Run the notebook manually** to test the full pipeline
2. **Verify embeddings in Lakebase:**
   ```sql
   SELECT COUNT(*) FROM job_embeddings;
   SELECT * FROM job_embeddings LIMIT 5;
   ```

3. **Cast arrays to vectors** (if needed):
   ```sql
   UPDATE job_embeddings 
   SET embedding = embedding::vector 
   WHERE embedding IS NOT NULL;
   ```

4. **Test semantic search:**
   ```sql
   SELECT title, company, 
          1 - (embedding <=> '[0.1,0.2,...]'::vector) AS similarity
   FROM job_embeddings
   ORDER BY embedding <=> '[0.1,0.2,...]'::vector
   LIMIT 10;
   ```

5. **Schedule the job** to run daily/weekly

6. **Integrate with Flask app** for real-time job recommendations

## Benefits of Notebook Format

✅ **Interactive Development** - Run cells one at a time, see results immediately
✅ **Better Documentation** - Markdown cells explain each step
✅ **Easier Debugging** - Inspect DataFrame schema and samples with `display()`
✅ **Widget Configuration** - Change parameters without editing code
✅ **Scheduling Ready** - Drop into Databricks Jobs/Workflows
✅ **Team Collaboration** - Easier for others to understand and modify
✅ **Visual Outputs** - Tables render nicely with `display()`

---

**Your job embeddings notebook is ready to use!** 🚀

[Open the notebook](#notebook-1196080723430297)
