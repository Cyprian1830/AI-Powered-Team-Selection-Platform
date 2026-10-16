"""Batch ETL: raw CSV -> validated/normalised staging (JSONL) -> SQLite star-ish model.

Steps are separate functions so Airflow can run them as individual tasks.
Bad rows are never dropped silently: they go to `rejected_records` with a reason.
"""
import csv, json, re, sqlite3
from datetime import date, datetime
from pathlib import Path

from . import config
from .taxonomy import normalize_role, normalize_seniority, normalize_tech

SCHEMA = """
CREATE TABLE employees(employee_id TEXT PRIMARY KEY, full_name TEXT NOT NULL, email TEXT, role TEXT NOT NULL,
  seniority TEXT NOT NULL, location TEXT, utc_offset INTEGER, total_experience_years REAL NOT NULL, hire_date TEXT);
CREATE TABLE employee_skills(employee_id TEXT REFERENCES employees, technology TEXT, years REAL, proficiency INTEGER,
  PRIMARY KEY(employee_id, technology));
CREATE TABLE project_history(employee_id TEXT REFERENCES employees, project_name TEXT, domain TEXT, role TEXT,
  technologies TEXT, start_date TEXT, end_date TEXT);
CREATE TABLE availability(employee_id TEXT REFERENCES employees, available_from TEXT, available_to TEXT, allocation_pct INTEGER);
CREATE TABLE rejected_records(entity TEXT, reason TEXT, payload TEXT);
CREATE TABLE etl_runs(run_at TEXT, stats TEXT);
CREATE TABLE IF NOT EXISTS recommendations(request_id TEXT PRIMARY KEY, created_at TEXT, request_json TEXT, result_json TEXT);
CREATE TABLE IF NOT EXISTS decisions(request_id TEXT, decided_at TEXT, manager TEXT, selected_ids TEXT, comment TEXT);
CREATE INDEX idx_skill_tech ON employee_skills(technology);
CREATE INDEX idx_avail_emp ON availability(employee_id);
"""


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def _date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _num(s):
    try:
        return float(str(s).strip())
    except (TypeError, ValueError):
        return None


def extract_and_validate(raw_dir=None, staging_dir=None) -> dict:
    """Extract + clean + validate + normalise. Returns stats; writes staging JSONL."""
    raw_dir, staging_dir = Path(raw_dir or config.RAW_DIR), Path(staging_dir or config.STAGING_DIR)
    staging_dir.mkdir(parents=True, exist_ok=True)
    rejects, clean = [], {"employees": {}, "skills": {}, "projects": [], "availability": []}
    rej = lambda ent, why, row: rejects.append({"entity": ent, "reason": why, "payload": row})

    for r in _read(raw_dir / "employees.csv"):
        eid = (r.get("employee_id") or "").strip()
        role, sen = normalize_role(r.get("role")), normalize_seniority(r.get("seniority"))
        exp = _num(r.get("total_experience_years"))
        m = re.match(r"UTC([+-]\d+)", (r.get("timezone") or "").strip())
        if not eid: rej("employees", "missing employee_id", r)
        elif eid in clean["employees"]: rej("employees", "duplicate employee_id", r)
        elif not role: rej("employees", f"unknown/missing role: {r.get('role')!r}", r)
        elif not sen: rej("employees", f"unknown seniority: {r.get('seniority')!r}", r)
        elif exp is None or exp < 0 or exp > 50: rej("employees", f"invalid experience: {r.get('total_experience_years')!r}", r)
        else:
            hd = _date(r.get("hire_date"))
            clean["employees"][eid] = dict(employee_id=eid, full_name=r["full_name"].strip(), email=r.get("email") or None,
                role=role, seniority=sen, location=(r.get("location") or "").strip() or None,
                utc_offset=int(m.group(1)) if m else None, total_experience_years=exp,
                hire_date=hd.isoformat() if hd else None)

    for r in _read(raw_dir / "skills.csv"):
        eid, tech, yrs = r["employee_id"].strip(), normalize_tech(r["technology"]), _num(r["years"])
        if eid not in clean["employees"]: rej("skills", "orphan: employee not in valid employees", r)
        elif not tech: rej("skills", f"unknown technology: {r['technology']!r}", r)
        elif yrs is None or yrs < 0: rej("skills", f"invalid years: {r['years']!r}", r)
        else:
            key = (eid, tech)  # de-duplicate: keep the highest-years record
            prev = clean["skills"].get(key)
            if not prev or yrs > prev["years"]:
                clean["skills"][key] = dict(employee_id=eid, technology=tech, years=yrs,
                                            proficiency=int(_num(r.get("proficiency")) or 3))

    for r in _read(raw_dir / "projects.csv"):
        eid, s, e = r["employee_id"].strip(), _date(r["start_date"]), _date(r["end_date"])
        if eid not in clean["employees"]: rej("projects", "orphan employee", r)
        elif not s or not e or e < s: rej("projects", "invalid project dates", r)
        else:
            techs = sorted({t for t in (normalize_tech(x) for x in r["technologies"].split(";")) if t})
            clean["projects"].append(dict(employee_id=eid, project_name=r["project_name"].strip(),
                domain=r["domain"].strip().lower(), role=normalize_role(r["role"]), technologies=techs,
                start_date=s.isoformat(), end_date=e.isoformat()))

    for r in _read(raw_dir / "availability.csv"):
        eid, f, t, a = r["employee_id"].strip(), _date(r["available_from"]), _date(r["available_to"]), _num(r["allocation_pct"])
        if eid not in clean["employees"]: rej("availability", "orphan employee", r)
        elif not f or not t or t < f: rej("availability", "invalid availability window", r)
        elif a is None or not 0 <= a <= 100: rej("availability", f"allocation out of range: {r['allocation_pct']!r}", r)
        else:
            clean["availability"].append(dict(employee_id=eid, available_from=f.isoformat(), available_to=t.isoformat(),
                                              allocation_pct=int(a)))

    for name, rows in [("employees", clean["employees"].values()), ("skills", clean["skills"].values()),
                       ("projects", clean["projects"]), ("availability", clean["availability"]), ("rejected", rejects)]:
        with open(staging_dir / f"{name}.jsonl", "w", encoding="utf-8") as f:
            f.writelines(json.dumps(x, ensure_ascii=False) + "\n" for x in rows)
    return {"employees": len(clean["employees"]), "skills": len(clean["skills"]), "projects": len(clean["projects"]),
            "availability": len(clean["availability"]), "rejected": len(rejects)}


def load(staging_dir=None, db_path=None) -> dict:
    """Rebuild the serving DB from staging inside one transaction (swap-in, keeps audit tables)."""
    staging_dir, db_path = Path(staging_dir or config.STAGING_DIR), Path(db_path or config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    rd = lambda n: [json.loads(l) for l in open(staging_dir / f"{n}.jsonl", encoding="utf-8")]
    con = sqlite3.connect(db_path)
    keep = {}
    for t in ("recommendations", "decisions"):  # audit data survives re-loads
        try: keep[t] = con.execute(f"SELECT * FROM {t}").fetchall()
        except sqlite3.OperationalError: keep[t] = []
    with con:
        for t in ("employees", "employee_skills", "project_history", "availability", "rejected_records", "etl_runs",
                  "recommendations", "decisions"):
            con.execute(f"DROP TABLE IF EXISTS {t}")
        con.executescript(SCHEMA)
        con.executemany("INSERT INTO employees VALUES(:employee_id,:full_name,:email,:role,:seniority,:location,:utc_offset,:total_experience_years,:hire_date)", rd("employees"))
        con.executemany("INSERT INTO employee_skills VALUES(:employee_id,:technology,:years,:proficiency)", rd("skills"))
        con.executemany("INSERT INTO project_history VALUES(?,?,?,?,?,?,?)",
                        [(p["employee_id"], p["project_name"], p["domain"], p["role"], ";".join(p["technologies"]), p["start_date"], p["end_date"]) for p in rd("projects")])
        con.executemany("INSERT INTO availability VALUES(:employee_id,:available_from,:available_to,:allocation_pct)", rd("availability"))
        con.executemany("INSERT INTO rejected_records VALUES(?,?,?)", [(r["entity"], r["reason"], json.dumps(r["payload"], ensure_ascii=False)) for r in rd("rejected")])
        for t, rows in keep.items():
            if rows: con.executemany(f"INSERT INTO {t} VALUES({','.join('?' * len(rows[0]))})", rows)
    n = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("employees", "employee_skills", "project_history", "availability", "rejected_records")}
    con.execute("INSERT INTO etl_runs VALUES(?,?)", (datetime.now().isoformat(), json.dumps(n))); con.commit(); con.close()
    return n


def quality_check(db_path=None, min_employees=10, max_reject_ratio=0.25) -> dict:
    """Gate before serving traffic: fail the DAG if data looks broken."""
    con = sqlite3.connect(Path(db_path or config.DB_PATH))
    n_emp = con.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    n_rej = con.execute("SELECT COUNT(*) FROM rejected_records").fetchone()[0]
    no_skill = con.execute("SELECT COUNT(*) FROM employees WHERE employee_id NOT IN (SELECT employee_id FROM employee_skills)").fetchone()[0]
    total = n_emp + n_rej
    if n_emp < min_employees: raise ValueError(f"Too few employees loaded: {n_emp}")
    if total and n_rej / total > max_reject_ratio: raise ValueError(f"Reject ratio too high: {n_rej}/{total}")
    return {"employees": n_emp, "rejected": n_rej, "employees_without_skills": no_skill}


def run_all():
    s = extract_and_validate(); l = load(); q = quality_check()
    return {"extract": s, "load": l, "quality": q}


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2))
