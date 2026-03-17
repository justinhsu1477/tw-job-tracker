#!/usr/bin/env python3
"""
Generate cover letters for job matches (Traditional Chinese).

Usage:
    python generate_cover_letters.py --jobs scored_jobs.json --indices "1,3,5"
    python generate_cover_letters.py --jobs scored_jobs.json --top 5
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common.config import load_config, get_user_info


def clean_description(text: str) -> str:
    """Strip markdown headers, deduplicate lines, and remove noise."""
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[.\-*]+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    seen, deduped = set(), []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            deduped.append(line)
        elif not stripped:
            deduped.append(line)
    return '\n'.join(deduped).strip()


def generate_cover_letter(job: dict, config: dict) -> str:
    """Generate a cover letter template for a job posting."""
    title = job.get('title', '職位')
    company = job.get('company', '公司')
    location = job.get('location', '未提供')
    match_score = job.get('match_score', 0)
    raw_description = job.get('description', '')
    description = clean_description(raw_description)

    user_info = get_user_info(config)
    user_name = user_info["name"] or "您的姓名"

    cover_letter = f"""# 求職信 - {company}

**職位：** {title}
**公司：** {company}
**地點：** {location}
**匹配分數：** {match_score}/100
**建立日期：** {datetime.now().strftime('%Y-%m-%d')}

---

## 求職信內容

{company} 人資團隊您好，

我是 {user_name}，對貴公司的 {title} 職位深感興趣。我擁有 [年資] 年的 [領域] 開發經驗，相信我的技術背景與貴公司的需求高度契合。

[描述您目前的角色和最相關的經驗。強調與此職位直接相關的專案或成就。]

我的技術背景包括：

- [與職位相關的關鍵技能 1]
- [與職位相關的關鍵技能 2]
- [與職位相關的關鍵技能 3]
- [與職位相關的關鍵技能 4]

我特別被 {company} 吸引，是因為 [與公司使命、產品或文化相關的具體原因]。期待有機會將我的技術能力帶入貴公司的團隊。

感謝您撥冗閱讀，期待進一步交流的機會。

此致

{user_name}

---

## 職缺詳情

**刊登日期：** {job.get('posted_date') or '未知'}
**遠端：** {'是' if job.get('remote') else '否'}
**工作類型：** {job.get('employment_type') or '未提供'}
**薪資：** {job.get('salary') or '未提供'}

**應徵連結：** {job.get('url', '#')}

### 匹配原因：
{job.get('match_reason', '一般匹配')}

### 職缺描述摘要：
{description[:800] if description else '無描述'}

---

**標籤：** #求職信 #{company.replace(' ', '-').replace(',', '').lower()}
**狀態：** 草稿
**已投遞：** [ ] 否

"""
    return cover_letter


def main():
    parser = argparse.ArgumentParser(description='Generate cover letters for job matches')
    parser.add_argument('--jobs', required=True, help='Path to scored jobs JSON file')
    parser.add_argument('--config', default='~/.config/tw-job-hunter/config.json',
                       help='Path to config file')
    parser.add_argument('--top', type=int, default=5,
                       help='Number of top jobs (ignored if --indices is set)')
    parser.add_argument('--indices', help='Comma-separated 1-based indices, e.g. "1,3,5"')
    parser.add_argument('--output-dir', help='Override output directory')

    args = parser.parse_args()
    config = load_config(args.config)

    if args.output_dir:
        output_base = Path(args.output_dir).expanduser()
    else:
        output_base = Path("/tmp/tw-job-hunter/cover-letters")

    today = datetime.now().strftime('%Y-%m-%d')
    output_dir = output_base / today
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(Path(args.jobs).expanduser()) as f:
        jobs = json.load(f)

    if args.indices:
        selected_indices = [int(i.strip()) - 1 for i in args.indices.split(',')]
        jobs_to_process = [jobs[i] for i in selected_indices if 0 <= i < len(jobs)]
    else:
        jobs_to_process = jobs[:min(args.top, len(jobs))]

    num_letters = len(jobs_to_process)
    print(f"Generating {num_letters} cover letters in {output_dir}/")

    for i, job in enumerate(jobs_to_process, 1):
        title = job.get('title', '職位')
        company = job.get('company', '公司')
        cover_letter = generate_cover_letter(job, config)

        safe_company = company.replace('/', '_').replace(':', '_').replace('|', '_')[:50]
        safe_title = title.replace('/', '_').replace(':', '_').replace('|', '_')[:40]
        filename = f"{safe_company} - {safe_title}.md"

        output_file = output_dir / filename
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(cover_letter)

        print(f"  {i}. {filename}")

    print(f"\nGenerated {num_letters} cover letter(s) in {output_dir}/")


if __name__ == '__main__':
    main()
