#!/usr/bin/env python3
"""
TW Job Search CLI - Search for jobs on Taiwan job boards and output JSON.

Supports:
  - 104 (default): 104人力銀行 — no API key required, Taiwan's largest job board

Usage:
    python run_search.py -o /tmp/jobs.json
    python run_search.py --provider 104 -o /tmp/jobs.json
    python run_search.py --keywords "後端工程師" --location "台北市"
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common.config import load_config


def main():
    parser = argparse.ArgumentParser(description="Search for jobs on Taiwan job boards")
    parser.add_argument("--config", default="~/.config/tw-job-hunter/config.json",
                        help="Path to config file")
    parser.add_argument("--provider", choices=["104"],
                        help="Search provider (overrides config search_provider)")
    parser.add_argument("--keywords", nargs="+", help="Override search keywords")
    parser.add_argument("--location", help="Override job location")
    parser.add_argument("--output", "-o", help="Output JSON file (default: stdout)")
    parser.add_argument("--include-seen", action="store_true",
                        help="Include previously seen jobs")
    parser.add_argument("--no-details", action="store_true",
                        help="Skip fetching full job descriptions (faster)")

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

    if provider == "104":
        from scraper_104 import scrape_jobs as scrape_104
        jobs = scrape_104(**common_kwargs)
    else:
        print(f"Unknown provider: {provider}", file=sys.stderr)
        sys.exit(1)

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
