# TW Job Tracker 台灣求職追蹤器

自動搜尋台灣求職網站、用你的 Notion 技能庫評分排序、AI 研究公司背景、結果寫回 Notion，支援面試追蹤。

## 特色

- **多來源搜尋** — 104 人力銀行 + CakeResume + Yourator，一鍵搜尋全合併
- **Notion 整合** — 從技術能力庫讀技能，評分後寫回 Notion Job Tracker
- **熟練度加權評分** — 精通(+8)、熟悉(+5)、了解(+3)，專案經歷額外加分
- **智慧過濾** — 自動排除實習、年資不符扣分、低薪提醒
- **薪資標準化** — 年薪/月薪/時薪統一換算成月薪，方便比較
- **中英文雙語匹配** — 技能同義詞表支援中英文（如 "微服務" = "microservice"）
- **AI 公司研究** — 自動搜尋公司產業、規模、評價、薪資參考（PTT/比薪水/Glassdoor）
- **面試追蹤** — Notion 內建面試階段、日期、筆記、offer 管理
- **Claude Skill** — 一鍵 `/tw-job-hunt` 完成全流程

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

# 搜尋所有來源
$PYTHON scripts/run_search.py --provider all -o /tmp/tw-jobs.json

# 或單一來源
$PYTHON scripts/run_search.py --provider 104 -o /tmp/tw-jobs.json
$PYTHON scripts/run_search.py --provider cakeresume -o /tmp/tw-jobs.json
$PYTHON scripts/run_search.py --provider yourator -o /tmp/tw-jobs.json

# 評分
$PYTHON scripts/score_jobs.py -i /tmp/tw-jobs.json -o /tmp/tw-scored.json

# 產生求職信（選擇編號）
$PYTHON scripts/generate_cover_letters.py --jobs /tmp/tw-scored.json --indices "1,3"
```

### 3. Claude Skill（推薦）

安裝為 Claude skill 後，直接在對話中輸入 `/tw-job-hunt`，自動完成：

1. 從 Notion 技術能力庫同步你的技能與專案
2. 搜尋 104 + CakeResume + Yourator 職缺
3. 用技能評分排序 + 薪資標準化
4. 寫入 Notion Job Tracker Database
5. **AI 公司研究** — 搜尋產業、規模、PTT/Glassdoor 評價、薪資參考
6. 等你選擇後產生求職信
7. **面試追蹤** — 更新面試階段、日期、筆記

### 4. 排程自動執行

```bash
# 每天早上 10 點自動搜尋（cron）
0 10 * * 1-5 bash ~/.claude/skills/tw-job-hunter/scripts/daily_tw_job_hunt.sh --provider all
```

或在 Claude Code 中說「幫我排程每天早上10點搜尋」。

## 架構

```
Notion（技術能力庫 + 專案經歷庫）
        ↓  MCP 讀取 → skills_cache.json
104 API ──────┐
CakeResume API┼→ run_search.py --provider all → 合併去重
Yourator API──┘        ↓
                     score_jobs.py（技能+專案+薪資標準化）
                                    ↓
                     Claude MCP → Notion Job Tracker DB
                                    ↓
                     Claude web search → 公司研究（產業/規模/評價/薪資）
                                    ↓
                     面試追蹤 / 求職信 → Notion
```

## 支援的求職網站

| 網站 | 狀態 | API Key | 特色 |
|------|------|---------|------|
| 104 人力銀行 | ✅ 已完成 | 不需要 | 台灣最大，各產業 |
| CakeResume | ✅ 已完成 | 不需要 | 科技/新創/國際公司 |
| Yourator | ✅ 已完成 | 不需要 | 新創/科技 |
| 1111 人力銀行 | 🔜 規劃中 | — | — |

## 評分邏輯

### 加分項

| 項目 | 分數 |
|------|------|
| 精通技能匹配 | +8/個 |
| 熟悉技能匹配 | +5/個 |
| 了解技能匹配 | +3/個 |
| 專案經歷匹配（≥2 技術重合） | +5/個專案 |
| 精通技能高度重合（≥3 個） | +10 |
| 職位類別匹配（後端/Java） | +15 |
| 技術棧匹配（Spring Boot 等） | +5 |
| 產業匹配（ERP/MES/WMS） | +8 |
| 遠端/混合工作 | +5 |

### 扣分項

| 項目 | 分數 |
|------|------|
| 實習/工讀職缺 | -50（幾乎排除） |
| 年資要求超過使用者+1年 | -10 |
| 薪資低於最低門檻 | -5 |

## 面試追蹤

在 Notion Job Tracker 中管理面試流程：

```
未面試 → 電話面試 → 技術面試 → 主管面試 → HR面試 → 已拿offer
                                                    → 已婉拒
```

| 欄位 | 說明 |
|------|------|
| 面試階段 | 下拉選單，7 種狀態 |
| 面試日期 | 面試時間 |
| 面試筆記 | 面試內容、問題記錄 |
| 薪資offer | 收到的薪資方案 |
| 跟進日期 | 下一步行動日期 |

在 Claude Code 中說「我拿到 XX 公司的面試了」即可更新。

## 設定

設定檔：`~/.config/tw-job-hunter/config.json`

```json
{
  "search_provider": "all",
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
    "min_score": 60,
    "years_experience": 2,
    "min_monthly_salary": 0
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
│   ├── common/              # 共用模組
│   │   ├── config.py        # 設定載入
│   │   ├── job_scoring.py   # 評分（技能+專案+負面訊號）
│   │   ├── dedup.py         # 去重（跨來源+中文標題）
│   │   ├── date_utils.py    # 日期工具
│   │   └── salary_utils.py  # 薪資標準化（年薪→月薪）
│   ├── scraper_104.py       # 104人力銀行爬蟲
│   ├── scraper_cakeresume.py# CakeResume爬蟲
│   ├── scraper_yourator.py  # Yourator爬蟲
│   ├── run_search.py        # 搜尋入口 CLI（支援 --provider all）
│   ├── score_jobs.py        # 評分 CLI
│   ├── generate_cover_letters.py # 中文求職信
│   ├── daily_tw_job_hunt.sh # 每日自動化腳本（cron用）
│   ├── setup_config.py      # 互動式設定
│   └── setup_venv.sh        # 環境建置
├── CLAUDE.md                # Claude 開發指引
├── SKILL.md                 # Claude Skill 定義
└── requirements.txt         # Python 依賴
```

## License

MIT
