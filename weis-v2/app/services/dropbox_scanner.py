"""Dropbox Document Intelligence — read-only scanner and extractor.

Scans Wollam Dropbox project folders, catalogs documents, extracts
structured data from Excel logs and PDF specs, and enriches WEIS
cc_context/pm_context with material specification context.

Phase 1: Discovery & inventory (no AI)
Phase 2: Structured extraction from Excel files (no AI)
Phase 3: Spec intelligence via Claude Haiku (AI-powered)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.config import DROPBOX_ROOT, ANTHROPIC_API_KEY
from app.database import get_connection
from app.services.document_extract import extract_text

logger = logging.getLogger(__name__)

# Folders we care about for extraction (priority order)
PRIORITY_FOLDERS = [
    "Cost Code Additions",
    "Drawings/02 - SPECIFICATIONS",
    "RFIs",
    "Submittals",
    "Job Setup",
    "Materials",
    "Change Orders",
]

# File extensions we can process
EXTRACTABLE_EXTENSIONS = {".xlsx", ".xls", ".pdf", ".csv", ".txt", ".docx", ".doc"}

# Regex to extract job number from folder name like "8602 - Valar Atomics (Kiewit)"
JOB_FOLDER_RE = re.compile(r"^(\d{4})\s*-\s*(.+)$")


# ---------------------------------------------------------------------------
# Phase 1 — Discovery & Inventory
# ---------------------------------------------------------------------------

def discover_projects(dropbox_root: Path = None) -> list[dict]:
    """Walk Dropbox root for folders matching 8xxx pattern.

    Returns list of dicts: {folder_name, job_number, folder_path, job_id (if matched)}
    """
    root = dropbox_root or DROPBOX_ROOT
    if not root.exists():
        raise FileNotFoundError(f"Dropbox root not found: {root}")

    conn = get_connection()
    try:
        # Build lookup: job_number -> job_id from DB
        rows = conn.execute("SELECT job_id, job_number FROM job").fetchall()
        job_lookup = {r["job_number"]: r["job_id"] for r in rows}
    finally:
        conn.close()

    projects = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        m = JOB_FOLDER_RE.match(entry.name)
        if not m:
            continue
        job_number = m.group(1)
        job_name = m.group(2).strip()
        job_id = job_lookup.get(job_number)
        projects.append({
            "folder_name": entry.name,
            "job_number": job_number,
            "job_name": job_name,
            "folder_path": str(entry),
            "job_id": job_id,
        })

    return projects


def _categorize_file(rel_path: str, file_name: str) -> str:
    """Determine doc_category from the relative path and filename."""
    rel_lower = rel_path.lower()
    name_lower = file_name.lower()

    if "cost code" in rel_lower or "cost code" in name_lower:
        if "log" in name_lower:
            return "cost_code_log"
        return "cost_code_addition"
    if "specification" in rel_lower or "specs" in rel_lower:
        return "spec"
    if "rfi" in rel_lower:
        if "log" in name_lower:
            return "rfi_log"
        return "rfi"
    if "submittal" in rel_lower:
        if "log" in name_lower:
            return "submittal_log"
        return "submittal"
    if "pipe spec" in rel_lower:
        return "pipe_spec"
    if "drawing" in rel_lower:
        return "drawing"
    if "change order" in rel_lower:
        return "change_order"
    if "job setup" in rel_lower or "contract" in rel_lower:
        return "contract"
    if "material" in rel_lower:
        return "material"
    return "other"


def scan_project_documents(
    folder_path: Path,
    job_id: int | None,
    conn: sqlite3.Connection | None = None,
) -> list[dict]:
    """Scan a single project folder and catalog all documents.

    Returns list of document records inserted/updated.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    docs = []
    folder = Path(folder_path)

    try:
        for fpath in folder.rglob("*"):
            if not fpath.is_file():
                continue
            ext = fpath.suffix.lower()
            if ext not in EXTRACTABLE_EXTENSIONS:
                continue

            rel_path = str(fpath.relative_to(folder))
            file_name = fpath.name
            category = _categorize_file(rel_path, file_name)

            try:
                stat = fpath.stat()
                file_size = stat.st_size
                modified_at = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat()
            except OSError:
                file_size = 0
                modified_at = None

            doc = {
                "job_id": job_id,
                "file_path": str(fpath),
                "file_name": file_name,
                "doc_category": category,
                "file_type": ext.lstrip("."),
                "file_size": file_size,
                "modified_at": modified_at,
            }

            # Upsert — skip if already scanned and file unchanged
            existing = conn.execute(
                """SELECT doc_id, modified_at, extracted
                   FROM dropbox_document
                   WHERE file_path = ?""",
                (str(fpath),),
            ).fetchone()

            if existing:
                if existing["modified_at"] == modified_at:
                    doc["doc_id"] = existing["doc_id"]
                    doc["status"] = "unchanged"
                else:
                    # File changed — re-catalog, mark as needing re-extraction
                    conn.execute(
                        """UPDATE dropbox_document
                           SET file_name=?, doc_category=?, file_type=?,
                               file_size=?, modified_at=?, scanned_at=?,
                               extracted=0
                           WHERE doc_id=?""",
                        (file_name, category, ext.lstrip("."),
                         file_size, modified_at,
                         datetime.now(timezone.utc).isoformat(),
                         existing["doc_id"]),
                    )
                    doc["doc_id"] = existing["doc_id"]
                    doc["status"] = "updated"
            else:
                cursor = conn.execute(
                    """INSERT INTO dropbox_document
                       (job_id, file_path, file_name, doc_category, file_type,
                        file_size, modified_at, scanned_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (job_id, str(fpath), file_name, category, ext.lstrip("."),
                     file_size, modified_at,
                     datetime.now(timezone.utc).isoformat()),
                )
                doc["doc_id"] = cursor.lastrowid
                doc["status"] = "new"

            docs.append(doc)

        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()

    return docs


def discover_and_scan_all(dropbox_root: Path = None) -> dict:
    """Phase 1: Discover all projects and scan their documents.

    Returns summary dict with counts.
    """
    projects = discover_projects(dropbox_root)
    conn = get_connection()

    total_docs = 0
    new_docs = 0
    updated_docs = 0
    matched_projects = 0
    unmatched_projects = []

    try:
        for proj in projects:
            if proj["job_id"] is None:
                unmatched_projects.append(proj["folder_name"])
                continue

            matched_projects += 1
            docs = scan_project_documents(
                Path(proj["folder_path"]),
                proj["job_id"],
                conn=conn,
            )
            total_docs += len(docs)
            new_docs += sum(1 for d in docs if d["status"] == "new")
            updated_docs += sum(1 for d in docs if d["status"] == "updated")

        conn.commit()
    finally:
        conn.close()

    return {
        "projects_found": len(projects),
        "projects_matched": matched_projects,
        "projects_unmatched": unmatched_projects,
        "total_documents": total_docs,
        "new_documents": new_docs,
        "updated_documents": updated_docs,
    }


# ---------------------------------------------------------------------------
# Phase 2 — Structured Extraction (Excel parsing, no AI)
# ---------------------------------------------------------------------------

def _extract_cost_code_log(doc_id: int, file_path: str, job_id: int,
                           conn: sqlite3.Connection) -> int:
    """Parse a Cost Code Log Excel file and extract cost code mappings."""
    text = extract_text(Path(file_path))
    if not text:
        return 0

    lines = text.strip().split("\n")
    extracts = 0

    for line in lines:
        cols = line.split("\t")
        if len(cols) < 2:
            continue

        # Look for rows that have a cost code pattern (e.g., 1000, 4QH-001, etc.)
        code = cols[0].strip()
        if not code or code.lower() in ("cost code", "code", "cc", ""):
            continue

        # Build content from available columns
        content = {
            "cost_code": code,
            "columns": [c.strip() for c in cols if c.strip()],
            "raw_line": line.strip(),
        }

        # Extract description from second column if present
        if len(cols) > 1 and cols[1].strip():
            content["description"] = cols[1].strip()

        conn.execute(
            """INSERT OR REPLACE INTO dropbox_extract
               (doc_id, job_id, extract_type, cost_code, content_json, extracted_at)
               VALUES (?, ?, 'cost_code_mapping', ?, ?, ?)""",
            (doc_id, job_id, code,
             json.dumps(content),
             datetime.now(timezone.utc).isoformat()),
        )
        extracts += 1

    return extracts


def _extract_cost_code_addition(doc_id: int, file_path: str, job_id: int,
                                conn: sqlite3.Connection) -> int:
    """Parse a Cost Code Addition Excel file (HJ Revised CC sheets)."""
    text = extract_text(Path(file_path))
    if not text:
        return 0

    lines = text.strip().split("\n")
    extracts = 0

    for line in lines:
        cols = line.split("\t")
        if len(cols) < 2:
            continue

        code = cols[0].strip()
        if not code or code.lower() in ("cost code", "code", "cc", ""):
            continue

        content = {
            "cost_code": code,
            "columns": [c.strip() for c in cols if c.strip()],
            "raw_line": line.strip(),
            "source_file": Path(file_path).name,
        }

        if len(cols) > 1 and cols[1].strip():
            content["description"] = cols[1].strip()

        conn.execute(
            """INSERT OR REPLACE INTO dropbox_extract
               (doc_id, job_id, extract_type, cost_code, content_json, extracted_at)
               VALUES (?, ?, 'cost_code_addition', ?, ?, ?)""",
            (doc_id, job_id, code,
             json.dumps(content),
             datetime.now(timezone.utc).isoformat()),
        )
        extracts += 1

    return extracts


def _extract_rfi_log(doc_id: int, file_path: str, job_id: int,
                     conn: sqlite3.Connection) -> int:
    """Parse an RFI Log Excel file and extract RFI summaries."""
    text = extract_text(Path(file_path))
    if not text:
        return 0

    lines = text.strip().split("\n")
    extracts = 0
    headers = None

    for line in lines:
        cols = line.split("\t")

        # Detect header row
        if headers is None:
            lower_cols = [c.strip().lower() for c in cols]
            if any(h in lower_cols for h in ("rfi", "rfi #", "rfi no", "number", "no.")):
                headers = [c.strip() for c in cols]
                continue
            continue

        if len(cols) < 2:
            continue

        # Build a dict from header+row
        content = {}
        for i, h in enumerate(headers):
            if i < len(cols) and cols[i].strip():
                content[h] = cols[i].strip()

        if not content:
            continue

        conn.execute(
            """INSERT INTO dropbox_extract
               (doc_id, job_id, extract_type, content_json, extracted_at)
               VALUES (?, ?, 'rfi_summary', ?, ?)""",
            (doc_id, job_id,
             json.dumps(content),
             datetime.now(timezone.utc).isoformat()),
        )
        extracts += 1

    return extracts


def _extract_submittal_log(doc_id: int, file_path: str, job_id: int,
                           conn: sqlite3.Connection) -> int:
    """Parse a Submittal Log Excel file and extract submittal summaries."""
    text = extract_text(Path(file_path))
    if not text:
        return 0

    lines = text.strip().split("\n")
    extracts = 0
    headers = None

    for line in lines:
        cols = line.split("\t")

        # Detect header row
        if headers is None:
            lower_cols = [c.strip().lower() for c in cols]
            if any(h in lower_cols for h in ("submittal", "submittal #", "sub #", "number")):
                headers = [c.strip() for c in cols]
                continue
            continue

        if len(cols) < 2:
            continue

        content = {}
        for i, h in enumerate(headers):
            if i < len(cols) and cols[i].strip():
                content[h] = cols[i].strip()

        if not content:
            continue

        conn.execute(
            """INSERT INTO dropbox_extract
               (doc_id, job_id, extract_type, content_json, extracted_at)
               VALUES (?, ?, 'submittal_summary', ?, ?)""",
            (doc_id, job_id,
             json.dumps(content),
             datetime.now(timezone.utc).isoformat()),
        )
        extracts += 1

    return extracts


# Dispatcher: doc_category -> extraction function
EXTRACTORS = {
    "cost_code_log": _extract_cost_code_log,
    "cost_code_addition": _extract_cost_code_addition,
    "rfi_log": _extract_rfi_log,
    "submittal_log": _extract_submittal_log,
}


def extract_excel_documents(job_id: int = None) -> dict:
    """Phase 2: Parse all unextracted Excel documents.

    If job_id provided, only process that job's documents.
    Returns summary dict.
    """
    conn = get_connection()
    total = 0
    extracted = 0
    errors = []

    try:
        query = """
            SELECT doc_id, job_id, file_path, file_name, doc_category
            FROM dropbox_document
            WHERE extracted = 0
              AND file_type IN ('xlsx', 'xls', 'csv')
              AND doc_category IN ('cost_code_log', 'cost_code_addition',
                                   'rfi_log', 'submittal_log')
        """
        params = []
        if job_id is not None:
            query += " AND job_id = ?"
            params.append(job_id)

        docs = conn.execute(query, params).fetchall()
        total = len(docs)

        for doc in docs:
            extractor = EXTRACTORS.get(doc["doc_category"])
            if not extractor:
                continue

            try:
                count = extractor(
                    doc["doc_id"], doc["file_path"],
                    doc["job_id"], conn,
                )
                conn.execute(
                    "UPDATE dropbox_document SET extracted = 1 WHERE doc_id = ?",
                    (doc["doc_id"],),
                )
                extracted += 1
                logger.info(
                    "Extracted %d items from %s", count, doc["file_name"]
                )
            except Exception as e:
                errors.append({"file": doc["file_name"], "error": str(e)})
                logger.warning("Failed to extract %s: %s", doc["file_name"], e)

        conn.commit()
    finally:
        conn.close()

    return {
        "documents_found": total,
        "documents_extracted": extracted,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Phase 3 — Spec Intelligence (AI-powered)
# ---------------------------------------------------------------------------

def extract_spec_with_ai(doc_id: int, file_path: str, job_id: int,
                         conn: sqlite3.Connection) -> int:
    """Use Claude Haiku to extract material specs from a PDF spec document."""
    import anthropic

    text = extract_text(Path(file_path))
    if not text or len(text.strip()) < 100:
        return 0

    # Truncate to fit in a reasonable prompt
    text = text[:40_000]

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""Analyze this construction specification document and extract:
1. Material types and specifications (e.g., carbon steel, CPVC, stainless, RTRP)
2. Cost code prefixes if mentioned (e.g., 1CA, 4QH, 5FL)
3. Pipe classes, pressure ratings, or material grades
4. Key material properties or requirements

Return ONLY valid JSON with this structure:
{{
  "materials": [
    {{
      "prefix": "cost code prefix if found, or null",
      "material_type": "e.g., Carbon Steel",
      "spec_number": "spec document number if present",
      "grade": "material grade if specified",
      "class": "ANSI class or pressure rating if specified",
      "properties": ["key property 1", "key property 2"],
      "notes": "any important notes about this material"
    }}
  ],
  "document_summary": "one-line summary of what this spec covers"
}}

If no material specs are found, return {{"materials": [], "document_summary": "..."}}.

DOCUMENT TEXT:
{text}""",
        }],
    )

    result_text = response.content[0].text.strip()

    # Parse the JSON response
    try:
        # Handle markdown code blocks
        if result_text.startswith("```"):
            result_text = re.sub(r"^```(?:json)?\n?", "", result_text)
            result_text = re.sub(r"\n?```$", "", result_text)
        result = json.loads(result_text)
    except json.JSONDecodeError:
        logger.warning("AI returned invalid JSON for doc %d", doc_id)
        result = {"materials": [], "document_summary": result_text[:200], "parse_error": True}

    extracts = 0
    for mat in result.get("materials", []):
        conn.execute(
            """INSERT INTO dropbox_extract
               (doc_id, job_id, extract_type, cost_code, content_json, extracted_at)
               VALUES (?, ?, 'spec_material', ?, ?, ?)""",
            (doc_id, job_id, mat.get("prefix"),
             json.dumps(mat),
             datetime.now(timezone.utc).isoformat()),
        )
        extracts += 1

    # Also store the document summary
    if result.get("document_summary"):
        conn.execute(
            """INSERT INTO dropbox_extract
               (doc_id, job_id, extract_type, content_json, extracted_at)
               VALUES (?, ?, 'spec_summary', ?, ?)""",
            (doc_id, job_id,
             json.dumps({"summary": result["document_summary"]}),
             datetime.now(timezone.utc).isoformat()),
        )
        extracts += 1

    return extracts


def extract_specs(job_id: int = None, all_jobs: bool = False) -> dict:
    """Phase 3: AI-powered spec extraction from PDF documents.

    Processes spec/pipe_spec documents that haven't been extracted yet.
    """
    conn = get_connection()
    total = 0
    extracted = 0
    errors = []

    try:
        query = """
            SELECT doc_id, job_id, file_path, file_name
            FROM dropbox_document
            WHERE extracted = 0
              AND file_type = 'pdf'
              AND doc_category IN ('spec', 'pipe_spec')
        """
        params = []
        if job_id is not None and not all_jobs:
            query += " AND job_id = ?"
            params.append(job_id)

        docs = conn.execute(query, params).fetchall()
        total = len(docs)

        for doc in docs:
            try:
                count = extract_spec_with_ai(
                    doc["doc_id"], doc["file_path"],
                    doc["job_id"], conn,
                )
                conn.execute(
                    "UPDATE dropbox_document SET extracted = 1 WHERE doc_id = ?",
                    (doc["doc_id"],),
                )
                extracted += 1
                logger.info(
                    "AI extracted %d materials from %s", count, doc["file_name"]
                )
            except Exception as e:
                errors.append({"file": doc["file_name"], "error": str(e)})
                logger.warning("AI extraction failed for %s: %s", doc["file_name"], e)

        conn.commit()
    finally:
        conn.close()

    return {
        "specs_found": total,
        "specs_extracted": extracted,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Enrichment — Push extractions → cc_context / pm_context
# ---------------------------------------------------------------------------

def enrich_context() -> dict:
    """Push Dropbox extractions into cc_context and pm_context tables.

    Only fills gaps — never overwrites existing manual or AI-synthesized context.
    """
    conn = get_connection()
    cc_added = 0
    cc_updated = 0
    pm_updated = 0

    try:
        # --- Enrich cc_context from cost code mappings ---
        cc_extracts = conn.execute("""
            SELECT e.job_id, e.cost_code, e.content_json, e.extract_type
            FROM dropbox_extract e
            WHERE e.extract_type IN ('cost_code_mapping', 'cost_code_addition', 'spec_material')
              AND e.cost_code IS NOT NULL
            ORDER BY e.job_id, e.cost_code
        """).fetchall()

        for ext in cc_extracts:
            content = json.loads(ext["content_json"])
            job_id = ext["job_id"]
            cost_code = ext["cost_code"]

            if not job_id or not cost_code:
                continue

            # Check existing cc_context
            existing = conn.execute(
                "SELECT * FROM cc_context WHERE job_id = ? AND cost_code = ?",
                (job_id, cost_code),
            ).fetchone()

            if existing and existing["source"] not in ("dropbox_specs", "dropbox_extract"):
                # Don't overwrite manual or AI-synthesized context
                # But we can append dropbox notes if notes field is empty
                if not existing["notes"]:
                    note = _build_cc_note(content, ext["extract_type"])
                    if note:
                        conn.execute(
                            """UPDATE cc_context SET notes = ?, source = ?
                               WHERE job_id = ? AND cost_code = ?""",
                            (note, existing["source"],
                             job_id, cost_code),
                        )
                        cc_updated += 1
                continue

            if existing and existing["source"] in ("dropbox_specs", "dropbox_extract"):
                # Update existing dropbox-sourced context
                note = _build_cc_note(content, ext["extract_type"])
                if note:
                    conn.execute(
                        """UPDATE cc_context SET notes = ?, source = ?
                           WHERE job_id = ? AND cost_code = ?""",
                        (note, "dropbox_extract",
                         job_id, cost_code),
                    )
                    cc_updated += 1
                continue

            # No existing context — create new entry
            note = _build_cc_note(content, ext["extract_type"])
            scope = content.get("description", "")
            source = "dropbox_specs" if ext["extract_type"] == "spec_material" else "dropbox_extract"

            conn.execute(
                """INSERT INTO cc_context
                   (job_id, cost_code, scope_included, notes, source)
                   VALUES (?, ?, ?, ?, ?)""",
                (job_id, cost_code, scope, note, source),
            )
            cc_added += 1

        # --- Enrich pm_context from RFI/Submittal summaries ---
        rfi_counts = conn.execute("""
            SELECT job_id, COUNT(*) as cnt
            FROM dropbox_extract
            WHERE extract_type = 'rfi_summary'
            GROUP BY job_id
        """).fetchall()

        for row in rfi_counts:
            job_id = row["job_id"]
            if not job_id:
                continue

            existing_pm = conn.execute(
                "SELECT * FROM pm_context WHERE job_id = ?",
                (job_id,),
            ).fetchone()

            rfi_note = f"[Dropbox] {row['cnt']} RFIs logged for this project."

            if existing_pm:
                # Append to key_challenges if not already noted
                challenges = existing_pm["key_challenges"] or ""
                if "Dropbox" not in challenges and "[Dropbox]" not in challenges:
                    new_challenges = (challenges + "\n" + rfi_note).strip() if challenges else rfi_note
                    conn.execute(
                        "UPDATE pm_context SET key_challenges = ? WHERE job_id = ?",
                        (new_challenges, job_id),
                    )
                    pm_updated += 1
            # Don't create pm_context rows just for RFI counts

        conn.commit()
    finally:
        conn.close()

    return {
        "cc_context_added": cc_added,
        "cc_context_updated": cc_updated,
        "pm_context_updated": pm_updated,
    }


def _build_cc_note(content: dict, extract_type: str) -> str:
    """Build a human-readable note from extraction content."""
    parts = []

    if extract_type == "spec_material":
        mat_type = content.get("material_type", "")
        grade = content.get("grade", "")
        mat_class = content.get("class", "")
        props = content.get("properties", [])
        notes = content.get("notes", "")

        if mat_type:
            parts.append(f"Material: {mat_type}")
        if grade:
            parts.append(f"Grade: {grade}")
        if mat_class:
            parts.append(f"Class: {mat_class}")
        if props:
            parts.append(f"Properties: {', '.join(props)}")
        if notes:
            parts.append(notes)

    elif extract_type in ("cost_code_mapping", "cost_code_addition"):
        desc = content.get("description", "")
        source = content.get("source_file", "")
        if desc:
            parts.append(f"From Dropbox: {desc}")
        if source:
            parts.append(f"Source: {source}")

    return " | ".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Reporting / Status
# ---------------------------------------------------------------------------

def get_scan_summary() -> dict:
    """Get summary stats from the Dropbox scan tables."""
    conn = get_connection()
    try:
        doc_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM dropbox_document"
        ).fetchone()["cnt"]

        by_category = conn.execute("""
            SELECT doc_category, COUNT(*) as cnt
            FROM dropbox_document
            GROUP BY doc_category
            ORDER BY cnt DESC
        """).fetchall()

        extracted_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM dropbox_document WHERE extracted = 1"
        ).fetchone()["cnt"]

        extract_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM dropbox_extract"
        ).fetchone()["cnt"]

        by_type = conn.execute("""
            SELECT extract_type, COUNT(*) as cnt
            FROM dropbox_extract
            GROUP BY extract_type
            ORDER BY cnt DESC
        """).fetchall()

        jobs_with_docs = conn.execute("""
            SELECT COUNT(DISTINCT job_id) as cnt
            FROM dropbox_document
            WHERE job_id IS NOT NULL
        """).fetchone()["cnt"]

        return {
            "total_documents": doc_count,
            "documents_extracted": extracted_count,
            "documents_pending": doc_count - extracted_count,
            "by_category": {r["doc_category"]: r["cnt"] for r in by_category},
            "total_extracts": extract_count,
            "by_extract_type": {r["extract_type"]: r["cnt"] for r in by_type},
            "jobs_with_documents": jobs_with_docs,
        }
    finally:
        conn.close()
