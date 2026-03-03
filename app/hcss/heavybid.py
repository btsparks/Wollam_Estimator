"""
HeavyBid API Wrapper

HeavyBid is HCSS's estimating system. It contains what was planned:
bid assumptions, cost buildup, resource rates, material takeoffs.

Comparing HeavyBid (planned) to HeavyJob (actual) is the core of
estimating intelligence — it tells you where the estimate was right,
where it was wrong, and what to adjust for next time.

Key endpoints:
    /api/v1/estimates              — List estimates for business unit
    /api/v1/estimates/{id}/biditems   — Pay items (what the owner pays for)
    /api/v1/estimates/{id}/activities — Cost buildup (how each item is priced)
    /api/v1/estimates/{id}/resources  — Labor and equipment rates
    /api/v1/estimates/{id}/materials  — Material items
    /api/v1/activityCodebook         — Activity code reference
    /api/v1/materialCodebook         — Material code reference
"""

from __future__ import annotations

from app.hcss.client import HCSSClient
from app.hcss.models import HBActivity, HBBidItem, HBEstimate, HBResource


class HeavyBidAPI:
    """
    Typed wrapper for HeavyBid API endpoints.

    Each method fetches data from HeavyBid and returns validated
    Pydantic models. Pagination is handled automatically.

    Usage:
        auth = HCSSAuth()
        client = HCSSClient(auth, base_url="https://api.hcss.com/heavybid")
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

    async def get_estimates(self) -> list[HBEstimate]:
        """
        List all estimates for the business unit.

        Returns:
            List of HBEstimate models.
        """
        records = await self._client.get_paginated(
            "/api/v1/estimates",
            params={"businessUnitId": self._bu_id},
        )
        return [HBEstimate.model_validate(r) for r in records]

    async def get_estimate(self, estimate_id: str) -> HBEstimate:
        """
        Get a single estimate by its HCSS UUID.

        Args:
            estimate_id: HCSS estimate UUID.

        Returns:
            HBEstimate model.
        """
        data = await self._client.get(f"/api/v1/estimates/{estimate_id}")
        return HBEstimate.model_validate(data)

    async def get_biditems(self, estimate_id: str) -> list[HBBidItem]:
        """
        Get bid items (pay items / scheduled values) for an estimate.

        Bid items are the owner's line items — what they pay us for.
        Each bid item is backed by one or more activities (cost buildup).

        Args:
            estimate_id: HCSS estimate UUID.

        Returns:
            List of HBBidItem models.
        """
        records = await self._client.get_paginated(
            f"/api/v1/estimates/{estimate_id}/biditems",
        )
        return [HBBidItem.model_validate(r) for r in records]

    async def get_activities(self, estimate_id: str) -> list[HBActivity]:
        """
        Get activities (cost buildup) for an estimate.

        Activities are the estimator's detail — how each bid item is priced.
        Breaks cost into labor, equipment, material, and subcontract.
        The production rate field tells you how fast the estimator assumed
        the crew would work.

        Args:
            estimate_id: HCSS estimate UUID.

        Returns:
            List of HBActivity models.
        """
        records = await self._client.get_paginated(
            f"/api/v1/estimates/{estimate_id}/activities",
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
            f"/api/v1/estimates/{estimate_id}/resources",
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
            f"/api/v1/estimates/{estimate_id}/materials",
        )

    async def get_activity_codebook(self) -> list[dict]:
        """
        Get the activity codebook (reference table for activity codes).

        This is a business-unit-level reference, not estimate-specific.

        Returns:
            List of activity code records.
        """
        return await self._client.get_paginated(
            "/api/v1/activityCodebook",
            params={"businessUnitId": self._bu_id},
        )

    async def get_material_codebook(self) -> list[dict]:
        """
        Get the material codebook (reference table for material codes).

        This is a business-unit-level reference, not estimate-specific.

        Returns:
            List of material code records.
        """
        return await self._client.get_paginated(
            "/api/v1/materialCodebook",
            params={"businessUnitId": self._bu_id},
        )
