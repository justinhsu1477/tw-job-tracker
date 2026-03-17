from __future__ import annotations

"""Job scoring logic - scores jobs against skills from Notion cache.

Scoring components:
1. Skill keyword matching with proficiency weighting (精通+8, 熟悉+5, 了解+3)
2. Project experience bonus (+5 per overlapping project)
3. Bonus rules for role/domain/remote alignment
4. Negative signals: exclude terms, experience level mismatch, low salary
"""

import json
import re
import sys
from pathlib import Path

SKILLS_CACHE_PATH = "~/.config/tw-job-hunter/skills_cache.json"

# Points per skill match, weighted by proficiency
PROFICIENCY_POINTS = {
    "精通": 8,
    "熟悉": 5,
    "了解": 3,
}

# Fallback skills if cache doesn't exist
_FALLBACK_SKILLS = [
    {"name": "Java", "proficiency": "精通"},
    {"name": "Spring Boot", "proficiency": "精通"},
    {"name": "SQL", "proficiency": "精通"},
    {"name": "PostgreSQL", "proficiency": "熟悉"},
    {"name": "Docker", "proficiency": "熟悉"},
    {"name": "Kubernetes", "proficiency": "熟悉"},
    {"name": "Redis", "proficiency": "熟悉"},
    {"name": "RabbitMQ", "proficiency": "熟悉"},
    {"name": "Kotlin", "proficiency": "熟悉"},
    {"name": "Android", "proficiency": "熟悉"},
    {"name": "Git", "proficiency": "精通"},
    {"name": "REST API", "proficiency": "精通"},
]

# Synonyms: maps a skill name to all variations to search for in job text
_SKILL_SYNONYMS = {
    "Java": ["java"],
    "Spring Boot": ["spring boot", "springboot", "spring-boot"],
    "Spring Security": ["spring security"],
    "JPA": ["jpa", "hibernate"],
    "SQL": ["sql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MySQL": ["mysql"],
    "MSSQL": ["mssql", "ms sql", "sql server"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Redis": ["redis"],
    "RabbitMQ": ["rabbitmq", "rabbit mq"],
    "Kafka": ["kafka"],
    "Kotlin": ["kotlin"],
    "Android": ["android"],
    "React": ["react"],
    "Next.js": ["next.js", "nextjs"],
    "Git": ["git"],
    "CI/CD": ["ci/cd", "cicd", "ci cd", "jenkins", "github actions"],
    "REST API": ["rest api", "restful", "rest"],
    "Microservices": ["microservice", "微服務"],
    "Python": ["python"],
    "TypeScript": ["typescript"],
    "JavaScript": ["javascript"],
    "AWS": ["aws", "amazon web services"],
    "GCP": ["gcp", "google cloud"],
    "Azure": ["azure"],
    "MongoDB": ["mongodb", "mongo"],
    "Elasticsearch": ["elasticsearch", "elastic search"],
    "GraphQL": ["graphql"],
    "gRPC": ["grpc"],
    "Vaadin": ["vaadin"],
    "JUnit": ["junit"],
    "Flyway": ["flyway"],
    "Liquibase": ["liquibase"],
    "Vue": ["vue", "vuejs", "vue.js"],
    "Angular": ["angular"],
    "Node.js": ["node.js", "nodejs", "node"],
}

# Bonus rules for Taiwan market
_BONUS_RULES = [
    # Role alignment — Backend/Java focus
    (["後端工程師", "backend engineer", "backend developer", "java engineer",
      "java developer", "java工程師"], 15),
    (["全端工程師", "fullstack", "full-stack", "full stack"], 10),
    (["軟體工程師", "software engineer", "software developer"], 10),
    # Domain bonuses
    (["erp", "mes", "wms", "scm", "製造", "manufacturing", "供應鏈"], 8),
    (["電商", "e-commerce", "ecommerce", "金融", "fintech"], 5),
    # Work style
    (["遠端", "remote", "居家辦公", "在家工作", "wfh", "hybrid", "混合辦公"], 5),
    # Tech stack depth bonus
    (["microservice", "微服務", "分散式", "distributed"], 5),
    (["spring cloud", "spring boot", "springboot"], 5),
]

# Terms that indicate the job is likely not a good fit
_EXCLUDE_TERMS = [
    "實習", "intern", "工讀",
]

# Terms that suggest a management role (neutral — not penalized, just flagged)
_MANAGEMENT_TERMS = ["主管", "manager", "lead", "director", "經理", "組長"]


def load_skills_cache() -> tuple[list[dict], list[dict]]:
    """Load skills and projects from Notion cache file.

    Returns (skills, projects).
    """
    path = Path(SKILLS_CACHE_PATH).expanduser()
    if not path.exists():
        print("[scoring] Skills cache not found, using fallback skills", file=sys.stderr)
        return _FALLBACK_SKILLS, []

    try:
        with open(path) as f:
            cache = json.load(f)
        skills = cache.get("skills", [])
        projects = cache.get("projects", [])
        if skills:
            print(f"[scoring] Loaded {len(skills)} skills, {len(projects)} projects from Notion cache", file=sys.stderr)
            return skills, projects
    except Exception as e:
        print(f"[scoring] Error reading skills cache: {e}", file=sys.stderr)

    return _FALLBACK_SKILLS, []


def _get_search_terms(skill_name: str) -> list[str]:
    """Get all search terms for a skill, including synonyms."""
    terms = _SKILL_SYNONYMS.get(skill_name, [])
    if not terms:
        # Default: lowercase the skill name
        terms = [skill_name.lower()]
    return terms


def _project_bonus(text: str, projects: list[dict]) -> tuple[int, list[str]]:
    """Calculate bonus from matching project experience.

    Each project with >=2 matching techs in the job text gives +5.
    Returns (bonus_points, matched_project_names).
    """
    if not projects:
        return 0, []

    bonus = 0
    matched = []
    for proj in projects:
        techs = proj.get("techs", [])
        if not techs:
            continue
        # Count how many project techs appear in job text
        match_count = sum(
            1 for tech in techs
            if any(term in text for term in _get_search_terms(tech))
        )
        if match_count >= 2:
            bonus += 5
            matched.append(proj.get("name", ""))

    return bonus, matched


def _experience_penalty(job: dict, max_years: int = 0) -> int:
    """Penalty if job requires more experience than user has.

    Returns 0 or negative number.
    """
    if not max_years:
        return 0

    exp_str = job.get("experience_level", "")
    # Extract number from strings like "5年以上", "3年以上"
    match = re.search(r"(\d+)\s*年", exp_str)
    if match:
        required = int(match.group(1))
        if required > max_years + 1:  # allow 1 year stretch
            return -10
    return 0


def _exclude_penalty(text: str) -> int:
    """Penalty for jobs that match exclude terms (internships, etc)."""
    if any(term in text for term in _EXCLUDE_TERMS):
        return -50  # effectively excludes
    return 0


def score_job(
    job: dict,
    skills: list[dict],
    projects: list[dict] | None = None,
    scoring_config: dict | None = None,
) -> tuple[int, str]:
    """Score a single job against skills. Returns (score, match_reason)."""
    text = (
        job.get("title", "") + " " +
        job.get("description", "") + " " +
        job.get("company", "")
    ).lower()

    scoring_config = scoring_config or {}
    score = 0
    matches = []
    reasons = []

    # Exclude penalty (internships etc)
    exclude_pen = _exclude_penalty(text)
    if exclude_pen:
        score += exclude_pen

    # Per-skill keyword match with proficiency weighting
    for skill in skills:
        name = skill.get("name", "")
        proficiency = skill.get("proficiency", "了解")
        points = PROFICIENCY_POINTS.get(proficiency, 3)

        search_terms = _get_search_terms(name)
        if any(term in text for term in search_terms):
            score += points
            matches.append(name)

    # Bonus: high tech stack overlap (>=3 精通 skills matched)
    expert_matches = sum(
        1 for skill in skills
        if skill.get("proficiency") == "精通"
        and any(term in text for term in _get_search_terms(skill.get("name", "")))
    )
    if expert_matches >= 3:
        score += 10

    # Project experience bonus
    if projects:
        proj_bonus, proj_names = _project_bonus(text, projects)
        if proj_bonus:
            score += proj_bonus
            reasons.append(f"專案匹配：{', '.join(proj_names)}")

    # Bonus rules
    for keywords, points in _BONUS_RULES:
        if any(kw in text for kw in keywords):
            score += points

    # Experience level penalty
    max_years = scoring_config.get("years_experience", 0)
    exp_pen = _experience_penalty(job, max_years)
    if exp_pen:
        score += exp_pen
        reasons.append("年資要求偏高")

    # Salary penalty
    min_monthly = scoring_config.get("min_monthly_salary", 0)
    if min_monthly:
        from common.salary_utils import parse_salary, salary_score_penalty
        parsed = parse_salary(job.get("salary", ""))
        sal_pen = salary_score_penalty(parsed, min_monthly)
        if sal_pen:
            score += sal_pen
            reasons.append("薪資偏低")

    score = max(0, min(score, 100))

    # Build reason string
    if matches:
        reason_parts = [f"匹配技能：{', '.join(matches[:6])}"]
    else:
        reason_parts = ["一般匹配"]
    reason_parts.extend(reasons)
    reason = "；".join(reason_parts)

    return score, reason


def score_jobs(
    jobs: list[dict],
    skills: list[dict] | None = None,
    config: dict | None = None,
) -> list[dict]:
    """Score and sort jobs. Returns jobs with match_score and match_reason added."""
    projects = []
    if skills is None:
        skills, projects = load_skills_cache()

    scoring_config = (config or {}).get("scoring", {})

    # Also normalize salary for display
    from common.salary_utils import parse_salary, format_monthly_range

    for job in jobs:
        s, reason = score_job(job, skills, projects, scoring_config)
        job["match_score"] = s
        job["match_reason"] = reason

        # Add normalized salary
        parsed = parse_salary(job.get("salary", ""))
        if parsed:
            job["salary_monthly"] = format_monthly_range(parsed)
        else:
            job["salary_monthly"] = ""

    jobs.sort(key=lambda x: x["match_score"], reverse=True)
    return jobs
