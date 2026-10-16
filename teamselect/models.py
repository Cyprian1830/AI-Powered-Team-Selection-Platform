from __future__ import annotations
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from .taxonomy import normalize_role, normalize_seniority, normalize_tech


class TechRequirement(BaseModel):
    name: str
    min_years: float = Field(0, ge=0)
    must_have: bool = False          # True => hard constraint
    weight: float = Field(1.0, gt=0)

    @field_validator("name")
    @classmethod
    def _canon(cls, v):
        c = normalize_tech(v)
        if not c: raise ValueError(f"Unknown technology '{v}'")
        return c


class RoleRequirement(BaseModel):
    role: str
    count: int = Field(1, ge=1)

    @field_validator("role")
    @classmethod
    def _canon(cls, v):
        c = normalize_role(v)
        if not c: raise ValueError(f"Unknown role '{v}'")
        return c


class ProjectRequest(BaseModel):
    project_name: str = "Untitled project"
    required_technologies: list[TechRequirement]
    required_roles: list[RoleRequirement]
    team_size: int = Field(ge=1, le=50)
    start_date: date
    end_date: date
    min_allocation_pct: int = Field(50, ge=1, le=100)
    min_total_experience_years: float = Field(0, ge=0)          # hard
    # --- soft ---
    preferred_seniority: list[str] = []
    preferred_domains: list[str] = []
    preferred_locations: list[str] = []
    reference_utc_offset: Optional[int] = None
    max_timezone_diff_hours: int = 3
    top_n_candidates: int = Field(10, ge=1, le=100)

    @field_validator("preferred_seniority")
    @classmethod
    def _sen(cls, v):
        out = [normalize_seniority(x) for x in v]
        if None in out: raise ValueError("Unknown seniority level")
        return out

    @field_validator("preferred_domains")
    @classmethod
    def _dom(cls, v): return [d.strip().lower() for d in v]

    @model_validator(mode="after")
    def _check(self):
        if self.end_date < self.start_date: raise ValueError("end_date before start_date")
        if sum(r.count for r in self.required_roles) > self.team_size:
            raise ValueError("Sum of required role counts exceeds team_size")
        return self


# ---- domain objects / results ----
class AvailabilityWindow(BaseModel):
    start: date; end: date; allocation_pct: int


class Employee(BaseModel):
    employee_id: str; full_name: str; role: str; seniority: str
    location: Optional[str]; utc_offset: Optional[int]; total_experience_years: float
    skills: dict[str, float]                 # tech -> years
    domains: dict[str, float]                # domain -> years on projects
    availability: list[AvailabilityWindow]


class ScoreComponent(BaseModel):
    name: str; weight: float; value: float   # value 0..1
    points: float                            # weight * value (on a 0..100 scale)
    detail: str


class CandidateResult(BaseModel):
    employee_id: str; full_name: str; role: str; seniority: str; location: Optional[str]
    total_experience_years: float
    score: float                             # 0..100
    components: list[ScoreComponent]
    matched: list[str]; gaps: list[str]; reasons: list[str]


class Rejection(BaseModel):
    employee_id: str; full_name: str; reasons: list[str]


class TeamMember(BaseModel):
    slot: str                                # role slot it fills
    candidate: CandidateResult
    adds_coverage: list[str]                 # technologies this person newly covers in the team


class TeamRecommendation(BaseModel):
    members: list[TeamMember]
    team_score: float
    covered_technologies: list[str]
    uncovered_technologies: list[str]
    unfilled_roles: list[str]
    warnings: list[str]


class RecommendationResult(BaseModel):
    request_id: str
    request: ProjectRequest
    eligible_count: int
    rejected_count: int
    rejection_summary: dict[str, int]
    ranked_candidates: list[CandidateResult]
    team: TeamRecommendation
    alternatives: dict[str, list[str]] = {}  # role -> next-best employee_ids (for the manager)
    explanation: Optional[dict] = None
