-- Job Embeddings Table for AI Job Hunting Copilot
-- Stores vector embeddings of job postings for semantic search

-- Enable pgvector extension (run once per database)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create job_embeddings table
CREATE TABLE "job_embeddings" (
	"id" serial PRIMARY KEY,
	"job_id" integer NOT NULL CONSTRAINT "job_embeddings_job_id_key" UNIQUE,
	"external_id" text,
	"title" text,
	"company" text,
	"location" text,
	"embedding" vector(384),
	"model_name" text DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
	"embedded_at" timestamp DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX "idx_job_embeddings_embedded_at" ON "job_embeddings" ("embedded_at");
CREATE INDEX "idx_job_embeddings_external_id" ON "job_embeddings" ("external_id");
CREATE INDEX "idx_job_embeddings_job_id" ON "job_embeddings" ("job_id");
CREATE INDEX "idx_job_embeddings_vector" ON "job_embeddings" USING ivfflat ("embedding");
CREATE UNIQUE INDEX "job_embeddings_job_id_key" ON "job_embeddings" ("job_id");
CREATE UNIQUE INDEX "job_embeddings_pkey" ON "job_embeddings" ("id");
ALTER TABLE "job_embeddings" ADD CONSTRAINT "fk_job_posting" FOREIGN KEY ("job_id") REFERENCES "job_postings"("job_id") ON DELETE CASCADE;