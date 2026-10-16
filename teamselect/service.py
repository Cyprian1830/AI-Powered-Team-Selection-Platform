import uuid
from collections import Counter

from .matching import filter_eligible
from .models import ProjectRequest, RecommendationResult
from .repository import EmployeeRepository
from .scoring import rank
from .team import build_team


def recommend(req: ProjectRequest, repo: EmployeeRepository) -> RecommendationResult:
    """Pure, deterministic pipeline: filter -> score -> assemble. No LLM involved."""
    employees = repo.load_all()
    eligible, rejected = filter_eligible(employees, req)
    ranked = rank(eligible, req)
    skills = {e.employee_id: e.skills for e in eligible}
    team = build_team(ranked, req, skills)
    def _cat(reason):
        for key, label in (("role", "role"), ("experience", "experience"), ("window", "availability"),
                           ("capacity", "capacity"), ("must-have", "must-have technology")):
            if key in reason: return label
        return "other"
    summary = Counter(_cat(r) for rj in rejected for r in rj.reasons)
    chosen = {m.candidate.employee_id for m in team.members}
    alts = {r.role: [c.employee_id for c in ranked if c.role == r.role and c.employee_id not in chosen][:3] for r in req.required_roles}
    return RecommendationResult(request_id=str(uuid.uuid4()), request=req, eligible_count=len(eligible), rejected_count=len(rejected),
                                rejection_summary=dict(summary), ranked_candidates=ranked[:req.top_n_candidates], team=team, alternatives=alts)
