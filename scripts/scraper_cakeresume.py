#!/usr/bin/env python3
from __future__ import annotations

"""
Cake (formerly CakeResume) Job Scraper - Scrapes jobs from cake.me.

Cake rebranded from CakeResume in mid-2024 and migrated to cake.me.
The old JSON API is gone. This scraper uses the Next.js _next/data
endpoint which returns structured job data as JSON.

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
from urllib.parse import quote

import httpx

sys.path.insert(0, str(Path(__file__).parent))

from common.config import load_config
from common.dedup import deduplicate_jobs, filter_seen_jobs, generate_job_id

BASE_URL = "https://www.cake.me"
JOBS_PAGE_URL = "https://www.cake.me/jobs"

REQUEST_DELAY = 2  # seconds between requests


def _build_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
        "Referer": "https://www.cake.me/jobs",
    }


def _get_build_id(client: httpx.Client) -> str | None:
    """Fetch the Next.js buildId from the main page."""
    try:
        resp = client.get(JOBS_PAGE_URL, headers=_build_headers(), follow_redirects=True)
        m = re.search(r'"buildId"\s*:\s*"([^"]+)"', resp.text)
        if m:
            return m.group(1)
    except Exception as e:
        print(f"  Failed to get Cake buildId: {e}", file=sys.stderr)
    return None


def _map_location(location: str) -> str:
    """Map location to Cake's location filter parameter."""
    location_map = {
        "台北市": "Taiwan",
        "新北市": "Taiwan",
        "桃園市": "Taiwan",
        "新竹市": "Taiwan",
        "台中市": "Taiwan",
        "台南市": "Taiwan",
        "高雄市": "Taiwan",
    }
    return location_map.get(location, location)


def normalize_cakeresume_job(job: dict) -> dict:
    """Normalize a Cake job listing to common schema."""
    title = job.get("title", "") or ""
    # Strip highlight <mark> tags
    title = re.sub(r"</?mark>", "", title)

    page_data = job.get("page", {}) or {}
    company = page_data.get("name", "") or ""
    company = re.sub(r"</?mark>", "", company)

    # Location
    locations = job.get("locations", []) or []
    if locations:
        location = locations[0] if isinstance(locations[0], str) else str(locations[0])
    else:
        location = ""

    # URL
    path = job.get("path", "")
    company_path = page_data.get("path", "")
    if path and company_path:
        job_url = f"{BASE_URL}/companies/{company_path}/jobs/{path}"
    elif path:
        job_url = f"{BASE_URL}/jobs/{path}"
    else:
        job_url = ""

    # Salary
    salary_data = job.get("salary", {}) or {}
    salary_min = int(float(salary_data.get("min", 0) or 0))
    salary_max = int(float(salary_data.get("max", 0) or 0))
    salary_type_raw = salary_data.get("type", "per_month")
    currency = salary_data.get("currency", "TWD")

    # Map Cake salary types to our schema
    if "year" in salary_type_raw:
        salary_type = "yearly"
    elif "hour" in salary_type_raw:
        salary_type = "hourly"
    else:
        salary_type = "monthly"

    if salary_min and salary_max:
        salary_desc = f"${salary_min:,}–${salary_max:,}"
        if salary_type == "yearly":
            salary_desc += " /年"
        elif salary_type == "hourly":
            salary_desc += " /時"
    elif salary_min:
        salary_desc = f"${salary_min:,}+"
    else:
        salary_desc = "待遇面議"

    # Posted/updated date
    content_updated = job.get("contentUpdatedAt", "") or ""
    posted_date = content_updated[:10] if content_updated else ""

    # Remote
    remote = False
    job_type = job.get("jobType", "") or ""
    if "remote" in job_type.lower() or any(
        kw in title.lower() for kw in ["遠端", "remote", "wfh"]
    ):
        remote = True

    # Description
    description = job.get("description", "") or ""
    description = re.sub(r"<[^>]+>", " ", description).strip()

    # Tags
    tags = job.get("tags", []) or []
    if tags:
        description += "\n\n技能標籤：" + "、".join(tags)

    # Experience
    min_exp = job.get("minWorkExpYear")
    exp_desc = f"{min_exp}年以上" if min_exp else "不拘"

    # Employment type
    emp_type_map = {
        "full_time": "全職",
        "part_time": "兼職",
        "contract": "約聘",
        "internship": "實習",
    }
    employment_type = emp_type_map.get(job_type, "全職")

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
        "employment_type": employment_type,
        "experience_level": exp_desc,
        "remote": remote,
        "source": "cakeresume",
        "scraped_at": datetime.now().isoformat(),
    }
    result["id"] = generate_job_id(result)
    return result


def search_cakeresume(
    keyword: str,
    build_id: str,
    location: str = "",
    page: int = 1,
    max_results: int = 20,
    client: httpx.Client | None = None,
) -> tuple[list[dict], int]:
    """Search Cake for jobs via _next/data endpoint. Returns (jobs, total_count)."""
    encoded_kw = quote(keyword, safe="")
    url = f"{BASE_URL}/_next/data/{build_id}/zh-TW/jobs/{encoded_kw}.json"

    params = {"keyword": keyword}
    if page > 1:
        params["page"] = str(page)
    # Note: cake.me _next/data endpoint does not support location_list params.
    # The zh-TW locale already filters to Taiwan region by default.

    headers = _build_headers()

    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=30)

    try:
        resp = client.get(url, headers=headers, params=params, follow_redirects=True)
        if resp.status_code != 200:
            print(f"  Cake API error {resp.status_code}", file=sys.stderr)
            return [], 0

        ct = resp.headers.get("content-type", "")
        if "json" not in ct:
            print(f"  Cake returned non-JSON (content-type: {ct})", file=sys.stderr)
            return [], 0

        data = resp.json()
        page_props = data.get("pageProps", {})
        initial_state = page_props.get("initialState", {})
        job_search = initial_state.get("jobSearch", {})

        # Jobs are stored as a dict keyed by path ID
        entities = job_search.get("entityByPathId", {})
        jobs = list(entities.values())

        total = len(jobs)
        return jobs[:max_results], total
    except Exception as e:
        print(f"  Cake request error: {e}", file=sys.stderr)
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
    """Search Cake for each keyword, aggregate and deduplicate."""
    search_config = config.get("search", {})
    keywords_list = keywords or search_config.get("keywords", [])
    loc = location or search_config.get("location", "")
    max_results = search_config.get("max_results_per_query", 20)

    print(f"Provider: Cake (CakeResume) | Location: {loc} | Keywords: {len(keywords_list)}")

    all_jobs = []
    with httpx.Client(timeout=30) as client:
        # Get the Next.js build ID first
        build_id = _get_build_id(client)
        if not build_id:
            print("  ERROR: Could not get Cake buildId, skipping", file=sys.stderr)
            return []

        print(f"  Build ID: {build_id[:12]}...")

        for kw in keywords_list:
            print(f"Searching: {kw}")
            raw_jobs, total = search_cakeresume(
                keyword=kw,
                build_id=build_id,
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

    parser = argparse.ArgumentParser(description="Search jobs on Cake (CakeResume)")
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
