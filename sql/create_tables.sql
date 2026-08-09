-- AI Job Hunting Copilot - Lakebase Tables
-- Run these SQL statements against your Lakebase Postgres database
-- to create the schema for the job hunting application.

-- Users table: stores basic user authentication and profile info
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Profiles table: detailed user profiles with career preferences
CREATE TABLE IF NOT EXISTS profiles (
    profile_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    target_roles TEXT[] DEFAULT '{}',  -- Array of target job titles
    location_preferences TEXT[] DEFAULT '{}',  -- Preferred work locations
    remote_preference VARCHAR(50) DEFAULT 'flexible',  -- remote, hybrid, onsite, flexible
    salary_min INTEGER,
    salary_max INTEGER,
    years_experience INTEGER,
    resume_text TEXT,  -- Full resume content
    job_preferences TEXT,  -- Work authorization, citizenship requirements, etc.
    resume_embedding vector(384),  
    linkedin_url VARCHAR(500),
    github_url VARCHAR(500),
    portfolio_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id)
);

-- Skills table: user skills and proficiency levels
CREATE TABLE IF NOT EXISTS skills (
    skill_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    skill_name VARCHAR(100) NOT NULL,
    proficiency_level VARCHAR(50),  -- beginner, intermediate, advanced, expert
    years_of_experience DECIMAL(3,1),
    is_primary BOOLEAN DEFAULT FALSE,  -- Key skill for job search
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, skill_name)
);

-- Job postings table: stores job listings from Adzuna API
CREATE TABLE IF NOT EXISTS job_postings (
    job_id SERIAL PRIMARY KEY,
    external_id VARCHAR(255) UNIQUE NOT NULL,  -- Adzuna job ID
    title VARCHAR(500) NOT NULL,
    company VARCHAR(255),
    location VARCHAR(255),
    salary_min INTEGER,
    salary_max INTEGER,
    description TEXT,
    requirements TEXT,
    description_embedding vector(384),  -- Embedding for semantic search
    is_remote BOOLEAN DEFAULT FALSE,
    contract_type VARCHAR(50),  -- full_time, part_time, contract, temporary
    category VARCHAR(100),
    url TEXT,
    posted_date DATE,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Applications table: tracks job application pipeline
CREATE TABLE IF NOT EXISTS applications (
    application_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    job_id INTEGER NOT NULL REFERENCES job_postings(job_id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'saved',  -- saved, applied, interviewing, rejected, offer, accepted
    applied_date DATE,
    cover_letter TEXT,
    custom_resume TEXT,  -- Tailored resume for this application
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, job_id)
);

-- Saved jobs table: quick saves for jobs to review later
CREATE TABLE IF NOT EXISTS saved_jobs (
    saved_job_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    job_id INTEGER NOT NULL REFERENCES job_postings(job_id) ON DELETE CASCADE,
    match_score DECIMAL(5,2),  -- 0-100 score from semantic matching
    match_reasoning TEXT,  -- AI-generated explanation of fit
    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, job_id)
);

-- Interview notes table: tracks interview rounds and feedback
CREATE TABLE IF NOT EXISTS interview_notes (
    interview_id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    interview_date DATE NOT NULL,
    interview_type VARCHAR(50),  -- phone_screen, technical, behavioral, onsite, final
    interviewer_name VARCHAR(255),
    notes TEXT,
    follow_up_date DATE,
    follow_up_completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Contacts table: networking and referral tracking
CREATE TABLE IF NOT EXISTS contacts (
    contact_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    contact_name VARCHAR(255) NOT NULL,
    company VARCHAR(255),
    title VARCHAR(255),
    email VARCHAR(255),
    linkedin_url VARCHAR(500),
    relationship VARCHAR(100),  -- recruiter, hiring_manager, referral, colleague
    notes TEXT,
    last_contact_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_profiles_user_id ON profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_skills_user_id ON skills(user_id);
CREATE INDEX IF NOT EXISTS idx_applications_user_id ON applications(user_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_saved_jobs_user_id ON saved_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_job_postings_active ON job_postings(is_active);
CREATE INDEX IF NOT EXISTS idx_interview_notes_application_id ON interview_notes(application_id);
CREATE INDEX IF NOT EXISTS idx_contacts_user_id ON contacts(user_id);
