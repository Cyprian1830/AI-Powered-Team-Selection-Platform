"""Real-time layer. Reads the serving DB prepared by the batch ETL (Airflow); never runs ETL itself."""
import json
from typing import Optional

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .explain import explain
from .models import ProjectRequest, RecommendationResult
from .repository import EmployeeRepository
from .service import recommend

app = FastAPI(title="Team Selection API", version="0.1.0")


@app.get("/", include_in_schema=False)
def ui():
    """Simple web form for managers (API docs stay at /docs)."""
    return FileResponse(Path(__file__).parent / "static" / "index.html")


def get_repo() -> EmployeeRepository:
    return EmployeeRepository()


class Decision(BaseModel):
    manager: str
    selected_employee_ids: list[str]
    comment: Optional[str] = None      # e.g. why the manager deviated from the recommendation


@app.get("/health")
def health(repo: EmployeeRepository = Depends(get_repo)):
    return {"status": "ok", "employees": len(repo.load_all())}


@app.post("/recommendations", response_model=RecommendationResult)
def create_recommendation(req: ProjectRequest, explain_with_ai: bool = True, repo: EmployeeRepository = Depends(get_repo)):
    result = recommend(req, repo)                      # deterministic
    if explain_with_ai:
        result.explanation = explain(result)           # verbalisation only
    repo.save_recommendation(result.request_id, req.model_dump_json(), result.model_dump_json())   # audit trail
    return result


@app.get("/recommendations/{request_id}", response_model=RecommendationResult)
def get_recommendation(request_id: str, repo: EmployeeRepository = Depends(get_repo)):
    raw = repo.get_recommendation(request_id)
    if not raw: raise HTTPException(404, "Unknown request_id")
    return json.loads(raw)


@app.post("/recommendations/{request_id}/decision")
def record_decision(request_id: str, d: Decision, repo: EmployeeRepository = Depends(get_repo)):
    """Human-in-the-loop: the manager's final choice is stored (and may differ from the AI recommendation)."""
    if not repo.get_recommendation(request_id): raise HTTPException(404, "Unknown request_id")
    known = {e.employee_id for e in repo.load_all()}
    bad = [i for i in d.selected_employee_ids if i not in known]
    if bad: raise HTTPException(422, f"Unknown employee ids: {bad}")
    repo.save_decision(request_id, d.manager, d.selected_employee_ids, d.comment)
    return {"status": "recorded"}
