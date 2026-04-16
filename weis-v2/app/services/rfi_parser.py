"""RFI & Clarifications Log Parser — uses Claude Haiku to extract Q&A pairs."""

import json
import logging
from app.database import get_connection
from app.config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)


def _call_haiku(prompt: str, max_tokens: int = 4096) -> str:
    """Call Claude Haiku for lightweight parsing tasks."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def build_rfi_log(bid_id: int) -> dict:
    """Scan RFI/clarification documents and extract Q&A pairs."""
    conn = get_connection()
    try:
        docs = conn.execute(
            "SELECT id, filename, extracted_text, addendum_number, date_received FROM bid_documents WHERE bid_id = ? AND doc_category = 'rfi_clarification' AND extracted_text IS NOT NULL",
            (bid_id,),
        ).fetchall()

        if not docs:
            return {"status": "ok", "created": 0, "skipped": 0, "message": "No RFI/clarification documents found"}

        # Load existing entries to avoid duplicates
        existing = conn.execute(
            "SELECT rfi_number, question FROM rfi_log WHERE bid_id = ?", (bid_id,)
        ).fetchall()
        existing_numbers = {r["rfi_number"] for r in existing if r["rfi_number"]}
        existing_questions = {(r["question"] or "")[:100] for r in existing}

        created = 0
        skipped = 0

        for doc in docs:
            text = (doc["extracted_text"] or "")[:6000]
            if not text.strip():
                continue

            prompt = f"""Extract RFI (Request for Information) question-and-answer pairs from this document.
The filename is: {doc['filename']}

Text:
{text}

Return a JSON array of RFI entries. Each entry should have:
- rfi_number (string or null — e.g., "RFI-001", "Q-1", "1")
- question (string, required — the question asked)
- asked_by (string or null — who asked)
- date_asked (string or null — ISO date format)
- response (string or null — the answer given)
- responded_by (string or null — who responded)
- date_responded (string or null — ISO date format)
- related_spec (string or null — referenced spec section)
- related_drawing (string or null — referenced drawing number)
- status (string — "answered", "pending", or "withdrawn")

Return ONLY valid JSON array. If no Q&A pairs found, return [].
Example: [{{"rfi_number": "RFI-001", "question": "What concrete strength is required?", "response": "4000 PSI per Section 03300", "status": "answered"}}]"""

            try:
                result_text = _call_haiku(prompt, max_tokens=4096)
                start = result_text.find("[")
                end = result_text.rfind("]") + 1
                if start >= 0 and end > start:
                    rfis = json.loads(result_text[start:end])
                else:
                    continue
            except Exception as e:
                logger.warning("Failed to parse RFIs from doc %d: %s", doc["id"], e)
                continue

            for rfi in rfis:
                question = (rfi.get("question") or "").strip()
                if not question:
                    continue

                rfi_num = rfi.get("rfi_number")

                # Dedup: skip if rfi_number matches or question prefix matches
                if rfi_num and rfi_num in existing_numbers:
                    skipped += 1
                    continue
                if question[:100] in existing_questions:
                    skipped += 1
                    continue

                conn.execute(
                    """INSERT INTO rfi_log (bid_id, document_id, rfi_number, question, asked_by,
                       date_asked, response, responded_by, date_responded, addendum_number,
                       related_spec, related_drawing, status, ai_generated)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (bid_id, doc["id"], rfi_num, question, rfi.get("asked_by"),
                     rfi.get("date_asked"), rfi.get("response"), rfi.get("responded_by"),
                     rfi.get("date_responded"), doc["addendum_number"],
                     rfi.get("related_spec"), rfi.get("related_drawing"),
                     rfi.get("status", "answered")),
                )

                if rfi_num:
                    existing_numbers.add(rfi_num)
                existing_questions.add(question[:100])
                created += 1

        conn.commit()
        return {"status": "ok", "created": created, "skipped": skipped}
    finally:
        conn.close()


def refresh_rfi_log(bid_id: int) -> dict:
    """Rebuild RFI log from documents."""
    return build_rfi_log(bid_id)
