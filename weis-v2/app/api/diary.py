"""Diary API — Endpoints for diary import and AI synthesis.

Provides endpoints to:
1. Import HeavyJob diary .txt exports from the local folder
2. Check import status across all jobs
3. Retrieve raw diary entries for a job
4. Trigger AI synthesis to generate draft PM context
"""

from fastapi import APIRouter, HTTPException

from app.services.diary_import import (
    import_all_diaries,
    get_diary_status,
    get_diary_entries,
    get_diary_summary,
)
from app.services.diary_synthesis import synthesize_job

router = APIRouter(prefix="/api/diary", tags=["diary"])


@router.post("/import")
def import_diaries():
    """Scan the Heavy Job Notes folder and import all diary .txt files."""
    result = import_all_diaries()
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/status")
def diary_status():
    """Return diary import status for all jobs with diary data."""
    return get_diary_status()


@router.get("/entries/{job_id}")
def diary_entries(job_id: int, cost_code: str | None = None):
    """Return raw diary entries for a job, optionally filtered by cost code."""
    entries = get_diary_entries(job_id, cost_code)
    if not entries:
        raise HTTPException(status_code=404, detail="No diary entries found")
    return entries


@router.get("/summary/{job_id}")
def diary_summary(job_id: int):
    """Return diary summary stats for a job."""
    summary = get_diary_summary(job_id)
    if not summary:
        raise HTTPException(status_code=404, detail="No diary data for this job")
    return summary


@router.post("/synthesize/{job_id}")
def synthesize(job_id: int):
    """Trigger AI synthesis for a job.

    Reads diary entries, sends to Claude for analysis, and saves
    draft pm_context + cc_context entries with source='ai_synthesized'.
    """
    result = synthesize_job(job_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result
