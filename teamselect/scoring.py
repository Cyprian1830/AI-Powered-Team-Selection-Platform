"""Explainable scoring (0-100). Every point is traceable to a component with a human-readable detail.

Weights are relative; components for criteria the manager did NOT specify are switched off and the
remaining weights are re-normalised, so a candidate is never punished for an unspecified preference.
"""
from .models import CandidateResult, Employee, ProjectRequest, ScoreComponent
from .taxonomy import SENIORITY_LEVELS

WEIGHTS = {"technologies": 50, "experience": 15, "seniority": 10, "domain": 15, "location": 10}


def _technologies(e, req):
    tot = sum(t.weight for t in req.required_technologies); got = 0.0; matched, gaps = [], []
    for t in req.required_technologies:
        y = e.skills.get(t.name, 0.0)
        if y <= 0:
            gaps.append(f"{t.name}: missing"); continue
        credit = min(y / t.min_years, 1.0) if t.min_years else 1.0
        got += t.weight * credit
        (matched if credit >= 1 else gaps).append(f"{t.name}: {y:g}y" + ("" if credit >= 1 else f" (required {t.min_years:g}y)"))
    v = got / tot if tot else 1.0
    return v, f"{len(matched)}/{len(req.required_technologies)} required technologies fully met", matched, gaps


def _experience(e, req):
    target = max(req.min_total_experience_years * 2, 5.0)
    v = min(e.total_experience_years / target, 1.0)
    return v, f"{e.total_experience_years:g}y total experience (full marks at {target:g}y)", [], []


def _seniority(e, req):
    idx = SENIORITY_LEVELS.index
    best = min(abs(idx(e.seniority) - idx(p)) for p in req.preferred_seniority)
    v = {0: 1.0, 1: 0.5}.get(best, 0.0)
    ok = e.seniority in req.preferred_seniority
    return v, f"{e.seniority} vs preferred {'/'.join(req.preferred_seniority)}", ([f"seniority {e.seniority}"] if ok else []), ([] if ok else [f"seniority {e.seniority} not in preferred {req.preferred_seniority}"])


def _domain(e, req):
    hit = {d: e.domains[d] for d in req.preferred_domains if e.domains.get(d, 0) > 0}
    miss = [d for d in req.preferred_domains if d not in hit]
    return (len(hit) / len(req.preferred_domains), f"domain experience in {len(hit)}/{len(req.preferred_domains)} preferred domains",
            [f"domain {d}: {y:.1f}y" for d, y in hit.items()], [f"no {d} domain experience" for d in miss])


def _location(e, req):
    if e.location and e.location in req.preferred_locations:
        return 1.0, f"based in preferred location {e.location}", [f"location {e.location}"], []
    if req.reference_utc_offset is not None and e.utc_offset is not None:
        diff = abs(e.utc_offset - req.reference_utc_offset)
        v = 1.0 if diff <= req.max_timezone_diff_hours else max(0.0, 1 - (diff - req.max_timezone_diff_hours) / 4)
        ok = diff <= req.max_timezone_diff_hours
        return v, f"time-zone difference {diff}h (allowed {req.max_timezone_diff_hours}h)", ([f"time zone ±{diff}h"] if ok else []), ([] if ok else [f"time zone ±{diff}h exceeds {req.max_timezone_diff_hours}h"])
    return 0.0, f"{e.location} is not a preferred location", [], [f"location {e.location} not preferred"]


def score_candidate(e: Employee, req: ProjectRequest) -> CandidateResult:
    active = {"technologies": _technologies, "experience": _experience}
    if req.preferred_seniority: active["seniority"] = _seniority
    if req.preferred_domains: active["domain"] = _domain
    if req.preferred_locations or req.reference_utc_offset is not None: active["location"] = _location
    total_w = sum(WEIGHTS[k] for k in active)
    comps, matched, gaps = [], [], []
    for name, fn in active.items():
        v, detail, m, g = fn(e, req)
        w = WEIGHTS[name] / total_w * 100
        comps.append(ScoreComponent(name=name, weight=round(w, 1), value=round(v, 3), points=round(w * v, 1), detail=detail))
        matched += m; gaps += g
    score = round(sum(c.points for c in comps), 1)
    top = max(comps, key=lambda c: c.points)
    reasons = [f"Strongest component: {top.name} ({top.points}/{top.weight}) – {top.detail}"]
    weakest = min(comps, key=lambda c: c.value)
    if weakest.value < 1: reasons.append(f"Biggest shortfall: {weakest.name} ({weakest.points}/{weakest.weight}) – {weakest.detail}")
    return CandidateResult(employee_id=e.employee_id, full_name=e.full_name, role=e.role, seniority=e.seniority, location=e.location,
                           total_experience_years=e.total_experience_years, score=score, components=comps, matched=matched, gaps=gaps, reasons=reasons)


def rank(employees, req):
    # tie-break on id => fully deterministic ordering
    return sorted((score_candidate(e, req) for e in employees), key=lambda c: (-c.score, c.employee_id))
