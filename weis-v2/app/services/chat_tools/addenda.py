"""Addenda tools — surface addendum content and supersession info.

list_addenda — what addenda exist for this bid
find_addendum_changes — search addenda for topic-specific changes
"""

from __future__ import annotations

import logging

from app.database import get_connection
from app.services.chat_tools.base import ChatTool

logger = logging.getLogger(__name__)


class ListAddendaTool(ChatTool):
    name = "list_addenda"
    description = (
        "List all addenda for this bid. Addenda supersede base documents — always check "
        "for addendum changes before finalizing any answer about scope, quantities, or "
        "contractor responsibilities."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "bid_id": {"type": "integer", "description": "The bid ID"},
        },
        "required": ["bid_id"],
    }
    contexts = ["bid"]

    def execute(self, **kwargs) -> list[dict]:
        bid_id = kwargs["bid_id"]
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT id AS document_id, filename, doc_category, page_count,
                          created_at, extracted_text
                   FROM bid_documents
                   WHERE bid_id = ? AND doc_category = 'addendum'
                   ORDER BY filename""",
                (bid_id,),
            ).fetchall()
            results = []
            for r in rows:
                text = r["extracted_text"] or ""
                results.append({
                    "document_id": r["document_id"],
                    "filename": r["filename"],
                    "page_count": r["page_count"],
                    "summary": text[:300] + "..." if len(text) > 300 else text,
                })
            return results
        finally:
            conn.close()


class FindAddendumChangesTool(ChatTool):
    name = "find_addendum_changes"
    description = (
        "Search addendum documents for changes related to a specific topic. Use this to "
        "check whether addenda supersede base-document language on scope, materials, "
        "quantities, or contractor responsibility. Critical for avoiding the #1 estimating "
        "error: missing supersession."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "bid_id": {"type": "integer", "description": "The bid ID"},
            "topic": {
                "type": "string",
                "description": "The topic to search for in addenda (e.g., 'turf reinforcement', 'liquidated damages', 'electrical scope')",
            },
        },
        "required": ["bid_id", "topic"],
    }
    contexts = ["bid"]

    def execute(self, **kwargs) -> list[dict]:
        bid_id = kwargs["bid_id"]
        topic = kwargs["topic"]

        # Try vector search first, restricted to addendum docs
        results = []
        try:
            from app.services.vector_store import search_bid
            all_results = search_bid(bid_id, topic, n_results=20)
            results = [r for r in all_results if r.get("doc_category") == "addendum"]
        except Exception:
            pass

        # Keyword fallback on addendum chunks
        if not results:
            results = self._keyword_search(bid_id, topic)

        return [
            {
                "filename": r.get("filename", ""),
                "section_heading": r.get("section_heading", ""),
                "snippet": (r.get("chunk_text", "") or "")[:400],
                "document_id": r.get("document_id", 0),
            }
            for r in results[:10]
        ]

    @staticmethod
    def _keyword_search(bid_id: int, topic: str) -> list[dict]:
        """Keyword search within addendum chunks."""
        import re
        conn = get_connection()
        try:
            words = re.findall(r'\b[a-z]{3,}\b', topic.lower())
            if not words:
                return []
            placeholders = " AND ".join("c.chunk_text LIKE ?" for _ in words)
            params = [f"%{w}%" for w in words]
            rows = conn.execute(
                f"""SELECT c.document_id, c.chunk_text, c.section_heading,
                           d.filename, d.doc_category
                    FROM bid_document_chunks c
                    JOIN bid_documents d ON c.document_id = d.id
                    WHERE c.bid_id = ? AND d.doc_category = 'addendum'
                    AND ({placeholders})
                    ORDER BY c.chunk_index LIMIT 10""",
                [bid_id] + params,
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()
