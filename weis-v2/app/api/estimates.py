"""
HeavyBid Estimate Insights API endpoints.

Serves synced HeavyBid estimate data and provides sync control
(list available estimates from HCSS, trigger selective sync).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.hcss.storage import (
    get_all_hb_estimates,
    get_hb_estimate_detail,
    get_hb_biditems,
    get_hb_activities,
    get_hb_resources,
    get_hb_estimates_for_job,
    upsert_hb_estimate,
    upsert_hb_biditems,
    upsert_hb_activities,
    upsert_hb_resources,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/estimates", tags=["estimates"])

BU_ID = "319078ad-cbfe-49e7-a8b4-b62fe0be273d"


# ── Request/Response Models ─────────────────────────────────────

class SyncRequest(BaseModel):
    estimate_ids: list[str]


class SyncResult(BaseModel):
    synced: int
    biditems: int
    activities: int
    resources: int
    errors: list[str]


# ── Endpoints ───────────────────────────────────────────────────

@router.get("/")
async def list_estimates(linked_job_id: Optional[int] = Query(None)):
    """List all synced estimates. Optionally filter by linked job."""
    if linked_job_id is not None:
        return get_hb_estimates_for_job(linked_job_id)
    return get_all_hb_estimates()


@router.get("/available")
async def list_available():
    """Fetch available estimates from HCSS API (live, not cached)."""
    from app.hcss.auth import HCSSAuth
    from app.hcss.heavybid import HeavyBidAPI

    auth = HCSSAuth()
    if not auth.is_configured:
        raise HTTPException(status_code=503, detail="HCSS credentials not configured")

    api = HeavyBidAPI(auth, BU_ID)
    estimates = await api.get_estimates()

    # Get already-synced estimate IDs
    synced_ids = {e["hcss_est_id"] for e in get_all_hb_estimates()}

    result = []
    for est in estimates:
        t = est.totals
        f = est.filters
        result.append({
            "hcss_est_id": est.id,
            "code": est.code,
            "name": est.name,
            "bid_total": t.bidTotal_Bid if t else None,
            "total_manhours": t.manhours_Total if t else None,
            "total_labor": t.totalLabor_Total if t else None,
            "total_equip": t.totalEqp_Total if t else None,
            "total_material": (t.permanentMaterial_Total or 0) + (t.constructionMaterial_Total or 0) if t else None,
            "total_subcontract": t.subcontract_Total if t else None,
            "state": f.state if f else None,
            "estimator": f.estimator if f else None,
            "bid_date": f.bidDate if f else None,
            "modified_date": f.modifiedDate if f else None,
            "already_synced": est.id in synced_ids,
        })
    return result


@router.post("/sync")
async def sync_estimates(req: SyncRequest) -> SyncResult:
    """Sync selected estimates from HCSS API into local DB."""
    from app.hcss.auth import HCSSAuth
    from app.hcss.heavybid import HeavyBidAPI

    auth = HCSSAuth()
    if not auth.is_configured:
        raise HTTPException(status_code=503, detail="HCSS credentials not configured")

    api = HeavyBidAPI(auth, BU_ID)

    synced = 0
    total_bi = 0
    total_act = 0
    total_res = 0
    errors = []

    for hcss_id in req.estimate_ids:
        try:
            # Fetch estimate detail
            estimate = await api.get_estimate(hcss_id)
            if not estimate:
                errors.append(f"Estimate {hcss_id} not found in HCSS")
                continue

            # Upsert estimate
            est_id = upsert_hb_estimate(estimate, BU_ID)

            # Fetch and upsert children
            biditems = await api.get_biditems(hcss_id)
            total_bi += upsert_hb_biditems(biditems, est_id)

            activities = await api.get_activities(hcss_id)
            total_act += upsert_hb_activities(activities, est_id)

            resources = await api.get_resources(hcss_id)
            total_res += upsert_hb_resources(resources, est_id)

            synced += 1
            logger.info("Synced estimate %s (%s): %d bi, %d act, %d res",
                        estimate.code, hcss_id, len(biditems), len(activities), len(resources))

        except Exception as e:
            logger.error("Failed to sync estimate %s: %s", hcss_id, e)
            errors.append(f"Error syncing {hcss_id}: {str(e)}")

    return SyncResult(
        synced=synced,
        biditems=total_bi,
        activities=total_act,
        resources=total_res,
        errors=errors,
    )


@router.get("/{estimate_id}")
async def get_estimate(estimate_id: int):
    """Get estimate detail with summary stats."""
    detail = get_hb_estimate_detail(estimate_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return detail


@router.get("/{estimate_id}/biditems")
async def get_biditems(estimate_id: int):
    """Get bid items for an estimate."""
    return get_hb_biditems(estimate_id)


@router.get("/{estimate_id}/activities")
async def get_activities(
    estimate_id: int,
    biditem_id: Optional[str] = Query(None),
):
    """Get activities for an estimate, optionally filtered by bid item."""
    return get_hb_activities(estimate_id, biditem_id)


@router.get("/{estimate_id}/resources")
async def get_resources(
    estimate_id: int,
    activity_id: Optional[str] = Query(None),
):
    """Get resources for an estimate, optionally filtered by activity."""
    return get_hb_resources(estimate_id, activity_id)
