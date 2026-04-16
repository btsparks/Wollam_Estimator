"""SOV Intelligence Mapper API endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.database import get_connection
from app.services.sov_mapper import (
    map_intelligence_to_sov,
    get_item_intelligence,
    get_sov_intelligence_summary,
    mark_sov_intelligence_stale,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bidding", tags=["sov-intelligence"])


class MapIntelligenceRequest(BaseModel):
    sov_item_ids: Optional[list[int]] = None


class DrawingCreateRequest(BaseModel):
    drawing_number: str
    title: Optional[str] = None
    revision: Optional[str] = None
    discipline: Optional[str] = None
    source_document: Optional[str] = None
    source_addendum: Optional[int] = None


# --- SOV Intelligence Mapping ---


@router.post("/bids/{bid_id}/sov/map-intelligence")
async def api_map_intelligence(bid_id: int, body: MapIntelligenceRequest = MapIntelligenceRequest()):
    """Trigger the SOV intelligence mapper for all or specified items."""
    conn = get_connection()
    try:
        bid = conn.execute("SELECT id FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")
    finally:
        conn.close()

    try:
        result = map_intelligence_to_sov(bid_id, body.sov_item_ids)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("SOV mapping failed for bid %d: %s", bid_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bids/{bid_id}/sov/{item_id}/intelligence")
async def api_get_item_intelligence(bid_id: int, item_id: int):
    """Get all intelligence findings for a specific SOV item."""
    return get_item_intelligence(bid_id, item_id)


@router.get("/bids/{bid_id}/sov/intelligence-summary")
async def api_intelligence_summary(bid_id: int):
    """Get finding counts and max severity per SOV item for badge display."""
    return get_sov_intelligence_summary(bid_id)


@router.post("/bids/{bid_id}/sov/mark-stale")
async def api_mark_stale(bid_id: int):
    """Mark all SOV intelligence for a bid as stale."""
    count = mark_sov_intelligence_stale(bid_id)
    return {"marked_stale": count}


@router.get("/bids/{bid_id}/sov/map-intelligence-stream")
async def api_map_intelligence_stream(bid_id: int):
    """Stream SOV intelligence mapping progress via Server-Sent Events."""
    conn = get_connection()
    try:
        bid = conn.execute("SELECT id FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")
    finally:
        conn.close()

    progress_queue = queue.Queue()

    def on_progress(current, total, item_number, status):
        progress_queue.put({"type": "progress", "current": current, "total": total, "item": item_number, "status": status})

    def run_mapping():
        try:
            result = map_intelligence_to_sov(bid_id, on_progress=on_progress)
            progress_queue.put({"type": "done", "result": result})
        except Exception as e:
            progress_queue.put({"type": "error", "message": str(e)})

    thread = threading.Thread(target=run_mapping, daemon=True)
    thread.start()

    async def event_stream():
        while True:
            try:
                msg = progress_queue.get_nowait()
                yield f"data: {json.dumps(msg)}\n\n"
                if msg["type"] in ("done", "error"):
                    return
            except queue.Empty:
                # Send heartbeat comment to keep connection alive during long API calls
                yield ": heartbeat\n\n"
                await asyncio.sleep(2)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Cost Tracking ---


@router.get("/bids/{bid_id}/cost-summary")
async def api_bid_cost_summary(bid_id: int):
    """Get API cost breakdown for a specific bid."""
    from app.services.cost_tracker import get_bid_cost_summary
    return get_bid_cost_summary(bid_id)


# --- Drawing Log ---


@router.get("/bids/{bid_id}/drawings")
async def api_list_drawings(bid_id: int):
    """List all drawings in the drawing log for this bid."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM drawing_log WHERE bid_id = ? ORDER BY drawing_number",
            (bid_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/bids/{bid_id}/drawings")
async def api_create_drawing(bid_id: int, body: DrawingCreateRequest):
    """Manually add a drawing to the log."""
    conn = get_connection()
    try:
        bid = conn.execute("SELECT id FROM active_bids WHERE id = ?", (bid_id,)).fetchone()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")

        try:
            cursor = conn.execute(
                """INSERT INTO drawing_log (bid_id, drawing_number, title, revision,
                   discipline, source_document, source_addendum)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (bid_id, body.drawing_number, body.title, body.revision,
                 body.discipline, body.source_document, body.source_addendum),
            )
            conn.commit()
            return {"id": cursor.lastrowid, "drawing_number": body.drawing_number}
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                raise HTTPException(status_code=409, detail=f"Drawing {body.drawing_number} already exists for this bid")
            raise
    finally:
        conn.close()


@router.delete("/bids/{bid_id}/drawings/{drawing_id}")
async def api_delete_drawing(bid_id: int, drawing_id: int):
    """Remove a drawing from the log."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM drawing_log WHERE id = ? AND bid_id = ?",
            (drawing_id, bid_id),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Drawing not found")
        return {"deleted": True}
    finally:
        conn.close()
