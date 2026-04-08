"""Document change summary service.

Compares current vs previous extracted text of an updated document
and uses Claude Haiku to produce a structured change summary.
"""

from __future__ import annotations

import json
import logging

import anthropic

from app.config import ANTHROPIC_API_KEY
from app.database import get_connection

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

DIFF_PROMPT = """You are reviewing changes to a construction bid document between two versions.

Given the PREVIOUS and CURRENT text of the document, produce a structured summary of what changed.

Return a JSON object:
{
  "summary": "Plain language summary of the changes (1-3 sentences)",
  "additions": ["New requirement or section added..."],
  "deletions": ["Removed requirement or section..."],
  "modifications": ["Changed X from Y to Z..."],
  "affected_spec_sections": ["03300", "31230"],
  "potential_sov_impact": ["Description of how this might affect pricing"]
}

Rules:
- Focus on substantive changes that affect scope, requirements, or pricing
- Ignore formatting changes, page number changes, or minor typo fixes
- Always reference specific section numbers when available
- Keep each item concise (1 sentence)
- Return ONLY valid JSON
"""


def summarize_document_changes(doc_id: int) -> dict | None:
    """Compare current vs previous text and summarize what changed.

    Returns None if no previous text is available.
    Returns dict with summary, additions, deletions, modifications, etc.
    """
    conn = get_connection()
    try:
        doc = conn.execute(
            "SELECT filename, extracted_text, previous_extracted_text FROM bid_documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
    finally:
        conn.close()

    if not doc:
        return None

    current = doc["extracted_text"] or ""
    previous = doc["previous_extracted_text"] or ""

    if not previous:
        return None

    if not current:
        return {
            "summary": "Document text could not be extracted from the updated version.",
            "additions": [],
            "deletions": [],
            "modifications": [],
            "affected_spec_sections": [],
            "potential_sov_impact": [],
        }

    # Truncate for token limits — use first and last portions
    max_chars = 40_000
    prev_text = previous[:max_chars]
    curr_text = current[:max_chars]

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_message = (
        f"Document: {doc['filename']}\n\n"
        f"PREVIOUS VERSION:\n{prev_text}\n\n"
        f"---\n\n"
        f"CURRENT VERSION:\n{curr_text}"
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=DIFF_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        return json.loads(text)

    except Exception as e:
        logger.error("Document diff failed for doc %d: %s", doc_id, e)
        return {
            "summary": f"Change analysis failed: {str(e)}",
            "additions": [],
            "deletions": [],
            "modifications": [],
            "affected_spec_sections": [],
            "potential_sov_impact": [],
        }
