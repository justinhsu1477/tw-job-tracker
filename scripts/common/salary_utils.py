from __future__ import annotations

"""Salary parsing and normalization for Taiwan job postings.

Taiwan salary formats:
- Monthly: "$40,000–$60,000", "月薪 40,000-60,000"
- Annual:  "$500,000–$800,000", "年薪 50萬-80萬"
- Hourly:  "$200–$300/hr"
- Vague:   "待遇面議", "依公司規定"
- Mixed:   "$70,000–$9,999,999" (104 max placeholder)

Standard: Taiwan uses 14-month salary (12 months + 2 bonus months).
"""

import re


# 104 uses 9,999,999 as "no upper limit"
_MAX_PLACEHOLDER = 9_000_000


def parse_salary(salary_str: str) -> dict | None:
    """Parse a Taiwan salary string into structured data.

    Returns dict with:
        min, max: raw numbers
        period: "month" | "year" | "hour"
        monthly_min, monthly_max: normalized to monthly
    Or None if unparseable / 待遇面議.
    """
    if not salary_str:
        return None

    s = salary_str.strip()

    # Skip negotiable / unspecified
    if any(kw in s for kw in ["面議", "依公司", "另計", "論件"]):
        return None

    # Detect period
    period = "month"  # default for Taiwan
    if any(kw in s for kw in ["年薪", "/年", "年"]):
        period = "year"
    elif any(kw in s for kw in ["/hr", "時薪", "/時"]):
        period = "hour"

    # Extract all numbers (handle commas)
    numbers = re.findall(r"[\d,]+", s)
    nums = []
    for n in numbers:
        try:
            val = int(n.replace(",", ""))
            nums.append(val)
        except ValueError:
            continue

    # Handle 萬 (10k unit): "50萬" = 500,000
    wan_match = re.findall(r"(\d+)\s*萬", s)
    if wan_match:
        nums = [int(w) * 10000 for w in wan_match]

    if not nums:
        return None

    sal_min = nums[0]
    sal_max = nums[1] if len(nums) > 1 else sal_min

    # Filter out 104's max placeholder
    if sal_max >= _MAX_PLACEHOLDER:
        sal_max = 0

    # Auto-detect: if both numbers > 200,000 and period is "month",
    # it's likely annual salary
    if period == "month" and sal_min > 200_000:
        period = "year"

    # Normalize to monthly
    monthly_min, monthly_max = _to_monthly(sal_min, sal_max, period)

    return {
        "min": sal_min,
        "max": sal_max,
        "period": period,
        "monthly_min": monthly_min,
        "monthly_max": monthly_max,
    }


def _to_monthly(sal_min: int, sal_max: int, period: str) -> tuple[int, int]:
    """Convert salary range to monthly equivalent."""
    if period == "year":
        # Taiwan standard: 14-month salary
        m_min = round(sal_min / 14) if sal_min else 0
        m_max = round(sal_max / 14) if sal_max else 0
    elif period == "hour":
        # Assume 176 hours/month (22 days * 8 hours)
        m_min = sal_min * 176 if sal_min else 0
        m_max = sal_max * 176 if sal_max else 0
    else:
        m_min = sal_min
        m_max = sal_max
    return m_min, m_max


def format_monthly_range(parsed: dict | None) -> str:
    """Format parsed salary as a readable monthly range string."""
    if not parsed:
        return ""
    m_min = parsed["monthly_min"]
    m_max = parsed["monthly_max"]
    if m_min and m_max:
        return f"月薪約 ${m_min:,}–${m_max:,}"
    elif m_min:
        return f"月薪約 ${m_min:,}+"
    return ""


def salary_score_penalty(parsed: dict | None, min_monthly: int = 0) -> int:
    """Return a scoring penalty if salary is below threshold.

    Returns 0 (no penalty) or a negative number.
    """
    if not parsed or not min_monthly:
        return 0
    m_max = parsed["monthly_max"] or parsed["monthly_min"]
    if m_max and m_max < min_monthly:
        return -5
    return 0
