"""Document upload & enrichment API endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from app.config import DOCUMENTS_DIR
from app.database import get_connection
from app.services.document_extract import extract_text
from app.services.document_enrichment import enrich_from_documents

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv", ".txt"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

# Document type options
DOC_TYPES = ["change_order", "production_kpi", "rfi_submittal", "material_tracking", "other"]


@router.post("/upload/{job_id}")
async def upload_document(
    job_id: int,
    file: UploadFile = File(...),
    doc_type: str = Form("other"),
):
    """Upload a document for a job and extract its text."""
    # Validate job exists
    conn = get_connection()
    try:
        job = conn.execute(
            "SELECT job_id, job_number FROM job WHERE job_id = ?", (job_id,),
        ).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
    finally:
        conn.close()

    # Validate file extension
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Validate doc_type
    if doc_type not in DOC_TYPES:
        doc_type = "other"

    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 20 MB)")

    # Save file to disk
    job_dir = DOCUMENTS_DIR / str(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    filepath = job_dir / filename

    # Handle duplicate filenames
    if filepath.exists():
        stem = filepath.stem
        i = 1
        while filepath.exists():
            filepath = job_dir / f"{stem}_{i}{ext}"
            i += 1

    filepath.write_bytes(content)

    # Extract text
    try:
        extracted = extract_text(filepath)
    except Exception as e:
        # Save record even if extraction fails
        extracted = ""
        extraction_error = str(e)
    else:
        extraction_error = None

    # Save to database
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO job_document (job_id, filename, filepath, doc_type,
                                         file_size, extracted_text, extraction_error)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                filepath.name,
                str(filepath),
                doc_type,
                len(content),
                extracted,
                extraction_error,
            ),
        )
        conn.commit()

        # Get the inserted doc
        doc = conn.execute(
            "SELECT * FROM job_document WHERE job_id = ? AND filepath = ?",
            (job_id, str(filepath)),
        ).fetchone()

        return {
            "id": doc["id"],
            "filename": doc["filename"],
            "doc_type": doc["doc_type"],
            "file_size": doc["file_size"],
            "text_length": len(extracted),
            "extraction_error": extraction_error,
        }
    finally:
        conn.close()


@router.get("/list/{job_id}")
async def list_documents(job_id: int):
    """List all documents uploaded for a job."""
    conn = get_connection()
    try:
        docs = conn.execute(
            """SELECT id, filename, doc_type, file_size,
                      LENGTH(extracted_text) as text_length,
                      extraction_error, analyzed, analyzed_at, uploaded_at
               FROM job_document
               WHERE job_id = ?
               ORDER BY uploaded_at DESC""",
            (job_id,),
        ).fetchall()
        return [dict(d) for d in docs]
    finally:
        conn.close()


@router.delete("/{doc_id}")
async def delete_document(doc_id: int):
    """Delete a document and its file."""
    conn = get_connection()
    try:
        doc = conn.execute(
            "SELECT id, filepath FROM job_document WHERE id = ?", (doc_id,),
        ).fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Delete file from disk
        filepath = Path(doc["filepath"])
        if filepath.exists():
            filepath.unlink()

        # Delete from database
        conn.execute("DELETE FROM job_document WHERE id = ?", (doc_id,))
        conn.commit()

        return {"deleted": True}
    finally:
        conn.close()


@router.post("/enrich/{job_id}")
async def enrich_job(job_id: int):
    """Run AI enrichment on all uploaded documents for a job."""
    result = enrich_from_documents(job_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/summary/{job_id}")
async def document_summary(job_id: int):
    """Get summary of uploaded documents for a job."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT COUNT(*) as doc_count,
                      SUM(file_size) as total_size,
                      SUM(CASE WHEN analyzed = 1 THEN 1 ELSE 0 END) as analyzed_count,
                      SUM(CASE WHEN extraction_error IS NOT NULL THEN 1 ELSE 0 END) as error_count
               FROM job_document WHERE job_id = ?""",
            (job_id,),
        ).fetchone()

        if not row or row["doc_count"] == 0:
            return None

        # Get doc types breakdown
        types = conn.execute(
            """SELECT doc_type, COUNT(*) as count
               FROM job_document WHERE job_id = ?
               GROUP BY doc_type""",
            (job_id,),
        ).fetchall()

        return {
            "doc_count": row["doc_count"],
            "total_size": row["total_size"],
            "analyzed_count": row["analyzed_count"],
            "error_count": row["error_count"],
            "by_type": {t["doc_type"]: t["count"] for t in types},
        }
    finally:
        conn.close()
