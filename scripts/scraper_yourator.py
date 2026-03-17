#!/usr/bin/env python3
from __future__ import annotations

"""
Yourator Job Scraper - Searches jobs via Yourator's public API.

Yourator specializes in startup/tech jobs in Taiwan.
Public JSON API, no authentication required.

Usage:
    python scraper_yourator.py --config ~/.config/tw-job-hunter/config.json
    python scraper_yourator.py --keywords "後端工程師"
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

SEARCH_URL = "https://www.yourator.co/api/v2/jobs"
BASE_URL = "https://www.yourator.co"

REQUEST_DELAY = 2  # seconds between requests


def _build_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://www.yourator.co/jobs",
    }


def _map_area(location: str) -> str:
    """Map location to Yourator area filter."""
    area_map = {
        "台北市": "taipei-city",
        "新北市": "new-taipei-city",
        "桃園市": "taoyuan-city",
        "新竹市": "hsinchu",
        "台中市": "taichung-city",
        "台南市": "tainan-city",
        "高雄市": "kaohsiung-city",
    }
    return area_map.get(location, "")


def normalize_yourator_job(job: dict) -> dict:
    """Normalize a Yourator job to common schema."""
    title = job.get("name", "") or job.get("title", "") or ""
    company_data = job.get("company", {}) or {}
    company = company_data.get("brand", "") or company_data.get("name", "") or ""

    # Location
    location = job.get("city", "") or ""
    if not location:
        area = job.get("area", "")
        location = area if isinstance(area, str) else ""

    # URL
    path = job.get("path", "") or ""
    if path:
        job_url = f"{BASE_URL}{path}" if path.startswith("/") else f"{BASE_URL}/{path}"
    else:
        job_url = job.get("url", "") or ""
    if not job_url and job.get("id"):
        job_url = f"{BASE_URL}/companies/{company_data.get('path', '')}/jobs/{job['id']}"

    # Salary
    salary_min = job.get("salary_min") or job.get("min_salary") or 0
    salary_max = job.get("salary_max") or job.get("max_salary") or 0
    salary_type = job.get("salary_type", "monthly")
    if salary_min and salary_max:
        salary_desc = f"${salary_min:,}–${salary_max:,}"
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
                posted_date = str(created_at)[:10]
        except Exception:
            posted_date = ""

    # Remote
    remote = job.get("remote", False) or job.get("is_remote", False)
    if not remote:
        remote = any(kw in title.lower() for kw in ["遠端", "remote", "wfh"])

    # Description - combine detail fields and tech tags
    desc_parts = []
    for field in ("description", "requirement", "description_plain"):
        val = job.get(field, "")
        if val:
            desc_parts.append(re.sub(r"<[^>]+>", " ", val).strip())

    # Add tech tags to description for better scoring
    tags = job.get("tags", []) or job.get("skills", [])
    if tags:
        tag_names = []
        for t in tags:
            if isinstance(t, str):
                tag_names.append(t)
            elif isinstance(t, dict):
                tag_names.append(t.get("name", ""))
        if tag_names:
            desc_parts.append("技能標籤：" + "、".join(tag_names))

    description = "\n\n".join(desc_parts)

    # Experience
    exp_min = job.get("experience_min") or job.get("min_experience")
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
        "employment_type": job.get("employment_type", "全職"),
        "experience_level": exp_desc,
        "remote": remote,
        "source": "yourator",
        "scraped_at": datetime.now().isoformat(),
    }
    result["id"] = generate_job_id(result)
    return result


def search_yourator(
    keyword: str,
    area: str = "",
    page: int = 1,
    max_results: int = 20,
    client: httpx.Client | None = None,
) -> tuple[list[dict], int]:
    """Search Yourator for jobs. Returns (jobs, total_count)."""
    params = {
        "term": keyword,
        "page": str(page),
    }
    if area:
        params["area"] = area

    headers = _build_headers()

    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=30)

    try:
        resp = client.get(SEARCH_URL, headers=headers, params=params, follow_redirects=True)
        if resp.status_code != 200:
            print(f"  Yourator API error {resp.status_code}", file=sys.stderr)
            return [], 0

        ct = resp.headers.get("content-type", "")
        if "json" not in ct:
            print(f"  Yourator returned non-JSON (content-type: {ct})", file=sys.stderr)
            return [], 0

        result = resp.json()
        # Yourator returns { "jobs": [...], "total": N }
        # or { "data": [...], "meta": {...} }
        jobs = result.get("jobs") or result.get("data") or []
        if not isinstance(jobs, list):
            jobs = []
        total = result.get("total") or result.get("meta", {}).get("total", len(jobs))
        return jobs[:max_results], total
    except Exception as e:
        print(f"  Yourator request error: {e}", file=sys.stderr)
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
    """Search Yourator for each keyword, aggregate and deduplicate."""
    search_config = config.get("search", {})
    keywords_list = keywords or search_config.get("keywords", [])
    loc = location or search_config.get("location", "")
    area = _map_area(loc)
    max_results = search_config.get("max_results_per_query", 20)

    print(f"Provider: Yourator | Location: {loc} ({area}) | Keywords: {len(keywords_list)}")

    all_jobs = []
    with httpx.Client(timeout=30) as client:
        for kw in keywords_list:
            print(f"Searching: {kw}")
            raw_jobs, total = search_yourator(
                keyword=kw,
                area=area,
                max_results=max_results,
                client=client,
            )
            normalized = [normalize_yourator_job(j) for j in raw_jobs]
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
    parser = argparse.ArgumentParser(description="Search jobs on Yourator")
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
