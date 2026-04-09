"""Tests for document upload, extraction, and API endpoints."""

import io
import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_connection
from app.services.document_extract import extract_text

client = TestClient(app)


# ── Extraction Tests ──


class TestTextExtraction:
    """Test text extraction from various file types."""

    def test_extract_txt(self, tmp_path):
        """Extract text from a plain text file."""
        f = tmp_path / "test.txt"
        f.write_text("Line 1\nLine 2\nLine 3")
        result = extract_text(f)
        assert "Line 1" in result
        assert "Line 3" in result

    def test_extract_csv(self, tmp_path):
        """Extract text from a CSV file."""
        f = tmp_path / "test.csv"
        with open(f, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Cost Code", "Description", "Amount"])
            writer.writerow(["1010", "Excavation", "50000"])
            writer.writerow(["2020", "Concrete", "120000"])
        result = extract_text(f)
        assert "Cost Code" in result
        assert "Excavation" in result
        assert "120000" in result

    def test_extract_unsupported_type(self, tmp_path):
        """Unsupported file types raise ValueError."""
        f = tmp_path / "test.pptx"
        f.write_bytes(b"fake content")
        with pytest.raises(ValueError, match="Unsupported"):
            extract_text(f)

    def test_extract_txt_truncation(self, tmp_path):
        """Very large files are truncated."""
        f = tmp_path / "big.txt"
        f.write_text("x" * 100_000)
        result = extract_text(f)
        assert len(result) <= 80_000


# ── API Tests ──


class TestDocumentAPI:
    """Test document upload and management API."""

    @pytest.fixture
    def job_id(self):
        """Get a valid job_id from the database."""
        conn = get_connection()
        row = conn.execute("SELECT job_id FROM job LIMIT 1").fetchone()
        conn.close()
        if not row:
            pytest.skip("No jobs in database")
        return row["job_id"]

    def test_upload_txt(self, job_id):
        """Upload a text file."""
        import uuid
        fname = f"test_co_{uuid.uuid4().hex[:8]}.txt"
        content = b"This is a test change order log.\nCO #1: Added 500 LF of pipe."
        resp = client.post(
            f"/api/documents/upload/{job_id}",
            files={"file": (fname, io.BytesIO(content), "text/plain")},
            data={"doc_type": "change_order"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == fname
        assert data["doc_type"] == "change_order"
        assert data["text_length"] > 0
        assert data["extraction_error"] is None

        # Cleanup
        client.delete(f"/api/documents/{data['id']}")

    def test_upload_csv(self, job_id):
        """Upload a CSV file."""
        import uuid
        fname = f"test_kpi_{uuid.uuid4().hex[:8]}.csv"
        csv_content = "Cost Code,Description,Hours\n1010,Excavation,500\n2020,Concrete,1200\n"
        resp = client.post(
            f"/api/documents/upload/{job_id}",
            files={"file": (fname, io.BytesIO(csv_content.encode()), "text/csv")},
            data={"doc_type": "production_kpi"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["doc_type"] == "production_kpi"
        assert data["text_length"] > 0

        # Cleanup
        client.delete(f"/api/documents/{data['id']}")

    def test_upload_bad_extension(self, job_id):
        """Unsupported file types are rejected."""
        resp = client.post(
            f"/api/documents/upload/{job_id}",
            files={"file": ("test.docx", io.BytesIO(b"fake"), "application/octet-stream")},
            data={"doc_type": "other"},
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    def test_upload_nonexistent_job(self):
        """Upload to nonexistent job returns 404."""
        resp = client.post(
            "/api/documents/upload/99999",
            files={"file": ("test.txt", io.BytesIO(b"content"), "text/plain")},
            data={"doc_type": "other"},
        )
        assert resp.status_code == 404

    def test_list_documents(self, job_id):
        """List documents for a job."""
        # Upload a file first
        resp = client.post(
            f"/api/documents/upload/{job_id}",
            files={"file": ("list_test.txt", io.BytesIO(b"test content"), "text/plain")},
            data={"doc_type": "other"},
        )
        doc_id = resp.json()["id"]

        # List
        resp = client.get(f"/api/documents/list/{job_id}")
        assert resp.status_code == 200
        docs = resp.json()
        assert len(docs) >= 1
        assert any(d["id"] == doc_id for d in docs)

        # Cleanup
        client.delete(f"/api/documents/{doc_id}")

    def test_delete_document(self, job_id):
        """Delete a document."""
        # Upload
        resp = client.post(
            f"/api/documents/upload/{job_id}",
            files={"file": ("delete_test.txt", io.BytesIO(b"delete me"), "text/plain")},
            data={"doc_type": "other"},
        )
        doc_id = resp.json()["id"]

        # Delete
        resp = client.delete(f"/api/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Verify gone
        resp = client.get(f"/api/documents/list/{job_id}")
        docs = resp.json()
        assert not any(d["id"] == doc_id for d in docs)

    def test_delete_nonexistent(self):
        """Delete nonexistent document returns 404."""
        resp = client.delete("/api/documents/99999")
        assert resp.status_code == 404

    def test_document_summary(self, job_id):
        """Summary endpoint returns counts."""
        resp = client.get(f"/api/documents/summary/{job_id}")
        assert resp.status_code == 200

    def test_job_detail_includes_doc_summary(self, job_id):
        """Job detail should include doc_summary field."""
        resp = client.get(f"/api/interview/job/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "doc_summary" in data
