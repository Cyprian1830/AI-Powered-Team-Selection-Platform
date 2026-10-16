"""Canonical vocabularies + alias maps used by ETL (data side) and API (request side).
Single source of truth so that "K8s" in HR data and "kubernetes" in a request meet."""
import re

TECH_ALIASES = {
    "python": ["python", "py", "python3", "python 3", "python3.11", "cpython"],
    "java": ["java", "java 17", "java17", "jdk"],
    "kotlin": ["kotlin", "kt"],
    "javascript": ["javascript", "js", "ecmascript", "es6"],
    "typescript": ["typescript", "ts"],
    "react": ["react", "reactjs", "react.js"],
    "angular": ["angular", "angularjs", "angular 2+"],
    "node.js": ["node.js", "nodejs", "node", "node js"],
    "fastapi": ["fastapi", "fast api"],
    "django": ["django"],
    "spring boot": ["spring boot", "springboot", "spring"],
    "sql": ["sql", "t-sql", "tsql", "ansi sql"],
    "postgresql": ["postgresql", "postgres", "psql", "pg"],
    "mongodb": ["mongodb", "mongo"],
    "kafka": ["kafka", "apache kafka"],
    "airflow": ["airflow", "apache airflow"],
    "spark": ["spark", "pyspark", "apache spark"],
    "dbt": ["dbt", "dbt core"],
    "docker": ["docker", "containers"],
    "kubernetes": ["kubernetes", "k8s", "kube"],
    "terraform": ["terraform", "tf"],
    "aws": ["aws", "amazon web services"],
    "azure": ["azure", "ms azure"],
    "gcp": ["gcp", "google cloud", "google cloud platform"],
    "ci/cd": ["ci/cd", "cicd", "ci-cd", "jenkins", "github actions", "gitlab ci"],
    "pytorch": ["pytorch", "torch"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "mlops": ["mlops", "ml ops"],
    "selenium": ["selenium"],
    "cypress": ["cypress"],
    "pytest": ["pytest"],
}

ROLE_ALIASES = {
    "Backend Developer": ["backend developer", "backend dev", "be developer", "back-end developer", "backend engineer"],
    "Frontend Developer": ["frontend developer", "frontend dev", "fe developer", "front-end developer", "frontend engineer"],
    "Data Engineer": ["data engineer", "de", "etl developer"],
    "DevOps Engineer": ["devops engineer", "devops", "sre", "platform engineer"],
    "QA Engineer": ["qa engineer", "qa", "tester", "test engineer", "sdet"],
    "ML Engineer": ["ml engineer", "machine learning engineer", "ai engineer"],
    "Tech Lead": ["tech lead", "technical lead", "team lead", "tl"],
}

SENIORITY_LEVELS = ["Junior", "Mid", "Senior", "Lead"]
SENIORITY_ALIASES = {
    "Junior": ["junior", "jr", "jnr"],
    "Mid": ["mid", "middle", "regular", "mid-level"],
    "Senior": ["senior", "sr", "snr"],
    "Lead": ["lead", "principal", "staff"],
}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _invert(d):
    return {_clean(a): canon for canon, aliases in d.items() for a in aliases + [canon]}


_TECH, _ROLE, _SEN = _invert(TECH_ALIASES), _invert(ROLE_ALIASES), _invert(SENIORITY_ALIASES)


def normalize_tech(raw):
    return _TECH.get(_clean(raw))


def normalize_role(raw):
    return _ROLE.get(_clean(raw))


def normalize_seniority(raw):
    return _SEN.get(_clean(raw))
