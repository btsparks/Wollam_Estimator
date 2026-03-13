"""Tests for diary parser, import, and API endpoints."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.diary_parser import parse_diary_file
from app.database import get_connection

client = TestClient(app)

DIARY_DIR = Path(__file__).parent.parent / "Heavy Job Notes"


# ── Parser Tests ──


class TestDiaryParser:
    """Test the diary file parser on real data."""

    @pytest.fixture(autouse=True)
    def check_files_exist(self):
        if not DIARY_DIR.exists():
            pytest.skip("Heavy Job Notes folder not found")

    def test_parse_8542_basic(self):
        """Parse the smallest file (8542) and check structure."""
        f = DIARY_DIR / "DiaryCCNotes - 8542.txt"
        if not f.exists():
            pytest.skip("8542 file not found")
        result = parse_diary_file(f)
        assert result["job_code"] == "8542"
        assert result["job_name"] is not None
        assert result["entry_count"] > 30
        assert len(result["entries"]) == result["entry_count"]

    def test_parse_8589_entries(self):
        """Parse 8589 (medium file) and check entry content."""
        f = DIARY_DIR / "DiaryCCNotes - 8589.txt"
        if not f.exists():
            pytest.skip("8589 file not found")
        result = parse_diary_file(f)
        assert result["job_code"] == "8589"
        assert result["job_name"] == "RTKC Capping 2025"
        assert result["entry_count"] > 500
        assert len(result["cost_codes_found"]) > 30
        assert len(result["foremen"]) > 5

    def test_parse_entry_fields(self):
        """Check that parsed entries have all expected fields."""
        f = DIARY_DIR / "DiaryCCNotes - 8542.txt"
        if not f.exists():
            pytest.skip("8542 file not found")
        result = parse_diary_file(f)
        entry = next(
            (e for e in result["entries"] if e.get("cost_code") and e.get("company_note")),
            None,
        )
        assert entry is not None
        assert entry["date"] is not None
        assert entry["foreman"] is not None
        assert entry["cost_code"] is not None
        assert entry["company_note"] != ""

    def test_parse_8593_different_format(self):
        """8593 has slightly different column widths."""
        f = DIARY_DIR / "DiaryCCNotes - 8593.txt"
        if not f.exists():
            pytest.skip("8593 file not found")
        result = parse_diary_file(f)
        assert result["job_code"] == "8593"
        assert result["entry_count"] > 40

    def test_parse_all_files_no_crash(self):
        """All 11 files should parse without exceptions."""
        for f in sorted(DIARY_DIR.glob("*.txt")):
            result = parse_diary_file(f)
            assert result["job_code"] is not None
            assert result["entry_count"] > 0

    def test_diary_level_notes_captured(self):
        """Diary notes (no cost code) should be captured."""
        f = DIARY_DIR / "DiaryCCNotes - 8589.txt"
        if not f.exists():
            pytest.skip("8589 file not found")
        result = parse_diary_file(f)
        diary_entries = [e for e in result["entries"] if e["cost_code"] is None]
        assert len(diary_entries) > 0
        assert diary_entries[0]["company_note"] != ""


# ── API Tests ──


class TestDiaryAPI:
    """Test diary API endpoints."""

    def test_diary_status(self):
        """GET /api/diary/status should return list."""
        resp = client.get("/api/diary/status")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_diary_entries_for_job(self):
        """GET /api/diary/entries/{job_id} returns entries if data exists."""
        # Get a job that has diary data
        conn = get_connection()
        row = conn.execute(
            "SELECT DISTINCT job_id FROM diary_entry LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            pytest.skip("No diary data imported")
        job_id = row["job_id"]

        resp = client.get(f"/api/diary/entries/{job_id}")
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) > 0
        assert "company_note" in entries[0]

    def test_diary_summary(self):
        """GET /api/diary/summary/{job_id} returns summary."""
        conn = get_connection()
        row = conn.execute(
            "SELECT DISTINCT job_id FROM diary_entry LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            pytest.skip("No diary data imported")
        job_id = row["job_id"]

        resp = client.get(f"/api/diary/summary/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entry_count"] > 0
        assert "foremen" in data

    def test_diary_entries_404(self):
        """Nonexistent job returns 404."""
        resp = client.get("/api/diary/entries/99999")
        assert resp.status_code == 404

    def test_interview_jobs_include_diary_count(self):
        """Job list should include diary_entry_count field."""
        resp = client.get("/api/interview/jobs")
        assert resp.status_code == 200
        jobs = resp.json()
        assert len(jobs) > 0
        assert "diary_entry_count" in jobs[0]

    def test_job_detail_includes_diary_summary(self):
        """Job detail should include diary_summary when available."""
        conn = get_connection()
        row = conn.execute(
            "SELECT DISTINCT job_id FROM diary_entry LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            pytest.skip("No diary data imported")
        job_id = row["job_id"]

        resp = client.get(f"/api/interview/job/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "diary_summary" in data
        assert data["diary_summary"]["entry_count"] > 0
