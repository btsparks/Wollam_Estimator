"""Tests for Bidding Platform — Bid CRUD, Documents, SOV, Pricing Groups."""

import io
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_connection

client = TestClient(app)

# Track IDs created during tests so we can clean up
_test_bid_ids = []


@pytest.fixture(autouse=True)
def cleanup_test_bids():
    """Clean up any bids created during tests so they don't pollute the real DB."""
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


# ── Helpers ──────────────────────────────────────────────────────

def create_test_bid(**kwargs):
    """Create a bid and return it."""
    data = {
        "bid_name": "Test Bid Project",
        "bid_number": "TB-001",
        "owner": "Test Owner",
        "bid_date": "2026-05-01",
        "location": "Salt Lake City, UT",
        "status": "active",
    }
    data.update(kwargs)
    res = client.post("/api/bidding/bids", json=data)
    assert res.status_code == 200
    bid = res.json()
    _test_bid_ids.append(bid["id"])
    return bid


# ── Bid CRUD ─────────────────────────────────────────────────────

class TestBidCRUD:

    def test_create_bid(self):
        bid = create_test_bid()
        assert bid["bid_name"] == "Test Bid Project"
        assert bid["bid_number"] == "TB-001"
        assert bid["owner"] == "Test Owner"
        assert bid["status"] == "active"
        assert bid["id"] is not None

    def test_create_bid_minimal(self):
        bid = create_test_bid(bid_name="Minimal Bid", bid_number=None, owner=None, bid_date=None, location=None)
        assert bid["bid_name"] == "Minimal Bid"
        assert bid["status"] == "active"

    def test_list_bids(self):
        create_test_bid(bid_name="List Test A")
        create_test_bid(bid_name="List Test B")
        res = client.get("/api/bidding/bids")
        assert res.status_code == 200
        bids = res.json()
        assert len(bids) >= 2
        # Check doc_count and sov_count are present
        assert "doc_count" in bids[0]
        assert "sov_count" in bids[0]

    def test_list_bids_filter_status(self):
        create_test_bid(bid_name="Active Bid", status="active")
        create_test_bid(bid_name="Submitted Bid", status="submitted")
        res = client.get("/api/bidding/bids?status=submitted")
        assert res.status_code == 200
        for b in res.json():
            assert b["status"] == "submitted"

    def test_get_bid(self):
        bid = create_test_bid()
        res = client.get(f"/api/bidding/bids/{bid['id']}")
        assert res.status_code == 200
        detail = res.json()
        assert detail["bid_name"] == "Test Bid Project"
        assert "doc_count" in detail
        assert "sov_count" in detail
        assert "group_count" in detail

    def test_get_bid_not_found(self):
        res = client.get("/api/bidding/bids/99999")
        assert res.status_code == 404

    def test_update_bid(self):
        bid = create_test_bid()
        res = client.put(f"/api/bidding/bids/{bid['id']}", json={
            "bid_name": "Updated Name",
            "status": "submitted",
            "contact_name": "John Doe",
        })
        assert res.status_code == 200
        updated = res.json()
        assert updated["bid_name"] == "Updated Name"
        assert updated["status"] == "submitted"
        assert updated["contact_name"] == "John Doe"

    def test_update_bid_new_fields(self):
        bid = create_test_bid()
        res = client.put(f"/api/bidding/bids/{bid['id']}", json={
            "bid_due_time": "14:00",
            "description": "A big project",
            "contact_email": "john@example.com",
        })
        assert res.status_code == 200
        updated = res.json()
        assert updated["bid_due_time"] == "14:00"
        assert updated["description"] == "A big project"
        assert updated["contact_email"] == "john@example.com"

    def test_delete_bid(self):
        bid = create_test_bid()
        res = client.delete(f"/api/bidding/bids/{bid['id']}")
        assert res.status_code == 200
        assert res.json()["deleted"] is True

        # Verify gone
        res = client.get(f"/api/bidding/bids/{bid['id']}")
        assert res.status_code == 404


# ── Document Upload ──────────────────────────────────────────────

class TestDocuments:

    def test_upload_document(self):
        bid = create_test_bid()
        content = b"Test document content for extraction"
        res = client.post(
            f"/api/bidding/bids/{bid['id']}/documents",
            files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
            data={"addendum_number": "0", "doc_category": "general"},
        )
        assert res.status_code == 200
        doc = res.json()
        assert doc["filename"] == "test.txt"
        assert doc["file_type"] == ".txt"
        assert doc["doc_category"] == "general"
        assert doc["addendum_number"] == 0
        assert doc["extraction_status"] == "complete"
        # extracted_text should NOT be in response
        assert "extracted_text" not in doc

    def test_upload_with_metadata(self):
        bid = create_test_bid()
        res = client.post(
            f"/api/bidding/bids/{bid['id']}/documents",
            files={"file": ("addendum1.txt", io.BytesIO(b"Addendum content"), "text/plain")},
            data={"addendum_number": "1", "doc_category": "addendum_package", "date_received": "2026-04-01"},
        )
        assert res.status_code == 200
        doc = res.json()
        assert doc["addendum_number"] == 1
        assert doc["doc_category"] == "addendum_package"
        assert doc["date_received"] == "2026-04-01"

    def test_upload_unsupported_type(self):
        bid = create_test_bid()
        res = client.post(
            f"/api/bidding/bids/{bid['id']}/documents",
            files={"file": ("test.exe", io.BytesIO(b"bad"), "application/octet-stream")},
            data={"doc_category": "general"},
        )
        assert res.status_code == 400

    def test_list_documents(self):
        bid = create_test_bid()
        # Upload 2 docs
        client.post(
            f"/api/bidding/bids/{bid['id']}/documents",
            files={"file": ("doc1.txt", io.BytesIO(b"content1"), "text/plain")},
            data={"addendum_number": "0", "doc_category": "spec"},
        )
        client.post(
            f"/api/bidding/bids/{bid['id']}/documents",
            files={"file": ("doc2.txt", io.BytesIO(b"content2"), "text/plain")},
            data={"addendum_number": "1", "doc_category": "drawing"},
        )

        res = client.get(f"/api/bidding/bids/{bid['id']}/documents")
        assert res.status_code == 200
        docs = res.json()
        assert len(docs) >= 2

    def test_list_documents_filter(self):
        bid = create_test_bid()
        client.post(
            f"/api/bidding/bids/{bid['id']}/documents",
            files={"file": ("spec.txt", io.BytesIO(b"spec"), "text/plain")},
            data={"addendum_number": "0", "doc_category": "spec"},
        )
        client.post(
            f"/api/bidding/bids/{bid['id']}/documents",
            files={"file": ("drawing.txt", io.BytesIO(b"draw"), "text/plain")},
            data={"addendum_number": "0", "doc_category": "drawing"},
        )

        res = client.get(f"/api/bidding/bids/{bid['id']}/documents?doc_category=spec")
        assert res.status_code == 200
        for doc in res.json():
            assert doc["doc_category"] == "spec"

    def test_get_document_with_text(self):
        bid = create_test_bid()
        upload = client.post(
            f"/api/bidding/bids/{bid['id']}/documents",
            files={"file": ("detail.txt", io.BytesIO(b"Full text here"), "text/plain")},
            data={"doc_category": "general"},
        )
        doc_id = upload.json()["id"]

        res = client.get(f"/api/bidding/documents/{doc_id}")
        assert res.status_code == 200
        doc = res.json()
        assert "extracted_text" in doc
        assert "Full text here" in doc["extracted_text"]

    def test_update_document(self):
        bid = create_test_bid()
        upload = client.post(
            f"/api/bidding/bids/{bid['id']}/documents",
            files={"file": ("update.txt", io.BytesIO(b"text"), "text/plain")},
            data={"doc_category": "general"},
        )
        doc_id = upload.json()["id"]

        res = client.put(f"/api/bidding/documents/{doc_id}", json={
            "doc_category": "spec",
            "notes": "Important spec document",
        })
        assert res.status_code == 200
        assert res.json()["doc_category"] == "spec"
        assert res.json()["notes"] == "Important spec document"

    def test_delete_document(self):
        bid = create_test_bid()
        upload = client.post(
            f"/api/bidding/bids/{bid['id']}/documents",
            files={"file": ("delete.txt", io.BytesIO(b"del"), "text/plain")},
            data={"doc_category": "general"},
        )
        doc_id = upload.json()["id"]

        res = client.delete(f"/api/bidding/documents/{doc_id}")
        assert res.status_code == 200
        assert res.json()["deleted"] is True

        res = client.get(f"/api/bidding/documents/{doc_id}")
        assert res.status_code == 404


# ── SOV Items ────────────────────────────────────────────────────

class TestSOV:

    def test_add_sov_item(self):
        bid = create_test_bid()
        res = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={
            "item_number": "1",
            "description": "Mobilization",
            "unit": "LS",
            "quantity": 1.0,
        })
        assert res.status_code == 200
        item = res.json()
        assert item["description"] == "Mobilization"
        assert item["unit"] == "LS"
        assert item["quantity"] == 1.0

    def test_list_sov_items(self):
        bid = create_test_bid()
        client.post(f"/api/bidding/bids/{bid['id']}/sov", json={
            "item_number": "1", "description": "Item A", "unit": "LS", "quantity": 1,
        })
        client.post(f"/api/bidding/bids/{bid['id']}/sov", json={
            "item_number": "2", "description": "Item B", "unit": "CY", "quantity": 500,
        })

        res = client.get(f"/api/bidding/bids/{bid['id']}/sov")
        assert res.status_code == 200
        items = res.json()
        assert len(items) >= 2
        # Should be ordered by sort_order
        assert items[0]["sort_order"] <= items[1]["sort_order"]

    def test_update_sov_item(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={
            "description": "Original", "unit": "LF",
        }).json()

        res = client.put(f"/api/bidding/sov/{item['id']}", json={
            "description": "Updated",
            "quantity": 100.5,
        })
        assert res.status_code == 200
        assert res.json()["description"] == "Updated"
        assert res.json()["quantity"] == 100.5

    def test_delete_sov_item(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={
            "description": "To Delete",
        }).json()

        res = client.delete(f"/api/bidding/sov/{item['id']}")
        assert res.status_code == 200
        assert res.json()["deleted"] is True

    def test_reorder_sov(self):
        bid = create_test_bid()
        i1 = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "First"}).json()
        i2 = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Second"}).json()
        i3 = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Third"}).json()

        # Reverse order
        res = client.put("/api/bidding/sov/reorder", json={
            "item_ids": [i3["id"], i2["id"], i1["id"]],
        })
        assert res.status_code == 200

        items = client.get(f"/api/bidding/bids/{bid['id']}/sov").json()
        descs = [i["description"] for i in items]
        assert descs[0] == "Third"
        assert descs[1] == "Second"
        assert descs[2] == "First"

    def test_sov_confirm(self):
        bid = create_test_bid()
        preview_items = [
            {"item_number": "1", "description": "Mob/Demob", "unit": "LS", "quantity": 1},
            {"item_number": "2", "description": "Excavation", "unit": "CY", "quantity": 5000},
        ]

        res = client.post(f"/api/bidding/bids/{bid['id']}/sov/confirm", json={
            "items": preview_items,
        })
        assert res.status_code == 200
        assert res.json()["saved"] == 2

        items = client.get(f"/api/bidding/bids/{bid['id']}/sov").json()
        assert len(items) >= 2


# ── SOV AI Parse (mocked) ───────────────────────────────────────

class TestSOVParse:

    @patch("app.services.sov_parser.anthropic.Anthropic")
    def test_sov_upload_parse(self, mock_anthropic_cls):
        """Test SOV upload with mocked Claude API."""
        # Mock the Claude response
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps([
            {"item_number": "1", "description": "Mobilization", "unit": "LS", "quantity": 1},
            {"item_number": "2", "description": "Grading", "unit": "CY", "quantity": 2500},
        ]))]
        mock_client.messages.create.return_value = mock_response

        bid = create_test_bid()

        csv_content = b"Item,Description,Unit,Qty\n1,Mobilization,LS,1\n2,Grading,CY,2500"
        res = client.post(
            f"/api/bidding/bids/{bid['id']}/sov/upload",
            files={"file": ("schedule.csv", io.BytesIO(csv_content), "text/csv")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["count"] == 2
        assert data["items"][0]["description"] == "Mobilization"
        assert data["items"][1]["quantity"] == 2500


# ── Pricing Groups ───────────────────────────────────────────────

class TestPricingGroups:

    def test_create_group(self):
        bid = create_test_bid()
        res = client.post(f"/api/bidding/bids/{bid['id']}/groups", json={
            "name": "Earthwork",
            "description": "All earthwork items",
        })
        assert res.status_code == 200
        group = res.json()
        assert group["name"] == "Earthwork"
        assert group["bid_id"] == bid["id"]

    def test_list_groups(self):
        bid = create_test_bid()
        client.post(f"/api/bidding/bids/{bid['id']}/groups", json={"name": "Group A"})
        client.post(f"/api/bidding/bids/{bid['id']}/groups", json={"name": "Group B"})

        res = client.get(f"/api/bidding/bids/{bid['id']}/groups")
        assert res.status_code == 200
        groups = res.json()
        assert len(groups) >= 2
        assert "item_count" in groups[0]

    def test_update_group(self):
        bid = create_test_bid()
        group = client.post(f"/api/bidding/bids/{bid['id']}/groups", json={"name": "Old Name"}).json()

        res = client.put(f"/api/bidding/groups/{group['id']}", json={"name": "New Name"})
        assert res.status_code == 200
        assert res.json()["name"] == "New Name"

    def test_delete_group_ungroups_items(self):
        bid = create_test_bid()
        group = client.post(f"/api/bidding/bids/{bid['id']}/groups", json={"name": "ToDelete"}).json()

        # Create item assigned to group
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={
            "description": "Grouped Item",
            "pricing_group_id": group["id"],
        }).json()

        # Delete group
        res = client.delete(f"/api/bidding/groups/{group['id']}")
        assert res.status_code == 200

        # Item should be ungrouped
        items = client.get(f"/api/bidding/bids/{bid['id']}/sov").json()
        target = next(i for i in items if i["id"] == item["id"])
        assert target["pricing_group_id"] is None

    def test_assign_items(self):
        bid = create_test_bid()
        group = client.post(f"/api/bidding/bids/{bid['id']}/groups", json={"name": "Assign Group"}).json()
        i1 = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "A"}).json()
        i2 = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "B"}).json()

        res = client.post(f"/api/bidding/groups/{group['id']}/assign", json={
            "item_ids": [i1["id"], i2["id"]],
        })
        assert res.status_code == 200
        assert res.json()["assigned"] == 2

        # Verify
        items = client.get(f"/api/bidding/bids/{bid['id']}/sov").json()
        for item in items:
            if item["id"] in [i1["id"], i2["id"]]:
                assert item["pricing_group_id"] == group["id"]

    def test_unassign_items(self):
        bid = create_test_bid()
        group = client.post(f"/api/bidding/bids/{bid['id']}/groups", json={"name": "Unassign Group"}).json()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "C"}).json()

        # Assign then unassign
        client.post(f"/api/bidding/groups/{group['id']}/assign", json={"item_ids": [item["id"]]})
        res = client.post(f"/api/bidding/groups/{group['id']}/unassign", json={"item_ids": [item["id"]]})
        assert res.status_code == 200

        items = client.get(f"/api/bidding/bids/{bid['id']}/sov").json()
        target = next(i for i in items if i["id"] == item["id"])
        assert target["pricing_group_id"] is None
