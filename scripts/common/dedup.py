from __future__ import annotations

"""Job deduplication logic for Taiwan job sites."""

import hashlib
import re
from pathlib import Path


def generate_job_id(job: dict) -> str:
    """Generate a unique ID for a job based on URL (primary) or title+company+location."""
    url = job.get("url", "").strip()
    if url:
        return hashlib.md5(url.encode()).hexdigest()[:12]
    key = f"{job.get('title', '')}-{job.get('company', '')}-{job.get('location', '')}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation for fuzzy title matching.

    Handles both English and Chinese characters.
    """
    # Keep Chinese characters (\\u4e00-\\u9fff), alphanumeric, and spaces
    return re.sub(r"[^\u4e00-\u9fffa-z0-9 ]", "", title.lower()).strip()


def deduplicate_jobs(jobs: list[dict]) -> list[dict]:
    """Remove duplicate jobs.

    Pass 1: deduplicate by URL (exact).
    Pass 2: deduplicate by normalized title, keeping the best source.
    """
    SOURCE_RANK = {"104": 0, "cakeresume": 1, "yourator": 2, "1111": 3}

    # Pass 1: URL dedup
    seen_urls: set[str] = set()
    url_unique: list[dict] = []
    for job in jobs:
        url = job.get("url", "").strip()
        if url not in seen_urls:
            seen_urls.add(url)
            url_unique.append(job)

    # Pass 2: title dedup — keep best-source version per unique title
    title_map: dict[str, dict] = {}
    for job in url_unique:
        key = _normalize_title(job.get("title", ""))
        if not key:
            continue
        if key not in title_map:
            title_map[key] = job
        else:
            existing_rank = SOURCE_RANK.get(title_map[key].get("source", ""), 99)
            new_rank = SOURCE_RANK.get(job.get("source", ""), 99)
            if new_rank < existing_rank:
                title_map[key] = job

    return list(title_map.values())


def load_seen_job_ids(config: dict) -> set[str]:
    """Load previously seen job IDs from Notion tracker DB via skills_cache.

    The skills_cache.json may contain a 'seen_job_ids' list written by
    the Claude skill flow after reading the Notion Job Tracker DB.
    """
    import json

    cache_path = Path("~/.config/tw-job-hunter/skills_cache.json").expanduser()
    if not cache_path.exists():
        return set()

    try:
        with open(cache_path) as f:
            cache = json.load(f)
        return set(cache.get("seen_job_ids", []))
    except Exception:
        return set()


def filter_seen_jobs(jobs: list[dict], config: dict) -> list[dict]:
    """Filter out jobs that have already been seen."""
    seen_ids = load_seen_job_ids(config)
    if not seen_ids:
        return jobs
    original_count = len(jobs)
    filtered = [j for j in jobs if j.get("id") not in seen_ids]
    print(f"Filtered {original_count - len(filtered)} previously seen jobs")
    return filtered
