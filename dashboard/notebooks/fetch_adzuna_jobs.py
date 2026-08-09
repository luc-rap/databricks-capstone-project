#!/usr/bin/env python3
"""
Local Adzuna Job Fetcher
========================
Run this script on your local machine (with internet access) to fetch job postings
from Adzuna API and save them to a CSV file.

Usage:
    python fetch_adzuna_jobs.py

Requirements:
    pip install requests pandas

The script will create a CSV file that you can upload to Databricks.
"""

import requests
import pandas as pd
from datetime import datetime
import sys

# ============================================
# CONFIGURATION - Update these values
# ============================================
ADZUNA_APP_ID = ""  # Replace with your actual app_id
ADZUNA_APP_KEY = ""  # I revoked the key... but go to https://developer.adzuna.com/ and just get your own

SEARCH_QUERY = "data engineer"
LOCATION_FILTER = "Florida"  # Leave empty "" for all US
RESULTS_PER_PAGE = 50
MAX_PAGES = 5  # Fetch up to 5 pages (250 jobs max)

# For local execution: saves to current directory
OUTPUT_FILE = f"adzuna_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# For Databricks execution: uncomment and update with your volume path
# OUTPUT_FILE = f"/Volumes/main/default/your_volume/adzuna_jobs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# ============================================
# Main Script
# ============================================

def fetch_adzuna_jobs(search_what, search_where, max_pages=5):
    """Fetch job postings from Adzuna API"""
    
    all_jobs = []
    country = "us"
    
    print(f"🔍 Searching for: '{search_what}'")
    if search_where:
        print(f"📍 Location: '{search_where}'")
    else:
        print(f"📍 Location: All US")
    print(f"📄 Fetching up to {max_pages} pages ({RESULTS_PER_PAGE} jobs/page)\n")
    
    for page in range(1, max_pages + 1):
        print(f"Fetching page {page}...", end=" ")
        
        # Build API parameters
        api_params = {
            "app_id": ADZUNA_APP_ID,
            "app_key": ADZUNA_APP_KEY,
            "what": search_what,
            "results_per_page": RESULTS_PER_PAGE,
        }
        
        if search_where:
            api_params["where"] = search_where
        
        try:
            response = requests.get(
                f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}",
                params=api_params,
                timeout=30
            )
            response.raise_for_status()
            
            jobs_data = response.json()
            jobs = jobs_data.get("results", [])
            
            if not jobs:
                print("No more results")
                break
            
            all_jobs.extend(jobs)
            print(f"✅ Got {len(jobs)} jobs")
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error: {e}")
            break
    
    return all_jobs


def parse_jobs_to_dataframe(jobs):
    """Convert raw Adzuna API response to pandas DataFrame"""
    
    records = []
    for job in jobs:
        # Extract nested fields safely
        company = job.get("company", {})
        if isinstance(company, dict):
            company_name = company.get("display_name")
        else:
            company_name = company
        
        location = job.get("location", {})
        if isinstance(location, dict):
            location_name = location.get("display_name")
        else:
            location_name = location
        
        category = job.get("category", {})
        if isinstance(category, dict):
            category_label = category.get("label")
        else:
            category_label = None
        
        # Build record matching the Lakebase schema
        record = {
            "external_id": str(job.get("id")),
            "title": job.get("title"),
            "company": company_name,
            "location": location_name,
            "description": job.get("description", ""),
            "url": job.get("redirect_url"),
            "salary_min": job.get("salary_min"),
            "salary_max": job.get("salary_max"),
            "contract_type": job.get("contract_type"),
            "category": category_label,
            "posted_date": job.get("created"),
            "fetched_at": datetime.now().isoformat()
        }
        
        records.append(record)
    
    return pd.DataFrame(records)


def main():
    print("="*60)
    print("Adzuna Job Fetcher (Local Script)")
    print("="*60 + "\n")
    
    # Fetch jobs
    jobs = fetch_adzuna_jobs(
        search_what=SEARCH_QUERY,
        search_where=LOCATION_FILTER,
        max_pages=MAX_PAGES
    )
    
    if not jobs:
        print("\n❌ No jobs fetched. Exiting.")
        sys.exit(1)
    
    print(f"\n✅ Total jobs fetched: {len(jobs)}")
    
    # Convert to DataFrame
    df = parse_jobs_to_dataframe(jobs)
    
    # Save to CSV
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\n💾 Saved to: {OUTPUT_FILE}")
    
    # Show preview
    print(f"\n📊 Preview (first 5 jobs):")
    print("-" * 60)
    for idx, row in df.head(5).iterrows():
        print(f"{idx+1}. {row['title']}")
        print(f"   Company: {row['company']}")
        print(f"   Location: {row['location']}")
        salary = ""
        if pd.notna(row['salary_min']) and pd.notna(row['salary_max']):
            salary = f"${row['salary_min']:,.0f} - ${row['salary_max']:,.0f}"
        elif pd.notna(row['salary_max']):
            salary = f"Up to ${row['salary_max']:,.0f}"
        if salary:
            print(f"   Salary: {salary}")
        print()
    
    print("="*60)
    print("✅ DONE!")
    print("="*60)
    print(f"\nNext steps:")
    print(f"1. Upload '{OUTPUT_FILE}' to Databricks (DBFS or Volume)")
    print(f"2. Use the ingestion notebook to load it into Lakebase")
    print(f"\nExample upload command:")
    print(f"   databricks fs cp {OUTPUT_FILE} dbfs:/FileStore/{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
