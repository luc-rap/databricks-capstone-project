# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Profile Embeddings Ingestion
# MAGIC %md
# MAGIC # Ingest User Profiles -> Vector Embeddings (Lakebase)
# MAGIC
# MAGIC This notebook:
# MAGIC 1. Reads user profiles with resume text from the `profiles` table in Lakebase
# MAGIC 2. Splits long resumes into overlapping chunks (500 chars, 100 overlap)
# MAGIC 3. Computes sentence embeddings for each chunk using `sentence-transformers/all-MiniLM-L6-v2`
# MAGIC 4. Writes chunk embeddings to `profile_embeddings` table for detailed job matching
# MAGIC
# MAGIC **Use case:** AI Job Hunting Copilot - match user profiles to relevant jobs using vector similarity search
# MAGIC
# MAGIC **When to run:**
# MAGIC - When users upload/update their CV via the profile page
# MAGIC - Scheduled job to process new/updated profiles periodically
# MAGIC - After bulk profile imports

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
# MAGIC Widgets let you override table names and embedding model without editing the notebook - useful when running as a scheduled Databricks Job.
# MAGIC
# MAGIC **Processing mode:**
# MAGIC - `process_all=False` (default): Only processes profiles without chunk embeddings (incremental)
# MAGIC - `process_all=True`: Recomputes ALL profile chunk embeddings (useful after model changes)

# COMMAND ----------

# DBTITLE 1,Setup Widgets
dbutils.widgets.text("profiles_table", "profiles", "Source table (user profiles)")
dbutils.widgets.text("profile_embeddings_table", "profile_embeddings", "Destination table (chunk vectors)")
dbutils.widgets.text("embedding_model", "sentence-transformers/all-MiniLM-L6-v2", "Embedding model")
dbutils.widgets.dropdown("process_all", "false", ["true", "false"], "Reprocess all profiles?")

# Read widget values
PROFILES_TABLE = dbutils.widgets.get("profiles_table")
PROFILE_EMBEDDINGS_TABLE = dbutils.widgets.get("profile_embeddings_table")
EMBEDDING_MODEL_NAME = dbutils.widgets.get("embedding_model")
PROCESS_ALL = dbutils.widgets.get("process_all").lower() == "true"

print(f"Using model '{EMBEDDING_MODEL_NAME}' -> 384-dim vectors")
print(f"Source table: '{PROFILES_TABLE}'")
print(f"Destination table: '{PROFILE_EMBEDDINGS_TABLE}'")
print(f"Process all profiles: {PROCESS_ALL}")

# COMMAND ----------

# DBTITLE 1,Lakebase Connection
# MAGIC %md
# MAGIC ## Resolve the Lakebase connection URL
# MAGIC
# MAGIC Reads the Postgres connection URL from Databricks secrets, parses it for psycopg2 direct connection (batch writes).

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

# Password or OAuth token
if parsed.password:
    db_password = parsed.password
    print(f"Connection details:")
    print(f"  Host: {db_host}:{db_port}")
    print(f"  Database: {db_name}")
    print(f"  User: {db_user}")
    print(f"  Using raw credentials from secret (no OAuth)")
else:
    # OAuth token fallback
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    db_password = w.dbutils.secrets.get(scope="database", key="lakebase-token")
    print(f"Connection details:")
    print(f"  Host: {db_host}:{db_port}")
    print(f"  Database: {db_name}")
    print(f"  User: {db_user}")
    print(f"  Using OAuth token from secret")

print(f"Connecting to: {db_host}:{db_port}/{db_name}")
print(f"Database: {db_name}")

# COMMAND ----------

# DBTITLE 1,Test Connection
import psycopg2

print(f"Testing connection to {db_host}:{db_port}/{db_name}")
print(f"Using authentication as user: {db_user}\n")

# Test psycopg2 connection
try:
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password,
        sslmode='require'
    )
    
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {PROFILES_TABLE}")
    count = cursor.fetchone()[0]
    print(f"✅ Connection successful! Found {count} profiles in {PROFILES_TABLE}")
    
    # Check table columns
    cursor.execute(f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = '{PROFILES_TABLE}'
        ORDER BY ordinal_position
    """)
    columns = [row[0] for row in cursor.fetchall()]
    print(f"\nColumns: {columns}")
    
    cursor.close()
    conn.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
    raise

# COMMAND ----------

# DBTITLE 1,Load Profiles
# MAGIC %md
# MAGIC ## Load user profiles from Lakebase
# MAGIC
# MAGIC Reads the `profiles` table directly using psycopg2.
# MAGIC
# MAGIC **Optimization:** By default, only fetches profiles that don't have chunk embeddings yet (checks for ANY chunks for that user). This prevents re-computing embeddings for profiles already processed in previous runs.
# MAGIC
# MAGIC Set `process_all=true` widget to recompute ALL chunk embeddings (useful after model updates).

# COMMAND ----------

# DBTITLE 1,Read Profiles from Lakebase
# Read profiles directly with psycopg2
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
    
    if PROCESS_ALL:
        # Reprocess ALL profiles
        print("🔄 Reprocessing ALL profiles (process_all=true)\n")
        cursor.execute(f"""
            SELECT 
                p.profile_id,
                p.user_id,
                p.resume_text
            FROM {PROFILES_TABLE} p
            WHERE p.resume_text IS NOT NULL
              AND trim(p.resume_text) != ''
        """)
    else:
        # Only fetch profiles that don't have chunk embeddings yet
        print("⚡ Processing NEW profiles only (profiles without chunk embeddings)\n")
        cursor.execute(f"""
            SELECT 
                p.profile_id,
                p.user_id,
                p.resume_text
            FROM {PROFILES_TABLE} p
            LEFT JOIN (
                SELECT DISTINCT user_id FROM {PROFILE_EMBEDDINGS_TABLE}
            ) e ON p.user_id = e.user_id
            WHERE p.resume_text IS NOT NULL
              AND trim(p.resume_text) != ''
              AND e.user_id IS NULL  -- Only profiles WITHOUT any chunks
        """)
    
    profile_rows = cursor.fetchall()
    print(f"✅ Found {len(profile_rows)} profiles to process from {PROFILES_TABLE}")
    
    # Show sample
    if len(profile_rows) > 0:
        print("\nSample profiles:")
        for i, row in enumerate(profile_rows[:5]):
            profile_id, user_id, resume_text = row
            preview = resume_text[:100].replace('\n', ' ') if resume_text else '(empty)'
            print(f"{i+1}. Profile {profile_id} (User {user_id}): {preview}...")
finally:
    cursor.close()
    conn.close()

if len(profile_rows) > 0:
    print(f"\n➡️ Ready to compute {len(profile_rows)} embeddings")
else:
    print("\n✅ All profiles already have embeddings! Nothing new to process.")

# COMMAND ----------

# DBTITLE 1,Compute Embeddings
# MAGIC %md
# MAGIC ## Compute embeddings with chunking
# MAGIC
# MAGIC Loads the sentence-transformers model once and processes all profiles with chunking strategy to handle long resumes:
# MAGIC
# MAGIC 1. **Chunking**: Splits each resume into overlapping 500-character chunks (100-char overlap) to handle the model's ~512 token limit
# MAGIC 2. **Embedding**: Embeds each chunk separately using **sentence-transformers/all-MiniLM-L6-v2** (384 dimensions)
# MAGIC 3. **Storage**: Stores individual chunk embeddings in `profile_embeddings` table
# MAGIC
# MAGIC This allows:
# MAGIC - **Detailed matching**: Match specific resume sections to job requirements
# MAGIC - **Flexible aggregation**: Can compute mean/max similarity across chunks at query time
# MAGIC - **Skills gap analysis**: Identify which resume sections match/don't match job requirements
# MAGIC
# MAGIC **Same chunking strategy as ticker news embeddings for consistency.**

# COMMAND ----------

# DBTITLE 1,Generate Embeddings
import os
import numpy as np
from sentence_transformers import SentenceTransformer
from datetime import datetime

# Chunking configuration (same as ticker news notebook)
CHUNK_SIZE = 500  # Characters per chunk
CHUNK_OVERLAP = 100  # Overlap between consecutive chunks

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Split text into overlapping chunks to handle long resumes."""
    if not text or len(text) <= chunk_size:
        return [text] if text else []
    
    chunks = []
    for start in range(0, len(text), chunk_size - overlap):
        chunk = text[start:start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(text):
            break
    return chunks

# Skip if no new profiles to process
if len(profile_rows) == 0:
    print("⏭️ Skipping embedding computation - no new profiles to process")
    embedding_records = []  # Empty list for next cell
else:
    # Load the embedding model once
    print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}...")
    os.environ["HF_HOME"] = "/tmp/.cache/huggingface"
    os.environ["TRANSFORMERS_CACHE"] = "/tmp/.cache/huggingface"
    os.environ["HF_HUB_CACHE"] = "/tmp/.cache/huggingface"

    model = SentenceTransformer(EMBEDDING_MODEL_NAME, cache_folder="/tmp/.cache/huggingface")
    print("✅ Model loaded!")
    print(f"\nChunking config: {CHUNK_SIZE} chars per chunk, {CHUNK_OVERLAP} overlap")

    # Compute embeddings for each chunk
    print(f"\nProcessing {len(profile_rows)} profiles with chunking...")
    embedding_records = []  # One record per chunk
    total_chunks = 0

    for i, row in enumerate(profile_rows):
        profile_id, user_id, resume_text = row
        
        # Split resume into chunks
        chunks = chunk_text(resume_text)
        total_chunks += len(chunks)
        
        if len(chunks) == 0:
            # Empty resume - skip
            continue
        
        # Embed each chunk
        chunk_vectors = model.encode(chunks, show_progress_bar=False)
        
        # Store each chunk embedding
        for chunk_index, (chunk_text_str, chunk_vector) in enumerate(zip(chunks, chunk_vectors)):
            embedding_records.append({
                'user_id': user_id,
                'chunk_index': chunk_index,
                'chunk_text': chunk_text_str,
                'embedding': chunk_vector.tolist(),
                'model_name': EMBEDDING_MODEL_NAME,
                'embedded_at': datetime.now()
            })
        
        if (i + 1) % 10 == 0:
            avg_chunks = total_chunks / (i + 1)
            print(f"  Processed {i + 1}/{len(profile_rows)} profiles (avg {avg_chunks:.1f} chunks/profile)")

    avg_chunks_per_profile = total_chunks / len(profile_rows) if profile_rows else 0
    print(f"\n✅ Computed {len(embedding_records)} chunk embeddings using {EMBEDDING_MODEL_NAME}")
    print(f"   Average chunks per profile: {avg_chunks_per_profile:.1f}")

    print(f"\nSample chunk embeddings:")
    for i in range(min(5, len(embedding_records))):
        rec = embedding_records[i]
        preview = rec['chunk_text'][:60].replace('\n', ' ') if rec['chunk_text'] else '(empty)'
        print(f"{i+1}. User {rec['user_id']}, Chunk {rec['chunk_index']}: {len(rec['embedding'])} dimensions - \"{preview}...\"")

# COMMAND ----------

# DBTITLE 1,Write Embeddings
# MAGIC %md
# MAGIC ## Write embeddings to Lakebase
# MAGIC
# MAGIC Batch inserts chunk embeddings using psycopg2's `execute_values` for high-throughput writes.
# MAGIC
# MAGIC **Note:** The embeddings table must already exist in Lakebase:
# MAGIC - Run `sql/create_profile_embeddings_table.sql` to create the table with chunk_index column
# MAGIC
# MAGIC Embeddings are written as PostgreSQL double precision arrays and automatically cast to pgvector's `vector` type.

# COMMAND ----------

# DBTITLE 1,Batch Insert Embeddings
from psycopg2.extras import execute_values

if len(embedding_records) > 0:
    print(f"\nInserting {len(embedding_records)} chunk embeddings into {PROFILE_EMBEDDINGS_TABLE}...")
    
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
        insert_data = [
            (
                rec['user_id'],
                rec['chunk_index'],
                rec['chunk_text'],
                '{' + ','.join(str(float(x)) for x in rec['embedding']) + '}',
                rec['model_name'],
                rec['embedded_at']
            )
            for rec in embedding_records
        ]
        
        # Batch insert with ON CONFLICT DO UPDATE
        insert_sql = f"""
            INSERT INTO {PROFILE_EMBEDDINGS_TABLE} (
                user_id, chunk_index, chunk_text, embedding, model_name, embedded_at
            ) VALUES %s
            ON CONFLICT (user_id, chunk_index) DO UPDATE SET
                chunk_text = EXCLUDED.chunk_text,
                embedding = EXCLUDED.embedding::vector,
                model_name = EXCLUDED.model_name,
                embedded_at = EXCLUDED.embedded_at
        """
        
        template = "(%s, %s, %s, %s::double precision[], %s, %s)"
        execute_values(cursor, insert_sql, insert_data, template=template, page_size=100)
        
        conn.commit()
        inserted_count = cursor.rowcount
        print(f"✅ Successfully inserted/updated {inserted_count} chunk embeddings")
        
        # Verify insertion
        cursor.execute(f"SELECT COUNT(*) FROM {PROFILE_EMBEDDINGS_TABLE}")
        total = cursor.fetchone()[0]
        print(f"   Total chunk embeddings in table: {total}")
        
        # Show chunks per user
        cursor.execute(f"""
            SELECT user_id, COUNT(*) as num_chunks
            FROM {PROFILE_EMBEDDINGS_TABLE}
            GROUP BY user_id
            ORDER BY num_chunks DESC
            LIMIT 5
        """)
        top_users = cursor.fetchall()
        print(f"\n   Top users by chunk count:")
        for user_id, num_chunks in top_users:
            print(f"      User {user_id}: {num_chunks} chunks")
        
    finally:
        cursor.close()
        conn.close()
else:
    print("⏭️ No new embeddings to write.")

print(f"\n✅ Profile chunk embeddings are now available in {PROFILE_EMBEDDINGS_TABLE}!")

# COMMAND ----------

# DBTITLE 1,Test Profile-to-Job Matching
# Test chunk-level profile-to-job matching
print("Testing chunk-level profile-to-job matching with pgvector...\n")

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
    
    # Pick a random profile chunk as reference
    cursor.execute(f"""
        SELECT user_id, chunk_index, chunk_text, embedding
        FROM {PROFILE_EMBEDDINGS_TABLE}
        ORDER BY RANDOM()
        LIMIT 1
    """)
    
    reference = cursor.fetchone()
    if reference:
        ref_user_id, ref_chunk_index, ref_chunk_text, ref_embedding = reference
        
        print(f"🎯 Sample Resume Chunk:")
        print(f"   User {ref_user_id}, Chunk {ref_chunk_index}")
        print(f"   Text: {ref_chunk_text[:150].replace(chr(10), ' ')}...")
        print(f"\n📊 Finding best matching jobs for this resume section...\n")
        
        # Find similar jobs using cosine distance (<=>)
        cursor.execute(f"""
            SELECT 
                j.title,
                j.company,
                j.location,
                1 - (j.embedding <=> %s::vector) AS similarity_score
            FROM job_embeddings j
            JOIN job_postings p ON j.job_id = p.job_id
            WHERE p.is_active = TRUE
            ORDER BY j.embedding <=> %s::vector
            LIMIT 5
        """, (ref_embedding, ref_embedding))
        
        matching_jobs = cursor.fetchall()
        
        for i, job in enumerate(matching_jobs, 1):
            title, company, location, similarity = job
            print(f"{i}. {title}")
            print(f"   Company: {company}")
            print(f"   Location: {location}")
            print(f"   Match Score: {similarity:.4f} ({int(similarity * 100)}%)")
            print()
        
        print("\n✅ Chunk-level matching works!")
        print("\n💡 Use this to show users WHICH PART of their resume matches each job")
    else:
        print("❌ No chunk embeddings found in the table")
        
finally:
    cursor.close()
    conn.close()

# COMMAND ----------

