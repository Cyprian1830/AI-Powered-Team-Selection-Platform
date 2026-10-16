import json, subprocess, sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def db(tmp_path_factory):
    d = tmp_path_factory.mktemp("ts"); raw = d / "raw"
    subprocess.run([sys.executable, str(ROOT / "scripts/generate_synthetic_data.py"), str(raw)], check=True, capture_output=True)
    from teamselect import etl
    stats = etl.extract_and_validate(raw, d / "staging"); etl.load(d / "staging", d / "t.db"); etl.quality_check(d / "t.db")
    return d / "t.db", stats


REQ = dict(required_technologies=[{"name": "k8s", "min_years": 1}, {"name": "Python"}], required_roles=[{"role": "devops", "count": 1}, {"role": "qa", "count": 1}],
           team_size=3, start_date="2026-11-15", end_date="2027-02-28", min_allocation_pct=50, min_total_experience_years=2)


def test_etl_rejects_and_normalises(db):
    path, stats = db
    assert stats["rejected"] >= 7
    import sqlite3
    c = sqlite3.connect(path)
    techs = {r[0] for r in c.execute("SELECT DISTINCT technology FROM employee_skills")}
    assert "k8s" not in techs and "py" not in techs and "COBOL-ish" not in techs
    assert c.execute("SELECT COUNT(*) FROM employee_skills WHERE years<0").fetchone()[0] == 0


def test_request_normalisation():
    from teamselect.models import ProjectRequest
    r = ProjectRequest(**REQ)
    assert r.required_technologies[0].name == "kubernetes" and r.required_roles[0].role == "DevOps Engineer"


def test_hard_constraints_hold_and_deterministic(db):
    from teamselect.models import ProjectRequest
    from teamselect.repository import EmployeeRepository
    from teamselect.service import recommend
    repo, req = EmployeeRepository(db[0]), ProjectRequest(**REQ)
    a, b = recommend(req, repo), recommend(req, repo)
    assert [c.employee_id for c in a.ranked_candidates] == [c.employee_id for c in b.ranked_candidates]
    emps = {e.employee_id: e for e in repo.load_all()}
    for m in a.team.members:
        e = emps[m.candidate.employee_id]
        assert e.role in ("DevOps Engineer", "QA Engineer") and e.total_experience_years >= 2
        assert any(w.start <= date(2026, 11, 15) and w.end >= date(2027, 2, 28) and w.allocation_pct >= 50 for w in e.availability)
    assert all(0 <= c.score <= 100 for c in a.ranked_candidates)
    assert all(abs(sum(x.points for x in c.components) - c.score) < 0.2 for c in a.ranked_candidates)


def test_api_flow(db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from teamselect.api import app, get_repo
    from teamselect.repository import EmployeeRepository
    app.dependency_overrides[get_repo] = lambda: EmployeeRepository(db[0])
    c = TestClient(app)
    assert c.get("/health").json()["status"] == "ok"
    r = c.post("/recommendations", json=REQ); assert r.status_code == 200, r.text
    body = r.json(); assert body["explanation"]["source"] == "template"
    ids = [m["candidate"]["employee_id"] for m in body["team"]["members"]]
    assert c.get(f"/recommendations/{body['request_id']}").status_code == 200
    assert c.post(f"/recommendations/{body['request_id']}/decision", json={"manager": "pm1", "selected_employee_ids": ids}).status_code == 200
    assert c.post(f"/recommendations/{body['request_id']}/decision", json={"manager": "pm1", "selected_employee_ids": ["NOPE"]}).status_code == 422
    assert c.post("/recommendations", json={**REQ, "team_size": 1}).status_code == 422


def test_ui_served(db):
    from teamselect.api import app
    r = TestClient(app).get("/")
    assert r.status_code == 200 and "Dobór zespołu" in r.text
