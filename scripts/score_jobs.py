#!/usr/bin/env python3
"""
Job Scoring CLI - Score jobs against skills from Notion cache.

Usage:
    python score_jobs.py -i /tmp/jobs.json -o /tmp/scored.json
    python score_jobs.py -i /tmp/jobs.json  # output to stdout
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common.job_scoring import score_jobs


def main():
    parser = argparse.ArgumentParser(description="Score jobs against skills")
    parser.add_argument("--input", "-i", required=True, help="Input jobs JSON file")
    parser.add_argument("--output", "-o", help="Output scored JSON file (default: stdout)")
    parser.add_argument("--config", help="Path to config JSON")

    args = parser.parse_args()

    with open(Path(args.input).expanduser()) as f:
        jobs = json.load(f)

    scored = score_jobs(jobs)
    print(f"Scored {len(scored)} jobs", file=sys.stderr)

    output = json.dumps(scored, indent=2, ensure_ascii=False, default=str)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
