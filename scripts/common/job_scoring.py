from __future__ import annotations

"""Job scoring logic - scores jobs against skills from Notion cache."""

import json
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


def load_skills_cache() -> list[dict]:
    """Load skills from Notion cache file.

    Expected format:
    {
        "skills": [
            {"name": "Java", "proficiency": "精通", "category": "語言"},
            ...
        ],
        "projects": [...],
        "updated_at": "2026-03-17T..."
    }
    """
    path = Path(SKILLS_CACHE_PATH).expanduser()
    if not path.exists():
        print("[scoring] Skills cache not found, using fallback skills", file=sys.stderr)
        return _FALLBACK_SKILLS

    try:
        with open(path) as f:
            cache = json.load(f)
        skills = cache.get("skills", [])
        if skills:
            print(f"[scoring] Loaded {len(skills)} skills from Notion cache", file=sys.stderr)
            return skills
    except Exception as e:
        print(f"[scoring] Error reading skills cache: {e}", file=sys.stderr)

    return _FALLBACK_SKILLS


def _get_search_terms(skill_name: str) -> list[str]:
    """Get all search terms for a skill, including synonyms."""
    terms = _SKILL_SYNONYMS.get(skill_name, [])
    if not terms:
        # Default: lowercase the skill name
        terms = [skill_name.lower()]
    return terms


def score_job(job: dict, skills: list[dict]) -> tuple[int, str]:
    """Score a single job against skills. Returns (score, match_reason)."""
    text = (
        job.get("title", "") + " " +
        job.get("description", "") + " " +
        job.get("company", "")
    ).lower()

    score = 0
    matches = []

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

    # Bonus rules
    for keywords, points in _BONUS_RULES:
        if any(kw in text for kw in keywords):
            score += points

    score = min(score, 100)
    reason = f"匹配技能：{', '.join(matches[:6])}" if matches else "一般匹配"
    return score, reason


def score_jobs(
    jobs: list[dict],
    skills: list[dict] | None = None,
    config: dict | None = None,
) -> list[dict]:
    """Score and sort jobs. Returns jobs with match_score and match_reason added."""
    if skills is None:
        skills = load_skills_cache()

    for job in jobs:
        s, reason = score_job(job, skills)
        job["match_score"] = s
        job["match_reason"] = reason

    jobs.sort(key=lambda x: x["match_score"], reverse=True)
    return jobs
