"""Tests for ChromaDB vector store service.

Uses an in-memory (ephemeral) ChromaDB client for fast, isolated tests.
"""

import pytest
from unittest.mock import patch

import chromadb

from app.services import vector_store
from app.services.vector_store import (
    embed_chunks,
    embed_document_chunks,
    remove_document_embeddings,
    search_bid,
    search_institutional,
    delete_bid_collection,
    collection_has_embeddings,
    get_index_stats,
    rebuild_bid_index,
    get_bid_collection,
    get_institutional_collection,
    reset_client,
)
from app.database import get_connection
from app.main import app

from fastapi.testclient import TestClient

client = TestClient(app)

_test_bid_ids = []


@pytest.fixture(autouse=True)
def in_memory_chroma(monkeypatch):
    """Replace persistent client with ephemeral for test isolation."""
    ephemeral = chromadb.EphemeralClient()
    monkeypatch.setattr(vector_store, "_client", ephemeral)
    yield ephemeral
    reset_client()


@pytest.fixture(autouse=True)
def cleanup_test_bids():
    """Clean up any bids created during tests."""
    _test_bid_ids.clear()
    yield
    if _test_bid_ids:
        conn = get_connection()
        try:
            for bid_id in _test_bid_ids:
                conn.execute("DELETE FROM agent_reports WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM bid_document_chunks WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM bid_documents WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM bid_sov_item WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM pricing_group WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM active_bids WHERE id = ?", (bid_id,))
            conn.commit()
        finally:
            conn.close()


def _create_test_bid(**kwargs):
    data = {
        "bid_name": "Vector Test Bid",
        "bid_number": "VT-001",
        "owner": "Test Owner",
        "status": "active",
    }
    data.update(kwargs)
    res = client.post("/api/bidding/bids", json=data)
    assert res.status_code == 200
    bid_id = res.json()["id"]
    _test_bid_ids.append(bid_id)
    return bid_id


def _make_chunks(doc_id=1, bid_id=1, count=5, prefix="chunk"):
    """Generate fake chunk dicts for embedding."""
    return [
        {
            "id": i + 1,
            "chunk_text": f"{prefix} {i}: This is test content about topic {i}",
            "section_heading": f"Section {i}",
            "document_id": doc_id,
            "filename": f"test_doc_{doc_id}.pdf",
            "doc_category": "specification" if i % 2 == 0 else "contract",
        }
        for i in range(count)
    ]


# ─────────────────────────────────────────────────────────────
# Collection basics
# ─────────────────────────────────────────────────────────────

def test_get_bid_collection_creates_collection():
    col = get_bid_collection(42)
    assert col.name == "bid_42"
    assert col.count() == 0


def test_get_institutional_collection():
    col = get_institutional_collection()
    assert col.name == "institutional_memory"
    assert col.count() == 0


# ─────────────────────────────────────────────────────────────
# Embed + search roundtrip
# ─────────────────────────────────────────────────────────────

def test_embed_and_search_roundtrip():
    chunks = [
        {"id": 1, "chunk_text": "concrete forming and rebar installation procedures",
         "section_heading": "Concrete", "document_id": 1,
         "filename": "specs.pdf", "doc_category": "specification"},
        {"id": 2, "chunk_text": "liquidated damages shall be five hundred dollars per day",
         "section_heading": "Legal", "document_id": 2,
         "filename": "contract.pdf", "doc_category": "contract"},
        {"id": 3, "chunk_text": "bonding requirements include performance and payment bonds",
         "section_heading": "Bonds", "document_id": 2,
         "filename": "contract.pdf", "doc_category": "contract"},
        {"id": 4, "chunk_text": "compaction testing at ninety five percent density required",
         "section_heading": "Testing", "document_id": 3,
         "filename": "geotech.pdf", "doc_category": "specification"},
        {"id": 5, "chunk_text": "general site grading and earthwork mass haul",
         "section_heading": "Earthwork", "document_id": 1,
         "filename": "specs.pdf", "doc_category": "specification"},
    ]

    count = embed_chunks(bid_id=1, chunks=chunks)
    assert count == 5

    # Search for bonding — should find the bonding chunk first
    results = search_bid(1, "bonding requirements", n_results=3)
    assert len(results) >= 1
    assert "bonding" in results[0]["chunk_text"].lower()
    assert results[0]["filename"] == "contract.pdf"
    assert "distance" in results[0]

    # Search for concrete — should find concrete chunk
    results = search_bid(1, "concrete rebar", n_results=2)
    assert len(results) >= 1
    assert "concrete" in results[0]["chunk_text"].lower()


def test_collection_isolation():
    """Bid 1 data should NOT appear in bid 2 searches."""
    chunks_1 = [
        {"id": 1, "chunk_text": "unique alpha content only in bid one",
         "section_heading": "", "document_id": 1,
         "filename": "a.pdf", "doc_category": "spec"},
    ]
    chunks_2 = [
        {"id": 2, "chunk_text": "unique beta content only in bid two",
         "section_heading": "", "document_id": 2,
         "filename": "b.pdf", "doc_category": "spec"},
    ]

    embed_chunks(1, chunks_1)
    embed_chunks(2, chunks_2)

    # Search bid 1 for bid 2 content
    results = search_bid(1, "beta content bid two", n_results=5)
    for r in results:
        assert "beta" not in r["chunk_text"]

    # Search bid 2 for bid 1 content
    results = search_bid(2, "alpha content bid one", n_results=5)
    for r in results:
        assert "alpha" not in r["chunk_text"]


def test_remove_document_embeddings():
    bid_id = 500  # Unique bid to avoid cross-test pollution
    chunks = _make_chunks(doc_id=10, bid_id=bid_id, count=3)
    other = _make_chunks(doc_id=20, bid_id=bid_id, count=2, prefix="other")
    for i, c in enumerate(other):
        c["id"] = i + 200
    all_chunks = chunks + other

    embed_chunks(bid_id, all_chunks)
    col = get_bid_collection(bid_id)
    assert col.count() == 5

    removed = remove_document_embeddings(bid_id, 10)
    assert removed == 3
    assert col.count() == 2


def test_search_with_doc_category_filter():
    bid_id = 501  # Unique bid to avoid cross-test pollution
    chunks = [
        {"id": 1, "chunk_text": "testing requirements for soil compaction",
         "section_heading": "", "document_id": 1,
         "filename": "spec.pdf", "doc_category": "specification"},
        {"id": 2, "chunk_text": "testing of contractor performance under contract",
         "section_heading": "", "document_id": 2,
         "filename": "contract.pdf", "doc_category": "contract"},
    ]
    embed_chunks(bid_id, chunks)

    # Filter to specification only
    results = search_bid(bid_id, "testing requirements", doc_category="specification")
    assert len(results) == 1
    assert results[0]["doc_category"] == "specification"


def test_delete_bid_collection():
    chunks = _make_chunks(doc_id=1, bid_id=5, count=3)
    embed_chunks(5, chunks)
    assert collection_has_embeddings(5)

    deleted = delete_bid_collection(5)
    assert deleted is True
    assert not collection_has_embeddings(5)


def test_collection_has_embeddings():
    assert not collection_has_embeddings(999)

    chunks = _make_chunks(doc_id=1, bid_id=999, count=1)
    embed_chunks(999, chunks)
    assert collection_has_embeddings(999)


def test_search_empty_collection():
    """Searching an empty collection should return [] without error."""
    results = search_bid(9999, "anything")
    assert results == []


def test_embed_chunks_batching():
    """Embed more than EMBED_BATCH_SIZE chunks."""
    chunks = _make_chunks(doc_id=1, bid_id=1, count=150)
    for i, c in enumerate(chunks):
        c["id"] = i + 1

    count = embed_chunks(1, chunks)
    assert count == 150

    col = get_bid_collection(1)
    assert col.count() == 150

    # Can still search
    results = search_bid(1, "test content", n_results=5)
    assert len(results) == 5


def test_embed_empty_chunks():
    count = embed_chunks(1, [])
    assert count == 0


# ─────────────────────────────────────────────────────────────
# Institutional memory
# ─────────────────────────────────────────────────────────────

def test_institutional_memory_roundtrip():
    col = get_institutional_collection()

    # Simulate PM context embeddings
    col.upsert(
        ids=["pm_1", "pm_2"],
        documents=[
            "Project Summary: Large pump station with deep excavation. Site Conditions: High water table.",
            "Project Summary: Highway bridge replacement over river. Key Challenges: Traffic management.",
        ],
        metadatas=[
            {"job_id": 8553, "source_type": "pm_context"},
            {"job_id": 8540, "source_type": "pm_context"},
        ],
    )

    results = search_institutional("pump station excavation", n_results=2)
    assert len(results) >= 1
    assert "pump station" in results[0]["chunk_text"].lower()
    assert results[0]["metadata"]["source_type"] == "pm_context"


def test_search_institutional_empty(in_memory_chroma):
    # Ensure a fresh institutional collection
    try:
        in_memory_chroma.delete_collection("institutional_memory")
    except Exception:
        pass
    results = search_institutional("anything")
    assert results == []


# ─────────────────────────────────────────────────────────────
# Index stats
# ─────────────────────────────────────────────────────────────

def test_get_index_stats_single_bid():
    chunks = _make_chunks(doc_id=1, bid_id=7, count=3)
    embed_chunks(7, chunks)

    stats = get_index_stats(bid_id=7)
    assert stats["chunk_count"] == 3
    assert stats["bid_id"] == 7


def test_get_index_stats_all():
    embed_chunks(1, _make_chunks(doc_id=1, bid_id=1, count=2))
    embed_chunks(2, _make_chunks(doc_id=2, bid_id=2, count=4))
    for i, c in enumerate(_make_chunks(doc_id=2, bid_id=2, count=4)):
        c["id"] = i + 100

    stats = get_index_stats()
    assert "bids" in stats
    assert "institutional" in stats


# ─────────────────────────────────────────────────────────────
# Rebuild from SQLite
# ─────────────────────────────────────────────────────────────

def test_rebuild_bid_index():
    """Create a bid with chunks in SQLite, rebuild, verify ChromaDB populated."""
    bid_id = _create_test_bid(bid_name="Rebuild Test", bid_number="RB-001")

    # Insert a document + chunks directly into SQLite
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO bid_documents
               (bid_id, filename, file_type, file_size_bytes, doc_category,
                extraction_status, extracted_text)
               VALUES (?, 'test.pdf', 'pdf', 1000, 'specification',
                       'complete', 'Some test content')""",
            (bid_id,),
        )
        doc_id = cursor.lastrowid

        for i in range(5):
            conn.execute(
                """INSERT INTO bid_document_chunks
                   (document_id, bid_id, chunk_index, chunk_text, section_heading)
                   VALUES (?, ?, ?, ?, ?)""",
                (doc_id, bid_id, i, f"Rebuild test chunk {i} about concrete formwork", f"Section {i}"),
            )
        conn.commit()
    finally:
        conn.close()

    # Rebuild
    result = rebuild_bid_index(bid_id)
    assert result["chunks_embedded"] == 5
    assert result["duration_seconds"] >= 0

    # Verify searchable
    results = search_bid(bid_id, "concrete formwork", n_results=3)
    assert len(results) >= 1
    assert "concrete" in results[0]["chunk_text"].lower()


# ─────────────────────────────────────────────────────────────
# Feature flag
# ─────────────────────────────────────────────────────────────

def test_feature_flag_import():
    """Verify the config flag exists and is boolean."""
    from app.config import VECTOR_SEARCH_ENABLED
    assert isinstance(VECTOR_SEARCH_ENABLED, bool)


# ─────────────────────────────────────────────────────────────
# Agent search queries
# ─────────────────────────────────────────────────────────────

def test_agent_search_queries_defined():
    """Each analysis agent should return non-empty search queries."""
    from app.agents.document_control import DocumentControlAgent
    from app.agents.legal_analyst import LegalAnalystAgent
    from app.agents.qaqc_manager import QAQCManagerAgent
    from app.agents.subcontract_manager import SubcontractManagerAgent
    from app.agents.chief_estimator import ChiefEstimatorAgent

    assert len(DocumentControlAgent().get_search_queries()) >= 5
    assert len(LegalAnalystAgent().get_search_queries()) >= 8
    assert len(QAQCManagerAgent().get_search_queries()) >= 6
    assert len(SubcontractManagerAgent().get_search_queries()) >= 6
    # Chief estimator is an aggregator — empty queries expected
    assert ChiefEstimatorAgent().get_search_queries() == []
