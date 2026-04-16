"""SOV Intelligence Mapper — maps agent findings to individual BSOV items.

Runs after agents complete. For each SOV item, uses AI to determine
which agent findings are relevant, then stores structured mappings
in sov_item_intelligence.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import anthropic

from app.config import ANTHROPIC_API_KEY
from app.database import get_connection

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"


MAPPER_SYSTEM_PROMPT = """You are an estimating intelligence mapper for construction bid preparation.

You will receive:
1. A single bid schedule item (number, description, quantity, unit)
2. Intelligence findings from multiple specialized agents who analyzed the full RFP document package

Your job: Identify which findings are directly relevant to this specific bid schedule item. For each relevant finding, extract:

Return a JSON object:
{
  "relevant_findings": [
    {
      "agent_name": "legal_analyst|qaqc_manager|subcontract_manager|document_control",
      "domain": "legal|qaqc|subcontract|document_control",
      "finding_type": "contract_risk|testing_requirement|submittal|inspection|certification|sub_scope|self_perform|spec_reference|addendum_change|missing_document|missing_information|flag",
      "title": "Short label (under 80 chars)",
      "detail": "Full description of how this finding applies to this bid item",
      "severity": "info|low|medium|high|critical",
      "spec_section": "Section reference if applicable, null otherwise",
      "clause_reference": "Contract clause if applicable, null otherwise",
      "source_document": "Filename where this was found, if identifiable",
      "confidence": 0.0-1.0
    }
  ],
  "drawing_references": [
    {
      "drawing_number": "C-101",
      "description": "Why this drawing is relevant to this item",
      "discipline": "civil|structural|mechanical|electrical|piping|architectural"
    }
  ],
  "missing_information": [
    {
      "what_is_missing": "Description of what's missing or ambiguous for THIS bid item",
      "why_it_matters": "How this gap affects pricing or execution of this specific item",
      "suggested_action": "rfi|clarification|verify|assumption",
      "suggested_question": "The specific question to ask the owner, or the assumption the estimator should document",
      "source_agent": "Which agent identified this gap"
    }
  ],
  "spec_sections_summary": "Comma-separated list of all spec sections relevant to this item",
  "estimator_notes": "Any additional context the estimator should know about this item based on the document analysis"
}

Rules:
- Only include findings that are DIRECTLY relevant to this specific bid item — don't include everything
- If a finding applies to the project generally (e.g., payment terms, retainage), include it if it affects how this item would be priced
- A finding can be relevant to multiple bid items — that's fine
- confidence: 1.0 = definitely relevant, 0.7+ = likely relevant, below 0.5 = don't include
- For spec_section and clause_reference, use exact references from the agent findings
- For missing_information: pull from agents' missing_information arrays AND identify additional gaps specific to this bid item that the agents may have missed. Think: "What would an estimator need to know to price this item that isn't in the documents?"
- Each missing_information entry should have a clear, actionable suggested_question or assumption — not vague concerns
- Return ONLY valid JSON — no markdown, no explanation
"""


def map_intelligence_to_sov(bid_id: int, sov_item_ids: list[int] | None = None, on_progress=None) -> dict:
    """Map agent intelligence to SOV items.

    Args:
        bid_id: The bid to process
        sov_item_ids: Optional specific items to map (default: all items)
        on_progress: Optional callback(current, total, item_number, status) for progress tracking.

    Returns:
        Summary dict with per-item mapping counts
    """
    conn = get_connection()
    try:
        bid = conn.execute(
            "SELECT * FROM active_bids WHERE id = ?", (bid_id,)
        ).fetchone()
        if not bid:
            raise ValueError(f"Bid {bid_id} not found")

        if sov_item_ids:
            placeholders = ",".join("?" for _ in sov_item_ids)
            sov_items = conn.execute(
                f"SELECT * FROM bid_sov_item WHERE bid_id = ? AND id IN ({placeholders}) AND COALESCE(in_scope, 1) = 1 ORDER BY sort_order",
                [bid_id] + sov_item_ids,
            ).fetchall()
        else:
            sov_items = conn.execute(
                "SELECT * FROM bid_sov_item WHERE bid_id = ? AND COALESCE(in_scope, 1) = 1 ORDER BY sort_order",
                (bid_id,),
            ).fetchall()

        if not sov_items:
            return {"bid_id": bid_id, "items_mapped": 0, "message": "No SOV items found"}

        reports = conn.execute(
            """SELECT agent_name, status, report_json, summary_text
               FROM agent_reports
               WHERE bid_id = ? AND agent_name != 'chief_estimator' AND status = 'complete'""",
            (bid_id,),
        ).fetchall()

        if not reports:
            return {"bid_id": bid_id, "items_mapped": 0, "message": "No agent reports available. Run agents first."}

        agent_findings = {}
        for r in reports:
            parsed = {}
            if r["report_json"]:
                try:
                    parsed = json.loads(r["report_json"])
                except json.JSONDecodeError:
                    continue
            agent_findings[r["agent_name"]] = {
                "summary": r["summary_text"],
                "report": parsed,
            }

        drawings = conn.execute(
            "SELECT * FROM drawing_log WHERE bid_id = ?", (bid_id,)
        ).fetchall()

    finally:
        conn.close()

    findings_context = _build_findings_context(agent_findings)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    results = {}
    total_tokens = 0
    start = time.time()

    total_items = len(sov_items)
    for idx, item in enumerate(sov_items):
        item_id = item["id"]
        item_num = item["item_number"] or "?"

        try:
            mapped = _map_single_item(
                client, dict(bid), dict(item), findings_context,
                [dict(d) for d in drawings],
            )
            total_tokens += mapped.get("tokens_used", 0)

            _save_item_intelligence(bid_id, item_id, mapped.get("findings", []))
            results[item_id] = {
                "item_number": item_num,
                "findings_count": len(mapped.get("findings", [])),
                "status": "complete",
            }
            if on_progress:
                on_progress(idx + 1, total_items, item_num, "complete")
        except Exception as e:
            logger.error("Failed to map SOV item %d: %s", item_id, e)
            results[item_id] = {
                "item_number": item_num,
                "findings_count": 0,
                "status": "error",
                "error": str(e),
            }
            if on_progress:
                on_progress(idx + 1, total_items, item_num, "error")

    duration = time.time() - start
    return {
        "bid_id": bid_id,
        "items_mapped": len([r for r in results.values() if r["status"] == "complete"]),
        "total_findings": sum(r.get("findings_count", 0) for r in results.values()),
        "total_tokens": total_tokens,
        "duration_seconds": round(duration, 2),
        "items": results,
    }


MAX_CONTEXT_CHARS = 40_000  # ~10K tokens — keeps each API call fast (~10-15s)
MAX_ITEMS_PER_ARRAY = 10   # Cap arrays to keep context lean


def _build_findings_context(agent_findings: dict) -> str:
    """Build a compact text representation of agent findings for the mapper prompt.

    Aggressively caps size so each per-item API call completes in ~10-15 seconds.
    """
    parts = []

    for agent_name, data in agent_findings.items():
        report = data.get("report", {})
        parts.append(f"\n=== {agent_name.upper().replace('_', ' ')} ===")
        parts.append(f"Summary: {data.get('summary', 'N/A')}")

        extracted = _extract_key_findings(agent_name, report)
        parts.append(json.dumps(extracted, indent=1, default=str))

    result = "\n".join(parts)
    if len(result) > MAX_CONTEXT_CHARS:
        result = result[:MAX_CONTEXT_CHARS] + "\n... [truncated]"
    return result


def _extract_key_findings(agent_name: str, report: dict) -> dict:
    """Extract only the mapper-relevant arrays from an agent report, capped."""
    key_fields = {
        "legal_analyst": ["key_risks", "liquidated_damages", "bonding", "retainage",
                          "insurance_requirements", "missing_information"],
        "qaqc_manager": ["testing_requirements", "certifications_required",
                         "submittals_required", "inspection_requirements",
                         "missing_information"],
        "subcontract_manager": ["recommended_sub_scopes", "self_perform_recommended",
                                "missing_information"],
        "document_control": ["addendum_changes", "missing_documents",
                             "missing_information"],
    }
    fields = key_fields.get(agent_name, list(report.keys()))
    extracted = {}
    for f in fields:
        if f in report:
            val = report[f]
            if isinstance(val, list) and len(val) > MAX_ITEMS_PER_ARRAY:
                extracted[f] = val[:MAX_ITEMS_PER_ARRAY]
                extracted[f"_{f}_note"] = f"Showing {MAX_ITEMS_PER_ARRAY} of {len(val)}"
            else:
                extracted[f] = val
    return extracted


def _map_single_item(
    client: anthropic.Anthropic,
    bid: dict,
    sov_item: dict,
    findings_context: str,
    drawings: list[dict],
) -> dict:
    """Map intelligence to a single SOV item via Claude API call."""
    item_text = (
        f"Bid Item {sov_item.get('item_number', '?')}: "
        f"{sov_item.get('description', '')}\n"
        f"Quantity: {sov_item.get('quantity', 'N/A')} {sov_item.get('unit', '')}\n"
        f"Discipline: {sov_item.get('discipline', 'N/A')}\n"
        f"Cost Code: {sov_item.get('cost_code', 'N/A')}"
    )

    drawing_text = ""
    if drawings:
        drawing_text = "\n\nAvailable Drawings:\n"
        for d in drawings:
            drawing_text += f"  - {d.get('drawing_number', '?')}: {d.get('title', '')} (Rev {d.get('revision', '?')}, {d.get('discipline', '')})\n"

    user_message = (
        f"Project: {bid.get('bid_name', '')}\n"
        f"Owner: {bid.get('owner', '')}\n"
        f"Location: {bid.get('location', '')}\n\n"
        f"BID SCHEDULE ITEM TO ANALYZE:\n{item_text}\n"
        f"{drawing_text}\n"
        f"AGENT INTELLIGENCE FINDINGS:\n{findings_context}"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=MAPPER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    input_tok = response.usage.input_tokens
    output_tok = response.usage.output_tokens
    tokens = input_tok + output_tok
    response_text = response.content[0].text

    # Log cost
    try:
        from app.services.cost_tracker import log_api_call
        log_api_call(
            bid_id=bid.get("id"),
            operation="sov_mapper",
            model=MODEL,
            input_tokens=input_tok,
            output_tokens=output_tok,
            detail=f"Item {sov_item.get('item_number', '?')}: {sov_item.get('description', '')[:50]}",
        )
    except Exception:
        pass

    parsed = _parse_mapper_response(response_text)

    findings = []
    for f in parsed.get("relevant_findings", []):
        findings.append({
            "agent_name": f.get("agent_name", "unknown"),
            "domain": f.get("domain", "general"),
            "finding_type": f.get("finding_type", "info"),
            "title": f.get("title", ""),
            "detail": f.get("detail", ""),
            "severity": f.get("severity", "info"),
            "spec_section": f.get("spec_section"),
            "clause_reference": f.get("clause_reference"),
            "source_document": f.get("source_document"),
            "confidence": f.get("confidence", 0.8),
            "metadata_json": json.dumps({
                "spec_sections_summary": parsed.get("spec_sections_summary"),
                "estimator_notes": parsed.get("estimator_notes"),
                "drawing_references": parsed.get("drawing_references", []),
            }),
        })

    for dr in parsed.get("drawing_references", []):
        findings.append({
            "agent_name": "sov_mapper",
            "domain": "drawing",
            "finding_type": "drawing_reference",
            "title": f"Drawing {dr.get('drawing_number', '?')}",
            "detail": dr.get("description", ""),
            "severity": "info",
            "spec_section": None,
            "clause_reference": None,
            "source_document": None,
            "confidence": 1.0,
            "metadata_json": json.dumps({"discipline": dr.get("discipline")}),
        })

    for mi in parsed.get("missing_information", []):
        action = mi.get("suggested_action", "verify")
        severity_map = {"rfi": "high", "clarification": "medium", "verify": "low", "assumption": "medium"}
        findings.append({
            "agent_name": mi.get("source_agent", "sov_mapper"),
            "domain": "missing_information",
            "finding_type": "missing_information",
            "title": mi.get("what_is_missing", "")[:80],
            "detail": mi.get("why_it_matters", ""),
            "severity": severity_map.get(action, "medium"),
            "spec_section": None,
            "clause_reference": None,
            "source_document": None,
            "confidence": 1.0,
            "metadata_json": json.dumps({
                "suggested_action": action,
                "suggested_question": mi.get("suggested_question"),
                "what_is_missing": mi.get("what_is_missing"),
            }),
        })

    return {"findings": findings, "tokens_used": tokens}


def _parse_mapper_response(text: str) -> dict:
    """Parse the mapper AI response into structured data."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return {"relevant_findings": [], "drawing_references": [], "missing_information": [], "parse_error": True}


def _save_item_intelligence(bid_id: int, sov_item_id: int, findings: list[dict]):
    """Save mapped findings to the database. Replaces existing mappings for the item."""
    conn = get_connection()
    try:
        now = datetime.now(tz=timezone.utc).isoformat()

        conn.execute(
            "DELETE FROM sov_item_intelligence WHERE bid_id = ? AND sov_item_id = ?",
            (bid_id, sov_item_id),
        )

        for f in findings:
            conn.execute(
                """INSERT INTO sov_item_intelligence
                   (bid_id, sov_item_id, agent_name, domain, finding_type,
                    title, detail, severity, spec_section, clause_reference,
                    source_document, confidence, metadata_json,
                    mapped_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    bid_id, sov_item_id, f["agent_name"], f["domain"],
                    f["finding_type"], f["title"], f["detail"],
                    f.get("severity", "info"), f.get("spec_section"),
                    f.get("clause_reference"), f.get("source_document"),
                    f.get("confidence", 0.8), f.get("metadata_json"),
                    now, now, now,
                ),
            )

        conn.commit()
    finally:
        conn.close()


def mark_sov_intelligence_stale(bid_id: int) -> int:
    """Mark all SOV intelligence for a bid as stale (called when agents re-run)."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE sov_item_intelligence SET is_stale = 1 WHERE bid_id = ? AND is_stale = 0",
            (bid_id,),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_item_intelligence(bid_id: int, sov_item_id: int) -> dict:
    """Get all intelligence findings for a specific SOV item, organized by domain."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM sov_item_intelligence
               WHERE bid_id = ? AND sov_item_id = ?
               ORDER BY
                   CASE severity
                       WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                       WHEN 'medium' THEN 2 WHEN 'low' THEN 3
                       ELSE 4
                   END,
                   domain, finding_type""",
            (bid_id, sov_item_id),
        ).fetchall()

        by_domain = {}
        for r in rows:
            d = dict(r)
            if d.get("metadata_json"):
                try:
                    d["metadata"] = json.loads(d["metadata_json"])
                except json.JSONDecodeError:
                    d["metadata"] = {}
            else:
                d["metadata"] = {}
            domain = d["domain"]
            if domain not in by_domain:
                by_domain[domain] = []
            by_domain[domain].append(d)

        estimator_notes = None
        spec_summary = None
        if rows:
            first = rows[0]
            if first["metadata_json"]:
                try:
                    meta = json.loads(first["metadata_json"])
                    estimator_notes = meta.get("estimator_notes")
                    spec_summary = meta.get("spec_sections_summary")
                except json.JSONDecodeError:
                    pass

        return {
            "sov_item_id": sov_item_id,
            "total_findings": len(rows),
            "is_stale": any(r["is_stale"] for r in rows) if rows else False,
            "domains": by_domain,
            "estimator_notes": estimator_notes,
            "spec_sections_summary": spec_summary,
        }
    finally:
        conn.close()


def get_sov_intelligence_summary(bid_id: int) -> list[dict]:
    """Get intelligence counts per SOV item (for badge display in SOV list)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT sov_item_id,
                      COUNT(*) as finding_count,
                      MAX(CASE severity
                          WHEN 'critical' THEN 4 WHEN 'high' THEN 3
                          WHEN 'medium' THEN 2 WHEN 'low' THEN 1
                          ELSE 0
                      END) as max_severity_num,
                      MAX(is_stale) as has_stale
               FROM sov_item_intelligence
               WHERE bid_id = ?
               GROUP BY sov_item_id""",
            (bid_id,),
        ).fetchall()

        severity_map = {4: "critical", 3: "high", 2: "medium", 1: "low", 0: "info"}
        return [
            {
                "sov_item_id": r["sov_item_id"],
                "finding_count": r["finding_count"],
                "max_severity": severity_map.get(r["max_severity_num"], "info"),
                "is_stale": bool(r["has_stale"]),
            }
            for r in rows
        ]
    finally:
        conn.close()
