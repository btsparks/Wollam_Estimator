"""
Phase C Integration Tests

End-to-end tests for the sync pipeline using mock data sources
and a temporary database. Validates:
    - Full sync pipeline (mock sources → DB → rate cards)
    - Idempotency (run twice, same results)
    - Single job sync
    - Estimate matching
    - Rate card correctness
    - Flagged items stored
    - Review / approval / KB aggregation flow
"""

import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from app.hcss.sync import HCSSSyncOrchestrator, MockHeavyJobSource, MockHeavyBidSource
from app.hcss import storage
from app.catalog.review import RateCardReview
from app.catalog.interview import PMInterviewWorkflow
from app.catalog.lessons import LessonsLearnedCapture
from app.catalog.aggregate import aggregate_card, rebuild_all
from app.transform.rate_card import RateCardGenerator, RateCardResult


@pytest.fixture(autouse=True)
def fresh_db():
    """Create a fresh temp DB with v2.0 schema for each test."""
    import app.config
    import app.database

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    # Save original DB_PATH
    original_config_path = app.config.DB_PATH
    original_db_path = app.database.DB_PATH

    # Point both modules at temp DB
    app.config.DB_PATH = Path(tmp.name)
    app.database.DB_PATH = Path(tmp.name)

    # Run v2.0 migration
    from scripts.migrate_v2 import TIER_1_TABLES, TIER_2_TABLES, TIER_3_TABLES, INDEXES
    conn = sqlite3.connect(tmp.name)
    for sql in TIER_1_TABLES + TIER_2_TABLES + TIER_3_TABLES:
        conn.execute(sql)
    for sql in INDEXES:
        conn.execute(sql)
    conn.commit()
    conn.close()

    yield tmp.name

    # Restore original DB_PATH
    app.config.DB_PATH = original_config_path
    app.database.DB_PATH = original_db_path

    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def _run(coro):
    """Helper to run async functions in sync test context."""
    return asyncio.run(coro)


def _create_orchestrator():
    """Create an orchestrator with mock sources."""
    return HCSSSyncOrchestrator(
        heavyjob_source=MockHeavyJobSource(),
        heavybid_source=MockHeavyBidSource(),
    )


# ─────────────────────────────────────────────────────────────
# Sync Pipeline Tests
# ─────────────────────────────────────────────────────────────

class TestSyncPipeline:
    """Test the full sync pipeline with mock data."""

    def test_sync_all_closed_jobs(self):
        """Full pipeline: 2 jobs synced with cost codes and rate cards."""
        orchestrator = _create_orchestrator()
        result = _run(orchestrator.sync_all_closed_jobs())

        assert result["jobs_processed"] == 2
        assert result["jobs_failed"] == 0
        assert len(result["errors"]) == 0

        # Verify jobs stored
        jobs = storage.get_all_jobs()
        assert len(jobs) == 2
        job_numbers = {j["job_number"] for j in jobs}
        assert "8553" in job_numbers
        assert "8576" in job_numbers

    def test_sync_stores_cost_codes(self):
        """Verify cost codes are stored for each job."""
        orchestrator = _create_orchestrator()
        _run(orchestrator.sync_all_closed_jobs())

        job_8553 = storage.get_job_by_number("8553")
        assert job_8553 is not None
        codes = storage.get_cost_codes_for_job(job_8553["job_id"])
        assert len(codes) > 20  # 8553 has ~38 cost codes

        job_8576 = storage.get_job_by_number("8576")
        assert job_8576 is not None
        codes = storage.get_cost_codes_for_job(job_8576["job_id"])
        assert len(codes) > 10  # 8576 has ~20 cost codes

    def test_sync_generates_rate_cards(self):
        """Verify rate cards are generated for each synced job."""
        orchestrator = _create_orchestrator()
        _run(orchestrator.sync_all_closed_jobs())

        cards = storage.get_all_rate_cards()
        assert len(cards) == 2

        for card in cards:
            assert card["status"] == "draft"
            items = storage.get_rate_items_for_card(card["card_id"])
            assert len(items) > 0

    def test_sync_is_idempotent(self):
        """Running sync twice produces same row counts."""
        orchestrator = _create_orchestrator()

        _run(orchestrator.sync_all_closed_jobs())
        jobs_first = storage.get_all_jobs()
        cards_first = storage.get_all_rate_cards()

        _run(orchestrator.sync_all_closed_jobs())
        jobs_second = storage.get_all_jobs()
        cards_second = storage.get_all_rate_cards()

        assert len(jobs_first) == len(jobs_second)
        assert len(cards_first) == len(cards_second)

    def test_sync_single_job(self):
        """Sync one job by ID."""
        orchestrator = _create_orchestrator()
        result = _run(orchestrator.sync_job("job-8553"))

        assert result["status"] == "completed"

        jobs = storage.get_all_jobs()
        assert len(jobs) == 1
        assert jobs[0]["job_number"] == "8553"

    def test_estimate_matched_to_job(self):
        """Verify estimate FK link is set."""
        orchestrator = _create_orchestrator()
        _run(orchestrator.sync_all_closed_jobs())

        job = storage.get_job_by_number("8553")
        assert job["estimate_id"] is not None

        estimate = storage.get_estimate_for_job(job["job_id"])
        assert estimate is not None
        assert "8553" in estimate["name"]


# ─────────────────────────────────────────────────────────────
# Storage Layer Tests
# ─────────────────────────────────────────────────────────────

class TestStorage:
    """Test storage layer idempotency and correctness."""

    def test_upsert_business_unit_twice(self):
        """Upserting same BU twice returns same ID."""
        id1 = storage.upsert_business_unit("bu-test", "Test BU")
        id2 = storage.upsert_business_unit("bu-test", "Test BU Updated")
        assert id1 == id2

    def test_upsert_job_twice(self):
        """Upserting same job twice returns same ID."""
        from app.hcss.models import HJJob
        bu_id = storage.upsert_business_unit("bu-test", "Test")
        job = HJJob(id="j-1", jobNumber="9999", description="Test Job", status="Closed")
        id1 = storage.upsert_job(job, bu_id)
        id2 = storage.upsert_job(job, bu_id)
        assert id1 == id2

    def test_sync_metadata(self):
        """Sync record create/update workflow."""
        sync_id = storage.create_sync_record("test", "full")
        assert sync_id > 0

        storage.update_sync_record(sync_id, "completed", jobs_processed=5)
        last = storage.get_last_sync("test")
        assert last is not None
        assert last["jobs_processed"] == 5


# ─────────────────────────────────────────────────────────────
# Rate Card Validation Tests
# ─────────────────────────────────────────────────────────────

class TestRateCardValidation:
    """Validate rate card correctness against known Phase B targets."""

    def test_flagged_items_stored(self):
        """Items with >20% variance have variance_flag = TRUE."""
        orchestrator = _create_orchestrator()
        _run(orchestrator.sync_all_closed_jobs())

        cards = storage.get_all_rate_cards()
        total_flagged = 0
        for card in cards:
            flagged = storage.get_flagged_items_for_card(card["card_id"])
            total_flagged += len(flagged)
            for item in flagged:
                assert item["variance_flag"] == 1
                assert abs(item["variance_pct"]) > 20

        # We know from Phase B data that there are flagged items
        assert total_flagged > 0

    def test_wall_fs_rate_8553(self):
        """Wall F/S (code 2340) on 8553 should be ~0.276 MH/SF actual."""
        orchestrator = _create_orchestrator()
        _run(orchestrator.sync_all_closed_jobs())

        job = storage.get_job_by_number("8553")
        card = storage.get_rate_card_for_job(job["job_id"])
        items = storage.get_rate_items_for_card(card["card_id"])

        wall_item = next((i for i in items if i["activity"] == "2340"), None)
        assert wall_item is not None
        assert wall_item["act_mh_per_unit"] is not None
        # 10110 MH / 36646 SF ≈ 0.276
        assert abs(wall_item["act_mh_per_unit"] - 0.276) < 0.01


# ─────────────────────────────────────────────────────────────
# Review + Interview + KB Aggregation Tests
# ─────────────────────────────────────────────────────────────

class TestReviewWorkflow:
    """Test the review → interview → approve → aggregate pipeline."""

    def _sync_and_get_card(self):
        """Helper: sync data and return first card info."""
        orchestrator = _create_orchestrator()
        _run(orchestrator.sync_all_closed_jobs())
        cards = storage.get_all_rate_cards()
        return cards[0]

    def test_submit_for_review(self):
        """draft → pending_review transition."""
        card = self._sync_and_get_card()
        review = RateCardReview()
        review.submit_for_review(card["card_id"])

        updated = storage.get_rate_card_for_job(card["job_id"])
        assert updated["status"] == "pending_review"

    def test_reject_sends_back_to_draft(self):
        """pending_review → draft on rejection."""
        card = self._sync_and_get_card()
        review = RateCardReview()
        review.submit_for_review(card["card_id"])
        review.reject(card["card_id"], "Needs more detail")

        updated = storage.get_rate_card_for_job(card["job_id"])
        assert updated["status"] == "draft"
        assert "REJECTED" in updated["pm_notes"]

    def test_approve_triggers_aggregation(self):
        """pending_review → approved, then rate_library populated."""
        card = self._sync_and_get_card()
        review = RateCardReview()
        review.submit_for_review(card["card_id"])
        review.approve(card["card_id"], pm_name="Travis Sparks", notes="Looks good")

        updated = storage.get_rate_card_for_job(card["job_id"])
        assert updated["status"] == "approved"
        assert updated["pm_name"] == "Travis Sparks"

        # Check rate_library was populated
        from app.database import get_connection
        conn = get_connection()
        try:
            count = conn.execute("SELECT COUNT(*) as cnt FROM rate_library").fetchone()["cnt"]
            assert count > 0
        finally:
            conn.close()

    def test_approve_wrong_status_raises(self):
        """Cannot approve a draft card."""
        card = self._sync_and_get_card()
        review = RateCardReview()
        with pytest.raises(ValueError, match="must be 'pending_review'"):
            review.approve(card["card_id"], pm_name="Test")

    def test_pending_reviews_list(self):
        """get_pending_reviews returns pending cards."""
        card = self._sync_and_get_card()
        review = RateCardReview()
        review.submit_for_review(card["card_id"])

        pending = review.get_pending_reviews()
        assert len(pending) >= 1
        assert pending[0]["status"] == "pending_review"


class TestPMInterview:
    """Test PM interview question generation and response handling."""

    def _get_rate_card_result(self) -> RateCardResult:
        """Helper: generate a rate card result from mock data."""
        import json
        mock_dir = Path(__file__).parent / "mock_data" / "heavyjob"
        with open(mock_dir / "costcodes_8553.json") as f:
            cost_codes_data = json.load(f)

        from app.hcss.models import HJCostCode
        cost_codes = [HJCostCode.model_validate(cc) for cc in cost_codes_data]

        generator = RateCardGenerator()
        return generator.generate_rate_card(
            job_number="8553",
            job_name="RTK SPD Pump Station",
            cost_codes=cost_codes,
        )

    def test_generate_questions(self):
        """Questions are generated from rate card data."""
        card = self._get_rate_card_result()
        workflow = PMInterviewWorkflow(rate_card=card)
        questions = workflow.generate_questions()

        assert len(questions) > 0
        types = {q["type"] for q in questions}
        assert "CONTEXT" in types  # Always has context questions

        # If there are flagged items, VARIANCE questions exist
        if card.flagged_items:
            assert "VARIANCE" in types
            variance_qs = [q for q in questions if q["type"] == "VARIANCE"]
            assert len(variance_qs) == len(card.flagged_items)

    def test_submit_response(self):
        """Responses can be submitted to questions."""
        card = self._get_rate_card_result()
        workflow = PMInterviewWorkflow(rate_card=card)
        questions = workflow.generate_questions()

        q = questions[0]
        workflow.submit_response(q["id"], "Test response")

        updated = workflow.questions
        answered = next(uq for uq in updated if uq.id == q["id"])
        assert answered.response == "Test response"

    def test_is_complete_all_variance_answered(self):
        """is_complete True when all VARIANCE questions answered."""
        card = self._get_rate_card_result()
        workflow = PMInterviewWorkflow(rate_card=card)
        questions = workflow.generate_questions()

        # Answer all required (VARIANCE) questions
        for q in questions:
            if q["required"]:
                workflow.submit_response(q["id"], "Answered")

        assert workflow.is_complete()

    def test_override_rate(self):
        """PM can override a recommended rate."""
        card = self._get_rate_card_result()
        workflow = PMInterviewWorkflow(rate_card=card)
        workflow.override_rate("2340", 0.30, "Based on my experience")

        assert "2340" in workflow._overrides
        assert workflow._overrides["2340"] == (0.30, "Based on my experience")


class TestLessonsLearned:
    """Test lessons learned capture and search."""

    def test_capture_and_retrieve(self):
        """Capture a lesson and retrieve it."""
        orchestrator = _create_orchestrator()
        _run(orchestrator.sync_all_closed_jobs())

        job = storage.get_job_by_number("8553")
        lessons = LessonsLearnedCapture()

        lesson_id = lessons.capture_lesson(
            job_id=job["job_id"],
            discipline="concrete",
            category="variance",
            description="Cold weather added 15% to forming costs",
            impact="high",
            recommendation="Add 15% contingency for winter forming",
            pm_name="Travis Sparks",
        )
        assert lesson_id > 0

        retrieved = lessons.get_lessons_for_job(job["job_id"])
        assert len(retrieved) == 1
        assert retrieved[0]["description"] == "Cold weather added 15% to forming costs"

    def test_search_by_discipline(self):
        """Search lessons by discipline."""
        orchestrator = _create_orchestrator()
        _run(orchestrator.sync_all_closed_jobs())

        job = storage.get_job_by_number("8553")
        lessons = LessonsLearnedCapture()

        lessons.capture_lesson(job["job_id"], "concrete", "variance", "Concrete lesson")
        lessons.capture_lesson(job["job_id"], "earthwork", "success", "Earthwork lesson")

        results = lessons.search_lessons(discipline="concrete")
        assert len(results) == 1
        assert results[0]["discipline"] == "concrete"

    def test_search_by_keyword(self):
        """Search lessons by keyword."""
        orchestrator = _create_orchestrator()
        _run(orchestrator.sync_all_closed_jobs())

        job = storage.get_job_by_number("8553")
        lessons = LessonsLearnedCapture()

        lessons.capture_lesson(job["job_id"], "concrete", "risk", "Cold weather impact on forming")

        results = lessons.search_lessons(keyword="cold weather")
        assert len(results) == 1


# ─────────────────────────────────────────────────────────────
# File Source Tests (real HJ Cost Reports)
# ─────────────────────────────────────────────────────────────

REPORTS_DIR = Path(__file__).parent.parent / "HJ Cost Reports"


@pytest.mark.skipif(
    not REPORTS_DIR.exists(),
    reason="HJ Cost Reports directory not present",
)
class TestFileSource:
    """Test the file-based HeavyJob source with real exported reports."""

    def _create_file_orchestrator(self):
        from app.hcss.file_source import FileHeavyJobSource, EmptyHeavyBidSource
        return HCSSSyncOrchestrator(
            heavyjob_source=FileHeavyJobSource(REPORTS_DIR),
            heavybid_source=EmptyHeavyBidSource(),
        )

    def test_file_source_discovers_jobs(self):
        """FileHeavyJobSource finds jobs from report files."""
        from app.hcss.file_source import FileHeavyJobSource
        source = FileHeavyJobSource(REPORTS_DIR)
        jobs = _run(source.get_jobs())
        assert len(jobs) >= 2
        job_numbers = {j.jobNumber for j in jobs}
        assert "8587" in job_numbers
        assert "8589" in job_numbers

    def test_file_source_parses_cost_codes(self):
        """FileHeavyJobSource parses cost codes from report files."""
        from app.hcss.file_source import FileHeavyJobSource
        source = FileHeavyJobSource(REPORTS_DIR)
        codes = _run(source.get_cost_codes("file-8587"))
        assert len(codes) > 50  # 8587 has 98 cost codes

        # Verify a known cost code has merged data
        code_1010 = next((c for c in codes if c.code == "1010"), None)
        assert code_1010 is not None
        assert code_1010.description == "Field Supervision"
        assert code_1010.budgetQuantity == 220.0
        assert code_1010.budgetLaborHours is not None
        assert code_1010.budgetLaborHours > 0
        assert code_1010.actualLaborHours is not None

    def test_file_sync_pipeline(self):
        """Full sync pipeline with file source produces rate cards."""
        orchestrator = self._create_file_orchestrator()
        result = _run(orchestrator.sync_all_closed_jobs())

        assert result["jobs_processed"] == 2
        assert result["jobs_failed"] == 0

        # Verify rate cards
        job_8587 = storage.get_job_by_number("8587")
        assert job_8587 is not None
        card = storage.get_rate_card_for_job(job_8587["job_id"])
        assert card is not None
        items = storage.get_rate_items_for_card(card["card_id"])
        assert len(items) > 50

    def test_file_sync_has_flagged_items(self):
        """File-synced rate cards have flagged variance items."""
        orchestrator = self._create_file_orchestrator()
        _run(orchestrator.sync_all_closed_jobs())

        cards = storage.get_all_rate_cards()
        file_cards = [c for c in cards if c["job_number"] in ("8587", "8589")]
        assert len(file_cards) == 2

        for card in file_cards:
            flagged = storage.get_flagged_items_for_card(card["card_id"])
            assert len(flagged) > 0, f"Job {card['job_number']} should have flagged items"
