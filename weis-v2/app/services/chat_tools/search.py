"""Semantic search tool — wraps vector_store.search_bid as an on-demand tool.

Replaces the old pre-loaded vector context injection. Claude decides when to search.
"""

from __future__ import annotations

import logging

from app.services.chat_tools.base import ChatTool

logger = logging.getLogger(__name__)


class SearchBidDocumentsTool(ChatTool):
    name = "search_bid_documents"
    description = (
        "Semantic search across all bid documents. Returns document pointers with "
        "snippets ranked by relevance. Use this to find which documents discuss a topic, "
        "then use read_document or view_drawing_pages to read them in full."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "bid_id": {"type": "integer", "description": "The bid ID to search within"},
            "query": {"type": "string", "description": "What to search for (natural language)"},
            "n_results": {
                "type": "integer",
                "description": "Number of results (default 10, max 20)",
                "default": 10,
            },
        },
        "required": ["bid_id", "query"],
    }
    contexts = ["bid"]

    def execute(self, **kwargs) -> list[dict]:
        bid_id = kwargs["bid_id"]
        query = kwargs["query"]
        n_results = min(kwargs.get("n_results", 10), 20)

        try:
            from app.services.vector_store import search_bid
            results = search_bid(bid_id, query, n_results=n_results)
        except Exception as e:
            logger.warning("Vector search failed, falling back to keyword: %s", e)
            results = []

        # Keyword fallback
        if not results:
            results = self._keyword_fallback(bid_id, query, n_results)

        return [
            {
                "document_id": r.get("document_id", 0),
                "filename": r.get("filename", ""),
                "section_heading": r.get("section_heading", ""),
                "doc_category": r.get("doc_category", ""),
                "snippet": (r.get("chunk_text", "") or "")[:200],
                "relevance_score": round(1 - r.get("distance", 1.0), 3) if "distance" in r else None,
            }
            for r in results
        ]

    @staticmethod
    def _keyword_fallback(bid_id: int, message: str, limit: int) -> list[dict]:
        """SQLite keyword search fallback when vector search returns nothing."""
        from app.database import get_connection
        import re

        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                      "being", "have", "has", "had", "do", "does", "did", "will",
                      "would", "could", "should", "may", "might", "shall", "can",
                      "this", "that", "these", "those", "what", "which", "who",
                      "whom", "how", "where", "when", "why", "and", "or", "but",
                      "not", "no", "in", "on", "at", "to", "for", "of", "with",
                      "by", "from", "it", "its", "i", "me", "my", "we", "our",
                      "you", "your", "he", "she", "they", "them", "their"}
        words = re.findall(r'\b[a-z]{3,}\b', message.lower())
        keywords = [w for w in words if w not in stopwords]
        if not keywords:
            return []

        conn = get_connection()
        try:
            placeholders = " OR ".join("c.chunk_text LIKE ?" for _ in keywords)
            params = [f"%{kw}%" for kw in keywords]
            rows = conn.execute(
                f"""SELECT c.document_id, c.chunk_text, c.section_heading,
                           d.filename, d.doc_category
                    FROM bid_document_chunks c
                    JOIN bid_documents d ON c.document_id = d.id
                    WHERE c.bid_id = ? AND ({placeholders})
                    ORDER BY c.chunk_index
                    LIMIT ?""",
                [bid_id] + params + [limit],
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()
