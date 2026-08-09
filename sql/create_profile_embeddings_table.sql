-- Profile Embeddings Table for AI Job Hunting Copilot
-- Stores vector embeddings of resume chunks for detailed job matching

-- Enable pgvector extension (run once per database)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create profile_embeddings table
CREATE TABLE "profile_embeddings" (
	"id" serial PRIMARY KEY,
	"user_id" integer NOT NULL,
	"chunk_index" integer NOT NULL,
	"chunk_text" text NOT NULL,
	"embedding" vector(384),
	"model_name" text DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
	"embedded_at" timestamp DEFAULT CURRENT_TIMESTAMP,
	CONSTRAINT "unique_user_chunk" UNIQUE("user_id","chunk_index")
);
CREATE INDEX "idx_profile_embeddings_chunk_index" ON "profile_embeddings" ("chunk_index");
CREATE INDEX "idx_profile_embeddings_embedded_at" ON "profile_embeddings" ("embedded_at");
CREATE INDEX "idx_profile_embeddings_user_id" ON "profile_embeddings" ("user_id");
CREATE INDEX "idx_profile_embeddings_vector" ON "profile_embeddings" USING ivfflat ("embedding");
CREATE UNIQUE INDEX "profile_embeddings_pkey" ON "profile_embeddings" ("id");
CREATE UNIQUE INDEX "unique_user_chunk" ON "profile_embeddings" ("user_id","chunk_index");
ALTER TABLE "profile_embeddings" ADD CONSTRAINT "fk_profile" FOREIGN KEY ("user_id") REFERENCES "profiles"("user_id") ON DELETE CASCADE;