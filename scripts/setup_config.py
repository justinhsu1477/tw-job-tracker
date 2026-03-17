#!/usr/bin/env python3
from __future__ import annotations

"""
Interactive setup script for TW Job Hunter configuration.

Creates the config file at ~/.config/tw-job-hunter/config.json

Usage:
    python setup_config.py
    python setup_config.py --validate
"""

import argparse
import json
import os
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "tw-job-hunter"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "search_provider": "104",
    "user_name": "",
    "notion": {
        "skills_db_id": "",
        "projects_db_id": "",
        "job_tracker_db_id": ""
    },
    "search": {
        "keywords": [],
        "location": "",
        "area_code": "",
        "remote": False,
        "time_range": "week",
        "max_results_per_query": 20,
    },
    "scoring": {
        "min_score": 60,
    }
}


def prompt(message: str, default: str = "", required: bool = False) -> str:
    """Prompt user for input."""
    if default:
        message = f"{message} [{default}]: "
    else:
        message = f"{message}: "

    while True:
        value = input(message).strip()
        if not value:
            value = default
        if required and not value:
            print("This field is required.")
            continue
        return value


def prompt_list(message: str, default: list | None = None) -> list:
    """Prompt user for comma-separated list."""
    default = default or []
    default_str = ", ".join(default) if default else ""
    print(f"{message}")
    value = prompt("Enter comma-separated values", default=default_str)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def validate_config(config: dict) -> list[str]:
    """Validate configuration and return list of errors."""
    errors = []

    search = config.get("search", {})
    if not search.get("keywords"):
        errors.append("至少需要一個搜尋關鍵字")

    if not config.get("user_name"):
        errors.append("缺少使用者名稱")

    return errors


def load_existing_config() -> dict:
    """Load existing config or return default."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Warning: Existing config is invalid, starting fresh.")
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Save config to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    os.chmod(CONFIG_FILE, 0o600)
    print(f"\nConfiguration saved to: {CONFIG_FILE}")


def setup_interactive() -> dict:
    """Run interactive setup."""
    print("=" * 50)
    print("TW Job Hunter 台灣求職助手 — 設定")
    print("=" * 50)
    print()

    config = load_existing_config()

    # User Name
    print("1. 使用者資訊")
    print("-" * 30)
    config["user_name"] = prompt(
        "您的姓名（用於求職信）",
        default=config.get("user_name", ""),
        required=True
    )
    print()

    # Notion IDs
    print("2. NOTION 整合")
    print("-" * 30)
    print("  從 Notion 的技術能力庫和專案經歷庫讀取您的技能資料。")
    print("  （可稍後透過 Claude skill 自動設定）")
    notion = config.get("notion", DEFAULT_CONFIG["notion"].copy())
    notion["skills_db_id"] = prompt(
        "技術能力庫 DB ID（可留空）",
        default=notion.get("skills_db_id", ""),
    )
    notion["projects_db_id"] = prompt(
        "專案經歷庫 DB ID（可留空）",
        default=notion.get("projects_db_id", ""),
    )
    config["notion"] = notion
    print()

    # Search Configuration
    print("3. 搜尋設定")
    print("-" * 30)

    search_config = config.get("search", DEFAULT_CONFIG["search"].copy())

    search_config["keywords"] = prompt_list(
        "搜尋關鍵字（如：'後端工程師, Java工程師, 軟體工程師'）",
        default=search_config.get("keywords", [])
    )

    search_config["location"] = prompt(
        "地區（如：'台北市'）",
        default=search_config.get("location", "")
    )

    remote_input = prompt(
        "是否只搜尋遠端工作？(yes/no)",
        default="no" if not search_config.get("remote") else "yes"
    )
    search_config["remote"] = remote_input.lower() in ("yes", "y")

    max_results = prompt(
        "每個關鍵字最多幾筆結果 (1-30)",
        default=str(search_config.get("max_results_per_query", 20))
    )
    search_config["max_results_per_query"] = min(30, int(max_results)) if max_results.isdigit() else 20

    search_config["time_range"] = prompt(
        "時間範圍 (day/3days/week/month)",
        default=search_config.get("time_range", "week")
    )

    config["search"] = search_config
    print()

    # Scoring
    print("4. 評分設定")
    print("-" * 30)
    scoring = config.get("scoring", DEFAULT_CONFIG["scoring"].copy())
    min_score = prompt(
        "最低顯示分數 (0-100)",
        default=str(scoring.get("min_score", 60))
    )
    scoring["min_score"] = int(min_score) if min_score.isdigit() else 60
    config["scoring"] = scoring
    print()

    return config


def main():
    parser = argparse.ArgumentParser(description="Setup TW Job Hunter configuration")
    parser.add_argument("--validate", action="store_true",
                        help="Only validate existing configuration")
    parser.add_argument("--show", action="store_true",
                        help="Show current configuration")

    args = parser.parse_args()

    if args.validate:
        if not CONFIG_FILE.exists():
            print(f"No config file found at {CONFIG_FILE}")
            sys.exit(1)
        config = load_existing_config()
        errors = validate_config(config)
        if errors:
            print("Configuration errors:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
        else:
            print("Configuration is valid!")
            sys.exit(0)

    if args.show:
        if not CONFIG_FILE.exists():
            print(f"No config file found at {CONFIG_FILE}")
            sys.exit(1)
        config = load_existing_config()
        print(json.dumps(config, indent=2, ensure_ascii=False))
        sys.exit(0)

    try:
        config = setup_interactive()
        errors = validate_config(config)
        if errors:
            print("\n設定警告:")
            for error in errors:
                print(f"  - {error}")

        save = prompt("儲存設定？(yes/no)", default="yes")
        if save.lower() in ("yes", "y"):
            save_config(config)
            print("\n設定完成！執行 /tw-job-hunt 開始搜尋。")
        else:
            print("\n設定未儲存。")

    except KeyboardInterrupt:
        print("\n\n設定已取消。")
        sys.exit(1)


if __name__ == "__main__":
    main()
