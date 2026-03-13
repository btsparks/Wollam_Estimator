"""Document Enrichment — AI analysis of uploaded PM documents.

Uses Claude to analyze uploaded documents (change orders, KPIs, RFI logs,
material tracking) and enrich existing PM/CC context with additional insights.
"""

from __future__ import annotations

import json
import logging
import re

import anthropic

from app.config import ANTHROPIC_API_KEY
from app.database import get_connection

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_DOC_TEXT = 30_000  # Max characters per doc to send to Claude


def enrich_from_documents(job_id: int) -> dict:
    """Run AI enrichment for a job using all its uploaded documents.

    Reads uploaded document text from job_document table, combines with
    existing context, and asks Claude to identify enrichments.

    Returns summary of what was enriched.
    """
    conn = get_connection()
    try:
        # Get job info
        job = conn.execute(
            "SELECT job_id, job_number, name FROM job WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if not job:
            return {"error": "Job not found"}
        job = dict(job)

        # Get all documents for this job
        docs = conn.execute(
            """SELECT id, filename, doc_type, extracted_text
               FROM job_document
               WHERE job_id = ? AND extracted_text IS NOT NULL AND extracted_text != ''
               ORDER BY uploaded_at""",
            (job_id,),
        ).fetchall()

        if not docs:
            return {"error": "No documents with extracted text found for this job"}

        docs = [dict(d) for d in docs]

        # Get existing PM context for reference
        pm = conn.execute(
            "SELECT * FROM pm_context WHERE job_id = ?", (job_id,),
        ).fetchone()
        existing_pm = dict(pm) if pm else {}

        # Get existing CC context for reference
        cc_rows = conn.execute(
            "SELECT cost_code, scope_included, conditions, notes, source FROM cc_context WHERE job_id = ?",
            (job_id,),
        ).fetchall()
        existing_cc = {r["cost_code"]: dict(r) for r in cc_rows}

        # Get cost codes for this job (so Claude knows what codes exist)
        cost_codes = conn.execute(
            """SELECT code, description, unit,
                      act_labor_hrs, act_qty, bgt_labor_hrs, bgt_qty
               FROM hj_costcode WHERE job_id = ? AND act_labor_hrs > 0
               ORDER BY code""",
            (job_id,),
        ).fetchall()
        cc_list = [dict(c) for c in cost_codes]

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        results = {
            "job_id": job_id,
            "documents_analyzed": len(docs),
            "job_level_enriched": False,
            "cost_codes_enriched": 0,
            "errors": [],
        }

        # ── Job-level enrichment ──
        try:
            job_enrichment = _enrich_job_level(client, job, docs, existing_pm, cc_list)
            if job_enrichment:
                _merge_pm_context(conn, job_id, job_enrichment, existing_pm)
                results["job_level_enriched"] = True
        except Exception as e:
            logger.warning("Job-level enrichment failed for %s: %s", job_id, e)
            results["errors"].append({"level": "job", "error": str(e)})

        # ── Cost-code-level enrichment ──
        try:
            cc_enrichments = _enrich_cost_codes(client, job, docs, cc_list, existing_cc)
            if cc_enrichments:
                for cc_code, cc_data in cc_enrichments.items():
                    _merge_cc_context(conn, job_id, cc_code, cc_data, existing_cc.get(cc_code, {}))
                    results["cost_codes_enriched"] += 1
        except Exception as e:
            logger.warning("CC enrichment failed for %s: %s", job_id, e)
            results["errors"].append({"level": "cost_codes", "error": str(e)})

        # Mark documents as analyzed
        doc_ids = [d["id"] for d in docs]
        conn.execute(
            f"UPDATE job_document SET analyzed = 1, analyzed_at = CURRENT_TIMESTAMP WHERE id IN ({','.join('?' * len(doc_ids))})",
            doc_ids,
        )

        conn.commit()
        return results

    finally:
        conn.close()


def _enrich_job_level(
    client: anthropic.Anthropic,
    job: dict,
    docs: list[dict],
    existing_pm: dict,
    cc_list: list[dict],
) -> dict | None:
    """Analyze documents for job-level context enrichments."""
    # Build document summaries
    doc_texts = []
    for d in docs:
        text = d["extracted_text"][:MAX_DOC_TEXT]
        doc_texts.append(f"=== Document: {d['filename']} (Type: {d['doc_type']}) ===\n{text}")

    all_docs_text = "\n\n".join(doc_texts)

    # Truncate if still too long
    if len(all_docs_text) > 60_000:
        all_docs_text = all_docs_text[:60_000] + "\n[... truncated ...]"

    # Build existing context summary
    existing_summary = ""
    if existing_pm:
        parts = []
        for field in ("project_summary", "site_conditions", "key_challenges", "key_successes", "lessons_learned"):
            if existing_pm.get(field):
                parts.append(f"  {field}: {existing_pm[field]}")
        if parts:
            existing_summary = "Existing PM Context:\n" + "\n".join(parts)

    prompt = f"""You are analyzing project documents from a construction job to enrich the project context for estimators.

Job: {job['name']} (Code: {job['job_number']})
Cost codes on this job: {len(cc_list)}

{existing_summary}

Documents to analyze:
{all_docs_text}

Based on these documents, identify NEW information that would be valuable for estimators pricing similar future work. Focus on:
- Change orders: scope changes, cost impacts, reasons
- Production data: actual vs planned rates, factors affecting productivity
- RFIs/Submittals: design issues, delays, resolutions
- Material: quantities, waste factors, lead times, supplier issues
- Schedule: delays, acceleration, weather impacts

IMPORTANT: Only include information that ADDS to or CLARIFIES the existing context. Don't repeat what's already known.

Respond in JSON only:
{{
    "project_summary_additions": "New facts about the project not in existing context. Empty string if nothing to add.",
    "site_conditions_additions": "Additional site condition details from documents. Empty string if nothing to add.",
    "key_challenges_additions": "Additional challenges revealed by documents. Empty string if nothing to add.",
    "key_successes_additions": "Additional successes revealed by documents. Empty string if nothing to add.",
    "lessons_learned_additions": "Additional lessons from documents. Empty string if nothing to add.",
    "change_order_summary": "Summary of change orders and their impact. Empty string if no CO data.",
    "schedule_notes": "Schedule impacts, delays, acceleration noted in documents. Empty string if none."
}}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_json_response(response.content[0].text)


def _enrich_cost_codes(
    client: anthropic.Anthropic,
    job: dict,
    docs: list[dict],
    cc_list: list[dict],
    existing_cc: dict[str, dict],
) -> dict[str, dict] | None:
    """Analyze documents for cost-code-specific enrichments."""
    # Build document text focused on cost-code-relevant content
    doc_texts = []
    for d in docs:
        text = d["extracted_text"][:MAX_DOC_TEXT]
        doc_texts.append(f"=== {d['filename']} ({d['doc_type']}) ===\n{text}")

    all_docs_text = "\n\n".join(doc_texts)

    if len(all_docs_text) > 60_000:
        all_docs_text = all_docs_text[:60_000] + "\n[... truncated ...]"

    # Build cost code reference
    cc_ref_lines = []
    for cc in cc_list[:100]:  # Limit to 100 cost codes for token management
        cc_ref_lines.append(
            f"  {cc['code']} — {cc.get('description', 'N/A')} ({cc.get('unit', 'N/A')})"
        )
    cc_ref = "\n".join(cc_ref_lines)

    prompt = f"""You are analyzing project documents from a construction job to find cost-code-specific insights for estimators.

Job: {job['name']} (Code: {job['job_number']})

Active cost codes on this job:
{cc_ref}

Documents:
{all_docs_text}

Identify cost codes mentioned or affected in these documents. For each affected cost code, extract relevant details.

IMPORTANT: Only include cost codes where the documents provide meaningful new information (change orders, production issues, material data, etc.). Skip codes not mentioned in the documents.

Respond in JSON only — a dictionary where keys are cost code numbers:
{{
    "1234": {{
        "conditions_additions": "New conditions info from documents for this code. E.g., 'CO #3 added 200 LF of additional pipe due to design change.'",
        "notes_additions": "Additional estimating notes from documents. E.g., 'Material lead time was 8 weeks vs. planned 4 weeks, causing 2-week delay.'"
    }},
    "5678": {{
        "conditions_additions": "...",
        "notes_additions": "..."
    }}
}}

If no cost codes are specifically referenced in the documents, respond with an empty JSON object: {{}}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_json_response(response.content[0].text)


def _merge_pm_context(conn, job_id: int, enrichment: dict, existing: dict) -> None:
    """Merge document enrichments into PM context."""
    # Build merged fields — append additions to existing content
    fields = {}
    for base_field in ("project_summary", "site_conditions", "key_challenges", "key_successes", "lessons_learned"):
        addition_key = f"{base_field}_additions"
        addition = enrichment.get(addition_key, "").strip()
        if addition:
            existing_val = existing.get(base_field, "") or ""
            if existing_val:
                fields[base_field] = f"{existing_val}\n\n[From documents] {addition}"
            else:
                fields[base_field] = f"[From documents] {addition}"

    # Add new fields (change_order_summary, schedule_notes) to general_notes
    extra_parts = []
    for extra_field in ("change_order_summary", "schedule_notes"):
        val = enrichment.get(extra_field, "").strip()
        if val:
            label = extra_field.replace("_", " ").title()
            extra_parts.append(f"[{label}] {val}")

    if extra_parts:
        existing_notes = existing.get("general_notes", "") or ""
        extra_text = "\n\n".join(extra_parts)
        if existing_notes:
            fields["general_notes"] = f"{existing_notes}\n\n{extra_text}"
        else:
            fields["general_notes"] = extra_text

    if not fields:
        return

    # Build dynamic UPDATE or INSERT
    source = "ai_document"
    if existing:
        # UPDATE existing row — only update fields that have additions
        set_clauses = []
        values = []
        for field, val in fields.items():
            set_clauses.append(f"{field} = ?")
            values.append(val)
        set_clauses.append("source = ?")
        values.append(source)
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values.append(job_id)

        conn.execute(
            f"UPDATE pm_context SET {', '.join(set_clauses)} WHERE job_id = ?",
            values,
        )
    else:
        # INSERT new row
        conn.execute(
            """INSERT INTO pm_context (job_id, project_summary, site_conditions,
                                       key_challenges, key_successes, lessons_learned,
                                       general_notes, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                fields.get("project_summary"),
                fields.get("site_conditions"),
                fields.get("key_challenges"),
                fields.get("key_successes"),
                fields.get("lessons_learned"),
                fields.get("general_notes"),
                source,
            ),
        )


def _merge_cc_context(conn, job_id: int, cost_code: str, enrichment: dict, existing: dict) -> None:
    """Merge document enrichments into CC context."""
    # Don't overwrite manual context
    if existing.get("source") == "manual":
        return

    conditions_add = enrichment.get("conditions_additions", "").strip()
    notes_add = enrichment.get("notes_additions", "").strip()

    if not conditions_add and not notes_add:
        return

    existing_conditions = existing.get("conditions", "") or ""
    existing_notes = existing.get("notes", "") or ""

    new_conditions = existing_conditions
    if conditions_add:
        if existing_conditions:
            new_conditions = f"{existing_conditions}\n\n[From documents] {conditions_add}"
        else:
            new_conditions = f"[From documents] {conditions_add}"

    new_notes = existing_notes
    if notes_add:
        if existing_notes:
            new_notes = f"{existing_notes}\n\n[From documents] {notes_add}"
        else:
            new_notes = f"[From documents] {notes_add}"

    conn.execute(
        """INSERT INTO cc_context (job_id, cost_code, conditions, notes, source)
           VALUES (?, ?, ?, ?, 'ai_document')
           ON CONFLICT(job_id, cost_code) DO UPDATE SET
               conditions = excluded.conditions,
               notes = excluded.notes,
               source = CASE WHEN cc_context.source = 'manual' THEN 'manual' ELSE 'ai_document' END,
               updated_at = CURRENT_TIMESTAMP""",
        (job_id, cost_code, new_conditions, new_notes),
    )


def _parse_json_response(text: str) -> dict | None:
    """Extract JSON from Claude's response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        logger.warning("Could not parse JSON from enrichment response: %s", text[:200])
        return None
