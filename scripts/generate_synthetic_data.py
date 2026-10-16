"""Generates deliberately *dirty* synthetic HR data (CSV) so the ETL has real work to do."""
import csv, random, sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from teamselect.taxonomy import TECH_ALIASES, ROLE_ALIASES

random.seed(42)
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data" / "raw"
OUT.mkdir(parents=True, exist_ok=True)
N = 80
TODAY = date(2026, 10, 14)

FIRST = "Anna Piotr Katarzyna Marek Ola Tomasz Ewa Jan Zofia Kamil Marta Adam Julia Bartek Natalia Paweł Ida Michał Ala Robert".split()
LAST = "Nowak Kowalski Wiśniewska Wójcik Kamińska Lewandowski Zielińska Szymański Woźniak Dąbrowski Kozłowska Jankowski".split()
LOCS = {"Kraków": 1, "Warsaw": 1, "Wrocław": 1, "Gdańsk": 1, "Berlin": 1, "London": 0, "Lisbon": 0, "Bangalore": 5}
DOMAINS = ["fintech", "healthcare", "e-commerce", "logistics", "telecom", "energy"]
ROLE_STACK = {
    "Backend Developer": ["python", "java", "spring boot", "fastapi", "django", "postgresql", "kafka", "docker", "aws", "sql", "kotlin", "node.js"],
    "Frontend Developer": ["javascript", "typescript", "react", "angular", "node.js", "cypress", "docker"],
    "Data Engineer": ["python", "sql", "spark", "airflow", "dbt", "kafka", "postgresql", "aws", "gcp", "docker"],
    "DevOps Engineer": ["docker", "kubernetes", "terraform", "aws", "azure", "ci/cd", "python", "gcp"],
    "QA Engineer": ["selenium", "cypress", "pytest", "python", "java", "ci/cd", "sql"],
    "ML Engineer": ["python", "pytorch", "scikit-learn", "mlops", "spark", "docker", "sql", "gcp"],
    "Tech Lead": ["java", "python", "kubernetes", "aws", "kafka", "docker", "spring boot", "react"],
}


def dirty_alias(canon):
    v = random.choice(TECH_ALIASES[canon])
    return random.choice([v, v, v.upper(), v.title(), f"  {v} "])


def dirty_date(d):
    return d.isoformat() if random.random() < 0.8 else d.strftime("%d/%m/%Y")


emps, skills, projects, avail = [], [], [], []
for i in range(1, N + 1):
    eid = f"E{i:04d}"
    role = random.choices(list(ROLE_ALIASES), weights=[26, 14, 14, 10, 12, 8, 6])[0]
    sen = random.choices(["Junior", "Mid", "Senior", "Lead"], weights=[20, 35, 33, 12])[0]
    exp = {"Junior": random.uniform(0.5, 2.5), "Mid": random.uniform(2.5, 6), "Senior": random.uniform(6, 12), "Lead": random.uniform(10, 18)}[sen]
    loc = random.choice(list(LOCS))
    role_raw = random.choice(ROLE_ALIASES[role]) if random.random() < 0.4 else role
    emps.append(dict(employee_id=eid, full_name=f"{random.choice(FIRST)} {random.choice(LAST)}",
                     email=f"{eid.lower()}@corp.example", role=role_raw,
                     seniority=random.choice([sen, sen.lower(), {"Senior": "Sr", "Junior": "Jr"}.get(sen, sen)]),
                     location=loc, timezone=f"UTC+{LOCS[loc]}", total_experience_years=round(exp, 1),
                     hire_date=dirty_date(TODAY - timedelta(days=int(exp * 200 + 100)))))
    for t in random.sample(ROLE_STACK[role], k=min(len(ROLE_STACK[role]), random.randint(3, 7))):
        skills.append(dict(employee_id=eid, technology=dirty_alias(t), years=round(random.uniform(0.3, min(exp, 10)), 1),
                           proficiency=random.randint(1, 5)))
    for p in range(random.randint(1, 4)):
        s = TODAY - timedelta(days=random.randint(200, 2500))
        e = s + timedelta(days=random.randint(90, 600))
        projects.append(dict(employee_id=eid, project_name=f"Project-{random.randint(100,999)}", domain=random.choice(DOMAINS),
                             role=role_raw, technologies=";".join(dirty_alias(t) for t in random.sample(ROLE_STACK[role], 3)),
                             start_date=dirty_date(s), end_date=dirty_date(min(e, TODAY))))
    start = TODAY + timedelta(days=random.choice([-30, 0, 14, 30, 60, 120]))
    avail.append(dict(employee_id=eid, available_from=dirty_date(start),
                      available_to=dirty_date(start + timedelta(days=random.choice([90, 180, 365, 540]))),
                      allocation_pct=random.choice([100, 100, 100, 80, 50, 50, 20, 0])))

# ---- inject data-quality problems ----
skills += random.sample(skills, 8)                                           # exact duplicates
emps.append(dict(emps[3]))                                                   # duplicate employee
skills.append(dict(employee_id="E0007", technology="python", years=-2, proficiency=3))   # negative years
skills.append(dict(employee_id="E0009", technology="COBOL-ish", years=3, proficiency=2)) # unknown tech
skills.append(dict(employee_id="E9999", technology="python", years=4, proficiency=4))    # orphan
emps.append(dict(employee_id="E0099", full_name="Bad Row", email="", role="", seniority="Mid", location="Kraków",
                 timezone="UTC+1", total_experience_years=5, hire_date="2020-01-01"))        # missing role
emps.append(dict(employee_id="E0098", full_name="Neg Exp", email="", role="QA", seniority="Mid", location="Kraków",
                 timezone="UTC+1", total_experience_years=-3, hire_date="not-a-date"))
avail.append(dict(employee_id="E0010", available_from="2026-01-01", available_to="2025-01-01", allocation_pct=100))  # inverted
avail.append(dict(employee_id="E0011", available_from="2026-11-01", available_to="2027-06-01", allocation_pct=250))  # >100


def dump(name, rows):
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


for n, r in [("employees", emps), ("skills", skills), ("projects", projects), ("availability", avail)]:
    dump(n, r)
print(f"Wrote dirty synthetic data to {OUT}: {len(emps)} employees, {len(skills)} skills, {len(projects)} projects, {len(avail)} availability rows")
