"""
HeavyBid API Wrapper

HeavyBid is HCSS's estimating system. It contains what was planned:
bid assumptions, cost buildup, resource rates, material takeoffs.

Comparing HeavyBid (planned) to HeavyJob (actual) is the core of
estimating intelligence — it tells you where the estimate was right,
where it was wrong, and what to adjust for next time.

Key endpoints (per HCSS API spec — v2 integration paths):
    /api/v2/integration/businessunits                          — List business units
    /api/v2/integration/businessunits/{buId}/estimates          — List estimates
    /api/v2/integration/businessunits/{buId}/biditems           — Bid items (filtered by estimateId)
    /api/v2/integration/businessunits/{buId}/activities         — Activities (filtered by estimateId)
    /api/v2/integration/businessunits/{buId}/resources          — Resources (filtered by estimateId)
    /api/v2/integration/businessunits/{buId}/materials          — Materials (filtered by estimateId)
    /api/v2/integration/activityCodebook                       — Activity code reference
    /api/v2/integration/materialCodebook                       — Material code reference
"""

from __future__ import annotations

from app.hcss.client import HCSSClient
from app.hcss.models import HBActivity, HBBidItem, HBEstimate, HBResource


class HeavyBidAPI:
    """
    Typed wrapper for HeavyBid API endpoints.

    Uses the v2 integration endpoint pattern where business unit ID
    is a path segment and estimate filtering uses OData-style $filter.

    Usage:
        auth = HCSSAuth()
        client = HCSSClient(auth, base_url="https://api.hcssapps.com/heavybid-estimate-insights")
        hb = HeavyBidAPI(client, business_unit_id="abc-123")
        estimates = await hb.get_estimates()
    """

    def __init__(self, client: HCSSClient, business_unit_id: str):
        """
        Args:
            client: Authenticated HCSSClient instance.
            business_unit_id: HCSS business unit UUID.
        """
        self._client = client
        self._bu_id = business_unit_id

    @property
    def _bu_path(self) -> str:
        """Base path prefix with business unit ID."""
        return f"/api/v2/integration/businessunits/{self._bu_id}"

    async def get_estimates(self) -> list[HBEstimate]:
        """
        List all estimates for the business unit.

        Returns:
            List of HBEstimate models.
        """
        records = await self._client.get_paginated(f"{self._bu_path}/estimates")
        return [HBEstimate.model_validate(r) for r in records]

    async def get_estimate(self, estimate_id: str) -> HBEstimate:
        """
        Get a single estimate by its HCSS UUID.

        Args:
            estimate_id: HCSS estimate UUID.

        Returns:
            HBEstimate model.
        """
        # Filter estimates list for the specific ID
        data = await self._client.get(
            f"{self._bu_path}/estimates",
            params={"$filter": f"estimateId eq '{estimate_id}'"},
        )
        records = data if isinstance(data, list) else data.get("data", data.get("items", [data]))
        if records:
            return HBEstimate.model_validate(records[0])
        raise ValueError(f"Estimate {estimate_id} not found")

    async def get_biditems(self, estimate_id: str) -> list[HBBidItem]:
        """
        Get bid items (pay items / scheduled values) for an estimate.

        Bid items are the owner's line items — what they pay us for.
        Uses $filter to scope to a specific estimate.

        Args:
            estimate_id: HCSS estimate UUID.

        Returns:
            List of HBBidItem models.
        """
        records = await self._client.get_paginated(
            f"{self._bu_path}/biditems",
            params={"$filter": f"estimateId eq '{estimate_id}'"},
        )
        return [HBBidItem.model_validate(r) for r in records]

    async def get_activities(self, estimate_id: str) -> list[HBActivity]:
        """
        Get activities (cost buildup) for an estimate.

        Activities are the estimator's detail — how each bid item is priced.
        Breaks cost into labor, equipment, material, and subcontract.

        Args:
            estimate_id: HCSS estimate UUID.

        Returns:
            List of HBActivity models.
        """
        records = await self._client.get_paginated(
            f"{self._bu_path}/activities",
            params={"$filter": f"estimateId eq '{estimate_id}'"},
        )
        return [HBActivity.model_validate(r) for r in records]

    async def get_resources(self, estimate_id: str) -> list[HBResource]:
        """
        Get labor and equipment resources for an estimate.

        Resources are the rate book — what rate was assumed for each
        worker type or piece of equipment in the estimate.

        Args:
            estimate_id: HCSS estimate UUID.

        Returns:
            List of HBResource models.
        """
        records = await self._client.get_paginated(
            f"{self._bu_path}/resources",
            params={"$filter": f"estimateId eq '{estimate_id}'"},
        )
        return [HBResource.model_validate(r) for r in records]

    async def get_materials(self, estimate_id: str) -> list[dict]:
        """
        Get material items for an estimate.

        Returns raw dicts — exact response schema validated during Phase C.

        Args:
            estimate_id: HCSS estimate UUID.

        Returns:
            List of material records.
        """
        return await self._client.get_paginated(
            f"{self._bu_path}/materials",
            params={"$filter": f"estimateId eq '{estimate_id}'"},
        )

    async def get_activity_codebook(self) -> list[dict]:
        """
        Get the activity codebook (reference table for activity codes).

        Business-unit-level reference, not estimate-specific.

        Returns:
            List of activity code records.
        """
        return await self._client.get_paginated(
            "/api/v2/integration/activityCodebook",
            params={"businessUnitId": self._bu_id},
        )

    async def get_material_codebook(self) -> list[dict]:
        """
        Get the material codebook (reference table for material codes).

        Business-unit-level reference, not estimate-specific.

        Returns:
            List of material code records.
        """
        return await self._client.get_paginated(
            "/api/v2/integration/materialCodebook",
            params={"businessUnitId": self._bu_id},
        )
