"""Tests for AI Estimating Chat — signal detection, context assembly, API routes."""

import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.chat import (
    detect_signals, search_rate_items, build_context_block,
    search_costcodes_direct, search_estimates, build_estimate_context,
)

client = TestClient(app)


# ── Signal Detection Tests ──

class TestDetectSignals:
    def test_detects_concrete_discipline(self):
        signals = detect_signals("What's a good rate for wall forming?")
        assert "concrete" in signals["disciplines"]

    def test_detects_earthwork_discipline(self):
        signals = detect_signals("How much excavation did we do on the last job?")
        assert "earthwork" in signals["disciplines"]

    def test_detects_piping_discipline(self):
        signals = detect_signals("What crew do we use for HDPE pipe fusing?")
        assert "piping" in signals["disciplines"]

    def test_detects_multiple_disciplines(self):
        signals = detect_signals("Compare concrete forming and steel erection rates")
        assert "concrete" in signals["disciplines"]
        assert "structural_steel" in signals["disciplines"]

    def test_detects_mh_rate_type(self):
        signals = detect_signals("What's the MH/SF for wall forming?")
        assert "mh_per_unit" in signals["rate_types"]

    def test_detects_cost_rate_type(self):
        signals = detect_signals("What's the cost per yard for concrete?")
        assert "cost_per_unit" in signals["rate_types"]

    def test_detects_crew_rate_type(self):
        signals = detect_signals("What crew size works for this scope?")
        assert "crew" in signals["rate_types"]

    def test_detects_production_rate_type(self):
        signals = detect_signals("What's our daily production for pipe installs?")
        assert "production" in signals["rate_types"]

    def test_extracts_keywords(self):
        signals = detect_signals("What's the production rate for 36-inch HDPE installs?")
        assert "inch" in signals["keywords"] or "hdpe" in signals["keywords"]

    def test_filters_stop_words(self):
        signals = detect_signals("What rate should I use for this?")
        assert "what" not in signals["keywords"]
        assert "this" not in signals["keywords"]

    def test_domain_terms_not_filtered(self):
        """Estimating terms like rate, cost, unit should pass through as keywords."""
        signals = detect_signals("Loading rates for piping cost codes")
        kws = signals["keywords"]
        assert "rates" in kws or "rate" in kws
        assert "cost" in kws

    def test_projects_passes_through(self):
        """'projects' should not be filtered — useful for job name matching."""
        signals = detect_signals("Show me projects with high crew costs")
        assert "projects" in signals["keywords"]
        assert "costs" in signals["keywords"]

    def test_no_signals_returns_empty(self):
        signals = detect_signals("Hi, can you help me?")
        # Keywords will still be extracted, but disciplines may be empty
        assert isinstance(signals["disciplines"], list)
        assert isinstance(signals["rate_types"], list)
        assert isinstance(signals["keywords"], list)


# ── Search Rate Items Tests ──

class TestSearchRateItems:
    def test_returns_list(self):
        signals = {"disciplines": ["concrete"], "rate_types": [], "keywords": []}
        results = search_rate_items(signals)
        assert isinstance(results, list)

    def test_broad_search_returns_data(self):
        """With no filters, should return some rate items from the 15K+ in the DB."""
        signals = {"disciplines": [], "rate_types": [], "keywords": []}
        results = search_rate_items(signals)
        assert len(results) > 0

    def test_results_have_expected_fields(self):
        signals = {"disciplines": [], "rate_types": [], "keywords": []}
        results = search_rate_items(signals)
        if results:
            item = results[0]
            assert "job_number" in item
            assert "cost_code" in item
            assert "confidence" in item
            assert "job_id" in item

    def test_keyword_search(self):
        signals = {"disciplines": [], "rate_types": [], "keywords": ["wall", "forming"]}
        results = search_rate_items(signals)
        assert isinstance(results, list)

    def test_max_30_results(self):
        signals = {"disciplines": [], "rate_types": [], "keywords": []}
        results = search_rate_items(signals)
        assert len(results) <= 30


# ── Costcode Direct Search Tests ──

class TestSearchCostcodesDirect:
    def test_returns_list(self):
        signals = {
            "disciplines": [], "rate_types": [], "keywords": ["wall"],
            "job_numbers": [], "job_name_keywords": [],
        }
        results = search_costcodes_direct(signals)
        assert isinstance(results, list)

    def test_excludes_known_pairs(self):
        """Should not return cost codes already found via rate_item."""
        signals = {
            "disciplines": [], "rate_types": [], "keywords": ["pour"],
            "job_numbers": [], "job_name_keywords": [],
        }
        # Get some results first
        all_results = search_costcodes_direct(signals)
        if all_results:
            # Exclude the first result and verify it's gone
            first = all_results[0]
            exclude = {(first["job_id"], first["cost_code"])}
            filtered = search_costcodes_direct(signals, exclude)
            excluded_keys = {(r["job_id"], r["cost_code"]) for r in filtered}
            assert (first["job_id"], first["cost_code"]) not in excluded_keys

    def test_results_have_source_flag(self):
        signals = {
            "disciplines": [], "rate_types": [], "keywords": ["excavation"],
            "job_numbers": [], "job_name_keywords": [],
        }
        results = search_costcodes_direct(signals)
        for item in results:
            assert item["source"] == "hj_costcode"

    def test_requires_filter_beyond_actuals(self):
        """Should return empty list if no job/keyword signals given."""
        signals = {
            "disciplines": [], "rate_types": [], "keywords": [],
            "job_numbers": [], "job_name_keywords": [],
        }
        results = search_costcodes_direct(signals)
        assert results == []


# ── Context Block Tests ──

class TestBuildContextBlock:
    def test_empty_items_returns_no_data_message(self):
        block = build_context_block([], {"disciplines": [], "rate_types": [], "keywords": []})
        assert "No matching rate data" in block

    def test_context_block_includes_job_number(self):
        signals = {"disciplines": [], "rate_types": [], "keywords": []}
        items = search_rate_items(signals)
        if items:
            block = build_context_block(items, signals)
            assert "JOB" in block
            assert "DATA GAPS:" in block

    def test_context_block_with_costcode_items(self):
        """Context block should include RAW COST CODE ACTUALS section."""
        signals = {
            "disciplines": [], "rate_types": [], "keywords": ["pour"],
            "job_numbers": [], "job_name_keywords": [],
        }
        cc_items = search_costcodes_direct(signals)
        if cc_items:
            block = build_context_block([], signals, costcode_items=cc_items)
            assert "RAW COST CODE ACTUALS" in block
            assert "no rate card calculated" in block.lower()


# ── Estimate Signal & Search Tests ──

class TestEstimateSignals:
    def test_detects_estimate_intent_bid(self):
        signals = detect_signals("What was bid on 8553?")
        assert signals["estimate_intent"] is True

    def test_detects_estimate_intent_estimate(self):
        signals = detect_signals("Show me the estimate for the weir project")
        assert signals["estimate_intent"] is True

    def test_no_estimate_intent_for_actuals(self):
        signals = detect_signals("What crew did we use on 8553?")
        assert signals["estimate_intent"] is False


class TestSearchEstimates:
    def test_returns_list(self):
        signals = {
            "disciplines": [], "rate_types": [], "keywords": [],
            "job_numbers": ["8553"], "job_name_keywords": [],
            "estimate_intent": True,
        }
        results = search_estimates(signals)
        assert isinstance(results, list)

    def test_finds_by_job_number(self):
        """Should find 8553-CO-WEIR estimate via linked_job_number."""
        signals = {
            "disciplines": [], "rate_types": [], "keywords": [],
            "job_numbers": ["8553"], "job_name_keywords": [],
            "estimate_intent": True,
        }
        results = search_estimates(signals)
        assert len(results) > 0
        codes = [r["code"] for r in results]
        assert any("8553" in c for c in codes)

    def test_estimate_has_bid_items(self):
        signals = {
            "disciplines": [], "rate_types": [], "keywords": [],
            "job_numbers": ["8553"], "job_name_keywords": [],
            "estimate_intent": True,
        }
        results = search_estimates(signals)
        if results:
            assert "bid_items" in results[0]
            assert "activities" in results[0]
            assert results[0]["source_type"] == "estimate"

    def test_estimate_context_block(self):
        signals = {
            "disciplines": [], "rate_types": [], "keywords": [],
            "job_numbers": ["8553"], "job_name_keywords": [],
            "estimate_intent": True,
        }
        results = search_estimates(signals)
        if results:
            block = build_estimate_context(results)
            assert "ESTIMATE DATA" in block
            assert "what was bid" in block

    def test_empty_estimate_context(self):
        block = build_estimate_context([])
        assert block == ""


# ── Chat API Tests ──

class TestChatAPI:
    def test_data_summary(self):
        res = client.get("/api/chat/data-summary")
        assert res.status_code == 200
        data = res.json()
        assert "total_jobs" in data
        assert "total_rate_items" in data
        assert "total_timecards" in data
        assert "disciplines" in data
        assert data["total_jobs"] > 0
        assert "total_estimates" in data

    def test_list_conversations_empty(self):
        res = client.get("/api/chat/conversations")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_get_conversation_404(self):
        res = client.get("/api/chat/conversations/99999")
        assert res.status_code == 404

    def test_delete_conversation_404(self):
        res = client.delete("/api/chat/conversations/99999")
        assert res.status_code == 404

    def test_send_empty_message(self):
        res = client.post("/api/chat/send", json={"message": ""})
        assert res.status_code == 400
