"""Agent execution engine — orchestrates running agents against bid documents.

Handles loading chunks, building context, running agents, and saving reports.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.database import get_connection
from app.agents.base import AgentReport

logger = logging.getLogger(__name__)

# Registry of available agents — populated by imports
_AGENT_REGISTRY: dict = {}


def _ensure_registry():
    """Lazy-import agents to avoid circular imports."""
    if _AGENT_REGISTRY:
        return
    from app.agents.document_control import DocumentControlAgent
    from app.agents.legal_analyst import LegalAnalystAgent
    from app.agents.qaqc_manager import QAQCManagerAgent
    from app.agents.subcontract_manager import SubcontractManagerAgent
    from app.agents.chief_estimator import ChiefEstimatorAgent

    for cls in [
        DocumentControlAgent,
        LegalAnalystAgent,
        QAQCManagerAgent,
        SubcontractManagerAgent,
        ChiefEstimatorAgent,
    ]:
        agent = cls()
        _AGENT_REGISTRY[agent.name] = agent


def get_available_agents() -> list[dict]:
    """Return list of available agents with metadata."""
    _ensure_registry()
    return [
        {"name": a.name, "display_name": a.display_name, "version": a.version}
        for a in _AGENT_REGISTRY.values()
    ]


def _load_bid_context(bid_id: int) -> dict:
    """Load bid metadata and SOV items for agent context."""
    conn = get_connection()
    try:
        bid = conn.execute(
            "SELECT * FROM active_bids WHERE id = ?", (bid_id,)
        ).fetchone()
        if not bid:
            raise ValueError(f"Bid {bid_id} not found")

        sov_items = conn.execute(
            """SELECT item_number, description, quantity, unit, notes
               FROM bid_sov_item WHERE bid_id = ? ORDER BY sort_order""",
            (bid_id,),
        ).fetchall()

        return {
            "bid_id": bid_id,
            "bid_name": bid["bid_name"],
            "bid_number": bid["bid_number"],
            "owner": bid["owner"],
            "general_contractor": bid["general_contractor"],
            "location": bid["location"],
            "project_type": bid["project_type"],
            "description": bid["description"],
            "sov_items": [dict(r) for r in sov_items],
        }
    finally:
        conn.close()


def _load_doc_chunks(bid_id: int, document_ids: list[int] | None = None) -> list[dict]:
    """Load document chunks for a bid, enriched with document metadata.

    If document_ids is provided, only load chunks for those documents.
    """
    conn = get_connection()
    try:
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            rows = conn.execute(
                f"""SELECT c.chunk_text, c.section_heading,
                           d.filename, d.doc_category
                    FROM bid_document_chunks c
                    JOIN bid_documents d ON c.document_id = d.id
                    WHERE c.bid_id = ? AND c.document_id IN ({placeholders})
                    ORDER BY d.addendum_number, d.filename, c.chunk_index""",
                [bid_id] + document_ids,
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT c.chunk_text, c.section_heading,
                          d.filename, d.doc_category
                   FROM bid_document_chunks c
                   JOIN bid_documents d ON c.document_id = d.id
                   WHERE c.bid_id = ?
                   ORDER BY d.addendum_number, d.filename, c.chunk_index""",
                (bid_id,),
            ).fetchall()

        return [dict(r) for r in rows]
    finally:
        conn.close()


def _save_report(bid_id: int, report: AgentReport) -> int:
    """Save an agent report to the database (upsert)."""
    conn = get_connection()
    try:
        now = datetime.now(tz=timezone.utc).isoformat()

        # Check if a report already exists
        existing = conn.execute(
            "SELECT id FROM agent_reports WHERE bid_id = ? AND agent_name = ?",
            (bid_id, report.agent_name),
        ).fetchone()

        report_json_str = json.dumps(report.report_json) if report.report_json else None

        if existing:
            conn.execute(
                """UPDATE agent_reports
                   SET status = ?, report_json = ?, summary_text = ?,
                       risk_rating = ?, flags_count = ?, tokens_used = ?,
                       duration_seconds = ?, error_message = ?,
                       input_doc_count = ?, input_chunk_count = ?,
                       is_stale = 0, updated_at = ?
                   WHERE id = ?""",
                (
                    report.status, report_json_str, report.summary_text,
                    report.risk_rating, report.flags_count, report.tokens_used,
                    report.duration_seconds, report.error_message,
                    report.input_doc_count, report.input_chunk_count,
                    now, existing["id"],
                ),
            )
            conn.commit()
            return existing["id"]
        else:
            cursor = conn.execute(
                """INSERT INTO agent_reports
                   (bid_id, agent_name, agent_version, status, report_json,
                    summary_text, risk_rating, flags_count, tokens_used,
                    duration_seconds, error_message, input_doc_count,
                    input_chunk_count, is_stale, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (
                    bid_id, report.agent_name, "1.0", report.status,
                    report_json_str, report.summary_text, report.risk_rating,
                    report.flags_count, report.tokens_used, report.duration_seconds,
                    report.error_message, report.input_doc_count,
                    report.input_chunk_count, now, now,
                ),
            )
            conn.commit()
            return cursor.lastrowid
    finally:
        conn.close()


def run_agent(bid_id: int, agent_name: str) -> AgentReport:
    """Run a single agent against a bid's documents."""
    _ensure_registry()
    agent = _AGENT_REGISTRY.get(agent_name)
    if not agent:
        raise ValueError(f"Unknown agent: {agent_name}. Available: {list(_AGENT_REGISTRY.keys())}")

    context = _load_bid_context(bid_id)
    chunks = _load_doc_chunks(bid_id)

    logger.info("Running agent %s on bid %d (%d chunks)", agent_name, bid_id, len(chunks))
    report = agent.run(bid_id, chunks, context)
    _save_report(bid_id, report)
    return report


def run_all_agents(bid_id: int, agent_names: list[str] | None = None) -> dict:
    """Run specified agents (or all) against a bid's documents.

    Returns summary dict with per-agent results.
    """
    _ensure_registry()

    names = agent_names or [
        n for n in _AGENT_REGISTRY if n != "chief_estimator"
    ]

    context = _load_bid_context(bid_id)
    chunks = _load_doc_chunks(bid_id)

    results = {}
    for name in names:
        agent = _AGENT_REGISTRY.get(name)
        if not agent:
            results[name] = {"status": "error", "error": f"Unknown agent: {name}"}
            continue

        logger.info("Running agent %s on bid %d (%d chunks)", name, bid_id, len(chunks))
        report = agent.run(bid_id, chunks, context)
        _save_report(bid_id, report)
        results[name] = {
            "status": report.status,
            "risk_rating": report.risk_rating,
            "flags_count": report.flags_count,
            "duration_seconds": round(report.duration_seconds, 2),
            "tokens_used": report.tokens_used,
            "summary": report.summary_text,
        }

    # Run chief estimator last if requested or running all
    if agent_names is None or "chief_estimator" in (agent_names or []):
        chief = _AGENT_REGISTRY.get("chief_estimator")
        if chief:
            logger.info("Running chief_estimator aggregation for bid %d", bid_id)
            report = chief.run(bid_id, chunks, context)
            _save_report(bid_id, report)
            results["chief_estimator"] = {
                "status": report.status,
                "risk_rating": report.risk_rating,
                "flags_count": report.flags_count,
                "duration_seconds": round(report.duration_seconds, 2),
                "tokens_used": report.tokens_used,
                "summary": report.summary_text,
            }

    return {"bid_id": bid_id, "agents": results}


def mark_reports_stale(bid_id: int) -> int:
    """Mark all agent reports for a bid as stale.

    Called after Dropbox sync detects changes.
    Returns count of reports marked stale.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE agent_reports SET is_stale = 1 WHERE bid_id = ? AND is_stale = 0",
            (bid_id,),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_intelligence_status(bid_id: int) -> dict:
    """Get per-agent staleness, last run time, and doc coverage for a bid."""
    conn = get_connection()
    try:
        reports = conn.execute(
            """SELECT agent_name, status, risk_rating, flags_count,
                      is_stale, updated_at, input_doc_count, input_chunk_count
               FROM agent_reports WHERE bid_id = ?""",
            (bid_id,),
        ).fetchall()

        total_docs = conn.execute(
            "SELECT COUNT(*) as cnt FROM bid_documents WHERE bid_id = ? AND extraction_status = 'complete'",
            (bid_id,),
        ).fetchone()["cnt"]

        total_chunks = conn.execute(
            "SELECT COUNT(*) as cnt FROM bid_document_chunks WHERE bid_id = ?",
            (bid_id,),
        ).fetchone()["cnt"]

        _ensure_registry()
        agent_status = {}
        for name in _AGENT_REGISTRY:
            agent_status[name] = {
                "display_name": _AGENT_REGISTRY[name].display_name,
                "status": "not_run",
                "is_stale": False,
            }

        stale_count = 0
        for r in reports:
            name = r["agent_name"]
            is_stale = bool(r["is_stale"])
            if is_stale:
                stale_count += 1
            agent_status[name] = {
                "display_name": _AGENT_REGISTRY.get(name, type("", (), {"display_name": name})).display_name,
                "status": r["status"],
                "risk_rating": r["risk_rating"],
                "flags_count": r["flags_count"],
                "is_stale": is_stale,
                "last_run": r["updated_at"],
                "input_doc_count": r["input_doc_count"],
                "input_chunk_count": r["input_chunk_count"],
            }

        return {
            "bid_id": bid_id,
            "total_documents": total_docs,
            "total_chunks": total_chunks,
            "agents_needing_reanalysis": stale_count,
            "agents": agent_status,
        }
    finally:
        conn.close()
