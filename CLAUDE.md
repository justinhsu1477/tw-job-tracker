# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## What This Is

A Claude skill (`/tw-job-hunt`) that automates job searching on **Taiwan job boards**: scrapes job postings from 104人力銀行 (no API key needed), scores them against skills from Notion, saves ranked results to a Notion Job Tracker database, and generates cover letters for user-selected jobs.

When installed as a skill, scripts run from `~/.claude/skills/tw-job-hunter/scripts/` with the venv at `~/.venv/tw-job-hunter/`.

## Commands

### Setup (first time)
```bash
bash scripts/setup_venv.sh
~/.venv/tw-job-hunter/bin/python3 scripts/setup_config.py
```

### Run individual pipeline steps
```bash
PYTHON=~/.venv/tw-job-hunter/bin/python3
CONFIG=~/.config/tw-job-hunter/config.json

# 1. Search 104
$PYTHON scripts/run_search.py --config $CONFIG -o /tmp/tw-jobs.json

# 2. Score
$PYTHON scripts/score_jobs.py -i /tmp/tw-jobs.json -o /tmp/tw-scored.json

# 3. Cover letters (after user selects)
$PYTHON scripts/generate_cover_letters.py --jobs /tmp/tw-scored.json --indices "1,3"
```

### Dependencies
`requirements.txt` lists `httpx` and `python-dateutil`. No external API keys required for 104.

## Architecture

### Data Flow
```
Notion（技術能力庫 + 專案經歷庫）
        ↓  MCP → skills_cache.json
104 API → scraper_104.py → run_search.py → [raw jobs JSON]
                                    ↓
                     score_jobs.py（reads skills_cache.json）
                                    ↓
                          [scored jobs JSON]
                                    ↓
                     Claude MCP → Notion Job Tracker DB
                                    ↓
                     Claude web search → 公司研究（產業/規模/評價/薪資）
                                    ↓  notion-update-page
                     generate_cover_letters.py → Notion pages
```

### Module Relationships
- `scripts/common/` — shared library
  - `config.py` — loads `~/.config/tw-job-hunter/config.json`
  - `job_scoring.py` — reads Notion skills cache, scores/ranks jobs (0–100) with proficiency weighting
  - `dedup.py` — URL-based dedup (pass 1), normalized-title dedup (pass 2), supports Chinese titles
  - `date_utils.py` — date helpers (supports Chinese relative dates like "3天前")
- `scraper_104.py` — Hits 104.com.tw internal API; no API key needed; search + detail endpoints
- `run_search.py` — provider-switching CLI (currently: `104`)
- `score_jobs.py` — CLI wrapper around `common.job_scoring.score_jobs()`
- `generate_cover_letters.py` — produces Chinese cover letter templates

### 104 API Details
- **Search**: `GET https://www.104.com.tw/jobs/search/api/jobs` (needs `Referer` header)
- **Detail**: `GET https://www.104.com.tw/job/ajax/content/{job_no}` (needs matching `Referer`)
- Rate limit: 3-second delay between requests
- Area codes: 台北市=6001001000, 新北市=6001002000, etc.

### Job Schema
Each job dict has: `title`, `company`, `location`, `description`, `url`, `posted_date`, `salary`, `employment_type`, `experience_level`, `remote` (bool), `source`, `scraped_at`, `id` (MD5 of URL), and after scoring: `match_score` (0–100), `match_reason`.

### Scoring Logic (`common/job_scoring.py`)
- Reads skills from `~/.config/tw-job-hunter/skills_cache.json` (written by Claude MCP from Notion)
- Per skill match: 精通 +8, 熟悉 +5, 了解 +3
- Bonus rules: role alignment (+15), tech stack depth (+10), domain match (+8), remote (+5)
- Falls back to hardcoded Java/Spring Boot skills if cache not found

### Notion Integration
- **Input**: 技術能力庫 (skills DB) + 專案經歷庫 (projects DB) → `skills_cache.json`
- **Output**: Job Tracker DB in Notion (created via MCP `notion-create-database`)
- MCP tools used: `notion-search`, `notion-fetch`, `notion-query-database-view`, `notion-create-database`, `notion-create-pages`

### Company Research (AI-powered, no script)
- After writing jobs to Notion, Claude uses **web search** to research top-scoring companies
- Sources: 104 company pages, PTT salary boards, 比薪水, Glassdoor, 面試趣
- Fills 5 Notion columns: 產業, 公司規模, 公司評價, 薪資參考, 公司簡介
- Only researches unique companies in the top 10 jobs to limit AI token usage
- Uses `notion-update-page` to write research back to existing rows

### Key Design Decisions
- **No API key needed**: 104 uses public internal API with Referer header
- **Notion as single source of truth**: skills come from Notion, results go back to Notion
- **Skills cache pattern**: Claude reads Notion → writes JSON cache → Python scripts read cache
- **3-second request delay**: prevents 104 rate limiting
- **Chinese + English matching**: skill synonyms table supports both languages

## Configuration
Config file: `~/.config/tw-job-hunter/config.json`

Key fields: `search_provider` (`"104"` default), `notion.skills_db_id`, `notion.projects_db_id`, `notion.job_tracker_db_id`, `user_name`, `search.keywords[]`, `search.location`, `search.area_code`, `search.remote`, `search.time_range`, `search.max_results_per_query`, `scoring.min_score`.
