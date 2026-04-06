"""Tests for Dropbox-linked bid document sync."""

import hashlib
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_connection
from app.services.bid_sync import (
    resolve_bid_folder,
    categorize_bid_file,
    sync_bid_documents,
)

client = TestClient(app)

_test_bid_ids = []


@pytest.fixture(autouse=True)
def cleanup_test_bids():
    """Clean up any bids created during tests."""
    _test_bid_ids.clear()
    yield
    if _test_bid_ids:
        conn = get_connection()
        try:
            for bid_id in _test_bid_ids:
                conn.execute("DELETE FROM bid_document_chunks WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM bid_documents WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM bid_sov_item WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM pricing_group WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM active_bids WHERE id = ?", (bid_id,))
            conn.commit()
        finally:
            conn.close()


def create_test_bid(**kwargs):
    """Create a bid via API and track for cleanup."""
    data = {
        "bid_name": "Sync Test Bid",
        "bid_number": "9999",
        "status": "active",
    }
    data.update(kwargs)
    res = client.post("/api/bidding/bids", json=data)
    assert res.status_code == 200
    bid = res.json()
    _test_bid_ids.append(bid["id"])
    return bid


# ── resolve_bid_folder ──────────────────────────────────────────


def test_resolve_bid_folder_wollam_format(tmp_path):
    """Resolve a bid folder in Wollam YY-MM-NNNN format."""
    (tmp_path / "25-10-2514 Kiewit Valar Atomics").mkdir()
    (tmp_path / "26-02-2554 Oklo Aurora Nuclear (Kiewit)").mkdir()
    (tmp_path / "unrelated_folder").mkdir()

    with patch("app.services.bid_sync.ESTIMATING_ROOT", tmp_path):
        result = resolve_bid_folder("2514")
        assert result is not None
        assert result.name == "25-10-2514 Kiewit Valar Atomics"

        result2 = resolve_bid_folder("2554")
        assert result2 is not None
        assert result2.name == "26-02-2554 Oklo Aurora Nuclear (Kiewit)"


def test_resolve_bid_folder_legacy_format(tmp_path):
    """Resolve a bid folder in legacy NNNN - Name format."""
    (tmp_path / "2847 - Rio Tinto Boron").mkdir()

    with patch("app.services.bid_sync.ESTIMATING_ROOT", tmp_path):
        result = resolve_bid_folder("2847")
        assert result is not None
        assert result.name == "2847 - Rio Tinto Boron"


def test_resolve_bid_folder_not_found(tmp_path):
    """Return None when no matching folder exists."""
    (tmp_path / "25-10-2514 Kiewit Valar Atomics").mkdir()

    with patch("app.services.bid_sync.ESTIMATING_ROOT", tmp_path):
        result = resolve_bid_folder("9999")
        assert result is None


# ── categorize_bid_file ─────────────────────────────────────────


class TestCategorizeBidFile:

    def test_spec_in_folder(self):
        cat, add = categorize_bid_file("Specifications/section_01.pdf", "section_01.pdf")
        assert cat == "spec"
        assert add == 0

    def test_addendum_spec(self):
        cat, add = categorize_bid_file("Addendum 1/specs_rev1.pdf", "specs_rev1.pdf")
        assert cat == "spec"
        assert add == 1

    def test_addendum_drawing(self):
        cat, add = categorize_bid_file("Addendum 2/drawings_rev2.pdf", "drawings_rev2.pdf")
        assert cat == "drawing"
        assert add == 2

    def test_contract(self):
        cat, add = categorize_bid_file("Contract/agreement.pdf", "agreement.pdf")
        assert cat == "contract"
        assert add == 0

    def test_general_fallback(self):
        cat, add = categorize_bid_file("misc_file.xlsx", "misc_file.xlsx")
        assert cat == "general"
        assert add == 0

    def test_addendum_hash_number(self):
        cat, add = categorize_bid_file("Addendum #3/notice.pdf", "notice.pdf")
        assert cat == "addendum_package"
        assert add == 3

    def test_rfi_folder(self):
        cat, add = categorize_bid_file("RFIs/rfi_001.pdf", "rfi_001.pdf")
        assert cat == "rfi_clarification"
        assert add == 0

    def test_bond_form(self):
        cat, add = categorize_bid_file("Bonds/bid_bond.pdf", "bid_bond.pdf")
        assert cat == "bond_form"
        assert add == 0

    def test_insurance_cert(self):
        cat, add = categorize_bid_file("Insurance/certificate.pdf", "certificate.pdf")
        assert cat == "insurance"
        assert add == 0


# ── sync_bid_documents ──────────────────────────────────────────


def test_sync_bid_documents_new_files(tmp_path):
    """Sync discovers new files and creates document records."""
    # Create fake bid folder with files
    bid_folder = tmp_path / "9999 - Test Project"
    bid_folder.mkdir()
    specs = bid_folder / "Specifications"
    specs.mkdir()
    (specs / "spec_01.txt").write_text("This is spec content.")
    (bid_folder / "schedule.txt").write_text("Bid schedule data.")

    bid = create_test_bid(bid_number="9999")
    bid_id = bid["id"]

    # Link the folder
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE active_bids SET dropbox_folder_path = ? WHERE id = ?",
            (str(bid_folder), bid_id),
        )
        conn.commit()
    finally:
        conn.close()

    # Run sync
    result = sync_bid_documents(bid_id)

    assert result["new"] == 2
    assert result["updated"] == 0
    assert result["unchanged"] == 0
    assert result["removed"] == 0
    assert result["total"] == 2

    # Verify documents in DB
    conn = get_connection()
    try:
        docs = conn.execute(
            "SELECT * FROM bid_documents WHERE bid_id = ? ORDER BY filename",
            (bid_id,),
        ).fetchall()
        assert len(docs) == 2

        # Check spec was categorized
        spec_doc = [d for d in docs if d["filename"] == "spec_01.txt"][0]
        assert spec_doc["doc_category"] == "spec"
        assert spec_doc["sync_action"] == "new"
        assert spec_doc["dropbox_path"] is not None
        assert spec_doc["extraction_status"] == "complete"

        # Check bid sync status
        bid_row = conn.execute("SELECT * FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        assert bid_row["sync_status"] == "complete"
        assert bid_row["last_synced_at"] is not None
    finally:
        conn.close()


def test_sync_bid_documents_detects_changes(tmp_path):
    """Sync detects modified files on second run."""
    bid_folder = tmp_path / "9999 - Test Project"
    bid_folder.mkdir()
    test_file = bid_folder / "readme.txt"
    test_file.write_text("Version 1")

    bid = create_test_bid(bid_number="9999")
    bid_id = bid["id"]

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE active_bids SET dropbox_folder_path = ? WHERE id = ?",
            (str(bid_folder), bid_id),
        )
        conn.commit()
    finally:
        conn.close()

    # First sync
    result1 = sync_bid_documents(bid_id)
    assert result1["new"] == 1

    # Modify the file
    test_file.write_text("Version 2 — updated content")

    # Second sync
    result2 = sync_bid_documents(bid_id)
    assert result2["updated"] == 1
    assert result2["new"] == 0
    assert result2["unchanged"] == 0


def test_sync_bid_documents_detects_removals(tmp_path):
    """Sync detects deleted files and marks them removed."""
    bid_folder = tmp_path / "9999 - Test Project"
    bid_folder.mkdir()
    file_a = bid_folder / "file_a.txt"
    file_b = bid_folder / "file_b.txt"
    file_a.write_text("File A content")
    file_b.write_text("File B content")

    bid = create_test_bid(bid_number="9999")
    bid_id = bid["id"]

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE active_bids SET dropbox_folder_path = ? WHERE id = ?",
            (str(bid_folder), bid_id),
        )
        conn.commit()
    finally:
        conn.close()

    # First sync
    result1 = sync_bid_documents(bid_id)
    assert result1["new"] == 2

    # Delete one file
    file_b.unlink()

    # Second sync
    result2 = sync_bid_documents(bid_id)
    assert result2["unchanged"] == 1
    assert result2["removed"] == 1

    # Verify sync_action in DB
    conn = get_connection()
    try:
        removed_doc = conn.execute(
            "SELECT * FROM bid_documents WHERE bid_id = ? AND filename = 'file_b.txt'",
            (bid_id,),
        ).fetchone()
        assert removed_doc["sync_action"] == "removed"
    finally:
        conn.close()


def test_sync_idempotent(tmp_path):
    """Running sync twice with no changes produces unchanged status."""
    bid_folder = tmp_path / "9999 - Test"
    bid_folder.mkdir()
    (bid_folder / "test.txt").write_text("static content")

    bid = create_test_bid(bid_number="9999")
    bid_id = bid["id"]

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE active_bids SET dropbox_folder_path = ? WHERE id = ?",
            (str(bid_folder), bid_id),
        )
        conn.commit()
    finally:
        conn.close()

    sync_bid_documents(bid_id)
    result = sync_bid_documents(bid_id)
    assert result["new"] == 0
    assert result["unchanged"] == 1
    assert result["updated"] == 0
    assert result["removed"] == 0


# ── API Endpoint Tests ──────────────────────────────────────────


def test_link_folder_endpoint(tmp_path):
    """POST /bids/{id}/link-folder resolves folder."""
    (tmp_path / "9999 - Link Test").mkdir()

    bid = create_test_bid(bid_number="9999")

    with patch("app.services.bid_sync.ESTIMATING_ROOT", tmp_path), \
         patch("app.api.bidding.resolve_bid_folder", wraps=resolve_bid_folder) as mock_resolve:
        # Patch at the service level so it uses tmp_path
        mock_resolve.side_effect = lambda n: resolve_bid_folder.__wrapped__(n) if hasattr(resolve_bid_folder, '__wrapped__') else resolve_bid_folder(n)

        # Use direct service call via API
        with patch("app.api.bidding.resolve_bid_folder") as api_mock:
            api_mock.return_value = tmp_path / "9999 - Link Test"
            res = client.post(f"/api/bidding/bids/{bid['id']}/link-folder", json={})

    assert res.status_code == 200
    data = res.json()
    assert data["linked"] is True
    assert "9999 - Link Test" in data["folder_path"]


def test_link_folder_not_found():
    """POST /bids/{id}/link-folder returns linked=false when no match."""
    bid = create_test_bid(bid_number="0000")

    with patch("app.api.bidding.resolve_bid_folder", return_value=None):
        res = client.post(f"/api/bidding/bids/{bid['id']}/link-folder", json={})

    assert res.status_code == 200
    data = res.json()
    assert data["linked"] is False


def test_sync_endpoint(tmp_path):
    """POST /bids/{id}/sync runs sync and returns results."""
    bid_folder = tmp_path / "9999 - Sync API"
    bid_folder.mkdir()
    (bid_folder / "doc.txt").write_text("Hello world")

    bid = create_test_bid(bid_number="9999")
    bid_id = bid["id"]

    # Link the folder
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE active_bids SET dropbox_folder_path = ? WHERE id = ?",
            (str(bid_folder), bid_id),
        )
        conn.commit()
    finally:
        conn.close()

    res = client.post(f"/api/bidding/bids/{bid_id}/sync")
    assert res.status_code == 200
    data = res.json()
    assert data["new"] == 1
    assert data["total"] == 1


def test_sync_endpoint_no_folder():
    """POST /bids/{id}/sync returns 400 if no folder linked."""
    bid = create_test_bid(bid_number="0000")
    res = client.post(f"/api/bidding/bids/{bid['id']}/sync")
    assert res.status_code == 400


def test_sync_status_endpoint(tmp_path):
    """GET /bids/{id}/sync-status returns status and counts."""
    bid_folder = tmp_path / "9999 - Status Test"
    bid_folder.mkdir()
    (bid_folder / "a.txt").write_text("content a")
    (bid_folder / "b.txt").write_text("content b")

    bid = create_test_bid(bid_number="9999")
    bid_id = bid["id"]

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE active_bids SET dropbox_folder_path = ? WHERE id = ?",
            (str(bid_folder), bid_id),
        )
        conn.commit()
    finally:
        conn.close()

    # Sync first
    client.post(f"/api/bidding/bids/{bid_id}/sync")

    # Check status
    res = client.get(f"/api/bidding/bids/{bid_id}/sync-status")
    assert res.status_code == 200
    data = res.json()
    assert data["sync_status"] == "complete"
    assert data["last_synced_at"] is not None
    assert data["document_counts"]["new"] == 2
    assert data["document_counts"]["total"] == 2


def test_create_bid_auto_links_folder(tmp_path):
    """Creating a bid with bid_number auto-resolves Dropbox folder."""
    (tmp_path / "8888 - Auto Link Test").mkdir()

    with patch("app.api.bidding.resolve_bid_folder") as mock:
        mock.return_value = tmp_path / "8888 - Auto Link Test"
        res = client.post("/api/bidding/bids", json={
            "bid_name": "Auto Link Bid",
            "bid_number": "8888",
        })

    assert res.status_code == 200
    bid = res.json()
    _test_bid_ids.append(bid["id"])
    assert bid["dropbox_folder_path"] is not None
    assert "8888" in bid["dropbox_folder_path"]


def test_documents_include_sync_fields(tmp_path):
    """GET /bids/{id}/documents includes dropbox_path and sync_action."""
    bid_folder = tmp_path / "9999 - Fields Test"
    bid_folder.mkdir()
    (bid_folder / "test.txt").write_text("content")

    bid = create_test_bid(bid_number="9999")
    bid_id = bid["id"]

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE active_bids SET dropbox_folder_path = ? WHERE id = ?",
            (str(bid_folder), bid_id),
        )
        conn.commit()
    finally:
        conn.close()

    client.post(f"/api/bidding/bids/{bid_id}/sync")

    res = client.get(f"/api/bidding/bids/{bid_id}/documents")
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) == 1
    assert "dropbox_path" in docs[0]
    assert docs[0]["sync_action"] == "new"
