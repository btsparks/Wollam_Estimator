"""
Field Intelligence Rate Card Generator

Analyzes actual timecard data to produce field intelligence cards.
Each cost code is evaluated by its activity level (how many timecards),
production rates (MH/unit, $/unit), daily crew analysis, and equipment usage.

This does NOT compare budget to actual. It analyzes what happened in the field
and assesses confidence based on data richness.

Process:
    1. Query timecards grouped by cost code
    2. Calculate activity metrics (timecard count, work days, crew size)
    3. Calculate production rates from actual totals
    4. Analyze daily crew breakdown (trades + equipment)
    5. Assess confidence based on data volume
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.database import get_connection
from app.transform.calculator import (
    FieldIntelCard,
    FieldIntelItem,
    assess_confidence,
    safe_divide,
)
from app.transform.mapper import DisciplineMapper


# Keep these for backwards compat with storage.py imports
@dataclass
class RateItemResult:
    """Legacy wrapper — maps to FieldIntelItem for storage layer."""
    discipline: str
    activity: str
    description: str | None = None
    unit: str | None = None
    bgt_mh_per_unit: float | None = None
    bgt_cost_per_unit: float | None = None
    act_mh_per_unit: float | None = None
    act_cost_per_unit: float | None = None
    rec_rate: float | None = None
    rec_basis: str | None = None
    qty_budget: float | None = None
    qty_actual: float | None = None
    confidence: str = "moderate"
    confidence_reason: str | None = None
    variance_pct: float | None = None
    variance_flag: bool = False
    # New fields
    timecard_count: int = 0
    work_days: int = 0
    crew_size_avg: float | None = None
    daily_qty_avg: float | None = None
    daily_qty_peak: float | None = None
    total_hours: float | None = None
    total_qty: float | None = None
    total_labor_cost: float | None = None
    total_equip_cost: float | None = None
    crew_breakdown: str | None = None


@dataclass
class RateCardResult:
    """Legacy wrapper — maps to FieldIntelCard for storage layer."""
    job_number: str
    job_name: str
    items: list[RateItemResult] = field(default_factory=list)
    flagged_items: list[RateItemResult] = field(default_factory=list)
    total_budget: float | None = None
    total_actual: float | None = None
    generated_date: datetime | None = None
    data_source: str = "hcss_api"


def _get(obj, key, default=None):
    """Get a value from a dict or Pydantic model."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class RateCardGenerator:
    """
    Generates field intelligence cards from timecard + cost code data.

    Queries the database directly for timecard activity per cost code,
    then calculates production rates, crew analysis, and confidence.
    """

    def __init__(self, mapper: DisciplineMapper | None = None):
        self._mapper = mapper or DisciplineMapper()

    def generate_rate_card(
        self,
        job_number: str,
        job_name: str,
        cost_codes: list[dict[str, Any]],
        estimate: Any | None = None,
    ) -> RateCardResult:
        """
        Generate a field intelligence rate card for a job.

        Args:
            job_number: Job number (e.g., '8553').
            job_name: Job description.
            cost_codes: List of cost code dicts from hj_costcode table.
        """
        if not cost_codes:
            return RateCardResult(
                job_number=job_number,
                job_name=job_name,
                generated_date=datetime.now(),
            )

        job_id = _get(cost_codes[0], "job_id") or _get(cost_codes[0], "jobId")
        if not job_id:
            return RateCardResult(
                job_number=job_number,
                job_name=job_name,
                generated_date=datetime.now(),
            )

        # Query timecard activity per cost code
        tc_stats = self._get_timecard_stats(job_id)
        equip_stats = self._get_equipment_stats(job_id)

        items: list[RateItemResult] = []
        total_labor_hrs = 0.0
        total_labor_cost = 0.0
        total_equip_cost = 0.0

        for cc in cost_codes:
            code = _get(cc, "code")
            if not code:
                continue

            discipline = self._mapper.map_code(code, _get(cc, "description"))
            stats = tc_stats.get(code, {})
            equip = equip_stats.get(code, {})

            item = self._build_item(cc, discipline, stats, equip)
            items.append(item)

            if item.total_hours:
                total_labor_hrs += item.total_hours
            if item.total_labor_cost:
                total_labor_cost += item.total_labor_cost
            if item.total_equip_cost:
                total_equip_cost += item.total_equip_cost

        # Sort by timecard_count descending — most active first
        items.sort(key=lambda x: x.timecard_count, reverse=True)

        return RateCardResult(
            job_number=job_number,
            job_name=job_name,
            items=items,
            flagged_items=[],
            total_budget=None,
            total_actual=round(total_labor_cost + total_equip_cost, 2) or None,
            generated_date=datetime.now(),
            data_source="hcss_api",
        )

    def _get_timecard_stats(self, job_id: int) -> dict[str, dict]:
        """Query timecard data grouped by cost code for a job."""
        conn = get_connection()
        try:
            # Per cost code aggregates
            rows = conn.execute("""
                SELECT cost_code,
                       COUNT(*) as tc_count,
                       COUNT(DISTINCT date) as work_days,
                       ROUND(SUM(hours), 2) as total_hours,
                       COUNT(DISTINCT employee_id) as unique_workers
                FROM hj_timecard
                WHERE job_id = ?
                GROUP BY cost_code
            """, (job_id,)).fetchall()

            stats = {}
            for r in rows:
                cc = r["cost_code"]
                stats[cc] = {
                    "tc_count": r["tc_count"],
                    "work_days": r["work_days"],
                    "total_hours": r["total_hours"],
                    "unique_workers": r["unique_workers"],
                }

            # Daily crew size per cost code (avg distinct employees per day)
            crew_rows = conn.execute("""
                SELECT cost_code,
                       ROUND(AVG(daily_crew), 1) as avg_crew,
                       MAX(daily_crew) as max_crew
                FROM (
                    SELECT cost_code, date, COUNT(DISTINCT employee_id) as daily_crew
                    FROM hj_timecard
                    WHERE job_id = ?
                    GROUP BY cost_code, date
                )
                GROUP BY cost_code
            """, (job_id,)).fetchall()
            for r in crew_rows:
                cc = r["cost_code"]
                if cc in stats:
                    stats[cc]["avg_crew"] = r["avg_crew"]
                    stats[cc]["max_crew"] = r["max_crew"]

            # Daily production (quantity per day)
            qty_rows = conn.execute("""
                SELECT cost_code,
                       ROUND(AVG(daily_qty), 2) as avg_qty,
                       ROUND(MAX(daily_qty), 2) as peak_qty
                FROM (
                    SELECT cost_code, date, MAX(quantity) as daily_qty
                    FROM hj_timecard
                    WHERE job_id = ? AND quantity IS NOT NULL AND quantity > 0
                    GROUP BY cost_code, date
                )
                GROUP BY cost_code
            """, (job_id,)).fetchall()
            for r in qty_rows:
                cc = r["cost_code"]
                if cc in stats:
                    stats[cc]["daily_qty_avg"] = r["avg_qty"]
                    stats[cc]["daily_qty_peak"] = r["peak_qty"]

            # Employee code breakdown per cost code (trade codes)
            trade_rows = conn.execute("""
                SELECT cost_code, employee_code, COUNT(DISTINCT date) as days_worked
                FROM hj_timecard
                WHERE job_id = ? AND employee_code IS NOT NULL AND employee_code != ''
                GROUP BY cost_code, employee_code
                ORDER BY cost_code, days_worked DESC
            """, (job_id,)).fetchall()
            for r in trade_rows:
                cc = r["cost_code"]
                if cc in stats:
                    if "trades" not in stats[cc]:
                        stats[cc]["trades"] = {}
                    stats[cc]["trades"][r["employee_code"]] = r["days_worked"]

            return stats
        finally:
            conn.close()

    def _get_equipment_stats(self, job_id: int) -> dict[str, dict]:
        """Query equipment entries grouped by cost code."""
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT cost_code,
                       ROUND(SUM(hours), 2) as total_equip_hours,
                       COUNT(DISTINCT equipment_id) as unique_equipment
                FROM hj_equipment_entry
                WHERE job_id = ?
                GROUP BY cost_code
            """, (job_id,)).fetchall()

            stats = {}
            for r in rows:
                cc = r["cost_code"]
                stats[cc] = {
                    "total_equip_hours": r["total_equip_hours"],
                    "unique_equipment": r["unique_equipment"],
                }

            # Equipment type breakdown
            equip_rows = conn.execute("""
                SELECT cost_code, equipment_code, equipment_desc,
                       COUNT(DISTINCT date) as days_used,
                       ROUND(SUM(hours), 1) as total_hours
                FROM hj_equipment_entry
                WHERE job_id = ? AND equipment_code IS NOT NULL
                GROUP BY cost_code, equipment_id
                ORDER BY cost_code, total_hours DESC
            """, (job_id,)).fetchall()
            for r in equip_rows:
                cc = r["cost_code"]
                if cc in stats:
                    if "equipment" not in stats[cc]:
                        stats[cc]["equipment"] = []
                    stats[cc]["equipment"].append({
                        "code": r["equipment_code"],
                        "desc": r["equipment_desc"],
                        "days": r["days_used"],
                        "hours": r["total_hours"],
                    })

            return stats
        finally:
            conn.close()

    def _build_item(
        self,
        cc: dict,
        discipline: str,
        tc_stats: dict,
        equip_stats: dict,
    ) -> RateItemResult:
        """Build a rate item from cost code data + timecard stats."""
        code = _get(cc, "code")
        unit = _get(cc, "unit") or _get(cc, "unitOfMeasure")
        tc_count = tc_stats.get("tc_count", 0)
        work_days = tc_stats.get("work_days", 0)

        # Actual totals from cost code table (aggregated from timecards)
        act_hours = _get(cc, "act_labor_hrs") or _get(cc, "actualLaborHours")
        act_qty = _get(cc, "act_qty") or _get(cc, "actualQuantity")
        act_labor_cost = _get(cc, "act_labor_cost") or _get(cc, "actualLaborCost")
        act_equip_cost = _get(cc, "act_equip_cost") or _get(cc, "actualEquipmentCost")

        # If we don't have act_hours from hj_costcode, use timecard sum
        if not act_hours and tc_stats.get("total_hours"):
            act_hours = tc_stats["total_hours"]

        # MH/unit
        act_mh_per_unit = safe_divide(act_hours, act_qty)

        # $/unit = (labor cost + equipment cost) / quantity
        combined_cost = None
        if act_labor_cost or act_equip_cost:
            combined_cost = (act_labor_cost or 0) + (act_equip_cost or 0)
        act_cost_per_unit = safe_divide(combined_cost, act_qty)

        # Crew breakdown JSON
        crew_data = {}
        if tc_stats.get("trades"):
            crew_data["trades"] = tc_stats["trades"]
        if equip_stats.get("equipment"):
            crew_data["equipment"] = equip_stats["equipment"]
        crew_json = json.dumps(crew_data) if crew_data else None

        # Confidence
        confidence, confidence_reason = assess_confidence(tc_count, work_days)

        return RateItemResult(
            discipline=discipline,
            activity=code,
            description=_get(cc, "description"),
            unit=unit,
            # Legacy fields — keep act rates, null out budget stuff
            bgt_mh_per_unit=None,
            bgt_cost_per_unit=None,
            act_mh_per_unit=act_mh_per_unit,
            act_cost_per_unit=act_cost_per_unit,
            rec_rate=act_mh_per_unit,  # Recommended = actual (no budget blending)
            rec_basis="actual" if act_mh_per_unit else None,
            qty_budget=None,
            qty_actual=act_qty,
            confidence=confidence,
            confidence_reason=confidence_reason,
            variance_pct=None,
            variance_flag=False,
            # New field intelligence fields
            timecard_count=tc_count,
            work_days=work_days,
            crew_size_avg=tc_stats.get("avg_crew"),
            daily_qty_avg=tc_stats.get("daily_qty_avg"),
            daily_qty_peak=tc_stats.get("daily_qty_peak"),
            total_hours=act_hours,
            total_qty=act_qty,
            total_labor_cost=act_labor_cost,
            total_equip_cost=act_equip_cost,
            crew_breakdown=crew_json,
        )
