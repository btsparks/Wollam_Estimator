"""Diary Synthesis — AI-powered context generation from diary entries.

Uses Claude to analyze daily foreman diary notes and generate draft
PM context (job-level) and CC context (cost-code-level) entries.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict

import anthropic

from app.config import ANTHROPIC_API_KEY
from app.database import get_connection

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_ENTRIES_PER_CC = 80
MAX_ENTRIES_JOB_LEVEL = 250


def synthesize_job(job_id: int) -> dict:
    """Run full AI synthesis for a job: job-level + all cost codes.

    Reads diary entries from the database, sends them to Claude for
    analysis, and saves the results to pm_context and cc_context tables
    with source='ai_synthesized'.

    Returns summary of what was synthesized.
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

        # Get all diary entries
        rows = conn.execute(
            """SELECT date, foreman, cost_code, cost_code_desc,
                      quantity, unit, company_note
               FROM diary_entry
               WHERE job_id = ? AND company_note != ''
               ORDER BY date, cost_code""",
            (job_id,),
        ).fetchall()

        entries = [dict(r) for r in rows]
        if not entries:
            return {"error": "No diary entries found for this job"}

        # Group by cost code
        by_cc: dict[str, list[dict]] = defaultdict(list)
        diary_notes: list[dict] = []
        for e in entries:
            if e["cost_code"]:
                by_cc[e["cost_code"]].append(e)
            else:
                diary_notes.append(e)

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        results = {"job_id": job_id, "cost_codes_synthesized": 0, "errors": []}

        # ── Cost-code-level synthesis ──
        for cc, cc_entries in by_cc.items():
            # Skip if manual context already exists
            existing = conn.execute(
                "SELECT source FROM cc_context WHERE job_id = ? AND cost_code = ?",
                (job_id, cc),
            ).fetchone()
            if existing and existing["source"] == "manual":
                continue

            try:
                cc_result = _synthesize_cost_code(
                    client, job, cc, cc_entries[0].get("cost_code_desc", ""), cc_entries
                )
                if cc_result:
                    _save_cc_context(conn, job_id, cc, cc_result)
                    results["cost_codes_synthesized"] += 1
            except Exception as e:
                logger.warning("CC synthesis failed for %s/%s: %s", job_id, cc, e)
                results["errors"].append({"cost_code": cc, "error": str(e)})

        # ── Job-level synthesis ──
        existing_pm = conn.execute(
            "SELECT source FROM pm_context WHERE job_id = ?", (job_id,),
        ).fetchone()

        if not existing_pm or existing_pm["source"] != "manual":
            try:
                job_result = _synthesize_job_level(client, job, entries, diary_notes)
                if job_result:
                    _save_pm_context(conn, job_id, job_result)
                    results["job_level"] = True
            except Exception as e:
                logger.warning("Job-level synthesis failed for %s: %s", job_id, e)
                results["errors"].append({"level": "job", "error": str(e)})

        conn.commit()
        return results

    finally:
        conn.close()


def _synthesize_cost_code(
    client: anthropic.Anthropic,
    job: dict,
    cost_code: str,
    cost_code_desc: str,
    entries: list[dict],
) -> dict | None:
    """Call Claude to synthesize context for a single cost code."""
    # Limit entries to avoid token overflow
    sampled = entries[:MAX_ENTRIES_PER_CC]

    # Format entries for the prompt
    entry_lines = []
    for e in sampled:
        qty_str = f" | {e['quantity']} {e['unit']}" if e.get("quantity") else ""
        entry_lines.append(f"- [{e['date']}] {e['foreman']}{qty_str}: {e['company_note']}")

    entries_text = "\n".join(entry_lines)

    prompt = f"""You are analyzing daily foreman diary entries from a construction job.

Job: {job['name']} (Code: {job['job_number']})
Cost Code: {cost_code} — {cost_code_desc}
Total diary entries for this code: {len(entries)} ({len(sampled)} shown)

Daily foreman notes:
{entries_text}

Based on these diary entries, provide a concise synthesis. Respond in JSON only:
{{
    "scope_included": "What work this cost code actually covers — specific activities, not just the code description. 2-3 sentences max.",
    "conditions": "Site conditions, access issues, weather impacts, or other factors that affected production. 1-2 sentences. Say 'None noted' if nothing stands out.",
    "notes": "Key observations for an estimator: equipment issues, crew patterns, productivity insights, coordination items, lessons. 2-4 sentences."
}}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_json_response(response.content[0].text)


def _synthesize_job_level(
    client: anthropic.Anthropic,
    job: dict,
    all_entries: list[dict],
    diary_notes: list[dict],
) -> dict | None:
    """Call Claude to synthesize job-level PM context."""
    # Sample entries across the job timeline
    sampled = _sample_entries(all_entries, MAX_ENTRIES_JOB_LEVEL)

    # Collect unique foremen and cost codes
    foremen = sorted(set(e["foreman"] for e in all_entries if e.get("foreman")))
    cost_codes = sorted(set(e["cost_code"] for e in all_entries if e.get("cost_code")))

    entry_lines = []
    for e in sampled:
        cc_str = f" [{e['cost_code']}]" if e.get("cost_code") else " [DIARY]"
        qty_str = f" ({e['quantity']} {e['unit']})" if e.get("quantity") else ""
        entry_lines.append(f"- [{e['date']}] {e['foreman']}{cc_str}{qty_str}: {e['company_note']}")

    # Add diary-level notes
    for e in diary_notes[:20]:
        entry_lines.append(f"- [{e['date']}] {e['foreman']} [DIARY]: {e['company_note']}")

    entries_text = "\n".join(entry_lines)

    prompt = f"""You are analyzing daily foreman diary entries from a construction job to create a project summary for estimators.

Job: {job['name']} (Code: {job['job_number']})
Foremen: {', '.join(foremen)}
Cost Codes: {len(cost_codes)} active codes
Total diary entries: {len(all_entries)} ({len(sampled)} sampled below)

Representative diary entries:
{entries_text}

Synthesize the following for an estimator who needs to understand this job. Respond in JSON only:
{{
    "project_summary": "2-3 sentence overview of this job — what was built, where, scale of operations.",
    "site_conditions": "Access constraints, terrain, weather patterns, mine site protocols, logistics. 2-3 sentences.",
    "key_challenges": "What made this job difficult — equipment issues, coordination problems, delays, material issues. 2-3 sentences.",
    "key_successes": "What went well — good production days, efficient methods, crew performance. 1-2 sentences.",
    "lessons_learned": "What should be done differently on similar future jobs. 1-2 sentences."
}}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_json_response(response.content[0].text)


def _sample_entries(entries: list[dict], max_count: int) -> list[dict]:
    """Sample entries evenly across the timeline."""
    if len(entries) <= max_count:
        return entries

    # Take every Nth entry to get even coverage
    step = len(entries) / max_count
    indices = [int(i * step) for i in range(max_count)]
    return [entries[i] for i in indices]


def _parse_json_response(text: str) -> dict | None:
    """Extract JSON from Claude's response, handling markdown code blocks."""
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON in the response
        m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        logger.warning("Could not parse JSON from synthesis response: %s", text[:200])
        return None


def _save_cc_context(conn, job_id: int, cost_code: str, data: dict) -> None:
    """Save AI-synthesized cost code context."""
    conn.execute(
        """INSERT INTO cc_context (job_id, cost_code, scope_included, conditions, notes, source)
           VALUES (?, ?, ?, ?, ?, 'ai_synthesized')
           ON CONFLICT(job_id, cost_code) DO UPDATE SET
               scope_included = excluded.scope_included,
               conditions = excluded.conditions,
               notes = excluded.notes,
               source = 'ai_synthesized',
               updated_at = CURRENT_TIMESTAMP""",
        (
            job_id,
            cost_code,
            data.get("scope_included"),
            data.get("conditions"),
            data.get("notes"),
        ),
    )


def _save_pm_context(conn, job_id: int, data: dict) -> None:
    """Save AI-synthesized job-level PM context."""
    conn.execute(
        """INSERT INTO pm_context (job_id, project_summary, site_conditions,
                                   key_challenges, key_successes, lessons_learned, source)
           VALUES (?, ?, ?, ?, ?, ?, 'ai_synthesized')
           ON CONFLICT(job_id) DO UPDATE SET
               project_summary = excluded.project_summary,
               site_conditions = excluded.site_conditions,
               key_challenges = excluded.key_challenges,
               key_successes = excluded.key_successes,
               lessons_learned = excluded.lessons_learned,
               source = 'ai_synthesized',
               updated_at = CURRENT_TIMESTAMP""",
        (
            job_id,
            data.get("project_summary"),
            data.get("site_conditions"),
            data.get("key_challenges"),
            data.get("key_successes"),
            data.get("lessons_learned"),
        ),
    )


# Needed for _parse_json_response regex fallback
import re  # noqa: E402
