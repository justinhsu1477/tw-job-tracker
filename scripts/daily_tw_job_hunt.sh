#!/usr/bin/env bash
# daily_tw_job_hunt.sh — Run the full TW job search pipeline.
#
# Usage:
#   bash scripts/daily_tw_job_hunt.sh              # default provider from config
#   bash scripts/daily_tw_job_hunt.sh --provider all  # all providers
#
# For cron:
#   0 10 * * * bash ~/.claude/skills/tw-job-hunter/scripts/daily_tw_job_hunt.sh --provider all
#
# NOTE: This script handles search + score only.
# Writing to Notion and company research require Claude MCP (use /tw-job-hunt skill).

set -euo pipefail

PYTHON="${HOME}/.venv/tw-job-hunter/bin/python3"
SKILL_DIR="${HOME}/.claude/skills/tw-job-hunter"
CONFIG="${HOME}/.config/tw-job-hunter/config.json"
DATE=$(date +%Y-%m-%d)
JOBS_FILE="/tmp/tw-jobs-${DATE}.json"
SCORED_FILE="/tmp/tw-scored-${DATE}.json"
LOG_FILE="${HOME}/.tw-job-hunter.log"

# Pass through any args (e.g. --provider all)
EXTRA_ARGS="$*"

echo "=== TW Job Hunt — ${DATE} ===" | tee -a "$LOG_FILE"

# Check python
if [ ! -f "$PYTHON" ]; then
    echo "ERROR: Python not found at $PYTHON" | tee -a "$LOG_FILE"
    echo "Run: bash scripts/setup_venv.sh" | tee -a "$LOG_FILE"
    exit 1
fi

# Check config
if [ ! -f "$CONFIG" ]; then
    echo "ERROR: Config not found at $CONFIG" | tee -a "$LOG_FILE"
    exit 1
fi

# Determine script directory (support both local dev and installed skill)
if [ -d "$SKILL_DIR/scripts" ]; then
    SCRIPTS="$SKILL_DIR/scripts"
else
    SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
fi

# Step 1: Search
echo "[1/2] Searching jobs..." | tee -a "$LOG_FILE"
$PYTHON "$SCRIPTS/run_search.py" --config "$CONFIG" -o "$JOBS_FILE" $EXTRA_ARGS 2>&1 | tee -a "$LOG_FILE"

# Step 2: Score
echo "[2/2] Scoring jobs..." | tee -a "$LOG_FILE"
$PYTHON "$SCRIPTS/score_jobs.py" -i "$JOBS_FILE" -o "$SCORED_FILE" 2>&1 | tee -a "$LOG_FILE"

# Summary
JOB_COUNT=$(python3 -c "import json; print(len(json.load(open('$SCORED_FILE'))))" 2>/dev/null || echo "?")
echo "" | tee -a "$LOG_FILE"
echo "Done! ${JOB_COUNT} jobs scored → ${SCORED_FILE}" | tee -a "$LOG_FILE"
echo "Next: run /tw-job-hunt in Claude Code to write to Notion and research companies." | tee -a "$LOG_FILE"
