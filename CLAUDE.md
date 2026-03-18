# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## What This Is

A Claude skill (`/tw-job-hunt`) that automates job searching on **Taiwan job boards**: scrapes job postings from 104人力銀行, CakeResume, and Yourator, scores them against skills from Notion, researches companies via AI, saves ranked results to a Notion Job Tracker database, and supports interview tracking and cover letter generation.

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

# 1. Search (single provider or all)
$PYTHON scripts/run_search.py --config $CONFIG -o /tmp/tw-jobs.json
$PYTHON scripts/run_search.py --provider all --config $CONFIG -o /tmp/tw-jobs.json
$PYTHON scripts/run_search.py --provider cakeresume --config $CONFIG -o /tmp/tw-jobs.json

# 2. Score
$PYTHON scripts/score_jobs.py -i /tmp/tw-jobs.json -o /tmp/tw-scored.json

# 3. Cover letters (after user selects)
$PYTHON scripts/generate_cover_letters.py --jobs /tmp/tw-scored.json --indices "1,3"
```

### Run full automated pipeline
```bash
bash scripts/daily_tw_job_hunt.sh                # default provider
bash scripts/daily_tw_job_hunt.sh --provider all  # all providers
```

### Dependencies
`requirements.txt` lists `httpx` and `python-dateutil`. No external API keys required.

## Architecture

### Data Flow
```
Notion（技術能力庫 + 專案經歷庫）
        ↓  MCP → skills_cache.json
104 API ──────┐
CakeResume API┼→ run_search.py --provider all → [raw jobs JSON]
Yourator API──┘        ↓ merge + cross-provider dedup
                     score_jobs.py（skills + projects + salary normalization）
                                    ↓
                          [scored jobs JSON — keyword score]
                                    ↓
                     Claude LLM → 語意重排 top 15（final = 40% keyword + 60% semantic）
                                    ↓
                     Claude MCP → Notion Job Tracker DB
                                    ↓
                     Claude web search → 公司研究（產業/規模/評價/薪資）
                                    ↓  notion-update-page
                     面試追蹤 / generate_cover_letters.py → Notion pages
```

### Module Relationships
- `scripts/common/` — shared library
  - `config.py` — loads `~/.config/tw-job-hunter/config.json`
  - `job_scoring.py` — proficiency-weighted scoring + project bonus + negative signals
  - `dedup.py` — URL dedup + title dedup, cross-provider (104 > cakeresume > yourator > 1111)
  - `date_utils.py` — date helpers (supports Chinese relative dates)
  - `salary_utils.py` — Taiwan salary parsing & monthly normalization
- `scraper_104.py` — 104.com.tw internal API scraper (no key needed)
- `scraper_cakeresume.py` — CakeResume public API scraper
- `scraper_yourator.py` — Yourator public API scraper
- `run_search.py` — provider-switching CLI: `104`, `cakeresume`, `yourator`, `all`
- `score_jobs.py` — CLI wrapper for scoring
- `generate_cover_letters.py` — Chinese cover letter templates
- `daily_tw_job_hunt.sh` — Full pipeline shell script (for cron)

### Provider Details

| Provider | API | Key | Rate Limit |
|----------|-----|-----|------------|
| 104 | `GET /jobs/search/api/jobs` | None (needs Referer header) | 3s delay |
| Cake (CakeResume) | Next.js `_next/data` (cake.me) | None (needs buildId) | 2s delay |
| Yourator | `GET /api/v4/jobs` | None | 2s delay |

### Job Schema
Each job dict has: `title`, `company`, `location`, `description`, `url`, `posted_date`, `salary`, `salary_monthly` (normalized), `employment_type`, `experience_level`, `remote` (bool), `source`, `scraped_at`, `id` (MD5 of URL), and after scoring: `match_score` (0–100), `match_reason`.

### Scoring Logic (`common/job_scoring.py`)
- Reads skills + projects from `~/.config/tw-job-hunter/skills_cache.json`
- Per skill match: 精通 +8, 熟悉 +5, 了解 +3
- Project overlap bonus: +5 per project with ≥2 matching techs
- Expert overlap bonus: +10 if ≥3 精通 skills match
- Bonus rules: role alignment (+15), tech stack (+10), domain (+8), remote (+5)
- Negative: internship exclusion (-50), experience mismatch (-10), low salary (-5)
- Salary normalization: auto-converts annual/hourly to monthly equivalent

### LLM Semantic Re-ranking (Step 3.5, no script)
- After keyword scoring, Claude takes top 15 jobs and does semantic matching
- Compares job descriptions against user's skills + projects using language understanding
- Catches non-obvious matches: "跨部門協作" ≈ "專案管理", "系統設計" ≈ "架構經驗"
- Final score = keyword_score × 0.4 + semantic_score × 0.6
- Transparent: match_reason shows both scores (e.g. "關鍵字:35 + 語意:78 → 最終:61")
- Cost: ~$0.01-0.03 per run (processes all 15 in one pass)

### Salary Normalization (`common/salary_utils.py`)
- Parses: "$40,000–$60,000", "年薪 50萬-80萬", "待遇面議"
- Annual → monthly: divide by 14 (Taiwan 14-month standard)
- Hourly → monthly: multiply by 176 (22 days × 8 hours)
- Filters out 104's $9,999,999 placeholder

### Company Research (AI-powered, no script)
- After writing jobs to Notion, Claude uses **web search** to research top-scoring companies
- Sources: 104 company pages, PTT salary boards, 比薪水, Glassdoor, 面試趣
- Fills 5 Notion columns: 產業, 公司規模, 公司評價, 薪資參考, 公司簡介
- Only researches unique companies in the top 10 jobs
- Uses `notion-update-page` to write research back

### Interview Tracking (Notion-native)
- Notion DB columns: 面試階段, 面試日期, 面試筆記, 薪資offer, 跟進日期
- Stages: 未面試 → 電話面試 → 技術面試 → 主管面試 → HR面試 → 已拿offer/已婉拒
- All managed via Claude MCP `notion-update-page` — no Python code needed

### Notion Integration
- **Input**: 技術能力庫 + 專案經歷庫 → `skills_cache.json`
- **Output**: Job Tracker DB with 20+ columns (includes `新增時間` created_time for tracking insertion order)
- MCP tools: `notion-search`, `notion-fetch`, `notion-query-database-view`, `notion-create-database`, `notion-create-pages`, `notion-update-page`

### Key Design Decisions
- **No API key needed**: all three providers use public APIs
- **Notion as single source of truth**: skills from Notion, results back to Notion
- **Skills cache pattern**: Claude reads Notion → JSON cache → Python reads cache
- **Cross-provider dedup**: same job on 104 + CakeResume → kept once (by source rank)
- **Chinese + English matching**: skill synonyms table supports both languages
- **Salary auto-normalization**: display comparable monthly figures regardless of format

## Configuration
Config file: `~/.config/tw-job-hunter/config.json`

Key fields: `search_provider` (`"104"` | `"cakeresume"` | `"yourator"` | `"all"`), `notion.skills_db_id`, `notion.projects_db_id`, `notion.job_tracker_db_id`, `user_name`, `search.keywords[]`, `search.location`, `search.area_code`, `search.remote`, `search.time_range`, `search.max_results_per_query`, `scoring.min_score`, `scoring.years_experience` (for mismatch penalty), `scoring.min_monthly_salary` (for salary penalty).
