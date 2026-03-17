#!/usr/bin/env python3
from __future__ import annotations

"""
104人力銀行 Job Scraper - Searches jobs via 104.com.tw internal API.

104 is Taiwan's largest job board (~50% market share).
No API key required — uses the same public endpoints as the 104 website.

API Details:
- Search: GET https://www.104.com.tw/jobs/search/list
- Detail: GET https://www.104.com.tw/job/ajax/content/{job_no}
- Requires Referer header to work

Usage:
    python scraper_104.py --config ~/.config/tw-job-hunter/config.json
    python scraper_104.py --keywords "後端工程師" --location "台北市"
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

SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs"
DETAIL_URL = "https://www.104.com.tw/job/ajax/content/{job_no}"

SEARCH_REFERER = "https://www.104.com.tw/jobs/search/"
JOB_REFERER = "https://www.104.com.tw/job/{job_no}"

# 104 area codes for major Taiwan cities/counties
AREA_CODES = {
    "台北市": "6001001000",
    "新北市": "6001002000",
    "桃園市": "6001003000",
    "台中市": "6001006000",
    "台南市": "6001010000",
    "高雄市": "6001011000",
    "新竹市": "6001004000",
    "新竹縣": "6001005000",
    "基隆市": "6001016000",
    "嘉義市": "6001009000",
    "嘉義縣": "6001009000",
    "宜蘭縣": "6001015000",
    "花蓮縣": "6001019000",
    "台東縣": "6001020000",
    "苗栗縣": "6001007000",
    "彰化縣": "6001008000",
    "南投縣": "6001008000",
    "雲林縣": "6001009000",
    "屏東縣": "6001012000",
    "澎湖縣": "6001013000",
    "全台": "",
}

# Map config time_range to 104's mode parameter
TIME_RANGE_MAP = {
    "day": "1",
    "3days": "3",
    "week": "7",
    "month": "30",
}

REQUEST_DELAY = 3  # seconds between requests to avoid rate limiting


def _build_headers(referer: str) -> dict:
    """Build request headers with required Referer."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
    }


def _resolve_area_code(location: str) -> str:
    """Resolve a location string to a 104 area code."""
    if not location:
        return ""
    # Direct match
    if location in AREA_CODES:
        return AREA_CODES[location]
    # Partial match
    for name, code in AREA_CODES.items():
        if name in location or location in name:
            return code
    return ""


def _extract_job_no(link: str) -> str:
    """Extract job number from a 104 job link like '//www.104.com.tw/job/abc123'."""
    match = re.search(r"/job/([a-zA-Z0-9]+)", link)
    return match.group(1) if match else ""


def _format_salary(salary_info: dict) -> str:
    """Format salary from 104 job data."""
    salary_desc = salary_info.get("jobSalary", "") if isinstance(salary_info, dict) else ""
    if salary_desc:
        return salary_desc
    # Try to build from structured fields
    s_type = salary_info.get("salaryType") if isinstance(salary_info, dict) else None
    s_low = salary_info.get("salaryLow", 0) if isinstance(salary_info, dict) else 0
    s_high = salary_info.get("salaryHigh", 0) if isinstance(salary_info, dict) else 0
    if s_low and s_high:
        return f"${s_low:,}–${s_high:,}"
    elif s_low:
        return f"${s_low:,}+"
    return ""


def _parse_appear_date(appear_date: str) -> str:
    """Convert 104's appearDate (e.g. '20260317') to ISO format."""
    if not appear_date or len(appear_date) < 8:
        return ""
    try:
        return datetime.strptime(appear_date[:8], "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return appear_date


def normalize_104_job(job: dict) -> dict:
    """Normalize a 104 search result to the common job dict format."""
    title = job.get("jobName", "") or ""
    company = job.get("custName", "") or ""
    location = job.get("jobAddrNoDesc", "") or job.get("jobAddress", "") or ""

    # Build job URL from link field
    link = job.get("link", {})
    job_url = link.get("job", "") if isinstance(link, dict) else ""
    if job_url and not job_url.startswith("http"):
        job_url = "https:" + job_url

    posted_date = _parse_appear_date(str(job.get("appearDate", "")))

    # Salary
    s_low = job.get("salaryLow", 0) or 0
    s_high = job.get("salaryHigh", 0) or 0
    if s_low and s_high:
        salary_desc = f"${s_low:,}–${s_high:,}"
    elif s_low:
        salary_desc = f"${s_low:,}+"
    else:
        salary_desc = "待遇面議"

    # Employment type from period field (5=全職, 6=兼職, etc.)
    period = job.get("period", 0)
    period_map = {1: "全職", 2: "兼職", 3: "高階", 5: "全職", 6: "兼職"}
    employment_type = period_map.get(period, "全職")

    # Experience from s10 field (years)
    s10 = job.get("s10", 0)
    exp_desc = f"{s10}年以上" if s10 else "不拘"

    # Remote detection from remoteWorkType field
    # 0=not remote, 1=fully remote, 2=hybrid
    remote_type = job.get("remoteWorkType", 0)
    remote = remote_type > 0
    if not remote:
        remote = any(kw in title.lower() for kw in ["遠端", "remote", "在家", "居家辦公", "wfh"])

    # Description from search result (brief)
    description = job.get("description", "") or ""

    result = {
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "url": job_url,
        "posted_date": posted_date,
        "salary": salary_desc,
        "employment_type": employment_type,
        "experience_level": exp_desc,
        "remote": remote,
        "source": "104",
        "scraped_at": datetime.now().isoformat(),
    }
    result["id"] = generate_job_id(result)
    # Store job_no for detail fetching
    result["_job_no"] = _extract_job_no(job_url) or job.get("jobNo", "")
    return result


def search_104(
    keyword: str,
    area: str = "",
    page: int = 1,
    max_results: int = 20,
    time_range: str = "week",
    client: httpx.Client | None = None,
) -> tuple[list[dict], int]:
    """Call 104 search API for a single keyword. Returns (jobs, total_count)."""
    params = {
        "keyword": keyword,
        "kwop": "7",
        "order": "15",
        "asc": "0",
        "page": str(page),
        "pagesize": str(min(max_results, 20)),
        "mode": "s",
        "jobsource": "2018indexpoc",
        "ro": "0",
    }
    if area:
        params["area"] = area

    # Time range filter via isnew param
    isnew = TIME_RANGE_MAP.get(time_range)
    if isnew:
        params["isnew"] = isnew

    headers = _build_headers(SEARCH_REFERER)

    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=30)

    try:
        resp = client.get(SEARCH_URL, headers=headers, params=params, follow_redirects=True)
        if resp.status_code != 200:
            print(f"  104 API error {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            return [], 0
        ct = resp.headers.get("content-type", "")
        if "json" not in ct:
            print(f"  104 API returned non-JSON (content-type: {ct})", file=sys.stderr)
            return [], 0
        result = resp.json()
        jobs = result.get("data", [])
        if not isinstance(jobs, list):
            jobs = []
        metadata = result.get("metadata", {})
        pagination = metadata.get("pagination", {})
        total = pagination.get("total", len(jobs))
        return jobs[:max_results], total
    except Exception as e:
        print(f"  104 request error: {e}", file=sys.stderr)
        return [], 0
    finally:
        if own_client:
            client.close()


def fetch_job_detail(job_no: str, client: httpx.Client) -> dict:
    """Fetch full job detail from 104 detail API."""
    url = DETAIL_URL.format(job_no=job_no)
    referer = JOB_REFERER.format(job_no=job_no)
    headers = _build_headers(referer)

    try:
        resp = client.get(url, headers=headers)
        if resp.status_code != 200:
            return {}
        return resp.json().get("data", {})
    except Exception:
        return {}


def enrich_with_details(jobs: list[dict], client: httpx.Client, max_detail: int = 30) -> list[dict]:
    """Fetch full descriptions for top jobs via detail API."""
    for i, job in enumerate(jobs[:max_detail]):
        job_no = job.get("_job_no", "")
        if not job_no:
            continue

        detail = fetch_job_detail(job_no, client)
        if not detail:
            continue

        # Extract full description from detail
        condition = detail.get("condition", {})
        job_detail = detail.get("jobDetail", {})

        desc_parts = []
        if job_detail.get("jobDescription"):
            desc_parts.append(job_detail["jobDescription"])
        if condition.get("other"):
            desc_parts.append(condition["other"])
        if condition.get("specialty"):
            specialties = condition["specialty"]
            if isinstance(specialties, list):
                desc_parts.append("專長：" + "、".join(s.get("description", "") for s in specialties if isinstance(s, dict)))

        if desc_parts:
            job["description"] = "\n\n".join(desc_parts)

        # Enrich salary if available from detail
        if not job["salary"] and detail.get("jobDetail", {}).get("salary"):
            job["salary"] = str(detail["jobDetail"]["salary"])

        # Enrich experience level
        if condition.get("workExp"):
            job["experience_level"] = condition["workExp"]

        # Check for remote in welfare/description
        welfare = detail.get("welfare", {})
        welfare_text = str(welfare) if welfare else ""
        if any(kw in welfare_text for kw in ["遠端", "remote", "在家", "居家"]):
            job["remote"] = True

        if i < max_detail - 1:
            time.sleep(REQUEST_DELAY)

    # Remove internal _job_no field
    for job in jobs:
        job.pop("_job_no", None)

    return jobs


def scrape_jobs(
    config: dict,
    keywords: list[str] | None = None,
    location: str | None = None,
    skip_seen: bool = True,
) -> list[dict]:
    """Search jobs on 104 for each keyword, aggregate and deduplicate."""
    search_config = config.get("search", {})
    keywords_list = keywords or search_config.get("keywords", [])
    loc = location or search_config.get("location", "")
    area_code = search_config.get("area_code", "") or _resolve_area_code(loc)
    time_range = search_config.get("time_range", "week")
    max_results = search_config.get("max_results_per_query", 20)
    fetch_details = config.get("fetch_details", True)

    print(f"Provider: 104人力銀行 | Location: {loc} ({area_code}) | Time: {time_range}")

    all_jobs = []
    with httpx.Client(timeout=30) as client:
        for kw in keywords_list:
            print(f"Searching: {kw}")
            raw_jobs, total = search_104(
                keyword=kw,
                area=area_code,
                max_results=max_results,
                time_range=time_range,
                client=client,
            )
            normalized = [normalize_104_job(j) for j in raw_jobs]
            all_jobs.extend(normalized)
            print(f"  Found {len(normalized)} postings (total available: {total})")

            if kw != keywords_list[-1]:
                time.sleep(REQUEST_DELAY)

        # Deduplicate across keywords
        all_jobs = deduplicate_jobs(all_jobs)

        # Filter previously seen jobs
        if skip_seen:
            all_jobs = filter_seen_jobs(all_jobs, config)

        # Fetch full descriptions for remaining jobs
        if fetch_details and all_jobs:
            print(f"Fetching details for {min(len(all_jobs), 30)} jobs...")
            all_jobs = enrich_with_details(all_jobs, client, max_detail=30)

    # Sort by posted date (newest first)
    all_jobs.sort(key=lambda j: j.get("posted_date", ""), reverse=True)

    print(f"Total: {len(all_jobs)} new jobs after dedup")
    return all_jobs


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Search jobs on 104人力銀行")
    parser.add_argument("--config", default="~/.config/tw-job-hunter/config.json")
    parser.add_argument("--keywords", nargs="+")
    parser.add_argument("--location")
    parser.add_argument("--output", "-o")
    parser.add_argument("--include-seen", action="store_true")
    parser.add_argument("--no-details", action="store_true",
                        help="Skip fetching full job descriptions (faster)")

    args = parser.parse_args()
    config = load_config(args.config)

    if args.no_details:
        config["fetch_details"] = False

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
