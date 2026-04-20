"""Document access tools for bid chat.

list_bid_documents — see what's in the bid
read_document — read full text of a document (or page range)
view_drawing_pages — see PDF pages visually via Anthropic document blocks
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from app.database import get_connection
from app.services.chat_tools.base import ChatTool

logger = logging.getLogger(__name__)

TEXT_LIMIT = 40_000  # chars before truncation notice
MAX_VISION_PAGES = 20


class ListBidDocumentsTool(ChatTool):
    name = "list_bid_documents"
    description = (
        "List all documents uploaded for this bid. Returns filename, category, "
        "page count, and document ID for each. Use this to understand what's "
        "available before reading specific documents. Optionally filter by category."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "bid_id": {"type": "integer", "description": "The bid ID"},
            "category": {
                "type": "string",
                "description": "Optional filter: 'spec', 'drawing', 'addendum', 'contract', 'general', etc.",
            },
        },
        "required": ["bid_id"],
    }
    contexts = ["bid"]

    def execute(self, **kwargs) -> list[dict]:
        bid_id = kwargs["bid_id"]
        category = kwargs.get("category")
        conn = get_connection()
        try:
            if category:
                rows = conn.execute(
                    """SELECT id AS document_id, filename, doc_category, file_type,
                              page_count, dropbox_path, created_at
                       FROM bid_documents WHERE bid_id = ? AND doc_category = ?
                       ORDER BY doc_category, filename""",
                    (bid_id, category),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id AS document_id, filename, doc_category, file_type,
                              page_count, dropbox_path, created_at
                       FROM bid_documents WHERE bid_id = ?
                       ORDER BY doc_category, filename""",
                    (bid_id,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


class ReadDocumentTool(ChatTool):
    name = "read_document"
    description = (
        "Read the full extracted text of a bid document, or a specific section. "
        "Use this to read specs, contracts, addenda, or any text-based document in full "
        "instead of relying on search snippets. For large documents, specify a page range."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "document_id": {"type": "integer", "description": "The document ID from list_bid_documents"},
            "section": {
                "type": "string",
                "description": "Optional: a section heading or keyword to extract only matching chunks",
            },
        },
        "required": ["document_id"],
    }
    contexts = ["bid"]

    def execute(self, **kwargs) -> dict:
        document_id = kwargs["document_id"]
        section = kwargs.get("section")
        conn = get_connection()
        try:
            doc = conn.execute(
                "SELECT id, filename, doc_category, extracted_text FROM bid_documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            if not doc:
                return {"error": f"Document {document_id} not found"}

            text = doc["extracted_text"] or ""

            # If section filter, return matching chunks instead
            if section:
                chunks = conn.execute(
                    """SELECT chunk_text, section_heading FROM bid_document_chunks
                       WHERE document_id = ? AND (
                           section_heading LIKE ? OR chunk_text LIKE ?
                       ) ORDER BY chunk_index""",
                    (document_id, f"%{section}%", f"%{section}%"),
                ).fetchall()
                if chunks:
                    text = "\n\n".join(
                        f"[{c['section_heading']}]\n{c['chunk_text']}" if c["section_heading"]
                        else c["chunk_text"]
                        for c in chunks
                    )
                # If no matching chunks, fall through to full text

            truncated = len(text) > TEXT_LIMIT
            if truncated:
                text = text[:TEXT_LIMIT] + f"\n\n... TRUNCATED at {TEXT_LIMIT} chars (total: {len(doc['extracted_text'] or '')} chars). Use the 'section' parameter to read specific sections."

            return {
                "document_id": document_id,
                "filename": doc["filename"],
                "doc_category": doc["doc_category"],
                "text": text,
                "truncated": truncated,
                "total_chars": len(doc["extracted_text"] or ""),
            }
        finally:
            conn.close()


class ViewDrawingPagesTool(ChatTool):
    name = "view_drawing_pages"
    description = (
        "View specific pages of a PDF document visually. This sends the actual PDF pages "
        "to you so you can read callouts, legends, dimensions, quantities, and details "
        "directly off the drawing. Use this for any visual content — site plans, profiles, "
        "sections, details, P&IDs. Max 20 pages per call."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "document_id": {"type": "integer", "description": "The document ID from list_bid_documents"},
            "pages": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Page numbers to view (1-based). Max 20 pages.",
            },
        },
        "required": ["document_id", "pages"],
    }
    contexts = ["bid"]

    # Flag so the chat engine knows to handle multi-block results
    returns_content_blocks = True

    def execute(self, **kwargs) -> dict:
        document_id = kwargs["document_id"]
        pages = kwargs.get("pages", [1])

        if len(pages) > MAX_VISION_PAGES:
            return {"error": f"Max {MAX_VISION_PAGES} pages per call. Requested {len(pages)}."}

        conn = get_connection()
        try:
            doc = conn.execute(
                "SELECT id, filename, doc_category, file_path, dropbox_path FROM bid_documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            if not doc:
                return {"error": f"Document {document_id} not found"}

            file_path = doc["file_path"] or doc["dropbox_path"]
            if not file_path:
                return {"error": f"No file path for document {document_id}"}

            path = Path(file_path)
            if not path.exists():
                return {"error": f"File not found: {file_path}"}
            if path.suffix.lower() != ".pdf":
                return {"error": f"Not a PDF: {path.suffix}. Use read_document for text extraction."}

            # Extract requested pages into a new PDF
            try:
                import pypdf
                reader = pypdf.PdfReader(str(path))
                total_pages = len(reader.pages)

                # Validate page numbers
                valid_pages = [p for p in pages if 1 <= p <= total_pages]
                if not valid_pages:
                    return {"error": f"No valid pages. Document has {total_pages} pages (1-{total_pages})."}

                writer = pypdf.PdfWriter()
                for p in valid_pages:
                    writer.add_page(reader.pages[p - 1])

                import io
                buf = io.BytesIO()
                writer.write(buf)
                pdf_bytes = buf.getvalue()

            except ImportError:
                return {"error": "pypdf not installed — cannot extract PDF pages"}
            except Exception as e:
                return {"error": f"PDF extraction failed: {e}"}

            b64 = base64.standard_b64encode(pdf_bytes).decode("ascii")
            page_desc = ", ".join(str(p) for p in valid_pages)

            return {
                "document_id": document_id,
                "filename": doc["filename"],
                "pages_returned": valid_pages,
                "total_pages": total_pages,
                "pdf_base64": b64,
                "description": f"Pages {page_desc} of {doc['filename']} ({total_pages} total pages)",
            }
        finally:
            conn.close()

    def format_for_claude(self, result: dict) -> list:
        """Return Anthropic content blocks: document block + text description."""
        if "error" in result:
            return result["error"]

        blocks = []
        # Text description block
        blocks.append({
            "type": "text",
            "text": result["description"],
        })
        # PDF document block (Anthropic native format)
        blocks.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": result["pdf_base64"],
            },
        })
        return blocks
