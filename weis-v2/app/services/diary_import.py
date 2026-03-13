"""Diary Import — Scan, parse, and store HeavyJob diary exports.

Reads .txt files from the Heavy Job Notes folder, parses them with
diary_parser, and stores structured entries in the diary_entry table.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import DIARY_DIR
from app.database import get_connection
from app.services.diary_parser import parse_diary_file


def import_all_diaries(folder: Path | None = None) -> dict:
    """Import all diary .txt files from the folder into the database.

    For each file:
    1. Extract job code from filename
    2. Match to job in database
    3. Parse entries
    4. Delete existing diary_entry rows for that job (re-import)
    5. Insert all entries

    Returns summary dict with per-job results.
    """
    folder = folder or DIARY_DIR
    if not folder.exists():
        return {"error": f"Folder not found: {folder}", "jobs": []}

    txt_files = sorted(folder.glob("*.txt"))
    if not txt_files:
        return {"error": "No .txt files found", "jobs": []}

    conn = get_connection()
    results = []

    try:
        for filepath in txt_files:
            result = _import_single_file(conn, filepath)
            results.append(result)

        conn.commit()
    finally:
        conn.close()

    total_entries = sum(r.get("entries_imported", 0) for r in results)
    matched = sum(1 for r in results if r.get("job_id"))

    return {
        "files_scanned": len(txt_files),
        "jobs_matched": matched,
        "total_entries": total_entries,
        "jobs": results,
    }


def _import_single_file(conn, filepath: Path) -> dict:
    """Parse and import a single diary file."""
    try:
        parsed = parse_diary_file(filepath)
    except Exception as e:
        return {
            "filename": filepath.name,
            "error": f"Parse error: {e}",
            "entries_imported": 0,
        }

    job_code = parsed["job_code"]
    if not job_code:
        return {
            "filename": filepath.name,
            "error": "Could not extract job code from filename",
            "entries_imported": 0,
        }

    # Match to job in database
    job_row = conn.execute(
        "SELECT job_id FROM job WHERE job_number = ?", (job_code,)
    ).fetchone()

    job_id = job_row["job_id"] if job_row else None

    if not job_id:
        return {
            "filename": filepath.name,
            "job_code": job_code,
            "job_name": parsed.get("job_name"),
            "error": f"No matching job in database for code {job_code}",
            "entries_imported": 0,
        }

    # Clear existing diary entries for this job
    conn.execute("DELETE FROM diary_entry WHERE job_id = ?", (job_id,))

    # Insert all entries
    entries = parsed["entries"]
    if entries:
        conn.executemany(
            """INSERT INTO diary_entry
               (job_id, job_code, date, foreman, foreman_full, cost_code,
                cost_code_desc, quantity, unit, slot, company_note,
                inspector_note, has_attachments, source_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    job_id,
                    job_code,
                    e["date"],
                    e["foreman"],
                    e["foreman_full"],
                    e["cost_code"],
                    e["cost_code_desc"],
                    e["quantity"],
                    e["unit"],
                    e["slot"],
                    e["company_note"],
                    e["inspector_note"],
                    e["has_attachments"],
                    filepath.name,
                )
                for e in entries
            ],
        )

    return {
        "filename": filepath.name,
        "job_code": job_code,
        "job_id": job_id,
        "job_name": parsed.get("job_name"),
        "entries_imported": len(entries),
        "foremen": parsed.get("foremen", []),
        "cost_codes_found": len(parsed.get("cost_codes_found", [])),
        "date_range": parsed.get("date_range"),
    }


def get_diary_status() -> list[dict]:
    """Return diary import status for all jobs that have diary data."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT
                de.job_id,
                de.job_code,
                j.name as job_name,
                COUNT(*) as entry_count,
                COUNT(DISTINCT de.cost_code) as cost_code_count,
                COUNT(DISTINCT de.foreman) as foreman_count,
                MIN(de.date) as date_start,
                MAX(de.date) as date_end,
                de.source_file
            FROM diary_entry de
            JOIN job j ON j.job_id = de.job_id
            GROUP BY de.job_id
            ORDER BY de.job_code
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_diary_entries(job_id: int, cost_code: str | None = None) -> list[dict]:
    """Return diary entries for a job, optionally filtered by cost code."""
    conn = get_connection()
    try:
        if cost_code:
            rows = conn.execute(
                """SELECT * FROM diary_entry
                   WHERE job_id = ? AND cost_code = ?
                   ORDER BY date, foreman""",
                (job_id, cost_code),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM diary_entry
                   WHERE job_id = ?
                   ORDER BY date, foreman, cost_code""",
                (job_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_diary_summary(job_id: int) -> dict | None:
    """Return diary summary stats for a single job."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) as entry_count,
                COUNT(DISTINCT cost_code) as cost_code_count,
                COUNT(DISTINCT foreman) as foreman_count,
                MIN(date) as date_start,
                MAX(date) as date_end,
                GROUP_CONCAT(DISTINCT foreman) as foremen
            FROM diary_entry
            WHERE job_id = ? AND cost_code IS NOT NULL
        """, (job_id,)).fetchone()

        if not row or row["entry_count"] == 0:
            return None

        r = dict(row)
        r["foremen"] = r["foremen"].split(",") if r["foremen"] else []
        return r
    finally:
        conn.close()
