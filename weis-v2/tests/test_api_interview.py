"""Tests for the PM Context Interview API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestJobList:
    def test_list_jobs_returns_200(self):
        r = client.get("/api/interview/jobs")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_job_has_required_fields(self):
        r = client.get("/api/interview/jobs")
        job = r.json()[0]
        required = [
            "job_id", "job_number", "name", "status",
            "cost_code_count", "cost_codes_with_data",
            "cost_codes_with_context", "data_richness",
            "interview_status",
        ]
        for field in required:
            assert field in job, f"Missing field: {field}"

    def test_interview_status_values(self):
        r = client.get("/api/interview/jobs")
        statuses = {j["interview_status"] for j in r.json()}
        assert statuses.issubset({"not_started", "in_progress", "complete"})

    def test_data_richness_range(self):
        r = client.get("/api/interview/jobs")
        for job in r.json():
            assert 0 <= job["data_richness"] <= 100


class TestJobDetail:
    def _get_first_job_id(self):
        jobs = client.get("/api/interview/jobs").json()
        # Find a job with actual data
        for j in jobs:
            if j["cost_codes_with_data"] > 0:
                return j["job_id"]
        return jobs[0]["job_id"]

    def test_job_detail_returns_200(self):
        job_id = self._get_first_job_id()
        r = client.get(f"/api/interview/job/{job_id}")
        assert r.status_code == 200

    def test_job_detail_structure(self):
        job_id = self._get_first_job_id()
        r = client.get(f"/api/interview/job/{job_id}")
        data = r.json()
        assert "job" in data
        assert "pm_context" in data
        assert "cost_codes" in data
        assert "top_5" in data

    def test_job_detail_job_fields(self):
        job_id = self._get_first_job_id()
        data = client.get(f"/api/interview/job/{job_id}").json()
        job = data["job"]
        assert "job_id" in job
        assert "job_number" in job
        assert "name" in job
        assert "total_actual_hrs" in job
        assert "cost_codes_with_data" in job

    def test_cost_code_fields(self):
        job_id = self._get_first_job_id()
        data = client.get(f"/api/interview/job/{job_id}").json()
        if data["cost_codes"]:
            cc = data["cost_codes"][0]
            assert "code" in cc
            assert "description" in cc
            assert "unit" in cc
            assert "act_labor_hrs" in cc
            assert "has_context" in cc
            assert "crew_breakdown" in cc

    def test_404_for_nonexistent_job(self):
        r = client.get("/api/interview/job/999999")
        assert r.status_code == 404


class TestSaveContext:
    def _get_test_job(self):
        jobs = client.get("/api/interview/jobs").json()
        for j in jobs:
            if j["cost_codes_with_data"] > 0:
                return j
        return jobs[0]

    def test_save_job_context(self):
        job = self._get_test_job()
        r = client.post("/api/interview/context", json={
            "job_id": job["job_id"],
            "type": "job",
            "data": {"pm_name": "Test User", "project_summary": "Pytest test"}
        })
        assert r.status_code == 200
        assert r.json()["status"] == "saved"
        assert r.json()["type"] == "job"

        # Verify it persisted
        detail = client.get(f"/api/interview/job/{job['job_id']}").json()
        assert detail["pm_context"] is not None
        assert detail["pm_context"]["pm_name"] == "Test User"

        # Cleanup
        self._cleanup_job_context(job["job_id"])

    def test_save_cost_code_context(self):
        job = self._get_test_job()
        detail = client.get(f"/api/interview/job/{job['job_id']}").json()
        if not detail["cost_codes"]:
            pytest.skip("No cost codes with data")

        cc_code = detail["cost_codes"][0]["code"]
        r = client.post("/api/interview/context", json={
            "job_id": job["job_id"],
            "type": "cost_code",
            "cost_code": cc_code,
            "data": {"scope_included": "Test scope", "conditions": "Test conditions"}
        })
        assert r.status_code == 200
        assert r.json()["status"] == "saved"
        assert r.json()["type"] == "cost_code"

        # Verify persistence
        detail2 = client.get(f"/api/interview/job/{job['job_id']}").json()
        cc = next(c for c in detail2["cost_codes"] if c["code"] == cc_code)
        assert cc["has_context"] is True
        assert cc["context"]["scope_included"] == "Test scope"

        # Cleanup
        self._cleanup_cc_context(job["job_id"], cc_code)

    def test_save_context_bad_type(self):
        r = client.post("/api/interview/context", json={
            "job_id": 1,
            "type": "invalid",
            "data": {}
        })
        assert r.status_code == 400

    def test_save_cc_context_missing_code(self):
        r = client.post("/api/interview/context", json={
            "job_id": 1,
            "type": "cost_code",
            "data": {"scope_included": "test"}
        })
        assert r.status_code == 400

    def _cleanup_job_context(self, job_id):
        from app.database import get_connection
        conn = get_connection()
        try:
            conn.execute("DELETE FROM pm_context WHERE job_id = ?", (job_id,))
            conn.commit()
        finally:
            conn.close()

    def _cleanup_cc_context(self, job_id, cost_code):
        from app.database import get_connection
        conn = get_connection()
        try:
            conn.execute("DELETE FROM cc_context WHERE job_id = ? AND cost_code = ?", (job_id, cost_code))
            conn.commit()
        finally:
            conn.close()


class TestMarkComplete:
    def test_mark_complete(self):
        job = client.get("/api/interview/jobs").json()[0]
        r = client.post(f"/api/interview/complete/{job['job_id']}")
        assert r.status_code == 200
        assert r.json()["status"] == "completed"
        assert "completed_at" in r.json()

        # Verify status changed
        jobs = client.get("/api/interview/jobs").json()
        updated = next(j for j in jobs if j["job_id"] == job["job_id"])
        assert updated["interview_status"] == "complete"

        # Cleanup
        import sqlite3
        from app.config import DB_PATH
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM pm_context WHERE job_id = ?", (job["job_id"],))
        conn.commit()
        conn.close()


class TestProgress:
    def test_progress_returns_200(self):
        r = client.get("/api/interview/progress")
        assert r.status_code == 200

    def test_progress_fields(self):
        data = client.get("/api/interview/progress").json()
        assert "total_jobs" in data
        assert "jobs_with_context" in data
        assert "jobs_complete" in data
        assert "total_cost_codes_with_data" in data
        assert "cost_codes_with_context" in data
        assert "top_priority_jobs" in data

    def test_progress_values(self):
        data = client.get("/api/interview/progress").json()
        assert data["total_jobs"] > 0
        assert data["total_cost_codes_with_data"] > 0


class TestStaticFiles:
    def test_index_html_served(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "WEIS" in r.text

    def test_css_served(self):
        r = client.get("/static/styles.css")
        assert r.status_code == 200
        assert "--wollam-navy" in r.text

    def test_js_served(self):
        r = client.get("/static/app.js")
        assert r.status_code == 200
        assert "navigate" in r.text
