"""Tests for agent framework, runner, and API endpoints.

All Claude API calls are mocked — no real API usage.
"""

import io
import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_connection
from app.agents.base import BaseAgent, AgentReport
from app.agents.runner import (
    get_available_agents,
    _load_bid_context,
    _load_doc_chunks,
    _save_report,
    mark_reports_stale,
    get_intelligence_status,
)
from app.services.document_chunker import chunk_text, chunk_document

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
        "bid_name": "Agent Test Bid",
        "bid_number": "AG-001",
        "owner": "Test Owner",
        "status": "active",
    }
    data.update(kwargs)
    res = client.post("/api/bidding/bids", json=data)
    assert res.status_code == 200
    bid = res.json()
    _test_bid_ids.append(bid["id"])
    return bid


def upload_test_doc(bid_id: int, content: str = "Test document content", filename: str = "test.txt"):
    """Upload a test document and return the doc record."""
    res = client.post(
        f"/api/bidding/bids/{bid_id}/documents",
        files={"file": (filename, io.BytesIO(content.encode()), "text/plain")},
        data={"doc_category": "spec"},
    )
    assert res.status_code == 200
    return res.json()


# ── Document Chunker Tests ──────────────────────────────────────

class TestChunker:

    def test_chunk_text_simple(self):
        text = "Hello world. " * 200  # ~2600 chars
        chunks = chunk_text(text)
        assert len(chunks) >= 1
        assert all("chunk_text" in c for c in chunks)
        assert all("chunk_index" in c for c in chunks)

    def test_chunk_text_empty(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []
        assert chunk_text(None) == []

    def test_chunk_text_with_sections(self):
        text = (
            "SECTION 03300 - CAST-IN-PLACE CONCRETE\n\n"
            "This section covers concrete work. " * 50 + "\n\n"
            "SECTION 31230 - EARTHWORK\n\n"
            "This section covers earthwork. " * 50
        )
        chunks = chunk_text(text)
        assert len(chunks) >= 2
        # At least one chunk should have a section heading
        headings = [c["section_heading"] for c in chunks if c["section_heading"]]
        assert len(headings) >= 1

    def test_chunk_text_short(self):
        text = "Short document."
        chunks = chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0]["chunk_text"] == "Short document."

    def test_chunk_document_creates_db_records(self):
        bid = create_test_bid()
        doc = upload_test_doc(bid["id"], "This is test content for chunking. " * 10)

        # Chunks should have been created during upload
        conn = get_connection()
        try:
            count = conn.execute(
                "SELECT COUNT(*) as cnt FROM bid_document_chunks WHERE document_id = ?",
                (doc["id"],),
            ).fetchone()["cnt"]
            assert count >= 1
        finally:
            conn.close()

    def test_rechunk_endpoint(self):
        bid = create_test_bid()
        upload_test_doc(bid["id"], "Content for rechunking. " * 20)

        res = client.post(f"/api/bidding/bids/{bid['id']}/rechunk")
        assert res.status_code == 200
        result = res.json()
        assert result["total_docs"] >= 1
        assert result["total_chunks"] >= 1


# ── Agent Registry Tests ────────────────────────────────────────

class TestAgentRegistry:

    def test_available_agents(self):
        agents = get_available_agents()
        names = [a["name"] for a in agents]
        assert "document_control" in names
        assert "legal_analyst" in names
        assert "qaqc_manager" in names
        assert "subcontract_manager" in names
        assert "chief_estimator" in names
        assert len(agents) == 5

    def test_list_agents_endpoint(self):
        res = client.get("/api/bidding/agents")
        assert res.status_code == 200
        agents = res.json()
        assert len(agents) == 5


# ── Agent Base Class Tests ──────────────────────────────────────

class TestBaseAgent:

    def test_empty_chunks_returns_report(self):
        agent = BaseAgent()
        agent.name = "test_agent"
        report = agent.run(bid_id=1, doc_chunks=[], context={})
        assert report.status == "complete"
        assert report.input_chunk_count == 0
        assert "No documents" in report.summary_text

    def test_build_batches(self):
        agent = BaseAgent()
        chunks = [
            {"chunk_text": "A" * 1000, "filename": "a.txt", "doc_category": "spec"},
            {"chunk_text": "B" * 1000, "filename": "b.txt", "doc_category": "drawing"},
        ]
        batches = agent._build_batches(chunks)
        assert len(batches) >= 1
        assert "a.txt" in batches[0]

    def test_parse_response_json(self):
        agent = BaseAgent()
        result = agent._parse_response('{"flags": ["test flag"]}')
        assert result == {"flags": ["test flag"]}

    def test_parse_response_code_fences(self):
        agent = BaseAgent()
        result = agent._parse_response('```json\n{"flags": []}\n```')
        assert result == {"flags": []}

    def test_parse_response_fallback(self):
        agent = BaseAgent()
        result = agent._parse_response("Some text before {\"flags\": []} some text after")
        assert result == {"flags": []}


# ── Report Storage Tests ────────────────────────────────────────

class TestReportStorage:

    def test_save_and_load_report(self):
        bid = create_test_bid()
        report = AgentReport(
            agent_name="test_agent",
            status="complete",
            summary_text="Test summary",
            report_json={"flags": ["flag1"]},
            risk_rating="medium",
            flags_count=1,
            tokens_used=100,
            duration_seconds=1.5,
        )

        report_id = _save_report(bid["id"], report)
        assert report_id > 0

        # Verify in DB
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM agent_reports WHERE id = ?", (report_id,)
            ).fetchone()
            assert row["agent_name"] == "test_agent"
            assert row["risk_rating"] == "medium"
            assert row["flags_count"] == 1
            parsed = json.loads(row["report_json"])
            assert parsed["flags"] == ["flag1"]
        finally:
            conn.close()

    def test_save_report_upsert(self):
        bid = create_test_bid()
        report1 = AgentReport(
            agent_name="test_agent",
            summary_text="First run",
            report_json={"flags": []},
        )
        id1 = _save_report(bid["id"], report1)

        report2 = AgentReport(
            agent_name="test_agent",
            summary_text="Second run",
            report_json={"flags": ["new_flag"]},
            flags_count=1,
        )
        id2 = _save_report(bid["id"], report2)

        # Should update same row
        assert id1 == id2

        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT summary_text, flags_count FROM agent_reports WHERE id = ?",
                (id1,),
            ).fetchone()
            assert row["summary_text"] == "Second run"
            assert row["flags_count"] == 1
        finally:
            conn.close()


# ── Staleness Tests ─────────────────────────────────────────────

class TestStaleness:

    def test_mark_reports_stale(self):
        bid = create_test_bid()
        report = AgentReport(
            agent_name="test_agent",
            report_json={"flags": []},
        )
        _save_report(bid["id"], report)

        count = mark_reports_stale(bid["id"])
        assert count == 1

        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT is_stale FROM agent_reports WHERE bid_id = ? AND agent_name = ?",
                (bid["id"], "test_agent"),
            ).fetchone()
            assert row["is_stale"] == 1
        finally:
            conn.close()

    def test_mark_stale_idempotent(self):
        bid = create_test_bid()
        report = AgentReport(agent_name="test_agent", report_json={})
        _save_report(bid["id"], report)

        mark_reports_stale(bid["id"])
        count = mark_reports_stale(bid["id"])  # Already stale
        assert count == 0

    def test_rerun_clears_stale(self):
        bid = create_test_bid()
        report = AgentReport(
            agent_name="test_agent",
            report_json={"flags": []},
        )
        _save_report(bid["id"], report)
        mark_reports_stale(bid["id"])

        # Save again — should clear stale flag
        _save_report(bid["id"], report)

        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT is_stale FROM agent_reports WHERE bid_id = ? AND agent_name = ?",
                (bid["id"], "test_agent"),
            ).fetchone()
            assert row["is_stale"] == 0
        finally:
            conn.close()


# ── Intelligence Status Tests ───────────────────────────────────

class TestIntelligenceStatus:

    def test_intelligence_status_no_reports(self):
        bid = create_test_bid()
        status = get_intelligence_status(bid["id"])
        assert status["bid_id"] == bid["id"]
        assert status["total_documents"] == 0
        assert status["agents_needing_reanalysis"] == 0
        assert "document_control" in status["agents"]
        assert status["agents"]["document_control"]["status"] == "not_run"

    def test_intelligence_status_with_report(self):
        bid = create_test_bid()
        report = AgentReport(
            agent_name="document_control",
            risk_rating="medium",
            flags_count=2,
            report_json={"flags": ["a", "b"]},
        )
        _save_report(bid["id"], report)

        status = get_intelligence_status(bid["id"])
        dc = status["agents"]["document_control"]
        assert dc["status"] == "complete"
        assert dc["risk_rating"] == "medium"
        assert dc["flags_count"] == 2

    def test_intelligence_status_endpoint(self):
        bid = create_test_bid()
        res = client.get(f"/api/bidding/bids/{bid['id']}/intelligence-status")
        assert res.status_code == 200
        data = res.json()
        assert "agents" in data


# ── Agent API Endpoint Tests ────────────────────────────────────

class TestAgentAPI:

    def test_get_reports_empty(self):
        bid = create_test_bid()
        res = client.get(f"/api/bidding/bids/{bid['id']}/reports")
        assert res.status_code == 200
        assert res.json() == []

    def test_get_report_not_found(self):
        bid = create_test_bid()
        res = client.get(f"/api/bidding/bids/{bid['id']}/reports/fake_agent")
        assert res.status_code == 404

    def test_clear_reports(self):
        bid = create_test_bid()
        report = AgentReport(agent_name="test_agent", report_json={})
        _save_report(bid["id"], report)

        res = client.delete(f"/api/bidding/bids/{bid['id']}/reports")
        assert res.status_code == 200
        assert res.json()["deleted"] >= 1

    def test_analyze_no_documents(self):
        bid = create_test_bid()
        res = client.post(f"/api/bidding/bids/{bid['id']}/analyze")
        assert res.status_code == 400
        assert "No documents" in res.json()["detail"]

    @patch("app.agents.base.anthropic.Anthropic")
    def test_analyze_single_agent(self, mock_anthropic_cls):
        """Test running a single agent with mocked Claude."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "documents_reviewed": 1,
            "document_index": [],
            "addendum_changes": [],
            "missing_documents": [],
            "flags": ["Test flag"],
        }))]
        mock_response.usage = MagicMock(input_tokens=500, output_tokens=200)
        mock_client.messages.create.return_value = mock_response

        bid = create_test_bid()
        upload_test_doc(bid["id"], "SECTION 03300 - CONCRETE\nTest spec content. " * 50)

        res = client.post(f"/api/bidding/bids/{bid['id']}/analyze/document_control")
        assert res.status_code == 200
        data = res.json()
        assert data["agent_name"] == "document_control"
        assert data["status"] == "complete"

    @patch("app.agents.base.anthropic.Anthropic")
    def test_analyze_all_agents(self, mock_anthropic_cls):
        """Test running all agents with mocked Claude."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({"flags": []}))]
        mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_client.messages.create.return_value = mock_response

        bid = create_test_bid()
        upload_test_doc(bid["id"], "Test content for all agents. " * 50)

        res = client.post(f"/api/bidding/bids/{bid['id']}/analyze")
        assert res.status_code == 200
        data = res.json()
        assert "agents" in data
        # Should have run 4 sub-agents + chief
        assert len(data["agents"]) >= 4

    def test_get_reports_after_save(self):
        bid = create_test_bid()
        report = AgentReport(
            agent_name="document_control",
            summary_text="Test",
            report_json={"flags": ["x"]},
            risk_rating="low",
            flags_count=1,
        )
        _save_report(bid["id"], report)

        res = client.get(f"/api/bidding/bids/{bid['id']}/reports")
        assert res.status_code == 200
        reports = res.json()
        assert len(reports) >= 1
        assert reports[0]["agent_name"] == "document_control"
        # report_json should be parsed as dict, not string
        assert isinstance(reports[0]["report_json"], dict)

    def test_get_single_report(self):
        bid = create_test_bid()
        report = AgentReport(
            agent_name="legal_analyst",
            summary_text="Legal test",
            report_json={"bid_type": "unit_price", "flags": []},
        )
        _save_report(bid["id"], report)

        res = client.get(f"/api/bidding/bids/{bid['id']}/reports/legal_analyst")
        assert res.status_code == 200
        data = res.json()
        assert data["agent_name"] == "legal_analyst"
        assert data["report_json"]["bid_type"] == "unit_price"
