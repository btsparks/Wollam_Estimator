"""Bidding Platform API — Bid Board, Documents, Schedule of Values, Pricing Groups.

Separate from estimates.py which serves HeavyBid historicals.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel

from app.config import BID_DOCUMENTS_DIR
from app.database import get_connection
from app.services.document_extract import extract_text
from app.services.sov_parser import parse_sov_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bidding", tags=["bidding"])

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv", ".txt", ".docx", ".doc"}

DOC_CATEGORIES = {
    "spec", "drawing", "contract", "bid_schedule", "rfi_clarification",
    "addendum_package", "bond_form", "insurance", "general",
}


# ── Request/Response Models ─────────────────────────────────────

class BidCreate(BaseModel):
    bid_name: str
    bid_number: Optional[str] = None
    owner: Optional[str] = None
    general_contractor: Optional[str] = None
    bid_date: Optional[str] = None
    bid_due_time: Optional[str] = None
    project_type: Optional[str] = None
    location: Optional[str] = None
    estimated_value: Optional[float] = None
    description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    status: Optional[str] = "active"
    notes: Optional[str] = None


class BidUpdate(BaseModel):
    bid_name: Optional[str] = None
    bid_number: Optional[str] = None
    owner: Optional[str] = None
    general_contractor: Optional[str] = None
    bid_date: Optional[str] = None
    bid_due_time: Optional[str] = None
    project_type: Optional[str] = None
    location: Optional[str] = None
    estimated_value: Optional[float] = None
    description: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class DocUpdate(BaseModel):
    doc_category: Optional[str] = None
    doc_label: Optional[str] = None
    addendum_number: Optional[int] = None
    date_received: Optional[str] = None
    notes: Optional[str] = None


class SOVItemCreate(BaseModel):
    item_number: Optional[str] = None
    description: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    notes: Optional[str] = None
    pricing_group_id: Optional[int] = None


class SOVItemUpdate(BaseModel):
    item_number: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    notes: Optional[str] = None
    pricing_group_id: Optional[int] = None


class SOVConfirm(BaseModel):
    items: list[dict]


class ReorderRequest(BaseModel):
    item_ids: list[int]


class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class AssignItems(BaseModel):
    item_ids: list[int]


# ── Bid CRUD ─────────────────────────────────────────────────────

@router.get("/bids")
async def list_bids(status: Optional[str] = Query(None)):
    """List all bids with optional status filter."""
    conn = get_connection()
    try:
        if status:
            bids = conn.execute(
                "SELECT * FROM active_bids WHERE status = ? ORDER BY bid_date ASC",
                (status,),
            ).fetchall()
        else:
            bids = conn.execute(
                "SELECT * FROM active_bids ORDER BY bid_date ASC"
            ).fetchall()

        result = []
        for b in bids:
            bid = dict(b)
            # Add doc count and sov count
            doc_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM bid_documents WHERE bid_id = ?",
                (b["id"],),
            ).fetchone()["cnt"]
            sov_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM bid_sov_item WHERE bid_id = ?",
                (b["id"],),
            ).fetchone()["cnt"]
            bid["doc_count"] = doc_count
            bid["sov_count"] = sov_count
            result.append(bid)

        return result
    finally:
        conn.close()


@router.post("/bids")
async def create_bid(bid: BidCreate):
    """Create a new bid project."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO active_bids
               (bid_name, bid_number, owner, general_contractor, bid_date, bid_due_time,
                project_type, location, estimated_value, description, contact_name,
                contact_email, status, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bid.bid_name, bid.bid_number, bid.owner, bid.general_contractor,
                bid.bid_date, bid.bid_due_time, bid.project_type, bid.location,
                bid.estimated_value, bid.description, bid.contact_name,
                bid.contact_email, bid.status, bid.notes,
            ),
        )
        conn.commit()
        bid_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.get("/bids/{bid_id}")
async def get_bid(bid_id: int):
    """Get bid detail with counts."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bid not found")

        bid = dict(row)
        bid["doc_count"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM bid_documents WHERE bid_id = ?", (bid_id,)
        ).fetchone()["cnt"]
        bid["sov_count"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM bid_sov_item WHERE bid_id = ?", (bid_id,)
        ).fetchone()["cnt"]
        bid["group_count"] = conn.execute(
            "SELECT COUNT(*) as cnt FROM pricing_group WHERE bid_id = ?", (bid_id,)
        ).fetchone()["cnt"]
        return bid
    finally:
        conn.close()


@router.put("/bids/{bid_id}")
async def update_bid(bid_id: int, bid: BidUpdate):
    """Update bid fields."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Bid not found")

        updates = {k: v for k, v in bid.model_dump().items() if v is not None}
        if not updates:
            return dict(existing)

        updates["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [bid_id]

        conn.execute(f"UPDATE active_bids SET {set_clause} WHERE id = ?", values)
        conn.commit()

        row = conn.execute("SELECT * FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/bids/{bid_id}")
async def delete_bid(bid_id: int):
    """Delete bid and all children (cascade)."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Bid not found")

        # Delete children first (foreign key order)
        conn.execute("DELETE FROM bid_document_chunks WHERE bid_id = ?", (bid_id,))
        conn.execute("DELETE FROM bid_documents WHERE bid_id = ?", (bid_id,))
        conn.execute("DELETE FROM bid_sov_item WHERE bid_id = ?", (bid_id,))
        conn.execute("DELETE FROM pricing_group WHERE bid_id = ?", (bid_id,))
        conn.execute("DELETE FROM active_bids WHERE id = ?", (bid_id,))
        conn.commit()

        # Clean up files
        bid_dir = BID_DOCUMENTS_DIR / str(bid_id)
        if bid_dir.exists():
            shutil.rmtree(bid_dir)

        return {"deleted": True, "bid_id": bid_id}
    finally:
        conn.close()


# ── Document Management ──────────────────────────────────────────

@router.post("/bids/{bid_id}/documents")
async def upload_document(
    bid_id: int,
    file: UploadFile = File(...),
    addendum_number: int = Form(0),
    doc_category: str = Form("general"),
    date_received: Optional[str] = Form(None),
):
    """Upload a document with metadata."""
    conn = get_connection()
    try:
        # Verify bid exists
        bid = conn.execute("SELECT id FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")

        # Validate file type
        suffix = Path(file.filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {suffix}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            )

        # Validate category
        if doc_category not in DOC_CATEGORIES:
            doc_category = "general"

        # Save file to disk
        bid_dir = BID_DOCUMENTS_DIR / str(bid_id)
        bid_dir.mkdir(parents=True, exist_ok=True)

        file_path = bid_dir / file.filename
        content = await file.read()
        file_path.write_bytes(content)

        file_hash = hashlib.sha256(content).hexdigest()
        file_size = len(content)

        # Extract text
        extracted_text = ""
        extraction_status = "pending"
        extraction_warning = None
        page_count = None
        word_count = None

        try:
            extracted_text = extract_text(file_path)
            extraction_status = "complete"
            word_count = len(extracted_text.split()) if extracted_text else 0
            if suffix == ".pdf":
                page_count = extracted_text.count("--- Page ")
        except Exception as e:
            extraction_status = "error"
            extraction_warning = str(e)
            logger.warning(f"Text extraction failed for {file.filename}: {e}")

        # Insert document record
        cursor = conn.execute(
            """INSERT INTO bid_documents
               (bid_id, filename, file_type, file_size_bytes, doc_category,
                extraction_status, extraction_warning, page_count, word_count,
                file_hash, addendum_number, date_received, file_path, extracted_text)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bid_id, file.filename, suffix, file_size, doc_category,
                extraction_status, extraction_warning, page_count, word_count,
                file_hash, addendum_number, date_received, str(file_path),
                extracted_text,
            ),
        )
        conn.commit()

        doc_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM bid_documents WHERE id = ?", (doc_id,)).fetchone()
        result = dict(row)
        # Don't send full extracted text in response
        result.pop("extracted_text", None)
        return result
    finally:
        conn.close()


@router.get("/bids/{bid_id}/documents")
async def list_documents(
    bid_id: int,
    addendum_number: Optional[int] = Query(None),
    doc_category: Optional[str] = Query(None),
):
    """List documents for a bid, filterable by addendum or category."""
    conn = get_connection()
    try:
        query = "SELECT * FROM bid_documents WHERE bid_id = ?"
        params: list = [bid_id]

        if addendum_number is not None:
            query += " AND addendum_number = ?"
            params.append(addendum_number)
        if doc_category:
            query += " AND doc_category = ?"
            params.append(doc_category)

        query += " ORDER BY addendum_number ASC, created_at ASC"

        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            # Don't send full extracted text in list view
            d.pop("extracted_text", None)
            result.append(d)
        return result
    finally:
        conn.close()


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int):
    """Get single document detail including extracted text."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM bid_documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        return dict(row)
    finally:
        conn.close()


@router.put("/documents/{doc_id}")
async def update_document(doc_id: int, update: DocUpdate):
    """Update document metadata."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM bid_documents WHERE id = ?", (doc_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Document not found")

        updates = {k: v for k, v in update.model_dump().items() if v is not None}
        if not updates:
            result = dict(existing)
            result.pop("extracted_text", None)
            return result

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [doc_id]
        conn.execute(f"UPDATE bid_documents SET {set_clause} WHERE id = ?", values)
        conn.commit()

        row = conn.execute("SELECT * FROM bid_documents WHERE id = ?", (doc_id,)).fetchone()
        result = dict(row)
        result.pop("extracted_text", None)
        return result
    finally:
        conn.close()


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int):
    """Delete document and its chunks."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM bid_documents WHERE id = ?", (doc_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Document not found")

        conn.execute("DELETE FROM bid_document_chunks WHERE document_id = ?", (doc_id,))
        conn.execute("DELETE FROM bid_documents WHERE id = ?", (doc_id,))
        conn.commit()

        # Clean up file
        if existing["file_path"]:
            fp = Path(existing["file_path"])
            if fp.exists():
                fp.unlink()

        return {"deleted": True, "doc_id": doc_id}
    finally:
        conn.close()


# ── Schedule of Values ───────────────────────────────────────────

@router.post("/bids/{bid_id}/sov/upload")
async def upload_sov(bid_id: int, file: UploadFile = File(...)):
    """Upload bid schedule file, AI-parse it, return preview."""
    conn = get_connection()
    try:
        bid = conn.execute("SELECT id FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")
    finally:
        conn.close()

    # Save temp file for parsing
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    bid_dir = BID_DOCUMENTS_DIR / str(bid_id)
    bid_dir.mkdir(parents=True, exist_ok=True)
    temp_path = bid_dir / f"_sov_upload_{file.filename}"

    content = await file.read()
    temp_path.write_bytes(content)

    try:
        items = parse_sov_file(temp_path)
        return {"items": items, "count": len(items), "filename": file.filename}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()


@router.post("/bids/{bid_id}/sov/confirm")
async def confirm_sov(bid_id: int, body: SOVConfirm):
    """Confirm parsed SOV items and save to database."""
    conn = get_connection()
    try:
        bid = conn.execute("SELECT id FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")

        # Get current max sort_order
        max_sort = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) as m FROM bid_sov_item WHERE bid_id = ?",
            (bid_id,),
        ).fetchone()["m"]

        saved = 0
        for i, item in enumerate(body.items):
            conn.execute(
                """INSERT INTO bid_sov_item
                   (bid_id, item_number, description, quantity, unit, sort_order, mapped_by)
                   VALUES (?, ?, ?, ?, ?, ?, 'ai_parsed')""",
                (
                    bid_id,
                    item.get("item_number"),
                    item.get("description", ""),
                    item.get("quantity"),
                    item.get("unit"),
                    max_sort + 1 + i,
                ),
            )
            saved += 1

        conn.commit()
        return {"saved": saved, "bid_id": bid_id}
    finally:
        conn.close()


@router.get("/bids/{bid_id}/sov")
async def list_sov(bid_id: int):
    """Get all SOV items for a bid."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT s.*, pg.name as group_name
               FROM bid_sov_item s
               LEFT JOIN pricing_group pg ON s.pricing_group_id = pg.id
               WHERE s.bid_id = ?
               ORDER BY s.sort_order ASC""",
            (bid_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/bids/{bid_id}/sov")
async def add_sov_item(bid_id: int, item: SOVItemCreate):
    """Manually add a SOV item."""
    conn = get_connection()
    try:
        bid = conn.execute("SELECT id FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")

        max_sort = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) as m FROM bid_sov_item WHERE bid_id = ?",
            (bid_id,),
        ).fetchone()["m"]

        cursor = conn.execute(
            """INSERT INTO bid_sov_item
               (bid_id, item_number, description, quantity, unit, notes,
                pricing_group_id, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bid_id, item.item_number, item.description, item.quantity,
                item.unit, item.notes, item.pricing_group_id, max_sort + 1,
            ),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM bid_sov_item WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.put("/sov/reorder")
async def reorder_sov(body: ReorderRequest):
    """Reorder SOV items — item_ids in desired order."""
    conn = get_connection()
    try:
        for i, item_id in enumerate(body.item_ids):
            conn.execute(
                "UPDATE bid_sov_item SET sort_order = ? WHERE id = ?",
                (i, item_id),
            )
        conn.commit()
        return {"reordered": len(body.item_ids)}
    finally:
        conn.close()


@router.put("/sov/{item_id}")
async def update_sov_item(item_id: int, item: SOVItemUpdate):
    """Update a SOV item."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM bid_sov_item WHERE id = ?", (item_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="SOV item not found")

        updates = {}
        for k, v in item.model_dump().items():
            if v is not None:
                updates[k] = v
        # Allow setting pricing_group_id to None (ungroup)
        if "pricing_group_id" not in updates and item.pricing_group_id is None and "pricing_group_id" in item.model_fields_set:
            updates["pricing_group_id"] = None

        if not updates:
            return dict(existing)

        updates["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [item_id]
        conn.execute(f"UPDATE bid_sov_item SET {set_clause} WHERE id = ?", values)
        conn.commit()

        row = conn.execute("SELECT * FROM bid_sov_item WHERE id = ?", (item_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/sov/{item_id}")
async def delete_sov_item(item_id: int):
    """Delete a SOV item."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM bid_sov_item WHERE id = ?", (item_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="SOV item not found")

        conn.execute("DELETE FROM bid_sov_item WHERE id = ?", (item_id,))
        conn.commit()
        return {"deleted": True, "item_id": item_id}
    finally:
        conn.close()



# ── Pricing Groups ───────────────────────────────────────────────

@router.post("/bids/{bid_id}/groups")
async def create_group(bid_id: int, group: GroupCreate):
    """Create a pricing group."""
    conn = get_connection()
    try:
        bid = conn.execute("SELECT id FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")

        cursor = conn.execute(
            "INSERT INTO pricing_group (bid_id, name, description) VALUES (?, ?, ?)",
            (bid_id, group.name, group.description),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM pricing_group WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.get("/bids/{bid_id}/groups")
async def list_groups(bid_id: int):
    """List pricing groups for a bid, with item counts."""
    conn = get_connection()
    try:
        groups = conn.execute(
            "SELECT * FROM pricing_group WHERE bid_id = ? ORDER BY name ASC",
            (bid_id,),
        ).fetchall()

        result = []
        for g in groups:
            gd = dict(g)
            gd["item_count"] = conn.execute(
                "SELECT COUNT(*) as cnt FROM bid_sov_item WHERE pricing_group_id = ?",
                (g["id"],),
            ).fetchone()["cnt"]
            result.append(gd)
        return result
    finally:
        conn.close()


@router.put("/groups/{group_id}")
async def update_group(group_id: int, group: GroupUpdate):
    """Update group name/description."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM pricing_group WHERE id = ?", (group_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Pricing group not found")

        updates = {k: v for k, v in group.model_dump().items() if v is not None}
        if not updates:
            return dict(existing)

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [group_id]
        conn.execute(f"UPDATE pricing_group SET {set_clause} WHERE id = ?", values)
        conn.commit()

        row = conn.execute("SELECT * FROM pricing_group WHERE id = ?", (group_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/groups/{group_id}")
async def delete_group(group_id: int):
    """Delete group and nullify items' pricing_group_id."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM pricing_group WHERE id = ?", (group_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Pricing group not found")

        conn.execute(
            "UPDATE bid_sov_item SET pricing_group_id = NULL WHERE pricing_group_id = ?",
            (group_id,),
        )
        conn.execute("DELETE FROM pricing_group WHERE id = ?", (group_id,))
        conn.commit()
        return {"deleted": True, "group_id": group_id}
    finally:
        conn.close()


@router.post("/groups/{group_id}/assign")
async def assign_items(group_id: int, body: AssignItems):
    """Assign SOV items to a pricing group."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM pricing_group WHERE id = ?", (group_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Pricing group not found")

        for item_id in body.item_ids:
            conn.execute(
                "UPDATE bid_sov_item SET pricing_group_id = ? WHERE id = ?",
                (group_id, item_id),
            )
        conn.commit()
        return {"assigned": len(body.item_ids), "group_id": group_id}
    finally:
        conn.close()


@router.post("/groups/{group_id}/unassign")
async def unassign_items(group_id: int, body: AssignItems):
    """Remove SOV items from a pricing group."""
    conn = get_connection()
    try:
        for item_id in body.item_ids:
            conn.execute(
                "UPDATE bid_sov_item SET pricing_group_id = NULL WHERE id = ? AND pricing_group_id = ?",
                (item_id, group_id),
            )
        conn.commit()
        return {"unassigned": len(body.item_ids), "group_id": group_id}
    finally:
        conn.close()
