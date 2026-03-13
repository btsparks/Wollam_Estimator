"""Diary Parser — Extracts structured entries from HeavyJob diary exports.

Parses the 'Diary and Cost Code Notes and Indexes / Working Conditions'
.txt export format from HeavyJob. Each file contains daily foreman notes
organized by date, foreman, and cost code.
"""

from __future__ import annotations

import re
from pathlib import Path


def parse_diary_file(filepath: Path) -> dict:
    """Parse a HeavyJob diary .txt export file.

    Returns:
        {
            "job_code": "8589",
            "job_name": "RTKC Capping 2025",
            "entry_count": 423,
            "entries": [ ... ],
            "foremen": ["GRANGE, DON", ...],
            "cost_codes_found": ["1010", "1011", ...],
            "date_range": ("07/08/2025", "01/08/2026"),
        }
    """
    text = filepath.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    # Extract job code from filename (e.g., "DiaryCCNotes - 8589.txt")
    m = re.search(r"(\d{4,5})", filepath.stem)
    job_code = m.group(1) if m else None
    job_name = None

    entries: list[dict] = []
    current_date = None
    current_foreman = None
    current_foreman_full = None

    entry: dict | None = None          # cost-code entry being built
    diary_parts: list[str] = []        # diary-level notes (no cost code)
    in_company_note = False

    for line in lines:
        stripped = line.strip()

        # Skip blanks
        if not stripped:
            continue

        # ── Page headers (skip) ──
        if "Wollam Construction" in stripped and not stripped.startswith("Job"):
            continue
        if stripped.startswith("Job Name:"):
            jm = re.search(
                r"Job Name:\s+(.+?)(?:\s{3,}Job Code\s+(\d+))?$", stripped
            )
            if jm:
                job_name = jm.group(1).strip()
                if jm.group(2):
                    job_code = jm.group(2)
            continue
        if stripped.startswith("Diary and Cost Code"):
            continue
        if stripped.startswith("Print records"):
            continue
        if re.match(r"^Date\s+Foreman", stripped):
            continue

        # ── Footer / filter summary (stop parsing) ──
        if stripped.startswith("NOTE:") or stripped.startswith("Filters in effect"):
            break
        if (
            re.match(r"^Dates\s*>=", stripped)
            or stripped.startswith("All Foremen")
            or stripped.startswith("Print :")
            or stripped.startswith("All Note")
            or stripped.startswith("All Cost")
        ):
            continue

        # ── Separator line ──
        if re.match(r"^_{5,}$", stripped):
            _flush_entry(entries, entry, current_date, current_foreman, current_foreman_full)
            _flush_diary(entries, diary_parts, current_date, current_foreman, current_foreman_full)
            entry = None
            diary_parts = []
            in_company_note = False
            continue

        # ── Attached Images/Documents ──
        if "Attached Images/Documents" in stripped:
            if entry:
                entry["has_attachments"] = True
            continue

        # ── Date + foreman line ──
        dm = re.match(r"^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+-\s+(.+?)$", stripped)
        if dm:
            _flush_entry(entries, entry, current_date, current_foreman, current_foreman_full)
            _flush_diary(entries, diary_parts, current_date, current_foreman, current_foreman_full)
            current_date = dm.group(1)
            current_foreman = dm.group(2).strip()
            current_foreman_full = dm.group(3).strip()
            entry = None
            diary_parts = []
            in_company_note = False
            continue

        # ── Cost code line (4 digits + description) ──
        cm = re.match(r"^(\d{4})\s{2,}(.+?)$", stripped)
        if cm:
            _flush_entry(entries, entry, current_date, current_foreman, current_foreman_full)
            _flush_diary(entries, diary_parts, current_date, current_foreman, current_foreman_full)
            diary_parts = []
            entry = {
                "cost_code": cm.group(1),
                "cost_code_desc": cm.group(2).strip(),
                "quantity": None,
                "unit": None,
                "slot": None,
                "note_parts": [],
                "inspector_parts": [],
                "has_attachments": False,
            }
            in_company_note = False
            continue

        # ── Quantity line ──
        qm = re.match(r"^([\d,]+\.\d+)\s+(\S+)\s*$", stripped)
        if qm and entry:
            entry["quantity"] = float(qm.group(1).replace(",", ""))
            entry["unit"] = qm.group(2)
            continue

        # ── Slot line ──
        sm = re.match(r"^Slot:\s+(\d+)", stripped)
        if sm and entry:
            entry["slot"] = int(sm.group(1))
            continue

        # ── Company Note ──
        nm = re.match(r"^Company Note:\s+(.*)", stripped)
        if nm and entry:
            note_text = nm.group(1).strip()
            if note_text:
                entry["note_parts"].append(note_text)
            in_company_note = True
            continue

        # ── Inspector Note ──
        im = re.match(r"^Inspector Note:\s*(.*)", stripped)
        if im:
            if entry:
                note_text = im.group(1).strip()
                if note_text:
                    entry["inspector_parts"].append(note_text)
            in_company_note = False
            continue

        # ── Continuation text (reviewer notes, Q&A flags, extra note lines) ──
        if in_company_note and entry and stripped:
            entry["note_parts"].append(stripped)
            continue

        # ── Diary-level notes (after date, before first cost code) ──
        if current_date and entry is None and stripped:
            diary_parts.append(stripped)
            continue

    # Flush last entry
    _flush_entry(entries, entry, current_date, current_foreman, current_foreman_full)
    _flush_diary(entries, diary_parts, current_date, current_foreman, current_foreman_full)

    # Collect metadata
    foremen = sorted(set(e["foreman"] for e in entries if e.get("foreman")))
    cost_codes = sorted(set(e["cost_code"] for e in entries if e.get("cost_code")))
    dates = [e["date"] for e in entries if e.get("date")]
    date_range = (min(dates), max(dates)) if dates else (None, None)

    return {
        "job_code": job_code,
        "job_name": job_name,
        "entry_count": len(entries),
        "entries": entries,
        "foremen": foremen,
        "cost_codes_found": cost_codes,
        "date_range": date_range,
    }


def _flush_entry(
    entries: list[dict],
    entry: dict | None,
    date: str | None,
    foreman: str | None,
    foreman_full: str | None,
) -> None:
    """Finalize and append a cost-code entry if one exists."""
    if entry and entry.get("cost_code"):
        entries.append({
            "date": date,
            "foreman": foreman,
            "foreman_full": foreman_full,
            "cost_code": entry["cost_code"],
            "cost_code_desc": entry["cost_code_desc"],
            "quantity": entry["quantity"],
            "unit": entry["unit"],
            "slot": entry.get("slot"),
            "company_note": " ".join(entry.get("note_parts", [])).strip(),
            "inspector_note": " ".join(entry.get("inspector_parts", [])).strip(),
            "has_attachments": entry.get("has_attachments", False),
        })


def _flush_diary(
    entries: list[dict],
    diary_parts: list[str],
    date: str | None,
    foreman: str | None,
    foreman_full: str | None,
) -> None:
    """Flush accumulated diary-level notes as an entry with cost_code=None."""
    if diary_parts and date:
        text = " ".join(diary_parts).strip()
        if text and len(text) > 5:  # Skip trivial entries
            entries.append({
                "date": date,
                "foreman": foreman,
                "foreman_full": foreman_full,
                "cost_code": None,
                "cost_code_desc": None,
                "quantity": None,
                "unit": None,
                "slot": None,
                "company_note": text,
                "inspector_note": "",
                "has_attachments": False,
            })
        diary_parts.clear()
