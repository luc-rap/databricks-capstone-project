-- AI Job Hunting Copilot - Lakebase Tables
-- Run these SQL statements against your Lakebase Postgres database
-- to create the schema for the job hunting application.

-- Users table: stores basic user authentication and profile info
CREATE TABLE "users" (
	"user_id" serial PRIMARY KEY,
	"email" varchar(255) NOT NULL CONSTRAINT "users_email_key" UNIQUE,
	"full_name" varchar(255) NOT NULL,
	"created_at" timestamp DEFAULT CURRENT_TIMESTAMP,
	"updated_at" timestamp DEFAULT CURRENT_TIMESTAMP,
	"last_login" timestamp,
	"is_active" boolean DEFAULT true
);
CREATE UNIQUE INDEX "users_email_key" ON "users" ("email");
CREATE UNIQUE INDEX "users_pkey" ON "users" ("user_id");

-- Profiles table: detailed user profiles with career preferences
CREATE TABLE "profiles" (
	"profile_id" serial PRIMARY KEY,
	"user_id" integer NOT NULL CONSTRAINT "profiles_user_id_key" UNIQUE,
	"target_roles" text[] DEFAULT '{}',
	"location_preferences" text[] DEFAULT '{}',
	"remote_preference" varchar(50) DEFAULT 'flexible',
	"salary_min" integer,
	"salary_max" integer,
	"years_experience" integer,
	"resume_text" text,
	"job_preferences" text,
	"created_at" timestamp DEFAULT CURRENT_TIMESTAMP,
	"updated_at" timestamp DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX "idx_profiles_user_id" ON "profiles" ("user_id");
CREATE UNIQUE INDEX "profiles_pkey" ON "profiles" ("profile_id");
CREATE UNIQUE INDEX "profiles_user_id_key" ON "profiles" ("user_id");
ALTER TABLE "profiles" ADD CONSTRAINT "profiles_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("user_id") ON DELETE CASCADE;


-- Job postings table: stores job listings from Adzuna API
CREATE TABLE "job_postings" (
	"job_id" serial PRIMARY KEY,
	"external_id" text NOT NULL CONSTRAINT "job_postings_external_id_key" UNIQUE,
	"title" text NOT NULL,
	"company" text,
	"location" text,
	"description" text,
	"url" text,
	"salary_min" numeric(12, 2),
	"salary_max" numeric(12, 2),
	"contract_type" text,
	"category" text,
	"posted_date" timestamp,
	"fetched_at" timestamp DEFAULT CURRENT_TIMESTAMP,
	"is_active" boolean DEFAULT true,
	"created_at" timestamp DEFAULT CURRENT_TIMESTAMP,
	"updated_at" timestamp DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX "idx_job_postings_active" ON "job_postings" ("is_active");
CREATE INDEX "idx_job_postings_category" ON "job_postings" ("category");
CREATE INDEX "idx_job_postings_company" ON "job_postings" ("company");
CREATE INDEX "idx_job_postings_external_id" ON "job_postings" ("external_id");
CREATE INDEX "idx_job_postings_fetched_at" ON "job_postings" ("fetched_at");
CREATE INDEX "idx_job_postings_is_active" ON "job_postings" ("is_active");
CREATE INDEX "idx_job_postings_location" ON "job_postings" ("location");
CREATE INDEX "idx_job_postings_posted_date" ON "job_postings" ("posted_date");
CREATE INDEX "idx_job_postings_search" ON "job_postings" USING gin ("to_tsvector('english'::regconfig, ((COALESCE(title, ''::text) || ' '::text) || COALESCE(description, ''::text)))");
CREATE UNIQUE INDEX "job_postings_external_id_key" ON "job_postings" ("external_id");
CREATE UNIQUE INDEX "job_postings_pkey" ON "job_postings" ("job_id");

-- Applications table: tracks job application pipeline
CREATE TABLE "applications" (
	"application_id" serial PRIMARY KEY,
	"user_id" integer NOT NULL,
	"job_id" integer NOT NULL,
	"status" varchar(50) DEFAULT 'saved',
	"applied_date" date,
	"cover_letter" text,
	"custom_resume" text,
	"notes" text,
	"created_at" timestamp DEFAULT CURRENT_TIMESTAMP,
	"updated_at" timestamp DEFAULT CURRENT_TIMESTAMP,
	CONSTRAINT "applications_user_id_job_id_key" UNIQUE("user_id","job_id")
);
CREATE UNIQUE INDEX "applications_pkey" ON "applications" ("application_id");
CREATE UNIQUE INDEX "applications_user_id_job_id_key" ON "applications" ("user_id","job_id");
CREATE INDEX "idx_applications_status" ON "applications" ("status");
CREATE INDEX "idx_applications_updated_at" ON "applications" ("updated_at");
CREATE INDEX "idx_applications_user_id" ON "applications" ("user_id");
ALTER TABLE "applications" ADD CONSTRAINT "applications_job_id_fkey" FOREIGN KEY ("job_id") REFERENCES "job_postings"("job_id") ON DELETE CASCADE;
ALTER TABLE "applications" ADD CONSTRAINT "applications_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("user_id") ON DELETE CASCADE;


-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_profiles_user_id ON profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_applications_user_id ON applications(user_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_job_postings_active ON job_postings(is_active);
