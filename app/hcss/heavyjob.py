"""
HeavyJob API Wrapper

HeavyJob is HCSS's field cost tracking system. It contains what
actually happened on each project: real hours, real costs, real
quantities, real crew data.

This wrapper provides typed methods for each HeavyJob endpoint.
All methods return Pydantic models for type safety and validation.

Key endpoints (per HCSS API spec):
    /api/v1/businessUnits/{buId}/jobs              — List jobs
    /api/v1/businessUnits/{buId}/costCodes/search   — Cost codes (POST with jobIds)
    /api/v1/businessUnits/{buId}/timeCards          — Time card summaries
    /api/v1/businessUnits/{buId}/hours/employee     — Employee hours (POST)
    /api/v1/businessUnits/{buId}/hours/equipment    — Equipment hours (POST)
    /api/v1/businessUnits/{buId}/jobs/{jobId}/changeOrders  — Change orders
    /api/v1/businessUnits/{buId}/jobs/{jobId}/materials     — Materials
    /api/v1/businessUnits/{buId}/jobs/{jobId}/subcontracts  — Subcontracts
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.hcss.client import HCSSClient
from app.hcss.models import (
    HJChangeOrder,
    HJCostCode,
    HJJob,
    HJMaterial,
    HJSubcontract,
    HJTimeCard,
)


class HeavyJobAPI:
    """
    Typed wrapper for HeavyJob API endpoints.

    Each method fetches data from HeavyJob and returns validated
    Pydantic models. Pagination is handled automatically by the
    underlying HCSSClient.

    Endpoint pattern: business unit ID is a path segment, not a query param.

    Usage:
        auth = HCSSAuth()
        client = HCSSClient(auth, base_url="https://api.hcssapps.com/heavyjob")
        hj = HeavyJobAPI(client, business_unit_id="abc-123")
        jobs = await hj.get_jobs(status="Closed")
    """

    def __init__(self, client: HCSSClient, business_unit_id: str):
        """
        Args:
            client: Authenticated HCSSClient instance.
            business_unit_id: HCSS business unit UUID. Required for all queries.
        """
        self._client = client
        self._bu_id = business_unit_id

    @property
    def _bu_path(self) -> str:
        """Base path prefix with business unit ID."""
        return f"/api/v1/businessUnits/{self._bu_id}"

    async def get_jobs(self, status: str | None = None) -> list[HJJob]:
        """
        List jobs for the business unit.

        Args:
            status: Filter by job status ('Active', 'Closed', 'Pending').
                    None returns all jobs.

        Returns:
            List of HJJob models.
        """
        params: dict[str, Any] = {}
        if status:
            params["status"] = status

        records = await self._client.get_paginated(
            f"{self._bu_path}/jobs", params=params,
        )
        return [HJJob.model_validate(r) for r in records]

    async def get_job(self, job_id: str) -> HJJob:
        """
        Get a single job by its HCSS UUID.

        Args:
            job_id: HCSS job UUID.

        Returns:
            HJJob model.
        """
        data = await self._client.get(f"{self._bu_path}/jobs/{job_id}")
        return HJJob.model_validate(data)

    async def get_cost_codes(self, job_id: str) -> list[HJCostCode]:
        """
        Get all cost codes for a job with budget and actual values.

        This is the core data for rate calculation. Uses POST search
        endpoint which accepts a list of job IDs (we send one at a time
        for simplicity, but the API supports batch).

        Args:
            job_id: HCSS job UUID.

        Returns:
            List of HJCostCode models.
        """
        # HCSS uses POST search endpoint for cost codes
        data = await self._client.post(
            f"{self._bu_path}/costCodes/search",
            data={"jobIds": [job_id], "includeUnused": True},
        )
        # Response may be a list or dict with data key
        records = data if isinstance(data, list) else data.get("data", data.get("items", []))
        return [HJCostCode.model_validate(r) for r in records]

    async def get_cost_codes_batch(self, job_ids: list[str]) -> list[HJCostCode]:
        """
        Get cost codes for multiple jobs in a single API call.

        More efficient than calling get_cost_codes for each job separately.

        Args:
            job_ids: List of HCSS job UUIDs.

        Returns:
            List of HJCostCode models across all requested jobs.
        """
        data = await self._client.post(
            f"{self._bu_path}/costCodes/search",
            data={"jobIds": job_ids, "includeUnused": True},
        )
        records = data if isinstance(data, list) else data.get("data", data.get("items", []))
        return [HJCostCode.model_validate(r) for r in records]

    async def get_timecards(
        self,
        job_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[HJTimeCard]:
        """
        Get time card entries for a job.

        Time cards record daily crew labor by cost code — used for
        crew analysis and production rate calculation.

        Args:
            job_id: HCSS job UUID.
            start_date: Filter start (inclusive).
            end_date: Filter end (inclusive).

        Returns:
            List of HJTimeCard models.
        """
        params: dict[str, Any] = {"jobId": job_id}
        if start_date:
            params["startDate"] = start_date.isoformat()
        if end_date:
            params["endDate"] = end_date.isoformat()

        records = await self._client.get_paginated(
            f"{self._bu_path}/timeCards", params=params,
        )
        return [HJTimeCard.model_validate(r) for r in records]

    async def get_employee_hours(
        self,
        job_ids: list[str],
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        """
        Get aggregated employee hour summaries.

        Uses POST endpoint with job IDs and optional date range in body.

        Args:
            job_ids: List of HCSS job UUIDs.
            start_date: Filter start (inclusive).
            end_date: Filter end (inclusive).

        Returns:
            List of employee hour summary records.
        """
        body: dict[str, Any] = {"jobIds": job_ids}
        if start_date:
            body["startDate"] = start_date.isoformat()
        if end_date:
            body["endDate"] = end_date.isoformat()

        data = await self._client.post(f"{self._bu_path}/hours/employee", data=body)
        return data if isinstance(data, list) else data.get("data", data.get("items", []))

    async def get_equipment_hours(
        self,
        job_ids: list[str],
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict]:
        """
        Get aggregated equipment hour summaries.

        Uses POST endpoint with job IDs and optional date range in body.

        Args:
            job_ids: List of HCSS job UUIDs.
            start_date: Filter start (inclusive).
            end_date: Filter end (inclusive).

        Returns:
            List of equipment hour summary records.
        """
        body: dict[str, Any] = {"jobIds": job_ids}
        if start_date:
            body["startDate"] = start_date.isoformat()
        if end_date:
            body["endDate"] = end_date.isoformat()

        data = await self._client.post(f"{self._bu_path}/hours/equipment", data=body)
        return data if isinstance(data, list) else data.get("data", data.get("items", []))

    async def get_change_orders(self, job_id: str) -> list[HJChangeOrder]:
        """
        Get change orders for a job.

        CO categories tell you about project risk:
            SC (Scope Change) — owner-directed additions
            DD (Design Development) — incomplete/evolving design

        On Job 8576, DD-driven COs averaged 61% of total CO value.

        Args:
            job_id: HCSS job UUID.

        Returns:
            List of HJChangeOrder models.
        """
        records = await self._client.get_paginated(
            f"{self._bu_path}/jobs/{job_id}/changeOrders",
        )
        return [HJChangeOrder.model_validate(r) for r in records]

    async def get_forecasts(self, job_id: str) -> list[dict]:
        """
        Get forecast data for a job.

        Returns raw dicts — schema validated during Phase C.

        Args:
            job_id: HCSS job UUID.

        Returns:
            List of forecast records.
        """
        return await self._client.get_paginated(
            f"{self._bu_path}/jobs/{job_id}/forecasts",
        )

    async def get_materials(self, job_id: str) -> list[HJMaterial]:
        """
        Get material receipts for a job.

        Material data feeds cost benchmarking — e.g., concrete at $265/CY
        for mine site delivery vs $205/CY standard.

        Args:
            job_id: HCSS job UUID.

        Returns:
            List of HJMaterial models.
        """
        records = await self._client.get_paginated(
            f"{self._bu_path}/jobs/{job_id}/materials",
        )
        return [HJMaterial.model_validate(r) for r in records]

    async def get_subcontracts(self, job_id: str) -> list[HJSubcontract]:
        """
        Get subcontract data for a job.

        Subcontract data tells us what scope was subbed out, to whom,
        and at what cost — useful for sub cost benchmarking and
        scope split decisions on future bids.

        Args:
            job_id: HCSS job UUID.

        Returns:
            List of HJSubcontract models.
        """
        records = await self._client.get_paginated(
            f"{self._bu_path}/jobs/{job_id}/subcontracts",
        )
        return [HJSubcontract.model_validate(r) for r in records]
