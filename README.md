# TW Job Tracker 台灣求職追蹤器

自動搜尋台灣求職網站、用你的 Notion 技能庫評分排序、結果寫回 Notion。

## 特色

- **104 人力銀行爬蟲** — 直接打 104 內部 API，不需要 API key
- **Notion 整合** — 從你的技術能力庫讀取技能，評分後寫回 Notion Job Tracker
- **熟練度加權評分** — 精通(+8)、熟悉(+5)、了解(+3)，不只是關鍵字匹配
- **中英文雙語匹配** — 技能同義詞表支援中英文（如 "微服務" = "microservice"）
- **Claude Skill** — 一鍵 `/tw-job-hunt` 完成搜尋→評分→存入 Notion 全流程

## 快速開始

### 1. 安裝

```bash
# 建立虛擬環境
bash scripts/setup_venv.sh

# 互動式設定
~/.venv/tw-job-hunter/bin/python3 scripts/setup_config.py
```

### 2. 搜尋職缺

```bash
PYTHON=~/.venv/tw-job-hunter/bin/python3

# 搜尋 104
$PYTHON scripts/run_search.py -o /tmp/tw-jobs.json

# 評分
$PYTHON scripts/score_jobs.py -i /tmp/tw-jobs.json -o /tmp/tw-scored.json

# 產生求職信（選擇編號）
$PYTHON scripts/generate_cover_letters.py --jobs /tmp/tw-scored.json --indices "1,3"
```

### 3. Claude Skill（推薦）

安裝為 Claude skill 後，直接在對話中輸入 `/tw-job-hunt`，自動完成：

1. 從 Notion 技術能力庫同步你的技能
2. 搜尋 104 人力銀行職缺
3. 用你的技能評分排序
4. 寫入 Notion Job Tracker Database
5. 等你選擇後產生求職信

## 架構

```
Notion（技術能力庫 + 專案經歷庫）
        ↓  MCP 讀取 → skills_cache.json
104 API → scraper_104.py → run_search.py → [raw jobs JSON]
                                    ↓
                     score_jobs.py（讀 skills_cache.json 評分）
                                    ↓
                          [scored jobs JSON]
                                    ↓
                     Claude MCP → Notion Job Tracker DB
```

## 支援的求職網站

| 網站 | 狀態 | API Key |
|------|------|---------|
| 104 人力銀行 | ✅ 已完成 | 不需要 |
| CakeResume | 🔜 規劃中 | — |
| Yourator | 🔜 規劃中 | — |
| 1111 人力銀行 | 🔜 規劃中 | — |

## 評分邏輯

| 項目 | 分數 |
|------|------|
| 精通技能匹配 | +8/個 |
| 熟悉技能匹配 | +5/個 |
| 了解技能匹配 | +3/個 |
| 職位類別匹配（後端/Java） | +15 |
| 技術棧高度重合（≥3 精通） | +10 |
| 產業匹配（ERP/MES/WMS） | +8 |
| 遠端/混合工作 | +5 |
| Spring Boot 相關 | +5 |

## 設定

設定檔：`~/.config/tw-job-hunter/config.json`

```json
{
  "search_provider": "104",
  "user_name": "Your Name",
  "notion": {
    "skills_db_id": "your-skills-db-id",
    "projects_db_id": "your-projects-db-id",
    "job_tracker_db_id": ""
  },
  "search": {
    "keywords": ["後端工程師", "Java工程師", "軟體工程師"],
    "location": "台北市",
    "area_code": "6001001000",
    "time_range": "week",
    "max_results_per_query": 20
  },
  "scoring": {
    "min_score": 60
  }
}
```

### 104 地區代碼

| 地區 | 代碼 |
|------|------|
| 台北市 | 6001001000 |
| 新北市 | 6001002000 |
| 桃園市 | 6001003000 |
| 新竹市 | 6001004000 |
| 台中市 | 6001006000 |
| 台南市 | 6001010000 |
| 高雄市 | 6001011000 |

## 目錄結構

```
tw-job-tracker/
├── scripts/
│   ├── common/           # 共用模組
│   │   ├── config.py     # 設定載入
│   │   ├── job_scoring.py # 評分（Notion 技能快取 + 加權）
│   │   ├── dedup.py      # 去重（支援中文標題）
│   │   └── date_utils.py # 日期工具（支援中文相對日期）
│   ├── scraper_104.py    # 104人力銀行爬蟲
│   ├── run_search.py     # 搜尋入口 CLI
│   ├── score_jobs.py     # 評分 CLI
│   ├── generate_cover_letters.py # 中文求職信產生器
│   ├── setup_config.py   # 互動式設定
│   └── setup_venv.sh     # 環境建置
├── CLAUDE.md             # Claude 開發指引
├── SKILL.md              # Claude Skill 定義
└── requirements.txt      # Python 依賴（httpx, python-dateutil）
```

## License

MIT
