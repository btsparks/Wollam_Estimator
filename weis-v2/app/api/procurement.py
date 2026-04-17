"""Procurement Register API — per-bid items, solicitations, gap analysis."""

import io
import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel

from app.database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bidding", tags=["procurement"])


class ProcurementCreate(BaseModel):
    name: str
    description: Optional[str] = None
    procurement_type: str = "subcontract"
    trade_match: Optional[str] = None
    status: str = "not_started"
    priority: str = "normal"
    target_send_date: Optional[str] = None
    notes: Optional[str] = None


class ProcurementUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    procurement_type: Optional[str] = None
    trade_match: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    target_send_date: Optional[str] = None
    notes: Optional[str] = None


class SolicitationCreate(BaseModel):
    vendor_id: Optional[int] = None
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    date_sent: Optional[str] = None
    date_expected: Optional[str] = None
    status: str = "not_sent"
    notes: Optional[str] = None


class SolicitationUpdate(BaseModel):
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    date_sent: Optional[str] = None
    date_expected: Optional[str] = None
    date_received: Optional[str] = None
    quote_amount: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class SOVLinkBody(BaseModel):
    sov_item_ids: list[int]


class AcceptSuggestions(BaseModel):
    suggestions: list[dict]


# ── Procurement Items ──────────────────────────────────────────


@router.get("/bids/{bid_id}/procurement")
async def list_procurement(
    bid_id: int,
    status: Optional[str] = Query(None),
    procurement_type: Optional[str] = Query(None),
):
    """List procurement items with solicitations and linked SOV items."""
    conn = get_connection()
    try:
        query = "SELECT * FROM procurement_item WHERE bid_id = ?"
        params: list = [bid_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        if procurement_type:
            query += " AND procurement_type = ?"
            params.append(procurement_type)
        query += " ORDER BY created_at ASC"

        items = conn.execute(query, params).fetchall()
        result = []
        for item in items:
            d = dict(item)
            # Solicitations
            sols = conn.execute(
                "SELECT * FROM procurement_solicitation WHERE procurement_item_id = ? ORDER BY created_at",
                (item["id"],),
            ).fetchall()
            d["solicitations"] = [dict(s) for s in sols]
            # Linked SOV items
            links = conn.execute(
                """SELECT psl.sov_item_id, s.item_number, s.description
                   FROM procurement_sov_link psl
                   JOIN bid_sov_item s ON psl.sov_item_id = s.id
                   WHERE psl.procurement_item_id = ?""",
                (item["id"],),
            ).fetchall()
            d["sov_links"] = [dict(l) for l in links]
            result.append(d)
        return result
    finally:
        conn.close()


@router.post("/bids/{bid_id}/procurement")
async def create_procurement(bid_id: int, body: ProcurementCreate):
    """Create a procurement item."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO procurement_item
               (bid_id, name, description, procurement_type, trade_match, status, priority, target_send_date, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bid_id, body.name, body.description, body.procurement_type, body.trade_match,
             body.status, body.priority, body.target_send_date, body.notes),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM procurement_item WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.put("/procurement/{item_id}")
async def update_procurement(item_id: int, body: ProcurementUpdate):
    """Update a procurement item."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM procurement_item WHERE id = ?", (item_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Procurement item not found")

        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            return dict(existing)
        updates["updated_at"] = datetime.now(tz=timezone.utc).isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [item_id]
        conn.execute(f"UPDATE procurement_item SET {set_clause} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM procurement_item WHERE id = ?", (item_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/procurement/{item_id}")
async def delete_procurement(item_id: int):
    """Delete procurement item and cascade solicitations."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM procurement_item WHERE id = ?", (item_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Procurement item not found")
        conn.execute("DELETE FROM procurement_solicitation WHERE procurement_item_id = ?", (item_id,))
        conn.execute("DELETE FROM procurement_sov_link WHERE procurement_item_id = ?", (item_id,))
        conn.execute("DELETE FROM procurement_item WHERE id = ?", (item_id,))
        conn.commit()
        return {"deleted": True, "item_id": item_id}
    finally:
        conn.close()


@router.post("/bids/{bid_id}/procurement/analyze-gaps")
async def analyze_gaps(bid_id: int):
    """Run AI gap analysis, returns suggestions with scope context."""
    from app.services.procurement_analyzer import analyze_procurement_gaps
    suggestions = analyze_procurement_gaps(bid_id)

    # Add context about work_type designations for user guidance
    conn = get_connection()
    try:
        counts = conn.execute(
            """SELECT
                SUM(CASE WHEN COALESCE(in_scope, 1) = 1 THEN 1 ELSE 0 END) as in_scope,
                SUM(CASE WHEN COALESCE(in_scope, 1) = 1 AND work_type = 'subcontract' THEN 1 ELSE 0 END) as subcontract,
                SUM(CASE WHEN COALESCE(in_scope, 1) = 1 AND work_type = 'self_perform' THEN 1 ELSE 0 END) as self_perform,
                SUM(CASE WHEN COALESCE(in_scope, 1) = 1 AND (work_type IS NULL OR work_type = 'undecided') THEN 1 ELSE 0 END) as undecided
               FROM bid_sov_item WHERE bid_id = ?""",
            (bid_id,),
        ).fetchone()
    finally:
        conn.close()

    return {
        "suggestions": suggestions,
        "count": len(suggestions),
        "scope_context": {
            "in_scope": counts["in_scope"] or 0,
            "subcontract": counts["subcontract"] or 0,
            "self_perform": counts["self_perform"] or 0,
            "undecided": counts["undecided"] or 0,
        },
    }


@router.post("/bids/{bid_id}/procurement/accept-suggestions")
async def accept_suggestions(bid_id: int, body: AcceptSuggestions):
    """Accept selected AI suggestions — creates procurement items."""
    conn = get_connection()
    try:
        created = 0
        for s in body.suggestions:
            cursor = conn.execute(
                """INSERT INTO procurement_item
                   (bid_id, name, procurement_type, trade_match, ai_suggested, ai_source, status)
                   VALUES (?, ?, ?, ?, 1, ?, 'not_started')""",
                (bid_id, s.get("name"), s.get("procurement_type", "subcontract"),
                 s.get("trade_match"), s.get("ai_source")),
            )
            item_id = cursor.lastrowid
            # Link SOV items if provided
            for sov_id in s.get("related_sov_items", []):
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO procurement_sov_link (procurement_item_id, sov_item_id) VALUES (?, ?)",
                        (item_id, sov_id),
                    )
                except Exception:
                    pass
            created += 1
        conn.commit()
        return {"created": created}
    finally:
        conn.close()


@router.get("/bids/{bid_id}/procurement/dashboard")
async def procurement_dashboard(bid_id: int):
    """Summary stats for procurement status bar."""
    conn = get_connection()
    try:
        items = conn.execute(
            "SELECT status FROM procurement_item WHERE bid_id = ?", (bid_id,)
        ).fetchall()
        total = len(items)
        by_status = {}
        for i in items:
            by_status[i["status"]] = by_status.get(i["status"], 0) + 1

        sol_count = conn.execute(
            """SELECT COUNT(*) as cnt FROM procurement_solicitation ps
               JOIN procurement_item pi ON ps.procurement_item_id = pi.id
               WHERE pi.bid_id = ?""",
            (bid_id,),
        ).fetchone()["cnt"]

        quotes = conn.execute(
            """SELECT COUNT(*) as cnt FROM procurement_solicitation ps
               JOIN procurement_item pi ON ps.procurement_item_id = pi.id
               WHERE pi.bid_id = ? AND ps.status = 'received'""",
            (bid_id,),
        ).fetchone()["cnt"]

        no_vendors = conn.execute(
            """SELECT COUNT(*) as cnt FROM procurement_item pi
               WHERE pi.bid_id = ? AND pi.id NOT IN (
                   SELECT DISTINCT procurement_item_id FROM procurement_solicitation
               )""",
            (bid_id,),
        ).fetchone()["cnt"]

        return {
            "total_items": total,
            "by_status": by_status,
            "rfps_sent": sol_count,
            "quotes_received": quotes,
            "no_vendors": no_vendors,
        }
    finally:
        conn.close()


@router.get("/bids/{bid_id}/procurement/export")
async def export_procurement(bid_id: int):
    """Export procurement register as Excel."""
    conn = get_connection()
    try:
        items = conn.execute(
            "SELECT * FROM procurement_item WHERE bid_id = ? ORDER BY created_at", (bid_id,)
        ).fetchall()
    finally:
        conn.close()

    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Procurement Register"
        ws.append(["Name", "Type", "Trade", "Status", "Priority", "Send Date", "Notes", "AI Suggested"])
        for r in items:
            ws.append([r["name"], r["procurement_type"], r["trade_match"], r["status"],
                       r["priority"], r["target_send_date"], r["notes"],
                       "Yes" if r["ai_suggested"] else ""])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f"attachment; filename=procurement_bid_{bid_id}.xlsx"})
    except ImportError:
        import csv
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Name", "Type", "Trade", "Status", "Priority", "Send Date", "Notes", "AI Suggested"])
        for r in items:
            writer.writerow([r["name"], r["procurement_type"], r["trade_match"], r["status"],
                             r["priority"], r["target_send_date"], r["notes"], r["ai_suggested"]])
        return Response(content=buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=procurement_bid_{bid_id}.csv"})


# ── Solicitations ──────────────────────────────────────────────


@router.post("/procurement/{item_id}/solicitations")
async def add_solicitation(item_id: int, body: SolicitationCreate):
    """Add a solicitation to a procurement item."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT id FROM procurement_item WHERE id = ?", (item_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Procurement item not found")

        # Auto-populate from vendor directory if vendor_id provided
        company = body.company_name
        contact = body.contact_name
        email = body.contact_email
        phone = body.contact_phone
        if body.vendor_id:
            vendor = conn.execute("SELECT * FROM vendor_directory WHERE id = ?", (body.vendor_id,)).fetchone()
            if vendor:
                company = company or vendor["company"]
                contact = contact or vendor["contact_name"]
                email = email or vendor["email"]
                phone = phone or vendor["phone"]

        cursor = conn.execute(
            """INSERT INTO procurement_solicitation
               (procurement_item_id, vendor_id, company_name, contact_name, contact_email,
                contact_phone, date_sent, date_expected, status, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item_id, body.vendor_id, company, contact, email, phone,
             body.date_sent, body.date_expected, body.status, body.notes),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM procurement_solicitation WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.put("/procurement/solicitations/{sol_id}")
async def update_solicitation(sol_id: int, body: SolicitationUpdate):
    """Update a solicitation."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM procurement_solicitation WHERE id = ?", (sol_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Solicitation not found")

        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            return dict(existing)
        updates["updated_at"] = datetime.now(tz=timezone.utc).isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [sol_id]
        conn.execute(f"UPDATE procurement_solicitation SET {set_clause} WHERE id = ?", values)
        conn.commit()
        row = conn.execute("SELECT * FROM procurement_solicitation WHERE id = ?", (sol_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/procurement/solicitations/{sol_id}")
async def delete_solicitation(sol_id: int):
    """Delete a solicitation."""
    conn = get_connection()
    try:
        existing = conn.execute("SELECT * FROM procurement_solicitation WHERE id = ?", (sol_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Solicitation not found")
        conn.execute("DELETE FROM procurement_solicitation WHERE id = ?", (sol_id,))
        conn.commit()
        return {"deleted": True, "solicitation_id": sol_id}
    finally:
        conn.close()


@router.get("/procurement/{item_id}/suggest-vendors")
async def suggest_vendors_for_item(item_id: int):
    """Suggest vendors from directory matching this item's trade."""
    from app.services.procurement_analyzer import suggest_vendors
    return suggest_vendors(item_id)


# ── SOV Linkage ────────────────────────────────────────────────


@router.post("/procurement/{item_id}/link-sov")
async def link_sov(item_id: int, body: SOVLinkBody):
    """Link procurement item to SOV items."""
    conn = get_connection()
    try:
        for sov_id in body.sov_item_ids:
            conn.execute(
                "INSERT OR IGNORE INTO procurement_sov_link (procurement_item_id, sov_item_id) VALUES (?, ?)",
                (item_id, sov_id),
            )
        conn.commit()
        return {"linked": len(body.sov_item_ids), "procurement_item_id": item_id}
    finally:
        conn.close()


@router.delete("/procurement/{item_id}/link-sov/{sov_item_id}")
async def unlink_sov(item_id: int, sov_item_id: int):
    """Unlink a SOV item from procurement item."""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM procurement_sov_link WHERE procurement_item_id = ? AND sov_item_id = ?",
            (item_id, sov_item_id),
        )
        conn.commit()
        return {"unlinked": True}
    finally:
        conn.close()
