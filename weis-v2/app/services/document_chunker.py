"""Document chunking service for bid documents.

Splits extracted text into chunks for agent analysis.
Strategy: section-heading-aware splitting with fallback to
overlapping fixed-size chunks.
"""

from __future__ import annotations

import logging
import re

from app.database import get_connection

logger = logging.getLogger(__name__)

# Target chunk size and overlap
CHUNK_SIZE = 2000
OVERLAP = 200

# Patterns that indicate section headings in construction docs
_HEADING_PATTERNS = [
    # Spec sections: "SECTION 03300", "DIVISION 03", etc.
    re.compile(r"^(?:SECTION|DIVISION)\s+\d+", re.MULTILINE | re.IGNORECASE),
    # Numbered sections: "1.0", "1.1", "2.0", "PART 1", "ARTICLE 3"
    re.compile(r"^(?:PART|ARTICLE)\s+\d+", re.MULTILINE | re.IGNORECASE),
    # All-caps lines (common in specs/contracts) — at least 4 words
    re.compile(r"^[A-Z][A-Z\s\-/&,]{15,}$", re.MULTILINE),
    # Drawing sheet markers
    re.compile(r"^(?:SHEET|DWG|DRAWING)\s+\S+", re.MULTILINE | re.IGNORECASE),
    # Page breaks from PDF extraction
    re.compile(r"^---\s*Page\s+\d+", re.MULTILINE),
]


def chunk_text(text: str) -> list[dict]:
    """Split text into chunks, preferring section-heading boundaries.

    Returns list of dicts: {chunk_index, chunk_text, section_heading}
    """
    if not text or not text.strip():
        return []

    # Try to find section boundaries
    boundaries = _find_section_boundaries(text)

    if boundaries and len(boundaries) >= 2:
        return _chunk_by_sections(text, boundaries)
    else:
        return _chunk_by_size(text)


def _find_section_boundaries(text: str) -> list[tuple[int, str]]:
    """Find section heading positions and their text.

    Returns list of (char_offset, heading_text) sorted by offset.
    """
    boundaries = []
    seen_offsets = set()

    for pattern in _HEADING_PATTERNS:
        for match in pattern.finditer(text):
            offset = match.start()
            # Deduplicate overlapping matches (within 10 chars)
            if any(abs(offset - s) < 10 for s in seen_offsets):
                continue
            seen_offsets.add(offset)

            heading = match.group(0).strip()[:100]
            boundaries.append((offset, heading))

    boundaries.sort(key=lambda x: x[0])
    return boundaries


def _chunk_by_sections(text: str, boundaries: list[tuple[int, str]]) -> list[dict]:
    """Chunk text at section boundaries, merging small sections."""
    chunks = []
    chunk_index = 0

    # Add text start if first boundary isn't at the beginning
    if boundaries[0][0] > 50:
        boundaries.insert(0, (0, ""))

    for i, (offset, heading) in enumerate(boundaries):
        # Get text from this boundary to the next
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        section_text = text[offset:end].strip()

        if not section_text:
            continue

        # If section is too large, sub-chunk it
        if len(section_text) > CHUNK_SIZE * 1.5:
            sub_chunks = _chunk_by_size(section_text)
            for sc in sub_chunks:
                sc["chunk_index"] = chunk_index
                sc["section_heading"] = heading or sc.get("section_heading")
                chunks.append(sc)
                chunk_index += 1
        # If section is tiny and we have a previous chunk, merge
        elif len(section_text) < CHUNK_SIZE * 0.3 and chunks:
            prev = chunks[-1]
            merged = prev["chunk_text"] + "\n\n" + section_text
            if len(merged) <= CHUNK_SIZE * 1.5:
                prev["chunk_text"] = merged
            else:
                chunks.append({
                    "chunk_index": chunk_index,
                    "chunk_text": section_text,
                    "section_heading": heading,
                })
                chunk_index += 1
        else:
            chunks.append({
                "chunk_index": chunk_index,
                "chunk_text": section_text,
                "section_heading": heading,
            })
            chunk_index += 1

    # Reindex
    for i, c in enumerate(chunks):
        c["chunk_index"] = i

    return chunks


def _chunk_by_size(text: str) -> list[dict]:
    """Fall back to fixed-size chunks with overlap."""
    chunks = []
    start = 0
    chunk_index = 0

    while start < len(text):
        end = start + CHUNK_SIZE

        # Try to break at a paragraph or sentence boundary
        if end < len(text):
            # Look for paragraph break near the end
            para_break = text.rfind("\n\n", start + CHUNK_SIZE // 2, end + 200)
            if para_break > start:
                end = para_break
            else:
                # Look for sentence break
                sentence_break = text.rfind(". ", start + CHUNK_SIZE // 2, end + 100)
                if sentence_break > start:
                    end = sentence_break + 1

        chunk_text_str = text[start:end].strip()
        if chunk_text_str:
            chunks.append({
                "chunk_index": chunk_index,
                "chunk_text": chunk_text_str,
                "section_heading": None,
            })
            chunk_index += 1

        # Move forward with overlap
        start = max(start + 1, end - OVERLAP)

    return chunks


def chunk_document(doc_id: int) -> int:
    """Chunk a single document and save to bid_document_chunks.

    Returns number of chunks created.
    """
    conn = get_connection()
    try:
        doc = conn.execute(
            "SELECT id, bid_id, extracted_text FROM bid_documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
        if not doc:
            return 0

        text = doc["extracted_text"]
        if not text or not text.strip():
            return 0

        bid_id = doc["bid_id"]

        # Delete existing chunks for this document
        conn.execute(
            "DELETE FROM bid_document_chunks WHERE document_id = ?",
            (doc_id,),
        )

        # Generate chunks
        chunks = chunk_text(text)

        # Insert
        for chunk in chunks:
            conn.execute(
                """INSERT INTO bid_document_chunks
                   (document_id, bid_id, chunk_index, chunk_text, section_heading)
                   VALUES (?, ?, ?, ?, ?)""",
                (doc_id, bid_id, chunk["chunk_index"],
                 chunk["chunk_text"], chunk["section_heading"]),
            )

        conn.commit()
        return len(chunks)
    finally:
        conn.close()


def chunk_all_bid_documents(bid_id: int) -> dict:
    """Chunk (or re-chunk) all documents for a bid.

    Returns {total_docs, chunked, total_chunks, skipped}.
    """
    conn = get_connection()
    try:
        docs = conn.execute(
            """SELECT id FROM bid_documents
               WHERE bid_id = ? AND extraction_status = 'complete'""",
            (bid_id,),
        ).fetchall()
    finally:
        conn.close()

    total_chunks = 0
    chunked = 0
    skipped = 0

    for doc in docs:
        count = chunk_document(doc["id"])
        if count > 0:
            chunked += 1
            total_chunks += count
        else:
            skipped += 1

    return {
        "total_docs": len(docs),
        "chunked": chunked,
        "total_chunks": total_chunks,
        "skipped": skipped,
    }
