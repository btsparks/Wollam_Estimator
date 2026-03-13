"""Interview API — FastAPI routes for PM Context Interview.

Thin wrapper over the interview service. All business logic lives
in app/services/interview.py.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.interview import (
    get_jobs_with_interview_status,
    get_job_interview_detail,
    save_job_context,
    save_cost_code_context,
    mark_interview_complete,
    get_interview_progress,
)

router = APIRouter(prefix="/api/interview", tags=["interview"])


# ── Pydantic models ──

class JobContextPayload(BaseModel):
    pm_name: str | None = None
    project_summary: str | None = None
    site_conditions: str | None = None
    key_challenges: str | None = None
    key_successes: str | None = None
    lessons_learned: str | None = None
    general_notes: str | None = None


class CostCodeContextPayload(BaseModel):
    description_override: str | None = None
    scope_included: str | None = None
    scope_excluded: str | None = None
    related_codes: list[str] | str | None = None
    conditions: str | None = None
    notes: str | None = None


class SaveContextRequest(BaseModel):
    job_id: int
    type: str  # "job" or "cost_code"
    cost_code: str | None = None
    data: dict


# ── Routes ──

@router.get("/jobs")
def list_jobs():
    """Return all jobs with interview status metadata."""
    return get_jobs_with_interview_status()


@router.get("/job/{job_id}")
def get_job_detail(job_id: int):
    """Return full job detail for the interview page."""
    result = get_job_interview_detail(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Job not found")
    return result


@router.post("/context")
def save_context(req: SaveContextRequest):
    """Save PM context for a job or cost code. Auto-save on field blur."""
    if req.type == "job":
        return save_job_context(req.job_id, req.data)
    elif req.type == "cost_code":
        if not req.cost_code:
            raise HTTPException(
                status_code=400,
                detail="cost_code required for cost_code context type"
            )
        return save_cost_code_context(req.job_id, req.cost_code, req.data)
    else:
        raise HTTPException(status_code=400, detail="type must be 'job' or 'cost_code'")


@router.post("/complete/{job_id}")
def complete_interview(job_id: int):
    """Mark a job's interview as complete."""
    return mark_interview_complete(job_id)


@router.get("/progress")
def progress():
    """Return overall interview progress stats."""
    return get_interview_progress()
