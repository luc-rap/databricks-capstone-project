# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Job Posting Embeddings Ingestion
# MAGIC %md
# MAGIC # Ingest Job Postings -> Vector Embeddings (Lakebase)
# MAGIC
# MAGIC This notebook:
# MAGIC 1. Fetches job postings from the Adzuna API for watchlisted search terms
# MAGIC 2. Stores raw job data in `job_postings` table in Lakebase
# MAGIC 3. Computes sentence embeddings for job descriptions using `sentence-transformers/all-MiniLM-L6-v2`
# MAGIC 4. Writes embeddings to `job_embeddings` table for semantic search and matching
# MAGIC
# MAGIC **Use case:** AI Job Hunting Copilot - match user profiles to relevant jobs using vector similarity search

# COMMAND ----------

# DBTITLE 1,Install Dependencies
#%pip uninstall -y psycopg2 psycopg2-binary
#%pip install -q 'databricks-sdk>=0.118.0' sentence-transformers trafilatura requests pandas

# COMMAND ----------

# DBTITLE 1,Restart Python
dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Configuration
# MAGIC %md
# MAGIC ## Config
# MAGIC
# MAGIC Widgets let you override table names, embedding model, search query, and location filter without editing the notebook - useful when running as a scheduled Databricks Job.
# MAGIC
# MAGIC **Location filter:**
# MAGIC - Uses Adzuna's `where` parameter for geographic filtering
# MAGIC - Examples: "California", "San Francisco", "Miami, Florida", "Remote"
# MAGIC - Leave empty to search all US locations
# MAGIC - Can combine state/city: "San Francisco, California"

# COMMAND ----------

# DBTITLE 1,Setup Widgets
dbutils.widgets.text("job_postings_table", "job_postings", "Destination table (raw jobs)")
dbutils.widgets.text("job_embeddings_table", "job_embeddings", "Destination table (vectors)")
dbutils.widgets.text("embedding_model", "sentence-transformers/all-MiniLM-L6-v2", "Embedding model")
dbutils.widgets.text("adzuna_secret_scope", "adzuna", "Adzuna API secret scope")
dbutils.widgets.text("search_query", "data engineer", "Job search query")
dbutils.widgets.text("location_filter", "", "Location (e.g., California, San Francisco, Remote)")
dbutils.widgets.text("results_per_page", "50", "Results per page")

JOB_POSTINGS_TABLE = dbutils.widgets.get("job_postings_table")
JOB_EMBEDDINGS_TABLE = dbutils.widgets.get("job_embeddings_table")
EMBEDDING_MODEL_NAME = dbutils.widgets.get("embedding_model")
ADZUNA_SECRET_SCOPE = dbutils.widgets.get("adzuna_secret_scope")
SEARCH_QUERY = dbutils.widgets.get("search_query")
LOCATION_FILTER = dbutils.widgets.get("location_filter").strip()
RESULTS_PER_PAGE = int(dbutils.widgets.get("results_per_page"))

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 produces 384-dim vectors

print(f"Using model '{EMBEDDING_MODEL_NAME}' -> {EMBEDDING_DIM}-dim vectors")
print(f"Search query: '{SEARCH_QUERY}'")
if LOCATION_FILTER:
    print(f"Location filter: '{LOCATION_FILTER}'")
else:
    print(f"Location: All US")
print(f"Results per page: {RESULTS_PER_PAGE}")

# COMMAND ----------

# DBTITLE 1,Location Filter Examples
# MAGIC %md
# MAGIC ### Location Filter Examples
# MAGIC
# MAGIC **Note:** The Adzuna US API uses the `where` parameter for location filtering (state, city, or keyword).
# MAGIC
# MAGIC **Example 1: California jobs**
# MAGIC - `location_filter` = "California"
# MAGIC
# MAGIC **Example 2: San Francisco jobs**
# MAGIC - `location_filter` = "San Francisco"
# MAGIC
# MAGIC **Example 3: Miami, Florida jobs**
# MAGIC - `location_filter` = "Miami, Florida"
# MAGIC
# MAGIC **Example 4: All US jobs (default)**
# MAGIC - `location_filter` = (empty)
# MAGIC
# MAGIC **Finding Remote Jobs:**
# MAGIC ⚠️ **"Remote" doesn't work as a location filter!** Adzuna doesn't tag jobs with "Remote" as a location.
# MAGIC
# MAGIC **Instead, add "remote" to your search query:**
# MAGIC - `search_query` = "data engineer remote"
# MAGIC - `location_filter` = (empty or specific state)
# MAGIC
# MAGIC This searches job titles/descriptions for remote work mentions.
# MAGIC
# MAGIC **Tip:** You can modify the widget values above and re-run cells 5 & 11 to fetch jobs with different filters!

# COMMAND ----------

# DBTITLE 1,Lakebase Connection
# MAGIC %md
# MAGIC ## Resolve the Lakebase connection URL
# MAGIC
# MAGIC Reads the Postgres connection URL from Databricks secrets

# COMMAND ----------

# DBTITLE 1,Parse Lakebase URL
import base64
import re
from urllib.parse import urlparse, quote_plus

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

def get_lakebase_url() -> str:
    secret = w.secrets.get_secret(scope="database", key="lakebase-url")
    return base64.b64decode(secret.value).decode("utf-8")

lakebase_url = get_lakebase_url()
parsed = urlparse(lakebase_url)

# Extract components
db_host = parsed.hostname
db_port = parsed.port or 5432
db_name = parsed.path.lstrip('/')
db_user = parsed.username
db_password = parsed.password

print(f"Connection details:")
print(f"  Host: {db_host}:{db_port}")
print(f"  Database: {db_name}")
print(f"  User: {db_user}")
print(f"  Using raw credentials from secret (no OAuth)")

print(f"Connecting to: {db_host}:{db_port}/{db_name}")
print(f"Database: {db_name}")

# COMMAND ----------

import psycopg2

print(f"Testing connection to {db_host}:{db_port}/{db_name}")
print(f"Using OAuth token authentication as user: {db_user}\n")

# Test psycopg3 connection with OAuth token
try:
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
        sslmode='require',
        connect_timeout=10
    )
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {JOB_POSTINGS_TABLE}")
    count = cursor.fetchone()[0]
    print(f"✅ Connection successful! Found {count} rows in {JOB_POSTINGS_TABLE}")
    
    cursor.execute(f"SELECT * FROM {JOB_POSTINGS_TABLE} LIMIT 5")
    rows = cursor.fetchall()
    colnames = [desc[0] for desc in cursor.description]
    print(f"\nColumns: {colnames}")
    for row in rows:
        print(row)
    
    cursor.close()
    conn.close()
    print("\n✅ psycopg3 with OAuth authentication working correctly!")
except Exception as e:
    import traceback
    print(f"❌ Connection failed: {e}")
    print(f"\nFull traceback:")
    traceback.print_exc()


# COMMAND ----------

# DBTITLE 1,Load CSV from Upload (Alternative to API)
# ============================================
# OPTION: Load Jobs from Uploaded CSV
# ============================================
# Use this cell if you ran fetch_adzuna_jobs.py locally and uploaded the CSV
# Skip cell 11 (direct API call) and use this instead

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# UPDATE THIS PATH with your uploaded CSV location
# Option 1: If uploaded to a Volume
CSV_PATH = "/Volumes/workspace/default/test/adzuna_jobs_20260809_110415.csv"

# Option 2: If uploaded to DBFS
# CSV_PATH = "/dbfs/tmp/adzuna_jobs.csv"

# Option 3: If created as a table via UI upload
# df = spark.table("main.default.adzuna_jobs_staging").toPandas()

print(f"📖 Reading CSV from {CSV_PATH}...")
try:
    df = pd.read_csv(CSV_PATH)
    print(f"✅ Loaded {len(df)} jobs from CSV\n")
except FileNotFoundError:
    print(f"❌ File not found: {CSV_PATH}")
    print("\nPlease upload your CSV and update CSV_PATH above.")
    print("\nUpload options:")
    print("  1. Catalog → Upload Data → Create Table")
    print("  2. Catalog → Volume → Upload File")
    print("  3. CLI: databricks fs cp file.csv dbfs:/tmp/")
    raise

# Show preview
print(f"📊 Sample jobs:")
for idx, row in df.head(3).iterrows():
    salary = ""
    if pd.notna(row.get('salary_min')) and pd.notna(row.get('salary_max')):
        salary = f" (${row['salary_min']:,.0f} - ${row['salary_max']:,.0f})"
    print(f"{idx+1}. {row['title']} at {row['company']} ({row['location']}){salary}")

# Insert into Lakebase
print(f"\n💾 Inserting into {JOB_POSTINGS_TABLE}...")
conn = psycopg2.connect(
    host=db_host,
    port=db_port,
    dbname=db_name,
    user=db_user,
    password=db_password,
    sslmode='require'
)

try:
    cursor = conn.cursor()
    
    # Prepare data for batch insert
    insert_data = [
        (
            row['external_id'],
            row['title'],
            row['company'],
            row['location'],
            row['description'],
            row['url'],
            row['salary_min'] if pd.notna(row.get('salary_min')) else None,
            row['salary_max'] if pd.notna(row.get('salary_max')) else None,
            row.get('contract_type'),
            row.get('category'),
            row.get('posted_date')
        )
        for _, row in df.iterrows()
    ]
    
    # Batch insert with ON CONFLICT DO UPDATE (upsert)
    insert_sql = f"""
        INSERT INTO {JOB_POSTINGS_TABLE} (
            external_id, title, company, location, description,
            url, salary_min, salary_max, contract_type, category, posted_date, fetched_at
        ) VALUES %s
        ON CONFLICT (external_id) DO UPDATE SET
            title = EXCLUDED.title,
            company = EXCLUDED.company,
            location = EXCLUDED.location,
            description = EXCLUDED.description,
            url = EXCLUDED.url,
            salary_min = EXCLUDED.salary_min,
            salary_max = EXCLUDED.salary_max,
            contract_type = EXCLUDED.contract_type,
            category = EXCLUDED.category,
            fetched_at = CURRENT_TIMESTAMP,
            is_active = TRUE
    """
    
    template = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)"
    execute_values(cursor, insert_sql, insert_data, template=template, page_size=100)
    
    conn.commit()
    inserted_count = cursor.rowcount
    print(f"✅ Successfully inserted/updated {inserted_count} job postings")
    
finally:
    cursor.close()
    conn.close()

print("\n✅ CSV data loaded into Lakebase!")
print("\n➡️ Continue to cell 14 to compute embeddings")

# COMMAND ----------

# DBTITLE 1,Fetch Jobs from Adzuna
# MAGIC %md
# MAGIC ## Fetch jobs from Adzuna API (Option 2 - if working from Databricks)
# MAGIC
# MAGIC Retrieves job postings matching the search query and stores them in Lakebase.
# MAGIC Uses ON CONFLICT DO NOTHING for deduplication.

# COMMAND ----------

# DBTITLE 1,Fetch and Store Jobs
import requests
import time
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values

# Get Adzuna credentials
adzuna_app_id_secret = w.secrets.get_secret(scope=ADZUNA_SECRET_SCOPE, key="app-id")
adzuna_app_key_secret = w.secrets.get_secret(scope=ADZUNA_SECRET_SCOPE, key="app-key")

adzuna_app_id = base64.b64decode(adzuna_app_id_secret.value).decode("utf-8")
adzuna_app_key = base64.b64decode(adzuna_app_key_secret.value).decode("utf-8")

# Build search query with location if provided
# Note: US Adzuna API doesn't support location0/location1 parameters reliably
# Instead, we include location terms in the search query using the 'where' parameter
search_what = SEARCH_QUERY
search_where = LOCATION_FILTER if LOCATION_FILTER else ""

if search_where:
    print(f"Fetching jobs for query: '{search_what}' in location: '{search_where}'")
else:
    print(f"Fetching jobs for query: '{search_what}' (All US)")

# Fetch jobs from Adzuna
country = "us"
page = 1

# Build API parameters
api_params = {
    "app_id": adzuna_app_id,
    "app_key": adzuna_app_key,
    "what": search_what,
    "results_per_page": RESULTS_PER_PAGE,
}

# Add location via 'where' parameter (more reliable for US)
if search_where:
    api_params["where"] = search_where

try:
    response = requests.get(
        f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}",
        params=api_params,
        timeout=30
    )
    response.raise_for_status()
except requests.exceptions.ConnectionError as e:
    if "Failed to resolve" in str(e) or "Name or service not known" in str(e):
        print("\n❌ Network Error: Cannot reach Adzuna API (api.adzuna.com)")
        print("\nThis cluster cannot resolve external DNS names.")
        print("\nPossible solutions:")
        print("  1. Check if the cluster has internet access enabled")
        print("  2. Verify firewall/network security group settings allow outbound HTTPS")
        print("  3. Try running on a different cluster with internet access")
        print("  4. Contact your workspace administrator about external API access")
        raise RuntimeError("Cannot connect to Adzuna API - DNS resolution failed") from e
    else:
        raise

jobs_data = response.json()
jobs = jobs_data.get("results", [])

print(f"✅ Fetched {len(jobs)} job postings")

# Insert jobs into Lakebase
if len(jobs) > 0:
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
        sslmode='require'
    )
    
    try:
        cursor = conn.cursor()
        
        # Prepare data for batch insert
        insert_data = []
        for job in jobs:
            external_id = str(job.get("id"))
            title = job.get("title")
            company = job.get("company", {}).get("display_name") if isinstance(job.get("company"), dict) else job.get("company")
            location = job.get("location", {}).get("display_name") if isinstance(job.get("location"), dict) else job.get("location")
            description = job.get("description", "")
            redirect_url = job.get("redirect_url")
            salary_min = job.get("salary_min")
            salary_max = job.get("salary_max")
            contract_type = job.get("contract_type")
            category = job.get("category", {}).get("label") if isinstance(job.get("category"), dict) else None
            created = job.get("created")
            
            insert_data.append((
                external_id, title, company, location, description,
                redirect_url, salary_min, salary_max, contract_type, category, created
            ))
        
        # Batch insert with ON CONFLICT DO NOTHING
        insert_sql = f"""
            INSERT INTO {JOB_POSTINGS_TABLE} (
                external_id, title, company, location, description,
                url, salary_min, salary_max, contract_type, category, posted_date, fetched_at
            ) VALUES %s
            ON CONFLICT (external_id) DO UPDATE SET
                title = EXCLUDED.title,
                company = EXCLUDED.company,
                location = EXCLUDED.location,
                description = EXCLUDED.description,
                url = EXCLUDED.url,
                salary_min = EXCLUDED.salary_min,
                salary_max = EXCLUDED.salary_max,
                contract_type = EXCLUDED.contract_type,
                category = EXCLUDED.category,
                fetched_at = CURRENT_TIMESTAMP,
                is_active = TRUE
        """
        
        template = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)"
        execute_values(cursor, insert_sql, insert_data, template=template, page_size=100)
        
        conn.commit()
        inserted_count = cursor.rowcount
        print(f"✅ Successfully inserted/updated {inserted_count} job postings")
        
    finally:
        cursor.close()
        conn.close()

print("\nReady to compute embeddings! Run the cells below to continue.")

# COMMAND ----------

# DBTITLE 1,Load Jobs into Spark
# MAGIC %md
# MAGIC ## Load raw job postings from Lakebase
# MAGIC
# MAGIC Reads the `job_postings` table directly using psycopg2 for simpler, single-process execution.
# MAGIC
# MAGIC **Optimization:** Only fetches jobs that don't have embeddings yet (LEFT JOIN filter). This prevents re-computing embeddings for jobs already processed in previous runs.

# COMMAND ----------

# DBTITLE 1,Read Jobs from Lakebase
# Read jobs directly with psycopg2 (no Spark JDBC)
conn = psycopg2.connect(
    host=db_host,
    port=db_port,
    dbname=db_name,
    user=db_user,
    password=db_password,
    sslmode='require'
)

try:
    cursor = conn.cursor()
    # Only fetch jobs that don't have embeddings yet (LEFT JOIN)
    cursor.execute(f"""
        SELECT 
            p.job_id,
            p.external_id,
            p.title,
            p.company,
            p.location,
            p.description,
            trim(concat(coalesce(p.title, ''), '. ', coalesce(p.description, ''))) AS embedding_text
        FROM {JOB_POSTINGS_TABLE} p
        LEFT JOIN {JOB_EMBEDDINGS_TABLE} e ON p.job_id = e.job_id
        WHERE p.is_active = TRUE
          AND (p.title IS NOT NULL OR p.description IS NOT NULL)
          AND e.job_id IS NULL  -- Only jobs WITHOUT embeddings
    """)
    
    jobs_rows = cursor.fetchall()
    print(f"✅ Found {len(jobs_rows)} NEW job postings (without embeddings) from {JOB_POSTINGS_TABLE}")
    
    # Show sample
    if len(jobs_rows) > 0:
        print("\nSample jobs:")
        for i, row in enumerate(jobs_rows[:5]):
            print(f"{i+1}. {row[2]} at {row[3]} ({row[4]})")
finally:
    cursor.close()
    conn.close()

if len(jobs_rows) > 0:
    print(f"\n➡️ Ready to compute {len(jobs_rows)} new embeddings")
else:
    print("\n✅ All jobs already have embeddings! Nothing new to process.")

# COMMAND ----------

# DBTITLE 1,Compute Embeddings
# MAGIC %md
# MAGIC ## Compute embeddings
# MAGIC
# MAGIC Loads the sentence-transformers model once and processes all jobs in batches for efficient embedding generation.
# MAGIC
# MAGIC Using **sentence-transformers/all-MiniLM-L6-v2** (384 dimensions)

# COMMAND ----------

# DBTITLE 1,Generate Embeddings with Pandas UDF
import os
from sentence_transformers import SentenceTransformer
from datetime import datetime

# Skip if no new jobs to process
if len(jobs_rows) == 0:
    print("⏭️ Skipping embedding computation - no new jobs to process")
    embedding_records = []  # Empty list for next cell
else:
    # Load the embedding model once
    print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}...")
    os.environ["HF_HOME"] = "/tmp/.cache/huggingface"
    os.environ["TRANSFORMERS_CACHE"] = "/tmp/.cache/huggingface"
    os.environ["HF_HUB_CACHE"] = "/tmp/.cache/huggingface"

    model = SentenceTransformer(EMBEDDING_MODEL_NAME, cache_folder="/tmp/.cache/huggingface")
    print("✅ Model loaded!")

    # Extract embedding texts from jobs
    embedding_texts = [row[6] for row in jobs_rows]  # embedding_text is column 6

    # Compute embeddings in batches
    print(f"\nComputing {len(embedding_texts)} embeddings in batches...")
    batch_size = 32
    all_embeddings = []

    for i in range(0, len(embedding_texts), batch_size):
        batch = embedding_texts[i:i+batch_size]
        vectors = model.encode(batch, show_progress_bar=False)
        all_embeddings.extend(vectors)
        if (i + batch_size) % 100 == 0:
            print(f"  Processed {min(i + batch_size, len(embedding_texts))}/{len(embedding_texts)} embeddings...")

    print(f"✅ Computed {len(all_embeddings)} embeddings using {EMBEDDING_MODEL_NAME}")

    # Build embedding records for insertion
    embedding_records = []
    for i, row in enumerate(jobs_rows):
        embedding_records.append({
            'job_id': row[0],
            'external_id': row[1],
            'title': row[2],
            'company': row[3],
            'location': row[4],
            'embedding': all_embeddings[i].tolist(),
            'model_name': EMBEDDING_MODEL_NAME,
            'embedded_at': datetime.now()
        })

    print(f"\nSample embeddings:")
    for i in range(min(3, len(embedding_records))):
        rec = embedding_records[i]
        print(f"{i+1}. {rec['title']}: {len(rec['embedding'])} dimensions")

# COMMAND ----------

# DBTITLE 1,Write Embeddings
# MAGIC %md
# MAGIC ## Write embeddings to Lakebase
# MAGIC
# MAGIC Batch inserts embeddings using psycopg2's `execute_values` for high-throughput writes.
# MAGIC
# MAGIC **Note:** The embeddings table must already exist in Lakebase. See `sql/setup_job_embeddings.sql` for the schema.
# MAGIC
# MAGIC Embeddings are written as PostgreSQL double precision arrays and automatically cast to pgvector's `vector` type.

# COMMAND ----------

# DBTITLE 1,Batch Insert Embeddings
if len(embedding_records) > 0:
    print(f"\nInserting {len(embedding_records)} embeddings into {JOB_EMBEDDINGS_TABLE}...")
    
    # Build connection
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
        sslmode='require'
    )
    
    try:
        cursor = conn.cursor()
        
        # Prepare data tuples for batch insert
        # Format embedding as PostgreSQL array literal: '{val1,val2,...}'
        insert_data = [
            (
                rec['job_id'],
                rec['external_id'],
                rec['title'],
                rec['company'],
                rec['location'],
                '{' + ','.join(str(float(x)) for x in rec['embedding']) + '}',
                rec['model_name'],
                rec['embedded_at']
            )
            for rec in embedding_records
        ]
        
        # Batch insert with ON CONFLICT DO UPDATE for upserts
        insert_sql = f"""
            INSERT INTO {JOB_EMBEDDINGS_TABLE} (
                job_id, external_id, title, company, location, embedding, model_name, embedded_at
            ) VALUES %s
            ON CONFLICT (job_id) DO UPDATE SET
                embedding = EXCLUDED.embedding::vector,
                model_name = EXCLUDED.model_name,
                embedded_at = EXCLUDED.embedded_at
        """
        
        # execute_values is much faster than individual INSERTs
        # Cast to double precision array, then to vector
        template = "(%s, %s, %s, %s, %s, %s::double precision[], %s, %s)"
        execute_values(cursor, insert_sql, insert_data, template=template, page_size=100)
        
        conn.commit()
        inserted_count = cursor.rowcount
        print(f"✅ Successfully inserted/updated {inserted_count} embeddings")
        print(f"\n✅ Embeddings are now searchable in {JOB_EMBEDDINGS_TABLE}!")
        
        # Verify insertion
        cursor.execute(f"SELECT COUNT(*) FROM {JOB_EMBEDDINGS_TABLE}")
        total = cursor.fetchone()[0]
        print(f"\nTotal embeddings in table: {total}")
        
    finally:
        cursor.close()
        conn.close()
else:
    print("⏭️ No new embeddings to write.")

# Show total count regardless
conn = psycopg2.connect(
    host=db_host,
    port=db_port,
    dbname=db_name,
    user=db_user,
    password=db_password,
    sslmode='require'
)

try:
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {JOB_EMBEDDINGS_TABLE}")
    total = cursor.fetchone()[0]
    print(f"\n📊 Total embeddings in database: {total}")
finally:
    cursor.close()
    conn.close()

# COMMAND ----------

# DBTITLE 1,Test Similarity Search
# Test vector similarity search
print("Testing pgvector similarity search...\n")

conn = psycopg2.connect(
    host=db_host,
    port=db_port,
    dbname=db_name,
    user=db_user,
    password=db_password,
    sslmode='require'
)

try:
    cursor = conn.cursor()
    
    # Pick a random job as reference
    cursor.execute(f"""
        SELECT job_id, title, company, location, embedding
        FROM {JOB_EMBEDDINGS_TABLE}
        ORDER BY RANDOM()
        LIMIT 1
    """)
    
    reference = cursor.fetchone()
    if reference:
        ref_job_id, ref_title, ref_company, ref_location, ref_embedding = reference
        
        print(f"🎯 Reference job:")
        print(f"   Title: {ref_title}")
        print(f"   Company: {ref_company}")
        print(f"   Location: {ref_location}")
        print(f"\n📊 Finding 5 most similar jobs...\n")
        
        # Find similar jobs using cosine distance (<=>)
        cursor.execute(f"""
            SELECT 
                e.title,
                e.company,
                e.location,
                p.salary_min,
                p.salary_max,
                p.url,
                1 - (e.embedding <=> %s::vector) AS similarity_score,
                e.embedding <=> %s::vector AS cosine_distance
            FROM {JOB_EMBEDDINGS_TABLE} e
            JOIN {JOB_POSTINGS_TABLE} p ON e.job_id = p.job_id
            WHERE p.is_active = TRUE
              AND e.job_id != %s  -- Exclude reference job
            ORDER BY e.embedding <=> %s::vector
            LIMIT 5
        """, (ref_embedding, ref_embedding, ref_job_id, ref_embedding))
        
        similar_jobs = cursor.fetchall()
        
        for i, job in enumerate(similar_jobs, 1):
            title, company, location, sal_min, sal_max, url, similarity, distance = job
            
            # Format salary
            salary_str = "Not specified"
            if sal_min and sal_max:
                salary_str = f"${sal_min:,.0f} - ${sal_max:,.0f}"
            elif sal_max:
                salary_str = f"Up to ${sal_max:,.0f}"
            
            print(f"{i}. {title}")
            print(f"   Company: {company}")
            print(f"   Location: {location}")
            print(f"   Salary: {salary_str}")
            print(f"   Similarity: {similarity:.4f} (distance: {distance:.4f})")
            print(f"   URL: {url[:60]}..." if url and len(url) > 60 else f"   URL: {url}")
            print()
        
        print("\n✅ Vector similarity search is working!")
        print("\nNote: Similarity ranges from 0 (opposite) to 1 (identical)")
        print("      Cosine distance ranges from 0 (identical) to 2 (opposite)")
    else:
        print("❌ No embeddings found in the table")
        
finally:
    cursor.close()
    conn.close()

# COMMAND ----------

# DBTITLE 1,Design Decision: No Chunking Strategy
# MAGIC %md
# MAGIC ## Design Decision: No Chunking Strategy
# MAGIC
# MAGIC **Current approach:** Single embedding per job (title + description)
# MAGIC
# MAGIC **Why no chunking?**
# MAGIC - Adzuna API summaries average **500 characters** (max 500)
# MAGIC - All jobs fit comfortably in a single embedding
# MAGIC - Sentence-transformers models handle up to ~2,000 chars easily
# MAGIC - Job postings need **holistic matching** - splitting would lose context
# MAGIC
# MAGIC **Alternative considered:** Scraping full descriptions from company URLs
# MAGIC - ⚠️ **50% failure rate** (403 blocks, timeouts, paywalls)
# MAGIC - 🚫 **Legal/ethical concerns** (ToS violations, tracking URLs, IP bans)
# MAGIC - ✅ **Decision:** Stick with API summaries (reliable, legal, sufficient for matching)