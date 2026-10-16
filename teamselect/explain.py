"""AI explanation layer. The LLM ONLY verbalises results computed by the deterministic engine.

Guardrails: (1) LLM receives a pseudonymised payload (employee_id, no names/emails);
(2) it cannot change scores/eligibility - output is plain text attached to the result;
(3) output is validated (must reference every team member id); (4) any failure => template fallback.
"""
import json, os

from . import config
from .models import RecommendationResult

SYSTEM = ("You are an assistant for a delivery manager. Explain a team recommendation that was computed by a deterministic "
          "scoring engine. Use ONLY the facts in the JSON. Never invent skills, numbers or people, never change scores, "
          "refer to people by employee_id. Be concise: 1) summary, 2) per-member rationale (strengths and gaps), "
          "3) team-level risks, 4) one sentence reminding that the manager makes the final decision.")


def build_payload(r: RecommendationResult) -> dict:
    """Pseudonymised, minimal data (GDPR data minimisation)."""
    return {
        "project": r.request.project_name, "team_size_requested": r.request.team_size,
        "eligible_candidates": r.eligible_count, "rejected_by_hard_constraints": r.rejection_summary,
        "team_score": r.team.team_score, "uncovered_technologies": r.team.uncovered_technologies,
        "unfilled_roles": r.team.unfilled_roles, "warnings": r.team.warnings,
        "members": [{"employee_id": m.candidate.employee_id, "slot": m.slot, "role": m.candidate.role,
                     "seniority": m.candidate.seniority, "score": m.candidate.score, "matched": m.candidate.matched,
                     "gaps": m.candidate.gaps, "adds_team_coverage": m.adds_coverage,
                     "components": [{"name": c.name, "points": c.points, "max": c.weight} for c in m.candidate.components]}
                    for m in r.team.members],
        "alternatives": r.alternatives,
    }


def template_explanation(r: RecommendationResult) -> str:
    t = r.team
    lines = [f"Recommended team for '{r.request.project_name}': {len(t.members)} of {r.request.team_size} people "
             f"(team score {t.team_score}/100). {r.eligible_count} of {r.eligible_count + r.rejected_count} employees passed the hard constraints.", ""]
    for m in t.members:
        c = m.candidate
        lines.append(f"- {c.employee_id} ({c.role}, {c.seniority}, {c.total_experience_years:g}y) – score {c.score}/100, slot: {m.slot}.")
        lines.append(f"  Strengths: {', '.join(c.matched[:5]) or 'none beyond hard constraints'}.")
        lines.append(f"  Gaps: {', '.join(c.gaps[:4]) or 'none'}." + (f" Adds team coverage: {', '.join(m.adds_coverage)}." if m.adds_coverage else ""))
    lines.append("")
    lines.append("Team risks: " + ("; ".join(t.warnings) if t.warnings else "all required technologies and roles are covered."))
    lines.append("This is a recommendation only – the final staffing decision remains with the manager.")
    return "\n".join(lines)


def explain(r: RecommendationResult) -> dict:
    payload = build_payload(r)
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            msg = anthropic.Anthropic().messages.create(model=config.LLM_MODEL, max_tokens=900, system=SYSTEM,
                                                        messages=[{"role": "user", "content": json.dumps(payload)}])
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            if all(m.candidate.employee_id in text for m in r.team.members):   # output validation
                return {"text": text, "source": "llm", "model": config.LLM_MODEL}
        except Exception as exc:  # network, quota, SDK missing -> degrade gracefully
            return {"text": template_explanation(r), "source": "template", "model": None, "note": f"LLM unavailable: {type(exc).__name__}"}
    return {"text": template_explanation(r), "source": "template", "model": None}
