"""Team assembly: greedy slot filling with a team-level coverage bonus (still fully deterministic)."""
from .models import CandidateResult, ProjectRequest, TeamMember, TeamRecommendation

COVERAGE_BONUS = 10.0   # max extra points for covering technologies the team does not have yet


def build_team(ranked: list[CandidateResult], req: ProjectRequest, skills_by_emp: dict[str, dict[str, float]]) -> TeamRecommendation:
    req_w = {t.name: t.weight for t in req.required_technologies}; total_w = sum(req_w.values())
    covered: set[str] = set(); chosen: list[TeamMember] = []; used: set[str] = set(); warnings, unfilled = [], []

    def new_cov(c):  return [t for t in req_w if t not in covered and skills_by_emp[c.employee_id].get(t, 0) > 0]
    def adj(c):      return c.score + COVERAGE_BONUS * sum(req_w[t] for t in new_cov(c)) / total_w

    def pick(pool, slot):
        if not pool: return False
        best = max(pool, key=lambda c: (adj(c), -ord(c.employee_id[-1])))   # deterministic
        chosen.append(TeamMember(slot=slot, candidate=best, adds_coverage=new_cov(best)))
        covered.update(new_cov(best)); used.add(best.employee_id); return True

    # scarcest roles first, so a rare role doesn't lose its only candidate to a flexible slot
    pools = {r.role: [c for c in ranked if c.role == r.role] for r in req.required_roles}
    for r in sorted(req.required_roles, key=lambda r: len(pools[r.role])):
        for i in range(r.count):
            if not pick([c for c in pools[r.role] if c.employee_id not in used], r.role):
                unfilled.append(r.role); warnings.append(f"No eligible candidate left for role '{r.role}' (slot {i + 1}).")
    while len(chosen) < req.team_size:
        if not pick([c for c in ranked if c.employee_id not in used], "Flex"):
            warnings.append(f"Only {len(chosen)} eligible people found for team size {req.team_size}."); break

    uncovered = [t for t in req_w if t not in covered]
    for t in uncovered: warnings.append(f"Nobody in the team covers required technology '{t}'.")
    cov_ratio = (total_w - sum(req_w[t] for t in uncovered)) / total_w if total_w else 1
    avg = sum(m.candidate.score for m in chosen) / len(chosen) if chosen else 0
    fill = len(chosen) / req.team_size
    return TeamRecommendation(members=chosen, team_score=round(avg * 0.6 + cov_ratio * 100 * 0.3 + fill * 100 * 0.1, 1),
                              covered_technologies=sorted(covered), uncovered_technologies=uncovered, unfilled_roles=unfilled, warnings=warnings)
