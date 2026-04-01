"""
HeavyJob API Wrapper

HeavyJob is HCSS's field cost tracking system. It contains what
actually happened on each project: real hours, real costs, real
quantities, real crew data.

Endpoint patterns (discovered from production API):
    /api/v1/jobs?businessUnitId={buId}              — List jobs
    /api/v1/costCodes?jobId={jobId}                 — Cost codes (GET with query param)
    /api/v1/costCodes/search                        — Cost codes (POST with jobIds)
    /api/v1/timeCardInfo?jobId={jobId}              — Time card summaries (cursor pagination)
    /api/v1/timeCards/{id}                          — Single time card detail (hours, cost codes)
    /api/v1/businessUnits                           — List business units
    /api/v1/employees?businessUnitId={buId}         — Employees
    /api/v1/forecasts?businessUnitId={buId}         — Job forecasts

Responses use {results: [...], metadata: {nextCursor: ...}} pagination format.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.hcss.client import HCSSClient
from app.hcss.models import (
    HJCostCode,
    HJEquipmentEntry,
    HJJob,
    HJTimeCard,
)


class HeavyJobAPI:
    """
    Typed wrapper for HeavyJob API endpoints.

    Each method fetches data from HeavyJob and returns validated
    Pydantic models. Pagination is handled automatically by the
    underlying HCSSClient.

    Usage:
        auth = HCSSAuth()
        client = HCSSClient(auth, base_url="https://api.hcssapps.com/heavyjob")
        hj = HeavyJobAPI(client, business_unit_id="abc-123")
        jobs = await hj.get_jobs(status="completed")
    """

    def __init__(self, client: HCSSClient, business_unit_id: str):
        self._client = client
        self._bu_id = business_unit_id

    async def get_business_units(self) -> list[dict]:
        """List all business units accessible to this client."""
        data = await self._client.get("/api/v1/businessUnits")
        return data if isinstance(data, list) else data.get("results", [data])

    async def get_jobs(self, status: str | None = None) -> list[HJJob]:
        """
        List jobs for the business unit.

        Args:
            status: Filter by status ('active', 'inactive', 'completed').
                    None returns all jobs.
        """
        params: dict[str, Any] = {"businessUnitId": self._bu_id}
        if status:
            params["status"] = status

        records = await self._client.get_paginated(
            "/api/v1/jobs", params=params,
        )
        return [HJJob.model_validate(r) for r in records]

    async def get_job(self, job_id: str) -> HJJob:
        """Get a single job by its HCSS UUID."""
        data = await self._client.get(f"/api/v1/jobs/{job_id}")
        return HJJob.model_validate(data)

    async def get_cost_codes(self, job_id: str) -> list[HJCostCode]:
        """
        Get all cost codes for a job with budget values.

        Uses query param endpoint which returns paginated results.
        """
        records = await self._client.get_paginated(
            "/api/v1/costCodes", params={"jobId": job_id},
        )
        return [HJCostCode.model_validate(r) for r in records]

    async def get_cost_codes_batch(self, job_ids: list[str]) -> list[HJCostCode]:
        """
        Get cost codes for multiple jobs via POST search endpoint.
        """
        data = await self._client.post(
            "/api/v1/costCodes/search",
            data={"jobIds": job_ids},
        )
        records = data if isinstance(data, list) else data.get("results", data.get("data", []))
        return [HJCostCode.model_validate(r) for r in records]

    async def get_timecard_summaries(
        self,
        job_id: str | None = None,
    ) -> list[dict]:
        """
        List timecard summaries for a job or entire business unit.

        Uses /api/v1/timeCardInfo with cursor-based pagination.
        Returns summary records with timecard IDs (no hours detail).
        """
        params: dict[str, Any] = {}
        if job_id:
            params["jobId"] = job_id
        else:
            params["businessUnitId"] = self._bu_id

        return await self._client.get_cursor_paginated(
            "/api/v1/timeCardInfo", params=params,
        )

    async def get_timecard_detail(self, timecard_id: str) -> dict:
        """
        Fetch full timecard detail including cost codes, employees, equipment.

        Returns nested structure with:
            costCodes: [{costCodeId, costCodeCode, quantity, unitOfMeasure, ...}]
            employees: [{employeeId, employeeCode, regularHours, overtimeHours, ...}]
            equipment: [{...}]
        """
        return await self._client.get(f"/api/v1/timeCards/{timecard_id}")

    async def get_timecards_flat(
        self,
        job_id: str,
    ) -> list[HJTimeCard]:
        """
        Get all timecards for a job, flattened to one row per employee per cost code.

        This is the main entry point for syncing actual labor hours.
        Fetches timecard summaries, then detail for each, then flattens.
        """
        summaries = await self.get_timecard_summaries(job_id=job_id)
        if not summaries:
            return []

        flat_records: list[HJTimeCard] = []
        for summary in summaries:
            tc_id = summary.get("id")
            if not tc_id:
                continue

            try:
                detail = await self.get_timecard_detail(tc_id)
            except Exception:
                continue

            flat_records.extend(_flatten_timecard(detail))

        return flat_records


def _flatten_timecard(detail: dict) -> list[HJTimeCard]:
    """
    Flatten a nested timecard response into flat HJTimeCard rows.

    Each row = one employee's hours on one cost code for one day.
    Quantity is the cost code's daily production (same for all employees).
    """
    tc_id = detail.get("id")
    job_id = detail.get("jobId")
    tc_date_raw = detail.get("date")
    tc_date = tc_date_raw[:10] if tc_date_raw else None
    foreman_id = detail.get("foremanId")
    foreman_name = detail.get("foremanDescription")
    is_approved = detail.get("isApproved", False)
    status = "Approved" if is_approved else "Pending"

    cost_codes = detail.get("costCodes", [])
    employees = detail.get("employees", [])

    # Build lookup: timeCardCostCodeId -> cost code info
    cc_lookup: dict[str, dict] = {}
    for cc in cost_codes:
        cc_lookup[cc["timeCardCostCodeId"]] = cc

    rows: list[HJTimeCard] = []

    for emp in employees:
        emp_id = emp.get("employeeId")
        emp_name = emp.get("employeeDescription") or emp.get("employeeCode")
        emp_code = emp.get("employeeCode")
        pay_class_code = emp.get("payClassCode")    # FORE, OPR1, LAB1, etc.
        pay_class_desc = emp.get("payClassDescription")  # Foreman, Operator, Laborer

        # Collect hours by timeCardCostCodeId
        hours_by_cc: dict[str, float] = {}
        for entry in emp.get("regularHours", []):
            cc_id = entry.get("timeCardCostCodeId")
            hours_by_cc[cc_id] = hours_by_cc.get(cc_id, 0) + (entry.get("hours") or 0)
        for entry in emp.get("overtimeHours", []):
            cc_id = entry.get("timeCardCostCodeId")
            hours_by_cc[cc_id] = hours_by_cc.get(cc_id, 0) + (entry.get("hours") or 0)
        for entry in emp.get("doubleOvertimeHours", []):
            cc_id = entry.get("timeCardCostCodeId")
            hours_by_cc[cc_id] = hours_by_cc.get(cc_id, 0) + (entry.get("hours") or 0)

        for tc_cc_id, total_hours in hours_by_cc.items():
            if total_hours == 0:
                continue

            cc_info = cc_lookup.get(tc_cc_id, {})
            rows.append(HJTimeCard(
                id=tc_id,
                jobId=job_id,
                costCodeId=cc_info.get("costCodeId"),
                costCode=cc_info.get("costCodeCode"),
                tc_date=tc_date,
                employeeId=emp_id,
                employeeName=emp_name,
                employeeCode=emp_code,
                payClassCode=pay_class_code,
                payClassDesc=pay_class_desc,
                hours=total_hours,
                foremanId=foreman_id,
                foremanName=foreman_name,
                status=status,
                quantity=cc_info.get("quantity"),
                notes=cc_info.get("privateNotes"),
            ))

    return rows


def _flatten_equipment(detail: dict) -> list[HJEquipmentEntry]:
    """
    Flatten equipment entries from a timecard response.

    Each row = one piece of equipment on one cost code for one day.
    """
    tc_id = detail.get("id")
    job_id = detail.get("jobId")
    tc_date_raw = detail.get("date")
    tc_date = tc_date_raw[:10] if tc_date_raw else None

    cost_codes = detail.get("costCodes", [])
    equipment_list = detail.get("equipment", [])

    if not equipment_list:
        return []

    cc_lookup: dict[str, dict] = {}
    for cc in cost_codes:
        cc_lookup[cc["timeCardCostCodeId"]] = cc

    rows: list[HJEquipmentEntry] = []

    for equip in equipment_list:
        equip_id = equip.get("equipmentId")
        equip_code = equip.get("equipmentCode")
        equip_desc = equip.get("equipmentDescription") or equip_code

        # Equipment uses totalHours (not regularHours/overtimeHours like employees)
        hours_by_cc: dict[str, float] = {}
        for entry in equip.get("totalHours", []):
            cc_id = entry.get("timeCardCostCodeId")
            hours_by_cc[cc_id] = hours_by_cc.get(cc_id, 0) + (entry.get("hours") or 0)
        # Fallback: some timecards may still use the old structure
        if not hours_by_cc:
            for entry in equip.get("regularHours", []):
                cc_id = entry.get("timeCardCostCodeId")
                hours_by_cc[cc_id] = hours_by_cc.get(cc_id, 0) + (entry.get("hours") or 0)
            for entry in equip.get("overtimeHours", []):
                cc_id = entry.get("timeCardCostCodeId")
                hours_by_cc[cc_id] = hours_by_cc.get(cc_id, 0) + (entry.get("hours") or 0)
            for entry in equip.get("doubleOvertimeHours", []):
                cc_id = entry.get("timeCardCostCodeId")
                hours_by_cc[cc_id] = hours_by_cc.get(cc_id, 0) + (entry.get("hours") or 0)

        for tc_cc_id, total_hours in hours_by_cc.items():
            if total_hours == 0:
                continue

            cc_info = cc_lookup.get(tc_cc_id, {})
            rows.append(HJEquipmentEntry(
                id=tc_id,
                jobId=job_id,
                costCodeId=cc_info.get("costCodeId"),
                costCode=cc_info.get("costCodeCode"),
                tc_date=tc_date,
                equipmentId=equip_id,
                equipmentCode=equip_code,
                equipmentDesc=equip_desc,
                hours=total_hours,
            ))

    return rows
