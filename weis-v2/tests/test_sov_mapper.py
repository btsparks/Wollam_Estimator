"""Tests for SOV Intelligence Mapper — service, API, and drawing log.

All Claude API calls are mocked — no real API usage.
"""

import io
import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_connection
from app.services.sov_mapper import (
    map_intelligence_to_sov,
    get_item_intelligence,
    get_sov_intelligence_summary,
    mark_sov_intelligence_stale,
    _parse_mapper_response,
)

client = TestClient(app)

_test_bid_ids = []

MOCK_MAPPER_RESPONSE = json.dumps({
    "relevant_findings": [
        {
            "agent_name": "qaqc_manager",
            "domain": "qaqc",
            "finding_type": "testing_requirement",
            "title": "Concrete cylinder breaks",
            "detail": "1 per 50 CY, per Section 03300",
            "severity": "medium",
            "spec_section": "03300-4.2",
            "clause_reference": None,
            "source_document": "specs.pdf",
            "confidence": 0.95,
        }
    ],
    "drawing_references": [
        {
            "drawing_number": "S-101",
            "description": "Foundation plan relevant to this item",
            "discipline": "structural",
        }
    ],
    "missing_information": [
        {
            "what_is_missing": "Concrete design strength not specified",
            "why_it_matters": "Affects mix design and cost",
            "suggested_action": "rfi",
            "suggested_question": "Please confirm concrete design strength",
            "source_agent": "qaqc_manager",
        }
    ],
    "spec_sections_summary": "03300, 03200",
    "estimator_notes": "Standard concrete scope with testing requirements",
})


@pytest.fixture(autouse=True)
def cleanup_test_bids():
    """Clean up any bids created during tests."""
    _test_bid_ids.clear()
    yield
    if _test_bid_ids:
        conn = get_connection()
        try:
            for bid_id in _test_bid_ids:
                conn.execute("DELETE FROM sov_item_intelligence WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM drawing_log WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM agent_reports WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM bid_document_chunks WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM bid_documents WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM bid_sov_item WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM pricing_group WHERE bid_id = ?", (bid_id,))
                conn.execute("DELETE FROM active_bids WHERE id = ?", (bid_id,))
            conn.commit()
        finally:
            conn.close()


def create_test_bid(**kwargs):
    data = {
        "bid_name": "SOV Mapper Test Bid",
        "bid_number": "SM-001",
        "owner": "Test Owner",
        "status": "active",
    }
    data.update(kwargs)
    res = client.post("/api/bidding/bids", json=data)
    assert res.status_code == 200
    bid = res.json()
    _test_bid_ids.append(bid["id"])
    return bid


def add_sov_item(bid_id, item_number, description, unit="EA", quantity=10):
    res = client.post(f"/api/bidding/bids/{bid_id}/sov", json={
        "item_number": item_number,
        "description": description,
        "unit": unit,
        "quantity": quantity,
    })
    assert res.status_code == 200
    return res.json()


def insert_mock_report(bid_id, agent_name, report_json, summary="Test summary"):
    """Insert a mock agent report directly into the database."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO agent_reports (bid_id, agent_name, status, report_json, summary_text, risk_rating, flags_count)
               VALUES (?, ?, 'complete', ?, ?, 'low', 0)""",
            (bid_id, agent_name, json.dumps(report_json), summary),
        )
        conn.commit()
    finally:
        conn.close()


def insert_mock_intelligence(bid_id, sov_item_id, domain="qaqc", severity="medium"):
    """Insert a mock intelligence finding directly."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO sov_item_intelligence
               (bid_id, sov_item_id, agent_name, domain, finding_type,
                title, detail, severity, confidence)
               VALUES (?, ?, 'test_agent', ?, 'test_finding', 'Test title', 'Test detail', ?, 0.9)""",
            (bid_id, sov_item_id, domain, severity),
        )
        conn.commit()
    finally:
        conn.close()


# ── Parse Response Tests ──

class TestParseMapperResponse:
    def test_parse_valid_json(self):
        result = _parse_mapper_response('{"relevant_findings": [], "drawing_references": []}')
        assert result["relevant_findings"] == []

    def test_parse_with_code_fences(self):
        text = '```json\n{"relevant_findings": [{"title": "test"}]}\n```'
        result = _parse_mapper_response(text)
        assert len(result["relevant_findings"]) == 1

    def test_parse_with_preamble(self):
        text = 'Here is the analysis:\n{"relevant_findings": [], "missing_information": []}'
        result = _parse_mapper_response(text)
        assert "relevant_findings" in result

    def test_parse_invalid_json(self):
        result = _parse_mapper_response("this is not json at all")
        assert result.get("parse_error") is True
        assert result["relevant_findings"] == []


# ── Service Tests ──

class TestMapIntelligenceToSOV:
    @patch("app.services.sov_mapper.anthropic.Anthropic")
    def test_basic_mapping(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=MOCK_MAPPER_RESPONSE)]
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 200
        mock_client.messages.create.return_value = mock_response

        bid = create_test_bid()
        item = add_sov_item(bid["id"], "1", "Concrete foundations", "CY", 500)

        insert_mock_report(bid["id"], "qaqc_manager", {
            "testing_requirements": [{"test": "Cylinder breaks", "frequency": "1/50CY"}],
        })

        result = map_intelligence_to_sov(bid["id"])
        assert result["items_mapped"] == 1
        assert result["total_findings"] > 0
        assert mock_client.messages.create.called

    @patch("app.services.sov_mapper.anthropic.Anthropic")
    def test_mapping_specific_items(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=MOCK_MAPPER_RESPONSE)]
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 200
        mock_client.messages.create.return_value = mock_response

        bid = create_test_bid()
        item1 = add_sov_item(bid["id"], "1", "Earthwork", "CY", 1000)
        item2 = add_sov_item(bid["id"], "2", "Concrete", "CY", 500)

        insert_mock_report(bid["id"], "qaqc_manager", {"testing_requirements": []})

        result = map_intelligence_to_sov(bid["id"], sov_item_ids=[item1["id"]])
        assert result["items_mapped"] == 1
        assert mock_client.messages.create.call_count == 1

    def test_mapping_no_reports(self):
        bid = create_test_bid()
        add_sov_item(bid["id"], "1", "Earthwork")
        result = map_intelligence_to_sov(bid["id"])
        assert result["items_mapped"] == 0
        assert "No agent reports" in result["message"]

    def test_mapping_no_sov_items(self):
        bid = create_test_bid()
        insert_mock_report(bid["id"], "qaqc_manager", {})
        result = map_intelligence_to_sov(bid["id"])
        assert result["items_mapped"] == 0
        assert "No SOV items" in result["message"]


class TestGetItemIntelligence:
    def test_by_domain(self):
        bid = create_test_bid()
        item = add_sov_item(bid["id"], "1", "Test item")

        insert_mock_intelligence(bid["id"], item["id"], domain="qaqc", severity="medium")
        insert_mock_intelligence(bid["id"], item["id"], domain="legal", severity="high")

        result = get_item_intelligence(bid["id"], item["id"])
        assert result["total_findings"] == 2
        assert "qaqc" in result["domains"]
        assert "legal" in result["domains"]

    def test_empty_item(self):
        bid = create_test_bid()
        item = add_sov_item(bid["id"], "1", "Test item")

        result = get_item_intelligence(bid["id"], item["id"])
        assert result["total_findings"] == 0
        assert result["domains"] == {}


class TestIntelligenceSummary:
    def test_summary_counts(self):
        bid = create_test_bid()
        item1 = add_sov_item(bid["id"], "1", "Item 1")
        item2 = add_sov_item(bid["id"], "2", "Item 2")

        insert_mock_intelligence(bid["id"], item1["id"], severity="high")
        insert_mock_intelligence(bid["id"], item1["id"], severity="low")
        insert_mock_intelligence(bid["id"], item2["id"], severity="critical")

        summary = get_sov_intelligence_summary(bid["id"])
        assert len(summary) == 2

        s1 = next(s for s in summary if s["sov_item_id"] == item1["id"])
        assert s1["finding_count"] == 2
        assert s1["max_severity"] == "high"

        s2 = next(s for s in summary if s["sov_item_id"] == item2["id"])
        assert s2["finding_count"] == 1
        assert s2["max_severity"] == "critical"


class TestStaleness:
    def test_mark_stale(self):
        bid = create_test_bid()
        item = add_sov_item(bid["id"], "1", "Test")
        insert_mock_intelligence(bid["id"], item["id"])
        insert_mock_intelligence(bid["id"], item["id"])

        count = mark_sov_intelligence_stale(bid["id"])
        assert count == 2

    def test_mark_stale_idempotent(self):
        bid = create_test_bid()
        item = add_sov_item(bid["id"], "1", "Test")
        insert_mock_intelligence(bid["id"], item["id"])

        mark_sov_intelligence_stale(bid["id"])
        count = mark_sov_intelligence_stale(bid["id"])
        assert count == 0

    def test_stale_reflected_in_summary(self):
        bid = create_test_bid()
        item = add_sov_item(bid["id"], "1", "Test")
        insert_mock_intelligence(bid["id"], item["id"])

        mark_sov_intelligence_stale(bid["id"])
        summary = get_sov_intelligence_summary(bid["id"])
        assert summary[0]["is_stale"] is True


# ── API Endpoint Tests ──

class TestSOVIntelligenceAPI:
    @patch("app.services.sov_mapper.anthropic.Anthropic")
    def test_map_intelligence_endpoint(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=MOCK_MAPPER_RESPONSE)]
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 200
        mock_client.messages.create.return_value = mock_response

        bid = create_test_bid()
        add_sov_item(bid["id"], "1", "Earthwork")
        insert_mock_report(bid["id"], "legal_analyst", {"key_risks": []})

        res = client.post(f"/api/bidding/bids/{bid['id']}/sov/map-intelligence")
        assert res.status_code == 200
        data = res.json()
        assert data["items_mapped"] == 1

    def test_get_item_intelligence_endpoint(self):
        bid = create_test_bid()
        item = add_sov_item(bid["id"], "1", "Test")
        insert_mock_intelligence(bid["id"], item["id"])

        res = client.get(f"/api/bidding/bids/{bid['id']}/sov/{item['id']}/intelligence")
        assert res.status_code == 200
        data = res.json()
        assert data["total_findings"] == 1

    def test_intelligence_summary_endpoint(self):
        bid = create_test_bid()
        item = add_sov_item(bid["id"], "1", "Test")
        insert_mock_intelligence(bid["id"], item["id"])

        res = client.get(f"/api/bidding/bids/{bid['id']}/sov/intelligence-summary")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["finding_count"] == 1

    def test_mark_stale_endpoint(self):
        bid = create_test_bid()
        item = add_sov_item(bid["id"], "1", "Test")
        insert_mock_intelligence(bid["id"], item["id"])

        res = client.post(f"/api/bidding/bids/{bid['id']}/sov/mark-stale")
        assert res.status_code == 200
        assert res.json()["marked_stale"] == 1

    def test_map_nonexistent_bid(self):
        res = client.post("/api/bidding/bids/99999/sov/map-intelligence")
        assert res.status_code == 404


# ── Drawing Log Tests ──

class TestDrawingLogAPI:
    def test_create_drawing(self):
        bid = create_test_bid()
        res = client.post(f"/api/bidding/bids/{bid['id']}/drawings", json={
            "drawing_number": "C-101",
            "title": "Site Plan",
            "revision": "A",
            "discipline": "civil",
        })
        assert res.status_code == 200
        assert res.json()["drawing_number"] == "C-101"

    def test_list_drawings(self):
        bid = create_test_bid()
        client.post(f"/api/bidding/bids/{bid['id']}/drawings", json={"drawing_number": "C-101"})
        client.post(f"/api/bidding/bids/{bid['id']}/drawings", json={"drawing_number": "S-201"})

        res = client.get(f"/api/bidding/bids/{bid['id']}/drawings")
        assert res.status_code == 200
        assert len(res.json()) == 2

    def test_delete_drawing(self):
        bid = create_test_bid()
        create_res = client.post(f"/api/bidding/bids/{bid['id']}/drawings", json={"drawing_number": "C-101"})
        drawing_id = create_res.json()["id"]

        res = client.delete(f"/api/bidding/bids/{bid['id']}/drawings/{drawing_id}")
        assert res.status_code == 200
        assert res.json()["deleted"] is True

        # Verify gone
        list_res = client.get(f"/api/bidding/bids/{bid['id']}/drawings")
        assert len(list_res.json()) == 0

    def test_duplicate_drawing(self):
        bid = create_test_bid()
        client.post(f"/api/bidding/bids/{bid['id']}/drawings", json={"drawing_number": "C-101"})
        res = client.post(f"/api/bidding/bids/{bid['id']}/drawings", json={"drawing_number": "C-101"})
        assert res.status_code == 409

    def test_delete_nonexistent_drawing(self):
        bid = create_test_bid()
        res = client.delete(f"/api/bidding/bids/{bid['id']}/drawings/99999")
        assert res.status_code == 404
