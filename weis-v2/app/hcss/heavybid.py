"""
HeavyBid Estimate Insights API Client

Wraps the HCSS HeavyBid API (v2 integration endpoints) for fetching
estimate data: estimates, bid items, activities, and resources.

Uses OData-style pagination ($top/$skip/$filter) which differs from
the HeavyJob API's skip/take pattern. Pagination is handled internally
to avoid modifying the shared HCSSClient.

Base URL: https://api.hcssapps.com/heavybid/api/v2/integration
Auth: OAuth 2.0 client credentials (heavybid:read heavybid:system:read)
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.hcss.auth import HCSSAuth
from app.hcss.models import HBEstimate, HBBidItem, HBActivity, HBResource

logger = logging.getLogger(__name__)

BASE_URL = "https://api.hcssapps.com/heavybid/api/v2/integration"
DEFAULT_PAGE_SIZE = 100


class HeavyBidAPI:
    """Client for the HeavyBid Estimate Insights API."""

    def __init__(self, auth: HCSSAuth, business_unit_id: str):
        self._auth = auth
        self._bu_id = business_unit_id

    async def get_estimates(self) -> list[HBEstimate]:
        """Fetch all estimates for the business unit."""
        records = await self._odata_paginate(
            f"/businessunits/{self._bu_id}/estimates"
        )
        results = []
        for r in records:
            try:
                results.append(HBEstimate.model_validate(r))
            except Exception as e:
                logger.warning("Failed to parse estimate %s: %s", r.get("id", "?"), e)
        return results

    async def get_estimate(self, estimate_id: str) -> Optional[HBEstimate]:
        """Fetch a single estimate by ID."""
        data = await self._get(
            f"/businessunits/{self._bu_id}/estimates/{estimate_id}"
        )
        if data:
            return HBEstimate.model_validate(data)
        return None

    async def get_biditems(self, estimate_id: str) -> list[HBBidItem]:
        """Fetch all bid items for an estimate."""
        records = await self._odata_paginate(
            f"/businessunits/{self._bu_id}/biditems",
            filter_expr=f"estimateId eq {estimate_id}",
        )
        results = []
        for r in records:
            try:
                results.append(HBBidItem.model_validate(r))
            except Exception as e:
                logger.warning("Failed to parse biditem %s: %s", r.get("id", "?"), e)
        return results

    async def get_activities(self, estimate_id: str) -> list[HBActivity]:
        """Fetch all activities for an estimate."""
        records = await self._odata_paginate(
            f"/businessunits/{self._bu_id}/activities",
            filter_expr=f"estimateId eq {estimate_id}",
        )
        results = []
        for r in records:
            try:
                results.append(HBActivity.model_validate(r))
            except Exception as e:
                logger.warning("Failed to parse activity %s: %s", r.get("id", "?"), e)
        return results

    async def get_resources(self, estimate_id: str) -> list[HBResource]:
        """Fetch all resources for an estimate."""
        records = await self._odata_paginate(
            f"/businessunits/{self._bu_id}/resources",
            filter_expr=f"estimateId eq {estimate_id}",
        )
        results = []
        for r in records:
            try:
                results.append(HBResource.model_validate(r))
            except Exception as e:
                logger.warning("Failed to parse resource %s: %s", r.get("id", "?"), e)
        return results

    # ── Internal helpers ────────────────────────────────────────

    async def _get(self, path: str, params: dict = None) -> Optional[dict]:
        """Single GET request, returns the 'data' value or None."""
        token = await self._auth.get_token()
        url = f"{BASE_URL}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                url,
                params=params or {},
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                body = resp.json()
                return body.get("data", body)
            else:
                logger.warning("GET %s -> %s: %s", url, resp.status_code, resp.text[:200])
                return None

    async def _odata_paginate(
        self,
        path: str,
        filter_expr: str = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[dict]:
        """
        Paginate an OData endpoint using $top/$skip.

        The HeavyBid API wraps results in {"data": [...], "currentTopValue": N,
        "currentSkipValue": N, "nextSkipValue": N}.
        """
        token = await self._auth.get_token()
        all_records = []
        skip = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                params = {"$top": str(page_size), "$skip": str(skip)}
                if filter_expr:
                    params["$filter"] = filter_expr

                url = f"{BASE_URL}{path}"
                resp = await client.get(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )

                if resp.status_code != 200:
                    logger.warning(
                        "OData paginate %s skip=%d -> %s: %s",
                        path, skip, resp.status_code, resp.text[:200],
                    )
                    break

                body = resp.json()
                data = body.get("data", [])
                if not data:
                    break

                all_records.extend(data)
                logger.info(
                    "Fetched %d records from %s (skip=%d, total=%d)",
                    len(data), path, skip, len(all_records),
                )

                # Check if there are more pages
                next_skip = body.get("nextSkipValue")
                if next_skip is not None and next_skip > skip and len(data) == page_size:
                    skip = next_skip
                else:
                    break

        return all_records
