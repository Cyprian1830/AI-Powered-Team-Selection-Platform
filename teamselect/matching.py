"""Deterministic eligibility filter. HARD constraints only; soft criteria live in scoring.py."""
from .models import Employee, ProjectRequest, Rejection


def check_hard_constraints(e: Employee, req: ProjectRequest) -> list[str]:
    """Return list of violated hard constraints (empty list => eligible)."""
    why = []
    roles = {r.role for r in req.required_roles}
    if e.role not in roles:
        why.append(f"role '{e.role}' not among required roles")
    if e.total_experience_years < req.min_total_experience_years:
        why.append(f"experience {e.total_experience_years}y < required {req.min_total_experience_years}y")
    # one availability window must cover the whole period with enough allocation
    covering = [w for w in e.availability if w.start <= req.start_date and w.end >= req.end_date]
    if not covering:
        why.append("not available for the whole requested window")
    elif max(w.allocation_pct for w in covering) < req.min_allocation_pct:
        why.append(f"free capacity {max(w.allocation_pct for w in covering)}% < required {req.min_allocation_pct}%")
    for t in req.required_technologies:
        if t.must_have and e.skills.get(t.name, 0) < max(t.min_years, 0.01):
            why.append(f"must-have '{t.name}' missing or below {t.min_years}y")
    return why


def filter_eligible(employees: list[Employee], req: ProjectRequest):
    eligible, rejected = [], []
    for e in employees:
        why = check_hard_constraints(e, req)
        (rejected.append(Rejection(employee_id=e.employee_id, full_name=e.full_name, reasons=why)) if why else eligible.append(e))
    return eligible, rejected
