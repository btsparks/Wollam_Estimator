"""Dropbox-linked bid document sync engine.

Scans a bid's linked Dropbox estimating folder, discovers documents,
categorizes them by folder structure, extracts text, and tracks changes
between syncs (new, updated, unchanged, removed).
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import ESTIMATING_ROOT, VECTOR_SEARCH_ENABLED
from app.database import get_connection
from app.services.document_extract import extract_text
from app.services.document_chunker import chunk_document
from app.agents.runner import mark_reports_stale

logger = logging.getLogger(__name__)

# Reuse from bidding.py
ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv", ".txt", ".docx", ".doc"}

# Addendum folder regex — matches "Addendum 1", "Addendum #2", "ADD-3", etc.
ADDENDUM_RE = re.compile(r"addendum\s*#?\s*(\d+)", re.IGNORECASE)

# Category mapping from folder/file names
_CATEGORY_PATTERNS = [
    (re.compile(r"spec", re.I), "spec"),
    (re.compile(r"drawing", re.I), "drawing"),
    (re.compile(r"contract", re.I), "contract"),
    (re.compile(r"bid\s*schedule", re.I), "bid_schedule"),
    (re.compile(r"rfi|clarification", re.I), "rfi_clarification"),
    (re.compile(r"addendum", re.I), "addendum_package"),
    (re.compile(r"bond", re.I), "bond_form"),
    (re.compile(r"insurance|certificate", re.I), "insurance"),
]


def resolve_bid_folder(bid_number: str) -> Path | None:
    """Find the Dropbox estimating folder for a bid number.

    Wollam folder convention: "YY-MM-NNNN Project Name"
    where NNNN is the estimate number (= bid_number).
    Also supports legacy format "NNNN - Project Name".

    Returns the full path, or None if not found.
    """
    if not ESTIMATING_ROOT.exists():
        logger.warning("Estimating root not found: %s", ESTIMATING_ROOT)
        return None

    # Match "YY-MM-{bid_number} ..." or "{bid_number} - ..."
    pattern = re.compile(
        rf"(?:^\d{{2}}-\d{{2}}-{re.escape(bid_number)}\s|^{re.escape(bid_number)}\s*-\s*)"
    )

    for entry in sorted(ESTIMATING_ROOT.iterdir()):
        if entry.is_dir() and pattern.match(entry.name):
            logger.info("Resolved bid %s to folder: %s", bid_number, entry)
            return entry

    logger.info("No folder found for bid number %s in %s", bid_number, ESTIMATING_ROOT)
    return None


def categorize_bid_file(rel_path: str, file_name: str) -> tuple[str, int]:
    """Determine doc_category and addendum_number from path and filename.

    Returns (doc_category, addendum_number).
    """
    # Check for addendum folder in the relative path
    addendum_number = 0
    addendum_match = ADDENDUM_RE.search(rel_path)
    if addendum_match:
        addendum_number = int(addendum_match.group(1))

    # Determine category from path and filename
    combined = rel_path + " " + file_name
    for pattern, category in _CATEGORY_PATTERNS:
        if pattern.search(combined):
            return category, addendum_number

    return "general", addendum_number


def discover_bid_files(bid_id: int) -> list[dict]:
    """Walk a bid's Dropbox folder and return the list of eligible files without processing.

    Returns list of dicts with: path, name, size, category.
    """
    conn = get_connection()
    try:
        bid = conn.execute(
            "SELECT dropbox_folder_path FROM active_bids WHERE id = ?", (bid_id,),
        ).fetchone()
        if not bid or not bid["dropbox_folder_path"]:
            return []

        folder = Path(bid["dropbox_folder_path"])
        if not folder.exists():
            return []

        files = []
        for fpath in folder.rglob("*"):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            rel_path = str(fpath.relative_to(folder))
            cat, addendum = categorize_bid_file(rel_path, fpath.name)
            files.append({
                "path": str(fpath),
                "name": fpath.name,
                "size": fpath.stat().st_size,
                "category": cat,
            })
        return files
    finally:
        conn.close()


def sync_bid_documents(bid_id: int, on_progress=None) -> dict:
    """Sync documents from a bid's linked Dropbox folder.

    Walks the folder, discovers/categorizes/extracts documents,
    and tracks changes (new, updated, unchanged, removed).

    Args:
        on_progress: Optional callback(current, total, filename, action) called per file.

    Returns dict with counts: new, updated, unchanged, removed, total, errors.
    """
    conn = get_connection()
    errors = []
    counts = {"new": 0, "updated": 0, "unchanged": 0, "removed": 0}

    try:
        bid = conn.execute(
            "SELECT id, dropbox_folder_path FROM active_bids WHERE id = ?",
            (bid_id,),
        ).fetchone()
        if not bid:
            raise ValueError(f"Bid {bid_id} not found")

        folder_path = bid["dropbox_folder_path"]
        if not folder_path:
            raise ValueError(f"Bid {bid_id} has no linked Dropbox folder")

        folder = Path(folder_path)
        if not folder.exists():
            raise ValueError(f"Dropbox folder not found: {folder_path}")

        # Mark as syncing
        conn.execute(
            "UPDATE active_bids SET sync_status = 'syncing' WHERE id = ?",
            (bid_id,),
        )
        conn.commit()

        # Track which dropbox_paths we see during this scan
        seen_paths = set()

        # Discover all eligible files first (for progress tracking)
        all_files = [
            fpath for fpath in folder.rglob("*")
            if fpath.is_file() and fpath.suffix.lower() in ALLOWED_EXTENSIONS
        ]
        total_files = len(all_files)
        current_file = 0

        # Process each file
        for fpath in all_files:
            suffix = fpath.suffix.lower()
            current_file += 1

            dropbox_path = str(fpath)
            seen_paths.add(dropbox_path)

            try:
                # Calculate hash
                file_bytes = fpath.read_bytes()
                file_hash = hashlib.sha256(file_bytes).hexdigest()
                file_size = len(file_bytes)

                # Categorize
                rel_path = str(fpath.relative_to(folder))
                doc_category, addendum_number = categorize_bid_file(rel_path, fpath.name)

                # Check if this file already exists in bid_documents (by dropbox_path or filename)
                existing = conn.execute(
                    "SELECT id, file_hash FROM bid_documents WHERE bid_id = ? AND dropbox_path = ?",
                    (bid_id, dropbox_path),
                ).fetchone()

                # Also check for a manually uploaded duplicate (same filename, no dropbox_path)
                if existing is None:
                    manual_dup = conn.execute(
                        "SELECT id, file_hash FROM bid_documents WHERE bid_id = ? AND filename = ? AND dropbox_path IS NULL",
                        (bid_id, fpath.name),
                    ).fetchone()
                    if manual_dup:
                        # Adopt the manual upload — link it to Dropbox and update hash
                        conn.execute(
                            """UPDATE bid_documents
                               SET dropbox_path = ?, file_path = ?, file_hash = ?,
                                   file_size_bytes = ?, doc_category = ?,
                                   addendum_number = ?, sync_action = 'unchanged'
                               WHERE id = ?""",
                            (dropbox_path, dropbox_path, file_hash,
                             file_size, doc_category, addendum_number,
                             manual_dup["id"]),
                        )
                        counts["unchanged"] += 1
                        if on_progress:
                            on_progress(current_file, total_files, fpath.name, "unchanged")
                        continue

                if existing is None:
                    # New file — insert and extract
                    extracted_text = ""
                    extraction_status = "pending"
                    extraction_warning = None
                    page_count = None
                    word_count = None

                    try:
                        extracted_text = extract_text(fpath)
                        extraction_status = "complete"
                        word_count = len(extracted_text.split()) if extracted_text else 0
                        if suffix == ".pdf":
                            page_count = extracted_text.count("--- Page ")
                    except Exception as e:
                        extraction_status = "error"
                        extraction_warning = str(e)
                        logger.warning("Extraction failed for %s: %s", fpath.name, e)

                    cursor = conn.execute(
                        """INSERT INTO bid_documents
                           (bid_id, filename, file_type, file_size_bytes, doc_category,
                            extraction_status, extraction_warning, page_count, word_count,
                            file_hash, addendum_number, file_path, extracted_text,
                            dropbox_path, sync_action, version)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', 1)""",
                        (
                            bid_id, fpath.name, suffix, file_size, doc_category,
                            extraction_status, extraction_warning, page_count, word_count,
                            file_hash, addendum_number, dropbox_path,
                            extracted_text, dropbox_path,
                        ),
                    )
                    conn.commit()
                    # Chunk the new document
                    new_doc_id = cursor.lastrowid
                    if extraction_status == "complete":
                        try:
                            chunk_document(new_doc_id)
                        except Exception as ce:
                            logger.warning("Chunking failed for %s: %s", fpath.name, ce)
                        if VECTOR_SEARCH_ENABLED:
                            try:
                                from app.services.vector_store import embed_document_chunks
                                embed_document_chunks(bid_id, new_doc_id)
                            except Exception as ce:
                                logger.warning("Embedding failed for %s: %s", fpath.name, ce)
                    counts["new"] += 1
                    if on_progress:
                        on_progress(current_file, total_files, fpath.name, "new")

                elif existing["file_hash"] != file_hash:
                    # File changed — save previous text for diffing, then re-extract
                    old_doc = conn.execute(
                        "SELECT extracted_text FROM bid_documents WHERE id = ?",
                        (existing["id"],),
                    ).fetchone()
                    if old_doc and old_doc["extracted_text"]:
                        conn.execute(
                            "UPDATE bid_documents SET previous_extracted_text = ? WHERE id = ?",
                            (old_doc["extracted_text"], existing["id"]),
                        )

                    extracted_text = ""
                    extraction_status = "pending"
                    extraction_warning = None
                    page_count = None
                    word_count = None

                    try:
                        extracted_text = extract_text(fpath)
                        extraction_status = "complete"
                        word_count = len(extracted_text.split()) if extracted_text else 0
                        if suffix == ".pdf":
                            page_count = extracted_text.count("--- Page ")
                    except Exception as e:
                        extraction_status = "error"
                        extraction_warning = str(e)

                    conn.execute(
                        """UPDATE bid_documents
                           SET file_hash = ?, file_size_bytes = ?, doc_category = ?,
                               extraction_status = ?, extraction_warning = ?,
                               page_count = ?, word_count = ?, extracted_text = ?,
                               addendum_number = ?, sync_action = 'updated',
                               version = version + 1
                           WHERE id = ?""",
                        (
                            file_hash, file_size, doc_category,
                            extraction_status, extraction_warning,
                            page_count, word_count, extracted_text,
                            addendum_number,
                            existing["id"],
                        ),
                    )
                    conn.commit()
                    # Re-chunk the updated document
                    if extraction_status == "complete":
                        try:
                            chunk_document(existing["id"])
                        except Exception as ce:
                            logger.warning("Re-chunking failed for %s: %s", fpath.name, ce)
                        if VECTOR_SEARCH_ENABLED:
                            try:
                                from app.services.vector_store import remove_document_embeddings, embed_document_chunks
                                remove_document_embeddings(bid_id, existing["id"])
                                embed_document_chunks(bid_id, existing["id"])
                            except Exception as ce:
                                logger.warning("Re-embedding failed for %s: %s", fpath.name, ce)
                    counts["updated"] += 1
                    if on_progress:
                        on_progress(current_file, total_files, fpath.name, "updated")

                else:
                    # Unchanged
                    conn.execute(
                        "UPDATE bid_documents SET sync_action = 'unchanged' WHERE id = ?",
                        (existing["id"],),
                    )
                    counts["unchanged"] += 1
                    if on_progress:
                        on_progress(current_file, total_files, fpath.name, "unchanged")

            except Exception as e:
                errors.append({"file": fpath.name, "error": str(e)})
                logger.warning("Error processing %s: %s", fpath.name, e)

        # Mark removed files — those with a dropbox_path that wasn't seen
        removed = conn.execute(
            """SELECT id FROM bid_documents
               WHERE bid_id = ? AND dropbox_path IS NOT NULL AND sync_action != 'removed'""",
            (bid_id,),
        ).fetchall()

        for row in removed:
            doc = conn.execute(
                "SELECT dropbox_path FROM bid_documents WHERE id = ?",
                (row["id"],),
            ).fetchone()
            if doc and doc["dropbox_path"] not in seen_paths:
                conn.execute(
                    "UPDATE bid_documents SET sync_action = 'removed' WHERE id = ?",
                    (row["id"],),
                )
                counts["removed"] += 1

        # Mark agent reports stale if documents changed
        if counts["new"] > 0 or counts["updated"] > 0:
            try:
                stale_count = mark_reports_stale(bid_id)
                if stale_count:
                    logger.info("Marked %d agent report(s) stale for bid %d", stale_count, bid_id)
            except Exception as e:
                logger.warning("Failed to mark reports stale: %s", e)
            try:
                from app.services.sov_mapper import mark_sov_intelligence_stale
                sov_stale = mark_sov_intelligence_stale(bid_id)
                if sov_stale:
                    logger.info("Marked %d SOV intelligence finding(s) stale for bid %d", sov_stale, bid_id)
            except Exception as e:
                logger.warning("Failed to mark SOV intelligence stale: %s", e)

        # Update bid sync metadata
        conn.execute(
            """UPDATE active_bids
               SET last_synced_at = ?, sync_status = 'complete'
               WHERE id = ?""",
            (datetime.now(tz=timezone.utc).isoformat(), bid_id),
        )
        conn.commit()

    except Exception as e:
        # Mark error status
        try:
            conn.execute(
                "UPDATE active_bids SET sync_status = 'error' WHERE id = ?",
                (bid_id,),
            )
            conn.commit()
        except Exception:
            pass
        raise

    finally:
        conn.close()

    counts["total"] = counts["new"] + counts["updated"] + counts["unchanged"] + counts["removed"]
    counts["errors"] = errors
    return counts
