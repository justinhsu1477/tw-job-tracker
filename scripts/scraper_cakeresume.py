#!/usr/bin/env python3
from __future__ import annotations

"""
CakeResume Job Scraper - Searches jobs via CakeResume's public API.

CakeResume is Taiwan's second-largest tech job board, popular among
startups and international companies.

Usage:
    python scraper_cakeresume.py --config ~/.config/tw-job-hunter/config.json
    python scraper_cakeresume.py --keywords "後端工程師"
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))

from common.config import load_config
from common.dedup import deduplicate_jobs, filter_seen_jobs, generate_job_id

SEARCH_URL = "https://www.cakeresume.com/api/v3/job-listings"
BASE_URL = "https://www.cakeresume.com"

REQUEST_DELAY = 2  # seconds between requests


def _build_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://www.cakeresume.com/jobs",
    }


def _map_location(location: str) -> str:
    """Map location to CakeResume's location filter."""
    location_map = {
        "台北市": "Taipei, Taiwan",
        "新北市": "New Taipei City, Taiwan",
        "桃園市": "Taoyuan, Taiwan",
        "新竹市": "Hsinchu, Taiwan",
        "台中市": "Taichung, Taiwan",
        "台南市": "Tainan, Taiwan",
        "高雄市": "Kaohsiung, Taiwan",
    }
    return location_map.get(location, location)


def normalize_cakeresume_job(job: dict) -> dict:
    """Normalize a CakeResume job listing to common schema."""
    title = job.get("title", "") or ""
    company_data = job.get("company", {}) or {}
    company = company_data.get("name", "") or ""

    # Location
    location = job.get("flat_city", "") or ""
    if not location:
        loc_list = job.get("location_list", [])
        if loc_list:
            location = loc_list[0] if isinstance(loc_list[0], str) else str(loc_list[0])

    # URL
    page_path = job.get("page_path", "") or job.get("path", "")
    if page_path:
        job_url = f"{BASE_URL}/companies/{company_data.get('path', '')}/jobs/{page_path}"
    else:
        job_url = job.get("page_url", "") or ""
    if not job_url and job.get("id"):
        job_url = f"{BASE_URL}/jobs/{job['id']}"

    # Salary
    salary_min = job.get("salary_min") or 0
    salary_max = job.get("salary_max") or 0
    salary_type = job.get("salary_type", "monthly")
    if salary_min and salary_max:
        salary_desc = f"${salary_min:,}–${salary_max:,}"
        if salary_type == "yearly":
            salary_desc += " /年"
    elif salary_min:
        salary_desc = f"${salary_min:,}+"
    else:
        salary_desc = "待遇面議"

    # Posted date
    created_at = job.get("created_at", "") or job.get("published_at", "")
    posted_date = ""
    if created_at:
        try:
            if isinstance(created_at, (int, float)):
                posted_date = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d")
            else:
                posted_date = created_at[:10]
        except Exception:
            posted_date = str(created_at)[:10]

    # Remote
    remote = job.get("remote", False)
    if not remote:
        remote = any(kw in title.lower() for kw in ["遠端", "remote", "wfh"])

    # Description
    description = job.get("description_plain", "") or job.get("description", "") or ""
    # Strip HTML tags if present
    description = re.sub(r"<[^>]+>", " ", description).strip()

    # Experience
    exp_min = job.get("experience_min")
    exp_desc = f"{exp_min}年以上" if exp_min else "不拘"

    result = {
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "url": job_url,
        "posted_date": posted_date,
        "salary": salary_desc,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_type": salary_type,
        "employment_type": job.get("job_type", "全職"),
        "experience_level": exp_desc,
        "remote": remote,
        "source": "cakeresume",
        "scraped_at": datetime.now().isoformat(),
    }
    result["id"] = generate_job_id(result)
    return result


def search_cakeresume(
    keyword: str,
    location: str = "",
    page: int = 1,
    max_results: int = 20,
    client: httpx.Client | None = None,
) -> tuple[list[dict], int]:
    """Search CakeResume for jobs. Returns (jobs, total_count)."""
    params = {
        "q": keyword,
        "page": str(page),
        "per_page": str(min(max_results, 25)),
        "order": "latest",
    }
    if location:
        params["location"] = _map_location(location)

    headers = _build_headers()

    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=30)

    try:
        resp = client.get(SEARCH_URL, headers=headers, params=params, follow_redirects=True)
        if resp.status_code != 200:
            print(f"  CakeResume API error {resp.status_code}", file=sys.stderr)
            return [], 0

        ct = resp.headers.get("content-type", "")
        if "json" not in ct:
            print(f"  CakeResume returned non-JSON (content-type: {ct})", file=sys.stderr)
            return [], 0

        result = resp.json()
        # CakeResume API may return { "job_listings": [...], "total_count": N }
        # or { "data": [...], "meta": { "total": N } }
        jobs = result.get("job_listings") or result.get("data") or []
        if not isinstance(jobs, list):
            jobs = []
        total = result.get("total_count") or result.get("meta", {}).get("total", len(jobs))
        return jobs[:max_results], total
    except Exception as e:
        print(f"  CakeResume request error: {e}", file=sys.stderr)
        return [], 0
    finally:
        if own_client:
            client.close()


def scrape_jobs(
    config: dict,
    keywords: list[str] | None = None,
    location: str | None = None,
    skip_seen: bool = True,
) -> list[dict]:
    """Search CakeResume for each keyword, aggregate and deduplicate."""
    search_config = config.get("search", {})
    keywords_list = keywords or search_config.get("keywords", [])
    loc = location or search_config.get("location", "")
    max_results = search_config.get("max_results_per_query", 20)

    print(f"Provider: CakeResume | Location: {loc} | Keywords: {len(keywords_list)}")

    all_jobs = []
    with httpx.Client(timeout=30) as client:
        for kw in keywords_list:
            print(f"Searching: {kw}")
            raw_jobs, total = search_cakeresume(
                keyword=kw,
                location=loc,
                max_results=max_results,
                client=client,
            )
            normalized = [normalize_cakeresume_job(j) for j in raw_jobs]
            all_jobs.extend(normalized)
            print(f"  Found {len(normalized)} postings (total: {total})")

            if kw != keywords_list[-1]:
                time.sleep(REQUEST_DELAY)

        all_jobs = deduplicate_jobs(all_jobs)

        if skip_seen:
            all_jobs = filter_seen_jobs(all_jobs, config)

    all_jobs.sort(key=lambda j: j.get("posted_date", ""), reverse=True)
    print(f"Total: {len(all_jobs)} new jobs after dedup")
    return all_jobs


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Search jobs on CakeResume")
    parser.add_argument("--config", default="~/.config/tw-job-hunter/config.json")
    parser.add_argument("--keywords", nargs="+")
    parser.add_argument("--location")
    parser.add_argument("--output", "-o")
    parser.add_argument("--include-seen", action="store_true")

    args = parser.parse_args()
    config = load_config(args.config)

    jobs = scrape_jobs(
        config,
        keywords=args.keywords,
        location=args.location,
        skip_seen=not args.include_seen,
    )

    output = json.dumps(jobs, indent=2, ensure_ascii=False, default=str)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved {len(jobs)} jobs to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
