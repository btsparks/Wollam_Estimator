"""Vendor Directory API — global CRUD, import, export."""

import io
import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel

from app.database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vendors", tags=["vendors"])


class VendorCreate(BaseModel):
    vendor_type: str = "construction"
    trade: str
    company: str
    contact_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    phone: Optional[str] = None
    cell: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    fax: Optional[str] = None
    is_dbe: Optional[int] = 0
    specialties: Optional[str] = None
    second_contact: Optional[str] = None
    second_phone: Optional[str] = None
    second_email: Optional[str] = None
    notes: Optional[str] = None


class VendorUpdate(BaseModel):
    vendor_type: Optional[str] = None
    trade: Optional[str] = None
    company: Optional[str] = None
    contact_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    phone: Optional[str] = None
    cell: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    fax: Optional[str] = None
    is_dbe: Optional[int] = None
    specialties: Optional[str] = None
    notes: Optional[str] = None


@router.get("")
async def list_vendors(
    trade: Optional[str] = Query(None),
    vendor_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    is_dbe: Optional[int] = Query(None),
    include_archived: bool = Query(False),
):
    """List vendors with optional filters."""
    conn = get_connection()
    try:
        query = "SELECT * FROM vendor_directory WHERE 1=1"
        params: list = []

        if not include_archived:
            query += " AND is_active = 1"
        if trade:
            query += " AND trade = ?"
            params.append(trade)
        if vendor_type:
            query += " AND vendor_type = ?"
            params.append(vendor_type)
        if state:
            query += " AND state = ?"
            params.append(state)
        if is_dbe is not None:
            query += " AND is_dbe = ?"
            params.append(is_dbe)
        if search:
            query += " AND (company LIKE ? OR contact_name LIKE ? OR specialties LIKE ? OR trade LIKE ?)"
            s = f"%{search}%"
            params.extend([s, s, s, s])

        query += " ORDER BY trade ASC, company ASC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/trades")
async def list_trades():
    """List unique trades with vendor counts."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT trade, vendor_type, COUNT(*) as count FROM vendor_directory WHERE is_active = 1 GROUP BY trade, vendor_type ORDER BY trade ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/export")
async def export_vendors():
    """Export full vendor directory as Excel or CSV."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT vendor_type, trade, company, contact_name, city, state, phone, cell, email, website, fax, is_dbe, specialties, is_active FROM vendor_directory ORDER BY vendor_type, trade, company"
        ).fetchall()
    finally:
        conn.close()

    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Vendor Directory"
        headers = ["Type", "Trade", "Company", "Contact", "City", "State", "Phone", "Cell", "Email", "Website", "Fax", "DBE", "Specialties", "Active"]
        ws.append(headers)
        for r in rows:
            ws.append([r["vendor_type"], r["trade"], r["company"], r["contact_name"],
                       r["city"], r["state"], r["phone"], r["cell"], r["email"],
                       r["website"], r["fax"], "Yes" if r["is_dbe"] else "",
                       r["specialties"], "Yes" if r["is_active"] else "No"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": "attachment; filename=vendor_directory.xlsx"})
    except ImportError:
        import csv
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Type", "Trade", "Company", "Contact", "City", "State", "Phone", "Cell", "Email", "Website", "Fax", "DBE", "Specialties", "Active"])
        for r in rows:
            writer.writerow([r["vendor_type"], r["trade"], r["company"], r["contact_name"],
                             r["city"], r["state"], r["phone"], r["cell"], r["email"],
                             r["website"], r["fax"], r["is_dbe"], r["specialties"], r["is_active"]])
        return Response(content=buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=vendor_directory.csv"})


@router.get("/{vendor_id}")
async def get_vendor(vendor_id: int):
    """Get single vendor detail."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM vendor_directory WHERE id = ?", (vendor_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Vendor not found")
        return dict(row)
    finally:
        conn.close()


@router.post("")
async def create_vendor(body: VendorCreate):
    """Create a vendor manually."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO vendor_directory
               (vendor_type, trade, company, contact_name, city, state, phone, cell,
                email, website, fax, is_dbe, specialties, second_contact, second_phone,
                second_email, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (body.vendor_type, body.trade, body.company, body.contact_name, body.city,
             body.state, body.phone, body.cell, body.email, body.website, body.fax,
             body.is_dbe or 0, body.specialties, body.second_contact, body.second_phone,
             body.second_email, body.notes),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM vendor_directory WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.put("/{vendor_id}")
async def update_vendor(vendor_id: int, body: VendorUpdate):
    """Update a vendor."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM vendor_directory WHERE id = ?", (vendor_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Vendor not found")

        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            return dict(existing)
        updates["updated_at"] = datetime.now(tz=timezone.utc).isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [vendor_id]
        conn.execute(f"UPDATE vendor_directory SET {set_clause} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM vendor_directory WHERE id = ?", (vendor_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/{vendor_id}")
async def delete_vendor(vendor_id: int):
    """Soft delete — set is_active = 0."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM vendor_directory WHERE id = ?", (vendor_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Vendor not found")
        conn.execute("UPDATE vendor_directory SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (vendor_id,))
        conn.commit()
        return {"archived": True, "vendor_id": vendor_id}
    finally:
        conn.close()


@router.post("/import")
async def import_vendors(file: UploadFile = File(...)):
    """Upload and import vendor Excel file."""
    import tempfile
    from app.services.vendor_import import import_vendor_excel

    suffix = ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = import_vendor_excel(tmp_path)
        return result
    finally:
        import os
        os.unlink(tmp_path)
