---
name: tw-job-hunt
description: |
  台灣求職助手 — 搜尋 104/CakeResume/Yourator 職缺，用 Notion 技能庫評分，
  AI 公司研究，結果寫回 Notion，支援面試追蹤。
  Triggers: /tw-job-hunt, "找工作", "搜尋職缺", "台灣求職"
user_invocable: true
---

# /tw-job-hunt — 台灣求職自動化

You are an automated job hunting assistant for Taiwan. Follow these steps exactly.

## Environment
```
PYTHON=~/.venv/tw-job-hunter/bin/python3
SKILL_DIR=~/.claude/skills/tw-job-hunter
CONFIG=~/.config/tw-job-hunter/config.json
CACHE=~/.config/tw-job-hunter/skills_cache.json
```

## Step 0 — Check Setup

If `$PYTHON` does not exist, run: `bash $SKILL_DIR/scripts/setup_venv.sh`
If `$CONFIG` does not exist, create a default config with the user's info.

## Step 1 — Sync Skills from Notion

Use the Notion MCP tools to read the user's skills:

1. Use `notion-query-database-view` on `collection://cb2d5c28-7fcd-4b0b-9ace-42f5ff3cf6e7` (技術能力庫) to get all skills with their 技術名稱, 分類, and 熟練度.

2. Use `notion-query-database-view` on `collection://8c49b0a9-00d4-488e-8566-98cd08531dff` (專案經歷庫) to get projects with 專案名稱, 使用技術, and 類別.

3. Write the combined data to `$CACHE` as JSON:
```json
{
  "skills": [
    {"name": "Java", "proficiency": "精通", "category": "語言"},
    {"name": "Spring Boot", "proficiency": "精通", "category": "框架"}
  ],
  "projects": [
    {"name": "WMS", "techs": ["Java", "Spring Boot", "PostgreSQL"], "category": "Backend"}
  ],
  "seen_job_ids": [],
  "updated_at": "2026-03-17T10:00:00"
}
```

If the Notion Job Tracker DB exists (check config `notion.job_tracker_db_id`), also read existing job URLs to populate `seen_job_ids`.

## Step 2 — Search Jobs

Run with `--provider all` to search all supported job boards:
```bash
$PYTHON $SKILL_DIR/scripts/run_search.py --config $CONFIG --provider all -o /tmp/tw-jobs.json
```

Supported providers:
- **104** — 104人力銀行 (Taiwan's largest, no API key)
- **cakeresume** — CakeResume (tech/startup focused)
- **yourator** — Yourator (startup/tech jobs)
- **all** — Run all providers, merge and cross-provider deduplicate

Report how many jobs were found from each provider.

## Step 3 — Score Jobs

Run:
```bash
$PYTHON $SKILL_DIR/scripts/score_jobs.py -i /tmp/tw-jobs.json -o /tmp/tw-scored.json
```

Read `/tmp/tw-scored.json` and filter to jobs with `match_score >= min_score` from config (default 60).

Scoring includes:
- Skill matching with proficiency weighting (精通+8, 熟悉+5, 了解+3)
- Project experience bonus (+5 per matching project)
- Role/domain/remote bonuses
- Negative signals: internship exclusion, experience mismatch penalty
- Salary normalization (月薪參考 field auto-filled)

## Step 4 — Create/Update Notion Job Tracker

If `notion.job_tracker_db_id` is empty in config:
1. Use `notion-create-database` to create a new "🎯 TW Job Tracker" database with these properties:
   - 職缺名稱 (title), 公司, 匹配分數 (number), 匹配原因, 薪資, 月薪參考
   - 地點, 遠端 (checkbox), 來源 (select: 104, CakeResume, Yourator, 1111), 連結 (url)
   - 刊登日期 (date), 搜尋日期 (date)
   - 狀態 (select: 待看, 有興趣, 已投遞, 不適合)
   - 產業, 公司規模, 公司評價, 薪資參考, 公司簡介
   - 面試階段 (select: 未面試, 電話面試, 技術面試, 主管面試, HR面試, 已拿offer, 已婉拒)
   - 面試日期 (date), 面試筆記, 薪資offer, 跟進日期 (date)
2. Save the new DB ID to config's `notion.job_tracker_db_id`.

Then use `notion-create-pages` to add each qualifying job as a row in the tracker.
Include `月薪參考` from scored data's `salary_monthly` field.

## Step 4.5 — Company Research (AI-powered)

For the **top 10 scoring jobs**, use web search to research each unique company. This step uses Claude's built-in web search — no Python script needed.

For each unique company, search:
1. `"{公司名稱}" 104人力銀行 公司介紹` — get industry, size, description
2. `"{公司名稱}" 薪資 PTT` or `"{公司名稱}" 面試 Glassdoor` — get salary references and reviews

Extract and fill these fields:
- **產業**: e.g. "金融科技", "電子商務", "SaaS", "遊戲"
- **公司規模**: e.g. "50-200人", "上市公司", "新創"
- **公司評價**: Brief summary from PTT/Glassdoor/面試趣, e.g. "PTT 評價正面，工作氛圍佳；Glassdoor 4.2/5"
- **薪資參考**: Market data from 比薪水/PTT/Glassdoor, e.g. "後端工程師約 60K-80K (比薪水)"
- **公司簡介**: 1-2 sentence description of what the company does

Then use `notion-update-page` to update each job's row in the tracker with the research results.

**Important notes:**
- Research unique companies only (don't repeat for same company with multiple jobs)
- If no reliable info found, leave the field empty rather than guessing
- Keep descriptions concise — this is for quick reference, not deep research
- Prefer Traditional Chinese sources (PTT, 比薪水, 面試趣) over English ones

## Step 5 — Present Results

Show the user a summary table:

```
# 🎯 今日職缺搜尋結果 (YYYY-MM-DD)

搜尋來源：104 + CakeResume + Yourator
找到 N 個匹配職缺（分數 ≥ 60）：

| # | 分數 | 職缺名稱 | 公司 | 月薪參考 | 產業 | 來源 |
|---|------|---------|------|---------|------|------|
| 1 | 85   | 後端工程師 | XX公司 | 50K-70K | 金融科技 | 104 |
...

已寫入 Notion Job Tracker。
- 如需產生求職信：告訴我編號（如："幫我產生 1, 3 的求職信"）
- 如需更新面試狀態：告訴我（如："我拿到 XX 公司的面試了"）
- 如需排程自動執行：告訴我（如："幫我排程每天早上10點搜尋"）
```

## Step 6 — Cover Letters (on user request)

When the user selects jobs by number:

1. Run:
```bash
$PYTHON $SKILL_DIR/scripts/generate_cover_letters.py --jobs /tmp/tw-scored.json --indices "1,3,5" --output-dir /tmp/tw-cover-letters
```

2. Read each generated cover letter file.

3. Use `notion-create-pages` to create a Notion page for each cover letter under the Job Tracker, with the cover letter content as the page body.

4. Show the user links to the created Notion pages.

## Step 7 — Interview Tracking (on user request)

When the user reports interview progress (e.g. "我拿到XX公司的面試了", "更新面試狀態"):

1. Find the matching job in the Notion Job Tracker DB using `notion-query-database-view`.

2. Ask the user for details (if not provided):
   - 面試階段: 電話面試/技術面試/主管面試/HR面試/已拿offer/已婉拒
   - 面試日期: when
   - 面試筆記: any notes (optional)
   - 薪資offer: if applicable
   - 跟進日期: next action date (optional)

3. Use `notion-update-page` to update the job's row:
   - Set 面試階段 to the reported stage
   - Set 面試日期
   - Set 狀態 to "已投遞" (if not already)
   - Add any notes to 面試筆記

4. Show updated status and a summary of all active interviews:

```
| 公司 | 職位 | 面試階段 | 面試日期 | 下次跟進 |
|------|------|---------|---------|---------|
| XX   | 後端 | 技術面試 | 03/20   | 03/25   |
```

## Step 8 — Scheduling (on user request)

When the user asks to schedule automatic runs (e.g. "幫我排程", "每天自動搜尋"):

Explain options:
1. **Claude Scheduled Task** (recommended): Use the `create_scheduled_task` MCP tool to schedule `/tw-job-hunt` to run at specified intervals.
2. **Cron job** (manual): Set up system cron with `daily_tw_job_hunt.sh` — handles search+score only, Notion write requires Claude.

For option 1, create a scheduled task that:
- Runs at the user's specified time (default: weekdays 10:00 AM)
- Invokes `/tw-job-hunt`
- Skips if today's jobs already exist in the tracker

## Important Notes

- **Never auto-generate cover letters** — always wait for the user to choose.
- **104 has no API key** — it just works with the Referer header.
- **3-second delay** between 104 API requests, 2-second for CakeResume/Yourator.
- **Skills cache** is refreshed from Notion every time the skill runs.
- Always use `ensure_ascii=False` when writing JSON with Chinese text.
- **Cross-provider dedup** handles same job posted on multiple boards.
