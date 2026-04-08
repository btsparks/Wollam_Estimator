"""Agent Intelligence API — run agents, get reports, check staleness.

Separate from bidding.py to keep file sizes manageable.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database import get_connection
from app.agents.runner import (
    run_agent,
    run_all_agents,
    get_available_agents,
    get_intelligence_status,
)
from app.services.document_chunker import chunk_all_bid_documents
from app.services.document_diff import summarize_document_changes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bidding", tags=["agents"])


class AnalyzeRequest(BaseModel):
    agent_names: Optional[list[str]] = None


# ── Agent Execution ─────────────────────────────────────────────

@router.get("/agents")
async def list_agents():
    """List available agents with metadata."""
    return get_available_agents()


@router.post("/bids/{bid_id}/analyze")
async def analyze_bid(bid_id: int, body: AnalyzeRequest = AnalyzeRequest()):
    """Run all agents (or specified subset) against bid documents."""
    conn = get_connection()
    try:
        bid = conn.execute("SELECT id FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")

        # Check documents exist
        doc_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM bid_documents WHERE bid_id = ? AND extraction_status = 'complete'",
            (bid_id,),
        ).fetchone()["cnt"]
        if doc_count == 0:
            raise HTTPException(status_code=400, detail="No documents with extracted text. Upload documents first.")

        # Ensure chunks exist
        chunk_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM bid_document_chunks WHERE bid_id = ?",
            (bid_id,),
        ).fetchone()["cnt"]
    finally:
        conn.close()

    # Auto-chunk if no chunks exist
    if chunk_count == 0:
        chunk_result = chunk_all_bid_documents(bid_id)
        if chunk_result["total_chunks"] == 0:
            raise HTTPException(status_code=400, detail="Documents could not be chunked. Check extraction quality.")

    result = run_all_agents(bid_id, body.agent_names)
    return result


@router.post("/bids/{bid_id}/analyze/{agent_name}")
async def analyze_bid_single(bid_id: int, agent_name: str):
    """Run a specific agent against bid documents."""
    conn = get_connection()
    try:
        bid = conn.execute("SELECT id FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")

        doc_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM bid_documents WHERE bid_id = ? AND extraction_status = 'complete'",
            (bid_id,),
        ).fetchone()["cnt"]
        if doc_count == 0:
            raise HTTPException(status_code=400, detail="No documents with extracted text.")

        chunk_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM bid_document_chunks WHERE bid_id = ?",
            (bid_id,),
        ).fetchone()["cnt"]
    finally:
        conn.close()

    if chunk_count == 0:
        chunk_all_bid_documents(bid_id)

    try:
        report = run_agent(bid_id, agent_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "agent_name": report.agent_name,
        "status": report.status,
        "risk_rating": report.risk_rating,
        "flags_count": report.flags_count,
        "duration_seconds": round(report.duration_seconds, 2),
        "tokens_used": report.tokens_used,
        "summary": report.summary_text,
    }


# ── Reports ─────────────────────────────────────────────────────

@router.get("/bids/{bid_id}/reports")
async def get_reports(bid_id: int):
    """Get all agent reports for a bid."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, agent_name, agent_version, status, report_json,
                      summary_text, risk_rating, flags_count, tokens_used,
                      duration_seconds, error_message, input_doc_count,
                      input_chunk_count, is_stale, created_at, updated_at
               FROM agent_reports WHERE bid_id = ?
               ORDER BY agent_name""",
            (bid_id,),
        ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            if d.get("report_json"):
                try:
                    d["report_json"] = json.loads(d["report_json"])
                except json.JSONDecodeError:
                    pass
            result.append(d)
        return result
    finally:
        conn.close()


@router.get("/bids/{bid_id}/reports/{agent_name}")
async def get_report(bid_id: int, agent_name: str):
    """Get a specific agent report."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT id, agent_name, agent_version, status, report_json,
                      summary_text, risk_rating, flags_count, tokens_used,
                      duration_seconds, error_message, input_doc_count,
                      input_chunk_count, is_stale, created_at, updated_at
               FROM agent_reports WHERE bid_id = ? AND agent_name = ?""",
            (bid_id, agent_name),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"No report found for agent '{agent_name}'")

        d = dict(row)
        if d.get("report_json"):
            try:
                d["report_json"] = json.loads(d["report_json"])
            except json.JSONDecodeError:
                pass
        return d
    finally:
        conn.close()


@router.delete("/bids/{bid_id}/reports")
async def clear_reports(bid_id: int):
    """Clear all agent reports for a bid (for re-analysis)."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM agent_reports WHERE bid_id = ?", (bid_id,)
        )
        conn.commit()
        return {"deleted": cursor.rowcount, "bid_id": bid_id}
    finally:
        conn.close()


# ── Intelligence Status ─────────────────────────────────────────

@router.get("/bids/{bid_id}/intelligence-status")
async def intelligence_status(bid_id: int):
    """Get per-agent staleness, last run time, and doc coverage."""
    conn = get_connection()
    try:
        bid = conn.execute("SELECT id FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")
    finally:
        conn.close()

    return get_intelligence_status(bid_id)


# ── Document Change Summaries ──────────────────────────────────

@router.get("/documents/{doc_id}/changes")
async def get_document_changes(doc_id: int):
    """Get AI-generated change summary for an updated document."""
    conn = get_connection()
    try:
        doc = conn.execute(
            "SELECT id, filename, previous_extracted_text FROM bid_documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        if not doc["previous_extracted_text"]:
            return {"doc_id": doc_id, "has_changes": False, "message": "No previous version available"}
    finally:
        conn.close()

    result = summarize_document_changes(doc_id)
    if result is None:
        return {"doc_id": doc_id, "has_changes": False}
    return {"doc_id": doc_id, "has_changes": True, "changes": result}
