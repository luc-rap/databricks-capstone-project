-- Sample data for testing the AI Job Hunting Copilot
-- Insert test users, profiles, skills, and job postings

-- Sample user
INSERT INTO users (email, full_name) VALUES
('test.user@example.com', 'Test User')
ON CONFLICT (email) DO NOTHING;

-- Sample profile
INSERT INTO profiles (
    user_id, 
    target_roles, 
    location_preferences,
    remote_preference,
    salary_min,
    salary_max,
    years_experience,
    resume_text
) VALUES (
    (SELECT user_id FROM users WHERE email = 'test.user@example.com'),
    ARRAY['Software Engineer', 'Backend Developer', 'Data Engineer'],
    ARRAY['San Francisco', 'Remote'],
    'remote',
    100000,
    150000,
    5,
    'Experienced software engineer with 5 years building scalable backend systems. Expert in Python, distributed systems, and cloud infrastructure.'
)
ON CONFLICT (user_id) DO NOTHING;

-- Sample skills
INSERT INTO skills (user_id, skill_name, proficiency_level, years_of_experience, is_primary) VALUES
((SELECT user_id FROM users WHERE email = 'test.user@example.com'), 'Python', 'expert', 5.0, TRUE),
((SELECT user_id FROM users WHERE email = 'test.user@example.com'), 'SQL', 'advanced', 4.0, TRUE),
((SELECT user_id FROM users WHERE email = 'test.user@example.com'), 'Docker', 'advanced', 3.0, FALSE),
((SELECT user_id FROM users WHERE email = 'test.user@example.com'), 'Kubernetes', 'intermediate', 2.0, FALSE),
((SELECT user_id FROM users WHERE email = 'test.user@example.com'), 'AWS', 'advanced', 4.0, TRUE)
ON CONFLICT (user_id, skill_name) DO NOTHING;

-- Sample job postings (you would fetch these from Adzuna API in production)
INSERT INTO job_postings (
    external_id,
    title,
    company,
    location,
    salary_min,
    salary_max,
    description,
    is_remote,
    contract_type,
    category,
    url,
    posted_date
) VALUES
(
    'adzuna_12345',
    'Senior Backend Engineer',
    'Tech Startup Inc',
    'San Francisco, CA',
    120000,
    160000,
    'We are looking for a Senior Backend Engineer to join our team. You will build scalable APIs using Python and work with modern cloud infrastructure. Requirements: 5+ years Python experience, strong system design skills, experience with Docker/Kubernetes.',
    FALSE,
    'full_time',
    'Engineering',
    'https://example.com/job/12345',
    CURRENT_DATE - INTERVAL '2 days'
),
(
    'adzuna_67890',
    'Remote Python Developer',
    'Remote First Company',
    'Remote',
    100000,
    140000,
    'Fully remote Python developer role. Build data pipelines and backend services. Must have: Python expertise, SQL proficiency, experience with cloud platforms (AWS/GCP).',
    TRUE,
    'full_time',
    'Engineering',
    'https://example.com/job/67890',
    CURRENT_DATE - INTERVAL '1 day'
)
ON CONFLICT (external_id) DO NOTHING;
