# Profile Match Scores - Implementation Guide

✅ **Status: Fully Implemented and Working!**

## Overview

The job search now shows **TWO match scores** for each job:

1. **🔍 Query Match** - How well the job matches the user's search query
2. **👤 Profile Match** - How well the job matches the user's resume/profile

## Architecture

### Frontend: `templates/search.html`
- Sends `include_profile_match: true` to backend (line 113)
- Displays both query and profile match badges (lines 161-201)
- Gracefully handles missing profile scores (shows only query match)

### Backend: `dashboard/app.py`
- `/api/search` endpoint reads `include_profile_match` parameter (line 385)
- Calls `add_profile_match_scores()` function to compute scores (lines 330-367)
- Returns both `similarity` and `profile_match_score` for each job

### Database: `profile_embeddings` table
- Stores chunked resume embeddings (user_id, chunk_index, chunk_text, embedding)
- Vector similarity search using pgvector `<=>` operator
- Computes MAX similarity across all chunks for each job

## How It Works

### 1. User Searches
```javascript
// Frontend sends request
fetch('/api/search', {
  method: 'POST',
  body: JSON.stringify({
    query: 'data engineer remote',
    include_profile_match: true  // Request profile scores
  })
})
```

### 2. Backend Computes Matches
```python
# In app.py - api_search() function
if include_profile_match:
    user = get_current_user()
    user_id = get_or_create_user(user['email'], user['name'])
    if user_id:
        jobs = add_profile_match_scores(jobs, user_id)
```

### 3. Profile Match Query
```sql
SELECT 
    je.job_id,
    MAX(1 - (pe.embedding <=> je.embedding)) AS profile_match_score
FROM job_embeddings je
CROSS JOIN profile_embeddings pe
WHERE pe.user_id = %s
  AND je.job_id = ANY(%s)
GROUP BY je.job_id
```

### 4. Response Format

```json
{
  "success": true,
  "query": "remote backend roles",
  "count": 20,
  "jobs": [
    {
      "job_id": 123,
      "title": "Senior Backend Engineer",
      "company": "Acme Corp",
      "location": "San Francisco, CA",
      "description": "...",
      "url": "https://...",
      "salary_min": 150000,
      "salary_max": 200000,
      "posted_date": "2026-08-08",
      "similarity": 0.85,              // Match to search query (existing)
      "profile_match_score": 0.92      // Match to user profile (NEW)
    },
    ...
  ]
}
```

## Frontend Display

Each job card shows both badges side-by-side:

```
┌────────────────────────────────────────────────────────┐
│ Senior Backend Engineer    [🔍 85% query] [👤 92% profile match] │
│ Acme Corp • San Francisco, CA                         │
└────────────────────────────────────────────────────────┘
```

**Color Coding for Profile Match:**
- 🟢 **80%+** = Green badge (Excellent Match)
- 🔵 **70-79%** = Blue badge (Strong Match)
- 🔵 **60-69%** = Info badge (Good Match)
- 🟡 **50-59%** = Yellow badge (Fair Match)
- ⚪ **<50%** = Gray badge (Low Match)

## Edge Cases (Handled Gracefully)

### User Not Logged In
✅ `profile_match_score` is `null`
✅ Frontend shows only query match badge
✅ No errors or broken UI

### User Has No Profile Embeddings
✅ `profile_match_score` is `null`
✅ Frontend shows only query match badge
💡 Prompt user: "Upload your resume to see profile match scores!"

### Profile Embeddings Not Yet Generated
📓 Run the ingestion notebook: `dashboard/notebooks/ingest_profile_embeddings`
⚙️ Or queue for background processing after resume upload

## Files in This Implementation

### Core Files (Already Implemented)
- ✅ `dashboard/templates/search.html` - Frontend with dual badges
- ✅ `dashboard/app.py` - Backend API with profile matching
- ✅ `dashboard/notebooks/ingest_profile_embeddings.py` - Generates embeddings
- ✅ `sql/search_jobs_with_profile_match.sql` - Reference SQL queries

### Database Schema
```sql
CREATE TABLE profile_embeddings (
    user_id INTEGER REFERENCES users(user_id),
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, chunk_index)
);
```

## Testing Checklist

- ✅ Anonymous user: Shows only query match
- ✅ Logged-in user (no profile): Shows only query match
- ✅ Logged-in user (with profile): Shows BOTH match scores
- ✅ Profile match scores are accurate (0.0-1.0 range)
- ✅ UI gracefully handles missing profile scores

## Performance Notes

- Profile match query uses `CROSS JOIN` across all user chunks
- Computes MAX similarity (best matching chunk wins)
- Query is fast due to pgvector indexing on embeddings
- Only runs when `include_profile_match: true` is sent

## Future Enhancements

💡 **Sort by Profile Match**: Add toggle to sort results by profile score instead of query score
💡 **Match Explanation**: Show which resume section matched best
💡 **Threshold Filtering**: Filter jobs below certain profile match threshold
💡 **Combined Score**: Weighted combination of query + profile match

---

**Implementation Complete!** 🎉

For reference SQL patterns, see: `sql/search_jobs_with_profile_match.sql`
