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
                conn.execute("DELETE FROM procurement_solicitation WHERE procurement_item_id IN (SELECT id FROM procurement_item WHERE bid_id = ?)", (bid_id,))
                conn.execute("DELETE FROM procurement_sov_link WHERE procurement_item_id IN (SELECT id FROM procurement_item WHERE bid_id = ?)", (bid_id,))
                conn.execute("DELETE FROM procurement_item WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM rfi_log WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM drawing_register WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM spec_register WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM bid_document_chunks WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM bid_documents WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM holding_distribution WHERE holding_item_id IN (SELECT id FROM bid_sov_item WHERE bid_id = ?)", (bid_id,))
                conn.execute("DELETE FROM sov_item_intelligence WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM bid_sov_item WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM bid_section WHERE bid_id = ?", (bid_id,))
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


# ── Section CRUD ────────────────────────────────────────────────

class TestSections:

    def test_create_section(self):
        bid = create_test_bid()
        res = client.post(f"/api/bidding/bids/{bid['id']}/sections", json={"name": "Division 3 — Concrete"})
        assert res.status_code == 200
        section = res.json()
        assert section["name"] == "Division 3 — Concrete"
        assert section["bid_id"] == bid["id"]
        assert section["collapsed"] == 0

    def test_list_sections_with_item_count(self):
        bid = create_test_bid()
        sec = client.post(f"/api/bidding/bids/{bid['id']}/sections", json={"name": "Section A"}).json()
        client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Item 1", "section_id": sec["id"]})

        res = client.get(f"/api/bidding/bids/{bid['id']}/sections")
        assert res.status_code == 200
        sections = res.json()
        assert len(sections) == 1
        assert sections[0]["item_count"] == 1

    def test_update_section(self):
        bid = create_test_bid()
        sec = client.post(f"/api/bidding/bids/{bid['id']}/sections", json={"name": "Old Name"}).json()

        res = client.put(f"/api/bidding/sections/{sec['id']}", json={"name": "New Name"})
        assert res.status_code == 200
        assert res.json()["name"] == "New Name"

    def test_delete_section_nullifies_items(self):
        bid = create_test_bid()
        sec = client.post(f"/api/bidding/bids/{bid['id']}/sections", json={"name": "To Delete"}).json()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Item 1", "section_id": sec["id"]}).json()

        res = client.delete(f"/api/bidding/sections/{sec['id']}")
        assert res.status_code == 200

        items = client.get(f"/api/bidding/bids/{bid['id']}/sov").json()
        target = next(i for i in items if i["id"] == item["id"])
        assert target["section_id"] is None

    def test_assign_items_to_section(self):
        bid = create_test_bid()
        sec = client.post(f"/api/bidding/bids/{bid['id']}/sections", json={"name": "Section A"}).json()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Item 1"}).json()

        res = client.post(f"/api/bidding/sections/{sec['id']}/assign", json={"item_ids": [item["id"]]})
        assert res.status_code == 200
        assert res.json()["assigned"] == 1

        items = client.get(f"/api/bidding/bids/{bid['id']}/sov").json()
        target = next(i for i in items if i["id"] == item["id"])
        assert target["section_id"] == sec["id"]
        assert target["section_name"] == "Section A"


# ── HCSS Number ─────────────────────────────────────────────────

class TestHCSSNumber:

    def test_create_sov_item_with_hcss_number(self):
        bid = create_test_bid()
        res = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={
            "description": "Concrete Work",
            "hcss_number": "3.01.001",
        })
        assert res.status_code == 200
        item = res.json()
        assert item["hcss_number"] == "3.01.001"

    def test_update_hcss_number(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Test"}).json()

        res = client.put(f"/api/bidding/sov/{item['id']}", json={"hcss_number": "5.01.002"})
        assert res.status_code == 200
        assert res.json()["hcss_number"] == "5.01.002"

    def test_clear_hcss_number(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={
            "description": "Test", "hcss_number": "3.01",
        }).json()

        res = client.put(f"/api/bidding/sov/{item['id']}", json={"hcss_number": None})
        assert res.status_code == 200
        assert res.json()["hcss_number"] is None

    def test_hcss_number_in_sov_list(self):
        bid = create_test_bid()
        client.post(f"/api/bidding/bids/{bid['id']}/sov", json={
            "description": "Item A", "hcss_number": "1.01",
        })
        items = client.get(f"/api/bidding/bids/{bid['id']}/sov").json()
        assert items[0]["hcss_number"] == "1.01"


# ── Work Type Bulk Assignment ────────────────────────────────────

class TestWorkType:

    def test_set_work_type_single(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Test"}).json()
        assert item["work_type"] == "undecided"

        res = client.put(f"/api/bidding/sov/{item['id']}", json={"work_type": "self_perform"})
        assert res.status_code == 200
        assert res.json()["work_type"] == "self_perform"

    def test_bulk_set_work_type(self):
        bid = create_test_bid()
        item1 = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "A"}).json()
        item2 = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "B"}).json()

        res = client.post(f"/api/bidding/bids/{bid['id']}/sov/set-work-type", json={
            "item_ids": [item1["id"], item2["id"]],
            "work_type": "subcontract",
        })
        assert res.status_code == 200
        assert res.json()["updated"] == 2

        items = client.get(f"/api/bidding/bids/{bid['id']}/sov").json()
        for item in items:
            assert item["work_type"] == "subcontract"

    def test_bulk_set_work_type_invalid(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "A"}).json()

        res = client.post(f"/api/bidding/bids/{bid['id']}/sov/set-work-type", json={
            "item_ids": [item["id"]],
            "work_type": "invalid_type",
        })
        assert res.status_code == 400


# ── Holding Account Distribution ─────────────────────────────────

class TestHoldingAccounts:

    def test_make_holding_account(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Equipment"}).json()

        res = client.post(f"/api/bidding/bids/{bid['id']}/sov/{item['id']}/make-holding", json={
            "holding_description": "crane, man lifts, forklift",
        })
        assert res.status_code == 200
        result = res.json()
        assert result["is_holding_account"] == 1
        assert result["holding_description"] == "crane, man lifts, forklift"

    def test_unmake_holding_account(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Equipment"}).json()
        client.post(f"/api/bidding/bids/{bid['id']}/sov/{item['id']}/make-holding", json={
            "holding_description": "crane",
        })

        res = client.delete(f"/api/bidding/bids/{bid['id']}/sov/{item['id']}/make-holding")
        assert res.status_code == 200
        result = res.json()
        assert result["is_holding_account"] == 0
        assert result["holding_description"] is None

    def test_set_distribution_targets(self):
        bid = create_test_bid()
        holding = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Equipment"}).json()
        target1 = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Concrete Work"}).json()
        target2 = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Steel Work"}).json()

        client.post(f"/api/bidding/bids/{bid['id']}/sov/{holding['id']}/make-holding", json={
            "holding_description": "shared equipment",
        })

        res = client.post(f"/api/bidding/bids/{bid['id']}/sov/{holding['id']}/distribute", json={
            "target_item_ids": [target1["id"], target2["id"]],
        })
        assert res.status_code == 200
        assert res.json()["target_count"] == 2

        dist = client.get(f"/api/bidding/bids/{bid['id']}/sov/{holding['id']}/distribution").json()
        assert len(dist) == 2
        target_ids = {d["target_item_id"] for d in dist}
        assert target1["id"] in target_ids
        assert target2["id"] in target_ids

    def test_list_holding_accounts(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Equipment"}).json()
        client.post(f"/api/bidding/bids/{bid['id']}/sov/{item['id']}/make-holding", json={
            "holding_description": "test",
        })

        res = client.get(f"/api/bidding/bids/{bid['id']}/holding-accounts")
        assert res.status_code == 200
        holdings = res.json()
        assert len(holdings) == 1
        assert holdings[0]["is_holding_account"] == 1

    def test_distribute_non_holding_fails(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Regular"}).json()

        res = client.post(f"/api/bidding/bids/{bid['id']}/sov/{item['id']}/distribute", json={
            "target_item_ids": [],
        })
        assert res.status_code == 404


# ── Out-of-Scope Agent Runner Filtering ──────────────────────────

class TestOutOfScopeFiltering:

    def test_agent_runner_loads_only_in_scope(self):
        """Verify _load_bid_context filters out-of-scope items."""
        bid = create_test_bid()
        client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "In Scope Item"})
        out_scope = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Out Scope Item"}).json()

        # Mark one item out of scope
        client.post(f"/api/bidding/bids/{bid['id']}/sov/set-scope", json={
            "item_ids": [out_scope["id"]], "in_scope": 0,
        })

        from app.agents.runner import _load_bid_context
        context = _load_bid_context(bid["id"])
        descriptions = [i["description"] for i in context["sov_items"]]
        assert "In Scope Item" in descriptions
        assert "Out Scope Item" not in descriptions

    def test_agent_context_includes_work_type(self):
        """Verify _load_bid_context includes work_type field."""
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Test Item"}).json()
        client.put(f"/api/bidding/sov/{item['id']}", json={"work_type": "self_perform"})

        from app.agents.runner import _load_bid_context
        context = _load_bid_context(bid["id"])
        assert context["sov_items"][0]["work_type"] == "self_perform"


# ══════════════════════════════════════════════════════════════
# PART B TESTS — Documents, Registers, RFI Log
# ══════════════════════════════════════════════════════════════


class TestDocumentTree:

    def test_empty_tree(self):
        bid = create_test_bid()
        res = client.get(f"/api/bidding/bids/{bid['id']}/documents/tree")
        assert res.status_code == 200
        data = res.json()
        assert data["tree"] == []
        assert data["stats"]["total_documents"] == 0

    def test_tree_with_documents(self):
        """Upload a doc and verify it appears in the tree."""
        bid = create_test_bid()
        # Upload a test document
        from io import BytesIO
        file_content = b"test document content for tree"
        res = client.post(
            f"/api/bidding/bids/{bid['id']}/documents",
            files={"file": ("test_drawing.pdf", BytesIO(file_content), "application/pdf")},
            data={"addendum_number": "1", "doc_category": "drawing"},
        )
        assert res.status_code == 200

        res = client.get(f"/api/bidding/bids/{bid['id']}/documents/tree")
        assert res.status_code == 200
        data = res.json()
        assert data["stats"]["total_documents"] == 1
        assert len(data["tree"]) >= 1
        # Find the document in the tree
        found = False
        for folder in data["tree"]:
            for child in folder.get("children", []):
                if child.get("filename") == "test_drawing.pdf":
                    found = True
                    assert child["doc_category"] == "drawing"
                    assert child["addendum_number"] == 1
        assert found

    def test_tree_stats(self):
        """Verify stats count documents correctly."""
        bid = create_test_bid()
        from io import BytesIO
        for i in range(3):
            client.post(
                f"/api/bidding/bids/{bid['id']}/documents",
                files={"file": (f"doc_{i}.txt", BytesIO(b"content"), "text/plain")},
                data={"doc_category": "general"},
            )
        res = client.get(f"/api/bidding/bids/{bid['id']}/documents/tree")
        assert res.json()["stats"]["total_documents"] == 3


class TestDrawingRegister:

    def test_list_empty_register(self):
        bid = create_test_bid()
        res = client.get(f"/api/bidding/bids/{bid['id']}/drawing-register")
        assert res.status_code == 200
        assert res.json() == []

    def test_update_drawing_register_entry(self):
        bid = create_test_bid()
        # Insert a test entry directly
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO drawing_register (bid_id, drawing_number, title, discipline, ai_generated) VALUES (?, ?, ?, ?, 1)",
                (bid["id"], "C-101", "Site Plan", "civil"),
            )
            conn.commit()
            reg_id = conn.execute("SELECT id FROM drawing_register WHERE bid_id = ? AND drawing_number = 'C-101'", (bid["id"],)).fetchone()["id"]
        finally:
            conn.close()

        res = client.put(f"/api/bidding/drawing-register/{reg_id}", json={"title": "Updated Site Plan"})
        assert res.status_code == 200
        assert res.json()["title"] == "Updated Site Plan"
        assert res.json()["ai_generated"] == 0  # manual override

    def test_export_drawing_register(self):
        bid = create_test_bid()
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO drawing_register (bid_id, drawing_number, title, discipline) VALUES (?, ?, ?, ?)",
                (bid["id"], "S-201", "Foundation Plan", "structural"),
            )
            conn.commit()
        finally:
            conn.close()

        res = client.get(f"/api/bidding/bids/{bid['id']}/drawing-register/export")
        assert res.status_code == 200
        # Should return either xlsx or csv
        assert "spreadsheet" in res.headers.get("content-type", "") or "csv" in res.headers.get("content-type", "")


class TestSpecRegister:

    def test_list_empty_register(self):
        bid = create_test_bid()
        res = client.get(f"/api/bidding/bids/{bid['id']}/spec-register")
        assert res.status_code == 200
        assert res.json() == []

    def test_update_spec_register_entry(self):
        bid = create_test_bid()
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO spec_register (bid_id, spec_section, title, division) VALUES (?, ?, ?, ?)",
                (bid["id"], "03300", "Cast-in-Place Concrete", "Division 03"),
            )
            conn.commit()
            reg_id = conn.execute("SELECT id FROM spec_register WHERE bid_id = ? AND spec_section = '03300'", (bid["id"],)).fetchone()["id"]
        finally:
            conn.close()

        res = client.put(f"/api/bidding/spec-register/{reg_id}", json={"title": "Concrete Work Updated"})
        assert res.status_code == 200
        assert res.json()["title"] == "Concrete Work Updated"

    def test_export_spec_register(self):
        bid = create_test_bid()
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO spec_register (bid_id, spec_section, title, division) VALUES (?, ?, ?, ?)",
                (bid["id"], "02710", "Erosion Control", "Division 02"),
            )
            conn.commit()
        finally:
            conn.close()

        res = client.get(f"/api/bidding/bids/{bid['id']}/spec-register/export")
        assert res.status_code == 200


class TestRFILog:

    def test_list_empty_rfi_log(self):
        bid = create_test_bid()
        res = client.get(f"/api/bidding/bids/{bid['id']}/rfi-log")
        assert res.status_code == 200
        assert res.json() == []

    def test_add_rfi_entry(self):
        bid = create_test_bid()
        res = client.post(f"/api/bidding/bids/{bid['id']}/rfi-log", json={
            "rfi_number": "RFI-001",
            "question": "What concrete strength is required?",
            "response": "4000 PSI per Section 03300",
            "status": "answered",
        })
        assert res.status_code == 200
        entry = res.json()
        assert entry["rfi_number"] == "RFI-001"
        assert entry["question"] == "What concrete strength is required?"
        assert entry["response"] == "4000 PSI per Section 03300"
        assert entry["ai_generated"] == 0

    def test_update_rfi_entry(self):
        bid = create_test_bid()
        entry = client.post(f"/api/bidding/bids/{bid['id']}/rfi-log", json={
            "question": "Thickness of slab?",
        }).json()

        res = client.put(f"/api/bidding/rfi-log/{entry['id']}", json={
            "response": "6 inches per drawing S-101",
            "status": "answered",
        })
        assert res.status_code == 200
        assert res.json()["response"] == "6 inches per drawing S-101"

    def test_delete_rfi_entry(self):
        bid = create_test_bid()
        entry = client.post(f"/api/bidding/bids/{bid['id']}/rfi-log", json={
            "question": "To be deleted",
        }).json()

        res = client.delete(f"/api/bidding/rfi-log/{entry['id']}")
        assert res.status_code == 200

        remaining = client.get(f"/api/bidding/bids/{bid['id']}/rfi-log").json()
        assert len(remaining) == 0

    def test_rfi_log_ordering(self):
        bid = create_test_bid()
        client.post(f"/api/bidding/bids/{bid['id']}/rfi-log", json={
            "rfi_number": "RFI-002", "question": "Q2", "addendum_number": 2,
        })
        client.post(f"/api/bidding/bids/{bid['id']}/rfi-log", json={
            "rfi_number": "RFI-001", "question": "Q1", "addendum_number": 1,
        })

        rfis = client.get(f"/api/bidding/bids/{bid['id']}/rfi-log").json()
        assert rfis[0]["rfi_number"] == "RFI-001"
        assert rfis[1]["rfi_number"] == "RFI-002"

    def test_export_rfi_log(self):
        bid = create_test_bid()
        client.post(f"/api/bidding/bids/{bid['id']}/rfi-log", json={
            "rfi_number": "RFI-001", "question": "Test question", "response": "Test answer",
        })
        res = client.get(f"/api/bidding/bids/{bid['id']}/rfi-log/export")
        assert res.status_code == 200

    def test_delete_rfi_not_found(self):
        res = client.delete("/api/bidding/rfi-log/99999")
        assert res.status_code == 404


# ══════════════════════════════════════════════════════════════
# PART C TESTS — Intelligence, Setup Progress, Refresh Pipeline
# ══════════════════════════════════════════════════════════════


class TestSetupProgress:

    def test_empty_bid_progress(self):
        bid = create_test_bid()
        res = client.get(f"/api/bidding/bids/{bid['id']}/setup-progress")
        assert res.status_code == 200
        data = res.json()
        assert data["documents_synced"] is False
        assert data["sov_defined"] is False
        assert data["scope_designated"] is False
        assert data["intelligence_analyzed"] is False
        assert data["intelligence_mapped"] is False

    def test_progress_with_docs_and_sov(self):
        bid = create_test_bid()
        # Add a document
        from io import BytesIO
        client.post(
            f"/api/bidding/bids/{bid['id']}/documents",
            files={"file": ("test.txt", BytesIO(b"content"), "text/plain")},
            data={"doc_category": "general"},
        )
        # Add an SOV item
        client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Test item"})

        res = client.get(f"/api/bidding/bids/{bid['id']}/setup-progress")
        data = res.json()
        assert data["documents_synced"] is True
        assert data["sov_defined"] is True
        assert data["counts"]["documents"] == 1
        assert data["counts"]["sov_items"] == 1

    def test_progress_with_scoped_items(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Test"}).json()
        client.put(f"/api/bidding/sov/{item['id']}", json={"work_type": "self_perform"})

        res = client.get(f"/api/bidding/bids/{bid['id']}/setup-progress")
        data = res.json()
        assert data["scope_designated"] is True
        assert data["counts"]["scoped_items"] == 1

    def test_progress_not_found(self):
        res = client.get("/api/bidding/bids/99999/setup-progress")
        assert res.status_code == 404


class TestRefreshPipeline:

    def test_refresh_stream_bid_not_found(self):
        """Refresh endpoint returns 404 for invalid bid."""
        res = client.get("/api/bidding/bids/99999/refresh-stream")
        assert res.status_code == 404


# ══════════════════════════════════════════════════════════════
# PART D TESTS — Vendors, Procurement, Solicitations, Gap Analysis
# ══════════════════════════════════════════════════════════════


# Track vendor IDs for cleanup
_test_vendor_ids = []

@pytest.fixture(autouse=True)
def cleanup_test_vendors():
    """Clean up any vendors created during tests."""
    _test_vendor_ids.clear()
    yield
    if _test_vendor_ids:
        conn = get_connection()
        try:
            for vid in _test_vendor_ids:
                conn.execute("DELETE FROM vendor_directory WHERE id = ?", (vid,))
            conn.commit()
        finally:
            conn.close()


class TestVendorCRUD:

    def test_create_vendor(self):
        res = client.post("/api/vendors", json={
            "trade": "Electrical",
            "company": "Test Electric Co",
            "vendor_type": "construction",
            "contact_name": "John Doe",
            "phone": "(801) 555-1234",
        })
        assert res.status_code == 200
        v = res.json()
        _test_vendor_ids.append(v["id"])
        assert v["trade"] == "Electrical"
        assert v["company"] == "Test Electric Co"
        assert v["is_active"] == 1

    def test_list_vendors(self):
        v = client.post("/api/vendors", json={"trade": "Concrete", "company": "Concrete Corp", "vendor_type": "construction"}).json()
        _test_vendor_ids.append(v["id"])

        res = client.get("/api/vendors")
        assert res.status_code == 200
        vendors = res.json()
        assert any(x["id"] == v["id"] for x in vendors)

    def test_list_vendors_search(self):
        v = client.post("/api/vendors", json={"trade": "Welding", "company": "UniqueWeldCo123", "vendor_type": "construction"}).json()
        _test_vendor_ids.append(v["id"])

        res = client.get("/api/vendors?search=UniqueWeldCo123")
        vendors = res.json()
        assert len(vendors) >= 1
        assert vendors[0]["company"] == "UniqueWeldCo123"

    def test_update_vendor(self):
        v = client.post("/api/vendors", json={"trade": "Steel", "company": "Steel Inc", "vendor_type": "materials"}).json()
        _test_vendor_ids.append(v["id"])

        res = client.put(f"/api/vendors/{v['id']}", json={"contact_name": "Jane Smith"})
        assert res.status_code == 200
        assert res.json()["contact_name"] == "Jane Smith"

    def test_soft_delete_vendor(self):
        v = client.post("/api/vendors", json={"trade": "Paint", "company": "Paint Co", "vendor_type": "construction"}).json()
        _test_vendor_ids.append(v["id"])

        res = client.delete(f"/api/vendors/{v['id']}")
        assert res.status_code == 200
        assert res.json()["archived"] is True

        # Should not appear in active list
        active = client.get("/api/vendors").json()
        assert not any(x["id"] == v["id"] for x in active)

        # Should appear with include_archived
        all_v = client.get("/api/vendors?include_archived=true").json()
        assert any(x["id"] == v["id"] for x in all_v)

    def test_list_trades(self):
        v = client.post("/api/vendors", json={"trade": "HVAC_Test_Trade", "company": "HVAC Co", "vendor_type": "construction"}).json()
        _test_vendor_ids.append(v["id"])

        res = client.get("/api/vendors/trades")
        assert res.status_code == 200
        trades = res.json()
        assert any(t["trade"] == "HVAC_Test_Trade" for t in trades)

    def test_export_vendors(self):
        res = client.get("/api/vendors/export")
        assert res.status_code == 200

    def test_vendor_not_found(self):
        res = client.get("/api/vendors/99999")
        assert res.status_code == 404


class TestProcurementCRUD:

    def test_create_procurement_item(self):
        bid = create_test_bid()
        res = client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={
            "name": "Electrical Sub",
            "procurement_type": "subcontract",
            "trade_match": "Electrical",
        })
        assert res.status_code == 200
        item = res.json()
        assert item["name"] == "Electrical Sub"
        assert item["procurement_type"] == "subcontract"
        assert item["status"] == "not_started"

    def test_list_procurement(self):
        bid = create_test_bid()
        client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={"name": "Item A"})
        client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={"name": "Item B"})

        res = client.get(f"/api/bidding/bids/{bid['id']}/procurement")
        assert res.status_code == 200
        items = res.json()
        assert len(items) == 2
        # Should include solicitations and sov_links arrays
        assert "solicitations" in items[0]
        assert "sov_links" in items[0]

    def test_update_procurement(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={"name": "Test"}).json()

        res = client.put(f"/api/bidding/procurement/{item['id']}", json={"status": "rfp_sent"})
        assert res.status_code == 200
        assert res.json()["status"] == "rfp_sent"

    def test_delete_procurement(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={"name": "Delete Me"}).json()

        res = client.delete(f"/api/bidding/procurement/{item['id']}")
        assert res.status_code == 200

        remaining = client.get(f"/api/bidding/bids/{bid['id']}/procurement").json()
        assert len(remaining) == 0

    def test_procurement_dashboard(self):
        bid = create_test_bid()
        client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={"name": "A"})
        client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={"name": "B", "status": "rfp_sent"})

        res = client.get(f"/api/bidding/bids/{bid['id']}/procurement/dashboard")
        assert res.status_code == 200
        d = res.json()
        assert d["total_items"] == 2
        assert d["by_status"]["not_started"] == 1
        assert d["by_status"]["rfp_sent"] == 1

    def test_export_procurement(self):
        bid = create_test_bid()
        client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={"name": "Export Test"})
        res = client.get(f"/api/bidding/bids/{bid['id']}/procurement/export")
        assert res.status_code == 200


class TestSolicitations:

    def test_add_solicitation(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={"name": "Test"}).json()

        res = client.post(f"/api/bidding/procurement/{item['id']}/solicitations", json={
            "company_name": "ABC Electric",
            "contact_name": "Bob",
            "status": "not_sent",
        })
        assert res.status_code == 200
        sol = res.json()
        assert sol["company_name"] == "ABC Electric"
        assert sol["status"] == "not_sent"

    def test_update_solicitation(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={"name": "Test"}).json()
        sol = client.post(f"/api/bidding/procurement/{item['id']}/solicitations", json={
            "company_name": "XYZ Corp",
        }).json()

        res = client.put(f"/api/bidding/procurement/solicitations/{sol['id']}", json={
            "status": "received",
            "quote_amount": 125000.00,
        })
        assert res.status_code == 200
        assert res.json()["status"] == "received"
        assert res.json()["quote_amount"] == 125000.00

    def test_delete_solicitation(self):
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={"name": "Test"}).json()
        sol = client.post(f"/api/bidding/procurement/{item['id']}/solicitations", json={
            "company_name": "Del Corp",
        }).json()

        res = client.delete(f"/api/bidding/procurement/solicitations/{sol['id']}")
        assert res.status_code == 200

    def test_solicitation_auto_populates_from_vendor(self):
        """When vendor_id is provided, contact info auto-populates."""
        v = client.post("/api/vendors", json={
            "trade": "Testing", "company": "TestLab Inc",
            "contact_name": "Lab Contact", "email": "lab@test.com",
            "vendor_type": "construction",
        }).json()
        _test_vendor_ids.append(v["id"])

        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={"name": "Testing"}).json()

        res = client.post(f"/api/bidding/procurement/{item['id']}/solicitations", json={
            "vendor_id": v["id"],
        })
        assert res.status_code == 200
        sol = res.json()
        assert sol["company_name"] == "TestLab Inc"
        assert sol["contact_name"] == "Lab Contact"
        assert sol["contact_email"] == "lab@test.com"


class TestSOVLinkage:

    def test_link_sov_items(self):
        bid = create_test_bid()
        sov = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Concrete"}).json()
        item = client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={"name": "Concrete Sub"}).json()

        res = client.post(f"/api/bidding/procurement/{item['id']}/link-sov", json={
            "sov_item_ids": [sov["id"]],
        })
        assert res.status_code == 200
        assert res.json()["linked"] == 1

        # Verify link shows up in procurement list
        items = client.get(f"/api/bidding/bids/{bid['id']}/procurement").json()
        assert len(items[0]["sov_links"]) == 1
        assert items[0]["sov_links"][0]["sov_item_id"] == sov["id"]

    def test_unlink_sov_item(self):
        bid = create_test_bid()
        sov = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Steel"}).json()
        item = client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={"name": "Steel Sub"}).json()
        client.post(f"/api/bidding/procurement/{item['id']}/link-sov", json={"sov_item_ids": [sov["id"]]})

        res = client.delete(f"/api/bidding/procurement/{item['id']}/link-sov/{sov['id']}")
        assert res.status_code == 200


class TestGapAnalysis:

    def test_gap_analysis_finds_unlinked_subs(self):
        """Subcontract SOV items without procurement links should be flagged."""
        bid = create_test_bid()
        sov = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Electrical Work"}).json()
        client.put(f"/api/bidding/sov/{sov['id']}", json={"work_type": "subcontract"})

        res = client.post(f"/api/bidding/bids/{bid['id']}/procurement/analyze-gaps")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 1
        assert any("Electrical" in s["name"] for s in data["suggestions"])

    def test_gap_analysis_excludes_out_of_scope(self):
        """Out-of-scope items must be invisible to gap analysis."""
        bid = create_test_bid()
        in_scope = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "In Scope Sub"}).json()
        out_scope = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Out Scope Sub"}).json()

        client.put(f"/api/bidding/sov/{in_scope['id']}", json={"work_type": "subcontract"})
        client.put(f"/api/bidding/sov/{out_scope['id']}", json={"work_type": "subcontract"})
        client.post(f"/api/bidding/bids/{bid['id']}/sov/set-scope", json={
            "item_ids": [out_scope["id"]], "in_scope": 0,
        })

        res = client.post(f"/api/bidding/bids/{bid['id']}/procurement/analyze-gaps")
        data = res.json()
        # Only the in-scope item should produce a suggestion
        sov_ids_in_suggestions = set()
        for s in data["suggestions"]:
            sov_ids_in_suggestions.update(s.get("related_sov_items", []))
        assert in_scope["id"] in sov_ids_in_suggestions or data["count"] >= 1
        assert out_scope["id"] not in sov_ids_in_suggestions

    def test_accept_suggestions(self):
        bid = create_test_bid()
        res = client.post(f"/api/bidding/bids/{bid['id']}/procurement/accept-suggestions", json={
            "suggestions": [
                {"name": "Test Sub", "procurement_type": "subcontract", "ai_source": "test"},
            ],
        })
        assert res.status_code == 200
        assert res.json()["created"] == 1

        items = client.get(f"/api/bidding/bids/{bid['id']}/procurement").json()
        assert len(items) == 1
        assert items[0]["ai_suggested"] == 1


class TestVendorSuggestion:

    def test_suggest_vendors_by_trade(self):
        v = client.post("/api/vendors", json={
            "trade": "Electrical_Test_Suggest", "company": "Suggest Electric",
            "vendor_type": "construction",
        }).json()
        _test_vendor_ids.append(v["id"])

        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/procurement", json={
            "name": "Electrical Sub", "trade_match": "Electrical_Test_Suggest",
        }).json()

        res = client.get(f"/api/bidding/procurement/{item['id']}/suggest-vendors")
        assert res.status_code == 200
        vendors = res.json()
        assert len(vendors) >= 1
        assert any(v["company"] == "Suggest Electric" for v in vendors)


# ══════════════════════════════════════════════════════════════
# INTEGRATION TESTS — Cross-Feature Consistency
# ══════════════════════════════════════════════════════════════


class TestCrossFeatureIntegration:

    def test_sov_count_excludes_out_of_scope(self):
        """Bid detail sov_count should only count in-scope items."""
        bid = create_test_bid()
        in_s = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "In scope"}).json()
        out_s = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Out scope"}).json()
        client.post(f"/api/bidding/bids/{bid['id']}/sov/set-scope", json={
            "item_ids": [out_s["id"]], "in_scope": 0,
        })

        detail = client.get(f"/api/bidding/bids/{bid['id']}").json()
        assert detail["sov_count"] == 1  # Only in-scope counted

    def test_sov_list_returns_both_scopes(self):
        """SOV list API returns both in-scope and out-of-scope items (frontend splits them)."""
        bid = create_test_bid()
        client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "In"})
        out = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Out"}).json()
        client.post(f"/api/bidding/bids/{bid['id']}/sov/set-scope", json={
            "item_ids": [out["id"]], "in_scope": 0,
        })

        items = client.get(f"/api/bidding/bids/{bid['id']}/sov").json()
        assert len(items) == 2  # Both returned for frontend rendering

    def test_setup_progress_end_to_end(self):
        """Verify setup progress accurately tracks workflow steps."""
        bid = create_test_bid()

        # Step 1: No docs, no SOV
        sp = client.get(f"/api/bidding/bids/{bid['id']}/setup-progress").json()
        assert sp["documents_synced"] is False
        assert sp["sov_defined"] is False

        # Step 2: Add a document
        from io import BytesIO
        client.post(
            f"/api/bidding/bids/{bid['id']}/documents",
            files={"file": ("test.txt", BytesIO(b"test"), "text/plain")},
            data={"doc_category": "general"},
        )
        sp = client.get(f"/api/bidding/bids/{bid['id']}/setup-progress").json()
        assert sp["documents_synced"] is True
        assert sp["sov_defined"] is False

        # Step 3: Add SOV item
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Test"}).json()
        sp = client.get(f"/api/bidding/bids/{bid['id']}/setup-progress").json()
        assert sp["sov_defined"] is True
        assert sp["scope_designated"] is False

        # Step 4: Set work_type
        client.put(f"/api/bidding/sov/{item['id']}", json={"work_type": "self_perform"})
        sp = client.get(f"/api/bidding/bids/{bid['id']}/setup-progress").json()
        assert sp["scope_designated"] is True

    def test_work_type_flows_to_procurement_gap(self):
        """Only subcontract items should generate procurement gaps, not self_perform."""
        bid = create_test_bid()
        sp_item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Self Perform Work"}).json()
        sub_item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Sub Work"}).json()
        und_item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Undecided Work"}).json()

        client.put(f"/api/bidding/sov/{sp_item['id']}", json={"work_type": "self_perform"})
        client.put(f"/api/bidding/sov/{sub_item['id']}", json={"work_type": "subcontract"})
        # und_item stays 'undecided'

        result = client.post(f"/api/bidding/bids/{bid['id']}/procurement/analyze-gaps").json()
        sov_ids_suggested = set()
        for s in result["suggestions"]:
            sov_ids_suggested.update(s.get("related_sov_items", []))

        # Only subcontract item should appear
        assert sub_item["id"] in sov_ids_suggested
        assert sp_item["id"] not in sov_ids_suggested
        assert und_item["id"] not in sov_ids_suggested

    def test_group_count_now_counts_sections(self):
        """group_count in bid detail should now count bid_section, not pricing_group."""
        bid = create_test_bid()
        client.post(f"/api/bidding/bids/{bid['id']}/sections", json={"name": "Division 1"})
        client.post(f"/api/bidding/bids/{bid['id']}/sections", json={"name": "Division 2"})

        detail = client.get(f"/api/bidding/bids/{bid['id']}").json()
        assert detail["group_count"] == 2

    def test_document_tree_builds_correctly(self):
        """Document tree should organize docs into folders."""
        bid = create_test_bid()
        from io import BytesIO
        for cat in ["drawing", "spec", "contract"]:
            client.post(
                f"/api/bidding/bids/{bid['id']}/documents",
                files={"file": (f"test_{cat}.pdf", BytesIO(b"content"), "application/pdf")},
                data={"doc_category": cat},
            )

        tree = client.get(f"/api/bidding/bids/{bid['id']}/documents/tree").json()
        assert tree["stats"]["total_documents"] == 3
        assert len(tree["tree"]) >= 1  # At least one folder

    def test_sov_update_all_part_a_fields(self):
        """PUT /sov/{item_id} should update all Part A fields in one call."""
        bid = create_test_bid()
        sec = client.post(f"/api/bidding/bids/{bid['id']}/sections", json={"name": "Div 3"}).json()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Test"}).json()

        res = client.put(f"/api/bidding/sov/{item['id']}", json={
            "hcss_number": "3.01.001",
            "work_type": "self_perform",
            "section_id": sec["id"],
            "description": "Updated Concrete Work",
            "quantity": 250.0,
            "unit": "CY",
            "notes": "Include pump truck",
        })
        assert res.status_code == 200
        updated = res.json()
        assert updated["hcss_number"] == "3.01.001"
        assert updated["work_type"] == "self_perform"
        assert updated["section_id"] == sec["id"]
        assert updated["description"] == "Updated Concrete Work"
        assert updated["quantity"] == 250.0
        assert updated["unit"] == "CY"
        assert updated["notes"] == "Include pump truck"

    def test_sov_update_holding_fields(self):
        """PUT /sov/{item_id} should handle holding account fields."""
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Equipment"}).json()

        res = client.put(f"/api/bidding/sov/{item['id']}", json={
            "is_holding_account": 1,
            "holding_description": "crane, man lifts, forklift",
        })
        assert res.status_code == 200
        assert res.json()["is_holding_account"] == 1
        assert res.json()["holding_description"] == "crane, man lifts, forklift"

    def test_sov_update_clear_nullable_fields(self):
        """PUT /sov/{item_id} should allow clearing nullable fields to None."""
        bid = create_test_bid()
        item = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={
            "description": "Test",
            "hcss_number": "5.01",
        }).json()
        assert item["hcss_number"] == "5.01"

        # Clear hcss_number by setting to None
        res = client.put(f"/api/bidding/sov/{item['id']}", json={"hcss_number": None})
        assert res.status_code == 200
        assert res.json()["hcss_number"] is None

    def test_section_sort_order_auto_increments(self):
        """Creating sections without sort_order should auto-increment."""
        bid = create_test_bid()
        s1 = client.post(f"/api/bidding/bids/{bid['id']}/sections", json={"name": "First"}).json()
        s2 = client.post(f"/api/bidding/bids/{bid['id']}/sections", json={"name": "Second"}).json()
        assert s2["sort_order"] > s1["sort_order"]

    def test_holding_distribution_replaces_targets(self):
        """Setting distribution should replace existing targets, not append."""
        bid = create_test_bid()
        h = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Holding"}).json()
        t1 = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Target 1"}).json()
        t2 = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Target 2"}).json()
        t3 = client.post(f"/api/bidding/bids/{bid['id']}/sov", json={"description": "Target 3"}).json()

        client.post(f"/api/bidding/bids/{bid['id']}/sov/{h['id']}/make-holding", json={
            "holding_description": "shared equipment",
        })

        # First distribution: t1, t2
        client.post(f"/api/bidding/bids/{bid['id']}/sov/{h['id']}/distribute", json={
            "target_item_ids": [t1["id"], t2["id"]],
        })
        dist = client.get(f"/api/bidding/bids/{bid['id']}/sov/{h['id']}/distribution").json()
        assert len(dist) == 2

        # Replace with t2, t3 — should NOT have t1 anymore
        client.post(f"/api/bidding/bids/{bid['id']}/sov/{h['id']}/distribute", json={
            "target_item_ids": [t2["id"], t3["id"]],
        })
        dist = client.get(f"/api/bidding/bids/{bid['id']}/sov/{h['id']}/distribution").json()
        assert len(dist) == 2
        target_ids = {d["target_item_id"] for d in dist}
        assert t1["id"] not in target_ids
        assert t2["id"] in target_ids
        assert t3["id"] in target_ids
