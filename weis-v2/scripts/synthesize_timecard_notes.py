"""Synthesize foreman timecard notes into PM context for all jobs.

Uses Claude Haiku to analyze foreman notes from hj_timecard and generate:
- cc_context: per cost code scope/conditions/notes
- pm_context: per job project summary/challenges/lessons

Skips cost codes and jobs that already have manual or diary-synthesized context.
Processes cost codes in batches of 5 per API call for efficiency.

Usage:
    python scripts/synthesize_timecard_notes.py              # All jobs
    python scripts/synthesize_timecard_notes.py --job 8465   # Single job
    python scripts/synthesize_timecard_notes.py --dry-run    # Preview without API calls
"""
import asyncio
import json
import logging
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

import anthropic
from app.config import ANTHROPIC_API_KEY
from app.database import get_connection

logging.basicConfig(level=logging.WARNING)

MODEL = "claude-haiku-4-5-20251001"
CC_BATCH_SIZE = 5          # Cost codes per API call
MAX_NOTES_PER_CC = 25      # Max distinct notes to send per cost code
MIN_NOTES_FOR_SYNTHESIS = 3  # Minimum notes needed to synthesize


def get_candidate_jobs(single_job: str = None) -> list[dict]:
    """Find jobs with timecard notes that need context synthesis."""
    conn = get_connection()
    try:
        if single_job:
            jobs = conn.execute("""
                SELECT j.job_id, j.job_number, j.name,
                       COUNT(DISTINCT t.cost_code) as cc_with_notes
                FROM job j
                JOIN hj_timecard t ON t.job_id = j.job_id
                WHERE j.job_number = ?
                  AND t.notes IS NOT NULL AND LENGTH(t.notes) >= 10
                GROUP BY j.job_id
            """, (single_job,)).fetchall()
        else:
            jobs = conn.execute("""
                SELECT j.job_id, j.job_number, j.name,
                       COUNT(DISTINCT t.cost_code) as cc_with_notes
                FROM job j
                JOIN hj_timecard t ON t.job_id = j.job_id
                WHERE t.notes IS NOT NULL AND LENGTH(t.notes) >= 10
                GROUP BY j.job_id
                ORDER BY cc_with_notes DESC
            """).fetchall()
        return [dict(j) for j in jobs]
    finally:
        conn.close()


def get_notes_for_cost_code(job_id: int, cost_code: str) -> list[dict]:
    """Get distinct foreman notes for a cost code, most frequent first."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT notes, COUNT(*) as freq,
                   MIN(date) as first_date, MAX(date) as last_date,
                   GROUP_CONCAT(DISTINCT foreman_name) as foremen
            FROM hj_timecard
            WHERE job_id = ? AND cost_code = ?
              AND notes IS NOT NULL AND LENGTH(notes) >= 10
            GROUP BY notes
            ORDER BY freq DESC
            LIMIT ?
        """, (job_id, cost_code, MAX_NOTES_PER_CC)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_candidate_cost_codes(job_id: int) -> list[dict]:
    """Find cost codes with notes that need synthesis (no existing manual/diary context)."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT t.cost_code,
                   cc.description as cc_desc,
                   cc.unit,
                   COUNT(DISTINCT t.notes) as unique_notes,
                   COUNT(*) as total_notes
            FROM hj_timecard t
            LEFT JOIN hj_costcode cc ON cc.job_id = t.job_id AND cc.code = t.cost_code
            LEFT JOIN cc_context ctx ON ctx.job_id = t.job_id AND ctx.cost_code = t.cost_code
                AND ctx.source IN ('manual', 'ai_synthesized')
            WHERE t.job_id = ?
              AND t.notes IS NOT NULL AND LENGTH(t.notes) >= 10
              AND ctx.id IS NULL
            GROUP BY t.cost_code
            HAVING unique_notes >= ?
            ORDER BY unique_notes DESC
        """, (job_id, MIN_NOTES_FOR_SYNTHESIS)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def needs_pm_context(job_id: int) -> bool:
    """Check if job needs pm_context synthesis."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT source FROM pm_context WHERE job_id = ?", (job_id,)
        ).fetchone()
        # Synthesize if no context, or if existing is not manual
        return row is None or row["source"] not in ("manual",)
    finally:
        conn.close()


def synthesize_cc_batch(client: anthropic.Anthropic, job: dict, batch: list[dict]) -> list[dict]:
    """Synthesize context for a batch of cost codes in one API call."""
    sections = []
    for cc_info in batch:
        notes = get_notes_for_cost_code(job["job_id"], cc_info["cost_code"])
        if not notes:
            continue

        note_lines = []
        for n in notes:
            freq = f" [{n['freq']}x]" if n["freq"] > 1 else ""
            note_lines.append(f"  - {n['notes'][:200]}{freq}")

        sections.append(
            f"COST CODE: {cc_info['cost_code']} — {cc_info.get('cc_desc') or 'No description'} "
            f"(Unit: {cc_info.get('unit') or 'N/A'}, {cc_info['unique_notes']} unique notes)\n"
            + "\n".join(note_lines)
        )

    if not sections:
        return []

    codes_text = "\n\n".join(sections)

    prompt = f"""You are analyzing foreman timecard notes from a heavy civil construction job.

Job: {job['name']} ({job['job_number']})

For each cost code below, the notes are daily entries written by foremen describing what the crew did.

{codes_text}

For EACH cost code, synthesize a brief context. Respond with a JSON array:
[
  {{
    "cost_code": "XXXX",
    "scope_included": "What work this code actually covers based on the notes. 1-2 sentences.",
    "conditions": "Site conditions, access, weather, or logistics factors. 1 sentence, or 'None noted'.",
    "notes": "Key takeaways for an estimator: equipment used, crew patterns, productivity observations. 1-2 sentences."
  }}
]

Be factual. Only state what the notes describe. No speculation."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=300 * len(batch),
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_json_array(response.content[0].text)


def synthesize_pm_level(client: anthropic.Anthropic, job: dict) -> dict | None:
    """Synthesize job-level PM context from timecard notes across all cost codes."""
    conn = get_connection()
    try:
        # Sample notes across cost codes and timeline
        rows = conn.execute("""
            SELECT t.cost_code, cc.description as cc_desc, t.date,
                   t.foreman_name, t.notes
            FROM hj_timecard t
            LEFT JOIN hj_costcode cc ON cc.job_id = t.job_id AND cc.code = t.cost_code
            WHERE t.job_id = ? AND t.notes IS NOT NULL AND LENGTH(t.notes) >= 15
            ORDER BY RANDOM()
            LIMIT 150
        """, (job["job_id"],)).fetchall()

        if len(rows) < 5:
            return None

        # Get job stats
        stats = conn.execute("""
            SELECT COUNT(DISTINCT t.cost_code) as active_codes,
                   COUNT(DISTINCT t.foreman_name) as foremen,
                   MIN(t.date) as first_date, MAX(t.date) as last_date,
                   ROUND(SUM(t.hours)) as total_hours
            FROM hj_timecard t
            WHERE t.job_id = ?
        """, (job["job_id"],)).fetchone()
    finally:
        conn.close()

    note_lines = []
    for r in rows:
        cc = r["cost_code"] or "?"
        desc = (r["cc_desc"] or "")[:30]
        note_lines.append(f"- [{r['date']}] {r['foreman_name'] or '?'} [{cc} {desc}]: {r['notes'][:150]}")

    notes_text = "\n".join(note_lines)

    prompt = f"""You are analyzing foreman timecard notes from a heavy civil construction job to create a project summary.

Job: {job['name']} ({job['job_number']})
Duration: {stats['first_date']} to {stats['last_date']}
Active cost codes: {stats['active_codes']}, Foremen: {stats['foremen']}, Total hours: {stats['total_hours']:,.0f}

Representative foreman notes (sampled across timeline):
{notes_text}

Synthesize the following for an estimator. Respond in JSON only:
{{
    "project_summary": "2-3 sentence overview — what was built, where, scale of operations.",
    "site_conditions": "Access, terrain, weather, logistics. 2 sentences.",
    "key_challenges": "What made this job difficult. 2 sentences.",
    "key_successes": "What went well. 1-2 sentences.",
    "lessons_learned": "What to do differently on similar jobs. 1-2 sentences."
}}

Be factual. Only state what the notes describe."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_json_obj(response.content[0].text)


def _parse_json_array(text: str) -> list[dict]:
    """Parse a JSON array from Claude's response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return []


def _parse_json_obj(text: str) -> dict | None:
    """Parse a JSON object from Claude's response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return None


def save_cc_context(job_id: int, cost_code: str, data: dict) -> None:
    """Save synthesized cost code context."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO cc_context (job_id, cost_code, scope_included, conditions, notes, source)
               VALUES (?, ?, ?, ?, ?, 'timecard_notes')
               ON CONFLICT(job_id, cost_code) DO UPDATE SET
                   scope_included = excluded.scope_included,
                   conditions = excluded.conditions,
                   notes = excluded.notes,
                   source = 'timecard_notes',
                   updated_at = CURRENT_TIMESTAMP""",
            (
                job_id, cost_code,
                data.get("scope_included"),
                data.get("conditions"),
                data.get("notes"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def save_pm_context(job_id: int, data: dict) -> None:
    """Save synthesized job-level PM context."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO pm_context (job_id, project_summary, site_conditions,
                                       key_challenges, key_successes, lessons_learned, source)
               VALUES (?, ?, ?, ?, ?, ?, 'timecard_notes')
               ON CONFLICT(job_id) DO UPDATE SET
                   project_summary = excluded.project_summary,
                   site_conditions = excluded.site_conditions,
                   key_challenges = excluded.key_challenges,
                   key_successes = excluded.key_successes,
                   lessons_learned = excluded.lessons_learned,
                   source = 'timecard_notes',
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
        conn.commit()
    finally:
        conn.close()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=str, help="Single job number to process")
    parser.add_argument("--dry-run", action="store_true", help="Preview without API calls")
    parser.add_argument("--cc-only", action="store_true", help="Only synthesize cost code context")
    parser.add_argument("--pm-only", action="store_true", help="Only synthesize PM context")
    args = parser.parse_args()

    start = time.time()
    jobs = get_candidate_jobs(args.job)
    print(f"Found {len(jobs)} jobs with timecard notes\n")

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    total_cc = 0
    total_pm = 0
    total_errors = 0
    total_api_calls = 0

    for ji, job in enumerate(jobs):
        job_num = job["job_number"]
        job_name = (job["name"] or "")[:40]
        print(f"[{ji+1}/{len(jobs)}] {job_num} - {job_name} ({job['cc_with_notes']} CCs with notes)")

        # ── Cost code synthesis ──
        if not args.pm_only:
            candidates = get_candidate_cost_codes(job["job_id"])
            if candidates:
                if args.dry_run:
                    print(f"  Would synthesize {len(candidates)} cost codes")
                else:
                    # Process in batches
                    for batch_start in range(0, len(candidates), CC_BATCH_SIZE):
                        batch = candidates[batch_start:batch_start + CC_BATCH_SIZE]
                        try:
                            results = synthesize_cc_batch(client, job, batch)
                            total_api_calls += 1
                            for result in results:
                                cc = result.get("cost_code")
                                if cc:
                                    save_cc_context(job["job_id"], cc, result)
                                    total_cc += 1
                        except Exception as e:
                            total_errors += 1
                            print(f"  ERROR batch {batch_start}: {e}")

                        # Rate limit
                        time.sleep(0.3)

                    print(f"  CC context: {len(candidates)} candidates → {total_cc} saved")

        # ── Job-level PM synthesis ──
        if not args.cc_only and needs_pm_context(job["job_id"]):
            if args.dry_run:
                print(f"  Would synthesize PM context")
            else:
                try:
                    pm_result = synthesize_pm_level(client, job)
                    total_api_calls += 1
                    if pm_result:
                        save_pm_context(job["job_id"], pm_result)
                        total_pm += 1
                        print(f"  PM context: saved")
                except Exception as e:
                    total_errors += 1
                    print(f"  PM ERROR: {e}")

                time.sleep(0.3)

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"Done in {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"  CC context synthesized: {total_cc}")
    print(f"  PM context synthesized: {total_pm}")
    print(f"  API calls: {total_api_calls}")
    print(f"  Errors: {total_errors}")


if __name__ == "__main__":
    main()
