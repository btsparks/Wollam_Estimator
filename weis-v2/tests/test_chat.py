"""Tests for AI Estimating Chat — signal detection, context assembly, SQL tool, API routes."""

import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.chat import (
    detect_signals, search_rate_items, build_context_block,
    search_costcodes_direct, search_estimates, build_estimate_context,
)
from app.services.sql_tool import validate_query, execute_sql

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


# ── SQL Tool Validation Tests ──

class TestSqlToolValidation:
    def test_select_passes(self):
        ok, err = validate_query("SELECT * FROM job LIMIT 5")
        assert ok is True
        assert err == ""

    def test_select_with_joins_passes(self):
        ok, err = validate_query("""
            SELECT ri.act_mh_per_unit, j.job_number
            FROM rate_item ri
            JOIN rate_card rc ON ri.card_id = rc.card_id
            JOIN job j ON rc.job_id = j.job_id
            WHERE ri.discipline = 'concrete'
            LIMIT 10
        """)
        assert ok is True

    def test_with_cte_passes(self):
        ok, err = validate_query("""
            WITH top_jobs AS (
                SELECT job_id, job_number FROM job LIMIT 5
            )
            SELECT * FROM top_jobs
        """)
        assert ok is True

    def test_drop_rejected(self):
        ok, err = validate_query("DROP TABLE job")
        assert ok is False
        assert "Blocked keyword" in err or "Only SELECT" in err

    def test_delete_rejected(self):
        ok, err = validate_query("DELETE FROM job WHERE job_id = 1")
        assert ok is False

    def test_update_rejected(self):
        ok, err = validate_query("UPDATE job SET name = 'hacked' WHERE job_id = 1")
        assert ok is False

    def test_insert_rejected(self):
        ok, err = validate_query("INSERT INTO job (job_number, name) VALUES ('9999', 'test')")
        assert ok is False

    def test_create_rejected(self):
        ok, err = validate_query("CREATE TABLE evil (id INTEGER)")
        assert ok is False

    def test_attach_rejected(self):
        ok, err = validate_query("ATTACH DATABASE 'other.db' AS other")
        assert ok is False

    def test_load_extension_rejected(self):
        ok, err = validate_query("SELECT load_extension('evil.so')")
        assert ok is False
        assert "Blocked function" in err

    def test_multiple_statements_rejected(self):
        ok, err = validate_query("SELECT 1; DROP TABLE job")
        assert ok is False

    def test_empty_query_rejected(self):
        ok, err = validate_query("")
        assert ok is False

    def test_comment_stripping(self):
        ok, err = validate_query("-- This is a comment\nSELECT 1")
        assert ok is True

    def test_pragma_rejected(self):
        ok, err = validate_query("PRAGMA table_info(job)")
        assert ok is False


# ── SQL Tool Execution Tests ──

class TestSqlToolExecution:
    def test_basic_query_returns_results(self):
        result = execute_sql("SELECT job_id, job_number, name FROM job LIMIT 3")
        assert result["error"] is None
        assert result["row_count"] > 0
        assert "job_id" in result["columns"]
        assert "job_number" in result["columns"]

    def test_row_limit_enforced(self):
        result = execute_sql("SELECT * FROM hj_costcode", row_limit=5)
        assert result["error"] is None
        assert result["row_count"] <= 5
        assert result["truncated"] is True  # 15K rows, only 5 returned

    def test_invalid_query_returns_error(self):
        result = execute_sql("SELECT * FROM nonexistent_table")
        assert result["error"] is not None
        assert "no such table" in result["error"]

    def test_blocked_query_returns_error(self):
        result = execute_sql("DROP TABLE job")
        assert result["error"] is not None

    def test_empty_result(self):
        result = execute_sql("SELECT * FROM job WHERE job_number = 'ZZZZZ'")
        assert result["error"] is None
        assert result["row_count"] == 0
        assert result["rows"] == []

    def test_long_text_truncated(self):
        """Long text values should be truncated to MAX_TEXT_LEN."""
        result = execute_sql(
            "SELECT project_summary FROM pm_context WHERE LENGTH(project_summary) > 500 LIMIT 1"
        )
        if result["row_count"] > 0:
            val = result["rows"][0][0]
            assert len(val) <= 503  # 500 + "..."

    def test_aggregate_query(self):
        result = execute_sql("SELECT COUNT(*) as cnt FROM job")
        assert result["error"] is None
        assert result["row_count"] == 1
        assert result["rows"][0][0] > 0

    def test_join_query(self):
        result = execute_sql("""
            SELECT j.job_number, COUNT(cc.cc_id) as cc_count
            FROM job j
            JOIN hj_costcode cc ON j.job_id = cc.job_id
            GROUP BY j.job_id
            ORDER BY cc_count DESC
            LIMIT 3
        """)
        assert result["error"] is None
        assert result["row_count"] > 0
        assert "job_number" in result["columns"]
        assert "cc_count" in result["columns"]
