"""ChromaDB vector store service for semantic search across bid documents.

Single interface for all vector embedding operations. Uses ChromaDB's
built-in default embedding function (all-MiniLM-L6-v2) — no external APIs.

Architecture:
- Per-bid collection isolation: bid_{bid_id}
- Institutional memory collection: institutional_memory
- SQLite remains source of truth; ChromaDB is a parallel search index
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import chromadb

from app.config import CHROMA_DIR, VECTOR_SEARCH_DEFAULT_RESULTS
from app.database import get_connection

logger = logging.getLogger(__name__)

# Singleton client
_client: Optional[chromadb.ClientAPI] = None

# Batch size for ChromaDB upsert operations
EMBED_BATCH_SIZE = 100


def get_chroma_client() -> chromadb.ClientAPI:
    """Return the singleton persistent ChromaDB client."""
    global _client
    if _client is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _client


def reset_client():
    """Reset the singleton client. Used only in tests."""
    global _client
    _client = None


def get_bid_collection(bid_id: int) -> chromadb.Collection:
    """Return (or create) the ChromaDB collection for a bid."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=f"bid_{bid_id}",
        metadata={"hnsw:space": "cosine"},
    )


def get_institutional_collection() -> chromadb.Collection:
    """Return (or create) the institutional memory collection."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name="institutional_memory",
        metadata={"hnsw:space": "cosine"},
    )


# ─────────────────────────────────────────────────────────────
# Embedding
# ─────────────────────────────────────────────────────────────

def embed_chunks(bid_id: int, chunks: list[dict]) -> int:
    """Upsert chunks into the bid's ChromaDB collection.

    Args:
        bid_id: The bid ID
        chunks: List of dicts with keys: id, chunk_text, section_heading,
                document_id, filename, doc_category

    Returns:
        Count of chunks embedded.
    """
    if not chunks:
        return 0

    try:
        collection = get_bid_collection(bid_id)
        total = 0

        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[i:i + EMBED_BATCH_SIZE]

            ids = [f"chunk_{c['id']}" for c in batch]
            documents = [c.get("chunk_text", "") for c in batch]
            metadatas = [
                {
                    "document_id": c.get("document_id", 0),
                    "doc_category": c.get("doc_category") or "",
                    "section_heading": c.get("section_heading") or "",
                    "filename": c.get("filename") or "",
                }
                for c in batch
            ]

            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            total += len(batch)

        logger.info("Embedded %d chunks for bid %d", total, bid_id)
        return total

    except Exception as e:
        logger.error("Failed to embed chunks for bid %d: %s", bid_id, e)
        return 0


def embed_document_chunks(bid_id: int, document_id: int) -> int:
    """Load chunks + doc metadata from SQLite and embed into ChromaDB.

    Convenience wrapper — call after chunking a document.
    Returns count of chunks embedded.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT c.id, c.chunk_text, c.section_heading, c.document_id,
                      d.filename, d.doc_category
               FROM bid_document_chunks c
               JOIN bid_documents d ON c.document_id = d.id
               WHERE c.document_id = ?""",
            (document_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return 0
    return embed_chunks(bid_id, [dict(r) for r in rows])


def remove_document_embeddings(bid_id: int, document_id: int) -> int:
    """Remove all chunk embeddings for a document from the bid's collection.

    Returns count of embeddings removed.
    """
    try:
        collection = get_bid_collection(bid_id)
        # Count before
        before = collection.count()
        collection.delete(where={"document_id": document_id})
        after = collection.count()
        removed = before - after
        if removed > 0:
            logger.info("Removed %d embeddings for doc %d from bid %d", removed, document_id, bid_id)
        return removed
    except Exception as e:
        logger.error("Failed to remove embeddings for doc %d bid %d: %s", document_id, bid_id, e)
        return 0


# ─────────────────────────────────────────────────────────────
# Search
# ─────────────────────────────────────────────────────────────

def search_bid(
    bid_id: int,
    query: str,
    n_results: int = VECTOR_SEARCH_DEFAULT_RESULTS,
    doc_category: str | None = None,
) -> list[dict]:
    """Semantic search within a bid's document collection.

    Returns list of dicts: {chunk_id, chunk_text, section_heading,
                            filename, doc_category, distance}
    """
    try:
        collection = get_bid_collection(bid_id)
        if collection.count() == 0:
            return []

        where = {"doc_category": doc_category} if doc_category else None

        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count()),
            where=where,
        )

        output = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                output.append({
                    "chunk_id": chunk_id,
                    "chunk_text": results["documents"][0][i] if results["documents"] else "",
                    "section_heading": meta.get("section_heading", ""),
                    "filename": meta.get("filename", ""),
                    "doc_category": meta.get("doc_category", ""),
                    "document_id": meta.get("document_id", 0),
                    "distance": results["distances"][0][i] if results["distances"] else 1.0,
                })
        return output

    except Exception as e:
        logger.error("Search failed for bid %d query '%s': %s", bid_id, query[:50], e)
        return []


def search_institutional(
    query: str,
    n_results: int = VECTOR_SEARCH_DEFAULT_RESULTS,
    filters: dict | None = None,
) -> list[dict]:
    """Semantic search across institutional memory.

    Returns list of dicts with chunk_text, metadata, and distance.
    """
    try:
        collection = get_institutional_collection()
        if collection.count() == 0:
            return []

        where = filters if filters else None

        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count()),
            where=where,
        )

        output = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                output.append({
                    "id": doc_id,
                    "chunk_text": results["documents"][0][i] if results["documents"] else "",
                    "metadata": meta,
                    "distance": results["distances"][0][i] if results["distances"] else 1.0,
                })
        return output

    except Exception as e:
        logger.error("Institutional search failed for '%s': %s", query[:50], e)
        return []


# ─────────────────────────────────────────────────────────────
# Collection management
# ─────────────────────────────────────────────────────────────

def delete_bid_collection(bid_id: int) -> bool:
    """Delete a bid's entire ChromaDB collection."""
    try:
        client = get_chroma_client()
        name = f"bid_{bid_id}"
        # Check if exists before deleting
        existing = [c.name for c in client.list_collections()]
        if name in existing:
            client.delete_collection(name)
            logger.info("Deleted collection %s", name)
            return True
        return False
    except Exception as e:
        logger.error("Failed to delete collection for bid %d: %s", bid_id, e)
        return False


def collection_has_embeddings(bid_id: int) -> bool:
    """Quick check: does this bid's collection have any embeddings?"""
    try:
        collection = get_bid_collection(bid_id)
        return collection.count() > 0
    except Exception:
        return False


def get_index_stats(bid_id: int | None = None) -> dict:
    """Return embedding counts per collection.

    If bid_id given, return stats for that bid only.
    Otherwise, return stats for all bids + institutional.
    """
    try:
        client = get_chroma_client()

        if bid_id is not None:
            collection = get_bid_collection(bid_id)
            return {
                "bid_id": bid_id,
                "collection": f"bid_{bid_id}",
                "chunk_count": collection.count(),
            }

        stats = {"bids": {}, "institutional": 0}
        for col in client.list_collections():
            name = col.name
            count = col.count()
            if name == "institutional_memory":
                stats["institutional"] = count
            elif name.startswith("bid_"):
                bid_id_str = name.replace("bid_", "")
                stats["bids"][bid_id_str] = count

        return stats

    except Exception as e:
        logger.error("Failed to get index stats: %s", e)
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────
# Rebuild / backfill
# ─────────────────────────────────────────────────────────────

def rebuild_bid_index(bid_id: int) -> dict:
    """Rebuild a bid's ChromaDB collection from SQLite bid_document_chunks.

    Returns: {chunks_embedded, duration_seconds}
    """
    start = time.time()

    # Clear existing collection
    try:
        delete_bid_collection(bid_id)
    except Exception:
        pass

    # Load all chunks from SQLite
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT c.id, c.chunk_text, c.section_heading, c.document_id,
                      d.filename, d.doc_category
               FROM bid_document_chunks c
               JOIN bid_documents d ON c.document_id = d.id
               WHERE c.bid_id = ?
               ORDER BY c.id""",
            (bid_id,),
        ).fetchall()
    finally:
        conn.close()

    chunks = [dict(r) for r in rows]
    count = embed_chunks(bid_id, chunks)

    duration = time.time() - start
    logger.info("Rebuilt index for bid %d: %d chunks in %.1fs", bid_id, count, duration)
    return {"chunks_embedded": count, "duration_seconds": round(duration, 2)}


def rebuild_institutional_index() -> dict:
    """Rebuild institutional memory from pm_context, cc_context,
    diary_entry, and job_document tables.

    Returns counts per source type and duration.
    """
    start = time.time()

    # Clear existing collection
    try:
        client = get_chroma_client()
        existing = [c.name for c in client.list_collections()]
        if "institutional_memory" in existing:
            client.delete_collection("institutional_memory")
    except Exception:
        pass

    collection = get_institutional_collection()
    counts = {"pm_context": 0, "cc_context": 0, "diary": 0, "job_document": 0}

    conn = get_connection()
    try:
        # 1. PM Context entries
        pm_rows = conn.execute(
            """SELECT id, job_id, project_summary, site_conditions,
                      key_challenges, key_successes, lessons_learned
               FROM pm_context"""
        ).fetchall()

        pm_ids, pm_docs, pm_metas = [], [], []
        for r in pm_rows:
            parts = []
            for field in ["project_summary", "site_conditions", "key_challenges",
                          "key_successes", "lessons_learned"]:
                val = r[field]
                if val and val.strip():
                    label = field.replace("_", " ").title()
                    parts.append(f"{label}: {val}")
            if parts:
                pm_ids.append(f"pm_{r['id']}")
                pm_docs.append("\n".join(parts))
                pm_metas.append({"job_id": r["job_id"], "source_type": "pm_context"})

        if pm_ids:
            for i in range(0, len(pm_ids), EMBED_BATCH_SIZE):
                collection.upsert(
                    ids=pm_ids[i:i + EMBED_BATCH_SIZE],
                    documents=pm_docs[i:i + EMBED_BATCH_SIZE],
                    metadatas=pm_metas[i:i + EMBED_BATCH_SIZE],
                )
            counts["pm_context"] = len(pm_ids)

        # 2. Cost Code Context entries
        cc_rows = conn.execute(
            """SELECT id, job_id, cost_code, scope_included, scope_excluded,
                      conditions, notes
               FROM cc_context"""
        ).fetchall()

        cc_ids, cc_docs, cc_metas = [], [], []
        for r in cc_rows:
            parts = []
            for field in ["scope_included", "scope_excluded", "conditions", "notes"]:
                val = r[field]
                if val and val.strip():
                    label = field.replace("_", " ").title()
                    parts.append(f"{label}: {val}")
            if parts:
                cc_ids.append(f"cc_{r['id']}")
                cc_docs.append("\n".join(parts))
                cc_metas.append({
                    "job_id": r["job_id"],
                    "cost_code": r["cost_code"] or "",
                    "source_type": "cc_context",
                })

        if cc_ids:
            for i in range(0, len(cc_ids), EMBED_BATCH_SIZE):
                collection.upsert(
                    ids=cc_ids[i:i + EMBED_BATCH_SIZE],
                    documents=cc_docs[i:i + EMBED_BATCH_SIZE],
                    metadatas=cc_metas[i:i + EMBED_BATCH_SIZE],
                )
            counts["cc_context"] = len(cc_ids)

        # 3. Diary entries — group by job + cost_code + date
        diary_rows = conn.execute(
            """SELECT id, job_id, foreman, cost_code, date,
                      company_note, inspector_note
               FROM diary_entry
               WHERE company_note IS NOT NULL OR inspector_note IS NOT NULL
               ORDER BY job_id, cost_code, date"""
        ).fetchall()

        # Group and embed
        diary_ids, diary_docs, diary_metas = [], [], []
        for r in diary_rows:
            parts = []
            if r["company_note"] and r["company_note"].strip():
                parts.append(r["company_note"].strip())
            if r["inspector_note"] and r["inspector_note"].strip():
                parts.append(f"Inspector: {r['inspector_note'].strip()}")
            if parts:
                diary_ids.append(f"diary_{r['id']}")
                diary_docs.append("\n".join(parts))
                diary_metas.append({
                    "job_id": r["job_id"],
                    "foreman": r["foreman"] or "",
                    "cost_code": r["cost_code"] or "",
                    "source_type": "diary",
                })

        if diary_ids:
            for i in range(0, len(diary_ids), EMBED_BATCH_SIZE):
                collection.upsert(
                    ids=diary_ids[i:i + EMBED_BATCH_SIZE],
                    documents=diary_docs[i:i + EMBED_BATCH_SIZE],
                    metadatas=diary_metas[i:i + EMBED_BATCH_SIZE],
                )
            counts["diary"] = len(diary_ids)

        # 4. Job documents — chunk extracted text and embed
        from app.services.document_chunker import chunk_text

        doc_rows = conn.execute(
            """SELECT id, job_id, doc_type, extracted_text
               FROM job_document
               WHERE extracted_text IS NOT NULL AND extracted_text != ''"""
        ).fetchall()

        jd_ids, jd_docs, jd_metas = [], [], []
        for r in doc_rows:
            chunks = chunk_text(r["extracted_text"])
            for chunk in chunks:
                jd_ids.append(f"jobdoc_{r['id']}_chunk_{chunk['chunk_index']}")
                jd_docs.append(chunk["chunk_text"])
                jd_metas.append({
                    "job_id": r["job_id"],
                    "doc_type": r["doc_type"] or "",
                    "source_type": "job_document",
                })

        if jd_ids:
            for i in range(0, len(jd_ids), EMBED_BATCH_SIZE):
                collection.upsert(
                    ids=jd_ids[i:i + EMBED_BATCH_SIZE],
                    documents=jd_docs[i:i + EMBED_BATCH_SIZE],
                    metadatas=jd_metas[i:i + EMBED_BATCH_SIZE],
                )
            counts["job_document"] = len(jd_ids)

    finally:
        conn.close()

    duration = time.time() - start
    logger.info(
        "Rebuilt institutional index: %s in %.1fs",
        counts, duration,
    )
    return {**counts, "duration_seconds": round(duration, 2)}
