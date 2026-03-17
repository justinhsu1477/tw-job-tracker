#!/usr/bin/env python3
"""
TW Job Search CLI - Search for jobs on Taiwan job boards and output JSON.

Supports:
  - 104 (default): 104人力銀行 — no API key required
  - cakeresume: CakeResume — tech/startup focused
  - yourator: Yourator — startup/tech jobs
  - all: Run all providers, merge and deduplicate

Usage:
    python run_search.py -o /tmp/jobs.json
    python run_search.py --provider all -o /tmp/jobs.json
    python run_search.py --provider cakeresume -o /tmp/jobs.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common.config import load_config
from common.dedup import deduplicate_jobs

PROVIDERS = ["104", "cakeresume", "yourator", "all"]


def _run_provider(provider: str, common_kwargs: dict) -> list[dict]:
    """Run a single provider and return jobs."""
    if provider == "104":
        from scraper_104 import scrape_jobs as scrape_104
        return scrape_104(**common_kwargs)
    elif provider == "cakeresume":
        from scraper_cakeresume import scrape_jobs as scrape_cake
        return scrape_cake(**common_kwargs)
    elif provider == "yourator":
        from scraper_yourator import scrape_jobs as scrape_yourator
        return scrape_yourator(**common_kwargs)
    else:
        print(f"Unknown provider: {provider}", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(description="Search for jobs on Taiwan job boards")
    parser.add_argument("--config", default="~/.config/tw-job-hunter/config.json",
                        help="Path to config file")
    parser.add_argument("--provider", choices=PROVIDERS,
                        help="Search provider (overrides config search_provider)")
    parser.add_argument("--keywords", nargs="+", help="Override search keywords")
    parser.add_argument("--location", help="Override job location")
    parser.add_argument("--output", "-o", help="Output JSON file (default: stdout)")
    parser.add_argument("--include-seen", action="store_true",
                        help="Include previously seen jobs")
    parser.add_argument("--no-details", action="store_true",
                        help="Skip fetching full job descriptions (faster, 104 only)")

    args = parser.parse_args()
    config = load_config(args.config)

    provider = args.provider or config.get("search_provider", "104")
    print(f"Using search provider: {provider}")

    if args.no_details:
        config["fetch_details"] = False

    common_kwargs = dict(
        config=config,
        keywords=args.keywords,
        location=args.location,
        skip_seen=not args.include_seen,
    )

    if provider == "all":
        # Run all providers and merge
        all_jobs = []
        for p in ["104", "cakeresume", "yourator"]:
            print(f"\n{'='*50}")
            print(f"Running provider: {p}")
            print(f"{'='*50}")
            try:
                jobs = _run_provider(p, common_kwargs)
                all_jobs.extend(jobs)
                print(f"  → {len(jobs)} jobs from {p}")
            except Exception as e:
                print(f"  → {p} failed: {e}", file=sys.stderr)

        # Cross-provider dedup
        print(f"\nMerging: {len(all_jobs)} total jobs before cross-provider dedup")
        jobs = deduplicate_jobs(all_jobs)
        print(f"After dedup: {len(jobs)} unique jobs")
    else:
        jobs = _run_provider(provider, common_kwargs)

    output = json.dumps(jobs, indent=2, ensure_ascii=False, default=str)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\nSaved {len(jobs)} jobs to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
