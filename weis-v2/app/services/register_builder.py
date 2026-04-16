"""Drawing & Spec Register Builder — uses Claude Haiku to parse document metadata."""

import json
import logging
from app.database import get_connection
from app.config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)


def _call_haiku(prompt: str, max_tokens: int = 2048) -> str:
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


def build_drawing_register(bid_id: int) -> dict:
    """Scan drawing documents and build/update the drawing register."""
    conn = get_connection()
    try:
        docs = conn.execute(
            "SELECT id, filename, extracted_text, addendum_number, date_received FROM bid_documents WHERE bid_id = ? AND doc_category = 'drawing' AND extracted_text IS NOT NULL",
            (bid_id,),
        ).fetchall()

        if not docs:
            return {"status": "ok", "created": 0, "updated": 0, "message": "No drawing documents found"}

        existing = conn.execute(
            "SELECT drawing_number, id, revision FROM drawing_register WHERE bid_id = ?", (bid_id,)
        ).fetchall()
        existing_map = {r["drawing_number"]: dict(r) for r in existing}

        created = 0
        updated = 0

        for doc in docs:
            text = (doc["extracted_text"] or "")[:3000]
            if not text.strip():
                continue

            prompt = f"""Extract drawing information from this document text. The filename is: {doc['filename']}

Text (first 3000 chars):
{text}

Return a JSON array of drawings found. Each drawing should have:
- drawing_number (string, required — e.g., "C-101", "S-201")
- title (string — what the drawing shows)
- discipline (string — civil, structural, mechanical, electrical, architectural, plumbing, or general)
- revision (string — revision number/letter, default "0")

Return ONLY valid JSON array. If no drawings can be identified, return [].
Example: [{{"drawing_number": "C-101", "title": "Site Plan", "discipline": "civil", "revision": "0"}}]"""

            try:
                result_text = _call_haiku(prompt, max_tokens=2048)
                # Extract JSON from response
                start = result_text.find("[")
                end = result_text.rfind("]") + 1
                if start >= 0 and end > start:
                    drawings = json.loads(result_text[start:end])
                else:
                    continue
            except Exception as e:
                logger.warning("Failed to parse drawings from doc %d: %s", doc["id"], e)
                continue

            for d in drawings:
                num = d.get("drawing_number", "").strip()
                if not num:
                    continue

                if num in existing_map:
                    # Check if revision changed
                    old_rev = existing_map[num].get("revision", "0")
                    new_rev = d.get("revision", "0")
                    if new_rev != old_rev:
                        conn.execute(
                            "UPDATE drawing_register SET revision = ?, previous_revision = ?, is_revised = 1, is_new = 0, title = COALESCE(?, title), discipline = COALESCE(?, discipline), document_id = ?, addendum_number = ?, date_received = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (new_rev, old_rev, d.get("title"), d.get("discipline"), doc["id"],
                             doc["addendum_number"], doc["date_received"], existing_map[num]["id"]),
                        )
                        updated += 1
                else:
                    conn.execute(
                        "INSERT INTO drawing_register (bid_id, document_id, drawing_number, title, discipline, revision, addendum_number, date_received, is_new, ai_generated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)",
                        (bid_id, doc["id"], num, d.get("title"), d.get("discipline"),
                         d.get("revision", "0"), doc["addendum_number"], doc["date_received"]),
                    )
                    existing_map[num] = {"drawing_number": num, "revision": d.get("revision", "0")}
                    created += 1

        conn.commit()
        return {"status": "ok", "created": created, "updated": updated}
    finally:
        conn.close()


def build_spec_register(bid_id: int) -> dict:
    """Scan spec documents and build/update the spec register."""
    conn = get_connection()
    try:
        docs = conn.execute(
            "SELECT id, filename, extracted_text, addendum_number, date_received FROM bid_documents WHERE bid_id = ? AND doc_category = 'spec' AND extracted_text IS NOT NULL",
            (bid_id,),
        ).fetchall()

        if not docs:
            return {"status": "ok", "created": 0, "updated": 0, "message": "No spec documents found"}

        existing = conn.execute(
            "SELECT spec_section, id FROM spec_register WHERE bid_id = ?", (bid_id,)
        ).fetchall()
        existing_map = {r["spec_section"]: dict(r) for r in existing}

        created = 0
        updated = 0

        for doc in docs:
            text = (doc["extracted_text"] or "")[:3000]
            if not text.strip():
                continue

            prompt = f"""Extract specification section information from this document. The filename is: {doc['filename']}

Text (first 3000 chars):
{text}

Return a JSON array of spec sections found. Each should have:
- spec_section (string, required — e.g., "02710", "03300", "Section 31 23 00")
- title (string — section title)
- division (string — e.g., "Division 02", "Division 03")

Return ONLY valid JSON array. If no specs can be identified, return [].
Example: [{{"spec_section": "03300", "title": "Cast-in-Place Concrete", "division": "Division 03"}}]"""

            try:
                result_text = _call_haiku(prompt, max_tokens=2048)
                start = result_text.find("[")
                end = result_text.rfind("]") + 1
                if start >= 0 and end > start:
                    specs = json.loads(result_text[start:end])
                else:
                    continue
            except Exception as e:
                logger.warning("Failed to parse specs from doc %d: %s", doc["id"], e)
                continue

            for s in specs:
                section = s.get("spec_section", "").strip()
                if not section:
                    continue

                if section in existing_map:
                    conn.execute(
                        "UPDATE spec_register SET is_revised = 1, is_new = 0, title = COALESCE(?, title), division = COALESCE(?, division), document_id = ?, addendum_number = ?, date_received = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (s.get("title"), s.get("division"), doc["id"],
                         doc["addendum_number"], doc["date_received"], existing_map[section]["id"]),
                    )
                    updated += 1
                else:
                    conn.execute(
                        "INSERT INTO spec_register (bid_id, document_id, spec_section, title, division, addendum_number, date_received, is_new, ai_generated) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1)",
                        (bid_id, doc["id"], section, s.get("title"), s.get("division"),
                         doc["addendum_number"], doc["date_received"]),
                    )
                    existing_map[section] = {"spec_section": section}
                    created += 1

        conn.commit()
        return {"status": "ok", "created": created, "updated": updated}
    finally:
        conn.close()


def refresh_registers(bid_id: int) -> dict:
    """Rebuild both registers."""
    drawing_result = build_drawing_register(bid_id)
    spec_result = build_spec_register(bid_id)
    return {"drawings": drawing_result, "specs": spec_result}
