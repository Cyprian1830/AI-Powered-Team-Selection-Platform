import sqlite3
from collections import defaultdict
from datetime import date
from typing import Optional

from . import config
from .models import AvailabilityWindow, Employee


class EmployeeRepository:
    """Read-side access. Swap for Postgres/warehouse implementation in production."""

    def __init__(self, db_path=None):
        self.db_path = db_path or config.DB_PATH

    def _con(self):
        c = sqlite3.connect(self.db_path); c.row_factory = sqlite3.Row; return c

    def load_all(self) -> list[Employee]:
        con = self._con()
        skills, domains, avail = defaultdict(dict), defaultdict(lambda: defaultdict(float)), defaultdict(list)
        for r in con.execute("SELECT * FROM employee_skills"): skills[r["employee_id"]][r["technology"]] = r["years"]
        for r in con.execute("SELECT employee_id, domain, start_date, end_date FROM project_history"):
            yrs = (date.fromisoformat(r["end_date"]) - date.fromisoformat(r["start_date"])).days / 365.25
            domains[r["employee_id"]][r["domain"]] += round(yrs, 2)
        for r in con.execute("SELECT * FROM availability"):
            avail[r["employee_id"]].append(AvailabilityWindow(start=r["available_from"], end=r["available_to"], allocation_pct=r["allocation_pct"]))
        out = [Employee(employee_id=r["employee_id"], full_name=r["full_name"], role=r["role"], seniority=r["seniority"],
                        location=r["location"], utc_offset=r["utc_offset"], total_experience_years=r["total_experience_years"],
                        skills=skills[r["employee_id"]], domains=dict(domains[r["employee_id"]]), availability=avail[r["employee_id"]])
               for r in con.execute("SELECT * FROM employees")]
        con.close(); return out

    def get(self, employee_id: str) -> Optional[Employee]:
        return next((e for e in self.load_all() if e.employee_id == employee_id), None)

    # --- audit / human-in-the-loop persistence ---
    def save_recommendation(self, request_id, request_json, result_json):
        con = self._con()
        with con: con.execute("INSERT INTO recommendations VALUES(?,datetime('now'),?,?)", (request_id, request_json, result_json))
        con.close()

    def get_recommendation(self, request_id):
        con = self._con(); r = con.execute("SELECT result_json FROM recommendations WHERE request_id=?", (request_id,)).fetchone(); con.close()
        return r[0] if r else None

    def save_decision(self, request_id, manager, selected_ids, comment):
        con = self._con()
        with con: con.execute("INSERT INTO decisions VALUES(?,datetime('now'),?,?,?)", (request_id, manager, ",".join(selected_ids), comment))
        con.close()
