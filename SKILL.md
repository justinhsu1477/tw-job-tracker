---
name: tw-job-hunt
description: 台灣求職助手 — 搜尋 104 人力銀行職缺，用 Notion 技能庫評分，結果寫回 Notion
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

Run:
```bash
$PYTHON $SKILL_DIR/scripts/run_search.py --config $CONFIG -o /tmp/tw-jobs.json
```

Report how many jobs were found.

## Step 3 — Score Jobs

Run:
```bash
$PYTHON $SKILL_DIR/scripts/score_jobs.py -i /tmp/tw-jobs.json -o /tmp/tw-scored.json
```

Read `/tmp/tw-scored.json` and filter to jobs with `match_score >= min_score` from config (default 60).

## Step 4 — Create/Update Notion Job Tracker

If `notion.job_tracker_db_id` is empty in config:
1. Use `notion-create-database` to create a new "🎯 TW Job Tracker" database with these properties:
   - 職缺名稱 (title)
   - 公司 (rich_text)
   - 匹配分數 (number)
   - 匹配原因 (rich_text)
   - 薪資 (rich_text)
   - 地點 (rich_text)
   - 遠端 (checkbox)
   - 來源 (select: 104, CakeResume, Yourator)
   - 連結 (url)
   - 刊登日期 (date)
   - 狀態 (select: 待看, 有興趣, 已投遞, 不適合)
   - 搜尋日期 (date)
2. Save the new DB ID to config's `notion.job_tracker_db_id`.

Then use `notion-create-pages` to add each qualifying job as a row in the tracker.

## Step 5 — Present Results

Show the user a summary table:

```
# 🎯 今日職缺搜尋結果 (YYYY-MM-DD)

找到 N 個匹配職缺（分數 ≥ 60）：

| # | 分數 | 職缺名稱 | 公司 | 薪資 | 地點 |
|---|------|---------|------|------|------|
| 1 | 85   | 後端工程師 | XX公司 | 50K-70K | 台北市 |
...

已寫入 Notion Job Tracker。
如需產生求職信，請告訴我編號（如："幫我產生 1, 3, 5 的求職信"）。
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

## Important Notes

- **Never auto-generate cover letters** — always wait for the user to choose.
- **104 has no API key** — it just works with the Referer header.
- **3-second delay** between 104 API requests is built into the scraper.
- **Skills cache** is refreshed from Notion every time the skill runs.
- Always use `ensure_ascii=False` when writing JSON with Chinese text.
