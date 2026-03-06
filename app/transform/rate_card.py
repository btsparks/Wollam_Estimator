"""
Rate Card Generator

Assembles rate cards from raw cost code data. A rate card is the
complete set of calculated rates for one job — one row per cost code,
with budget rates, actual rates, recommended rates, confidence levels,
and variance flags.

Process:
    1. Map each cost code to a discipline (using DisciplineMapper)
    2. Calculate unit costs for each code (using UnitCostCalculator)
    3. Assess confidence for each rate
    4. Calculate variances and flag items >20%
    5. Assemble into a RateCard with separate flagged_items list

The rate card lifecycle:
    draft → pending_review → approved

Draft cards are auto-generated. pending_review means the PM has been
asked to review. approved means the PM has confirmed the rates and
they're ready for the knowledge base.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.hcss.models import HJCostCode, RateCard, RateItem
from app.transform.calculator import UnitCostCalculator
from app.transform.mapper import DisciplineMapper


@dataclass
class RateItemResult:
    """
    Intermediate result for a single rate calculation.

    Used internally during rate card generation before converting
    to the final RateItem Pydantic model.
    """
    discipline: str
    activity: str                              # Cost code
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


@dataclass
class RateCardResult:
    """
    Complete rate card for one job.

    Contains all rate items plus summary metrics and a separate
    list of flagged items (>20% variance) that require PM explanation.
    """
    job_number: str
    job_name: str
    items: list[RateItemResult] = field(default_factory=list)
    flagged_items: list[RateItemResult] = field(default_factory=list)

    total_budget: float | None = None
    total_actual: float | None = None
    generated_date: datetime | None = None
    data_source: str = "hcss_api"


class RateCardGenerator:
    """
    Generates rate cards from raw cost code data.

    Orchestrates the DisciplineMapper and UnitCostCalculator to produce
    a complete rate card for a job. Each cost code gets mapped to a
    discipline, its rates calculated, confidence assessed, and variance
    flagged.

    Usage:
        generator = RateCardGenerator()
        card = generator.generate_rate_card(
            job_number="8553",
            job_name="RTK SPD Pump Station",
            cost_codes=cost_code_list,
        )
    """

    def __init__(
        self,
        mapper: DisciplineMapper | None = None,
        calculator: UnitCostCalculator | None = None,
    ):
        """
        Args:
            mapper: DisciplineMapper instance. Creates default if not provided.
            calculator: UnitCostCalculator instance. Creates default if not provided.
        """
        self._mapper = mapper or DisciplineMapper()
        self._calc = calculator or UnitCostCalculator()

    def generate_rate_card(
        self,
        job_number: str,
        job_name: str,
        cost_codes: list[dict[str, Any] | HJCostCode],
        estimate: Any | None = None,
    ) -> RateCardResult:
        """
        Generate a complete rate card from cost code data.

        Steps:
            1. Map each cost code to a discipline
            2. Calculate unit costs (MH/unit and $/unit)
            3. Assess confidence
            4. Calculate variance and flag items >20%
            5. Assemble into RateCardResult

        Args:
            job_number: Job number (e.g., '8553').
            job_name: Job description.
            cost_codes: List of cost code data — either HJCostCode models
                        or dicts with equivalent keys.
            estimate: Optional HBEstimate for bid-side data (Phase D).

        Returns:
            RateCardResult with all items and flagged items separated.
        """
        items: list[RateItemResult] = []
        flagged: list[RateItemResult] = []

        total_budget = 0.0
        total_actual = 0.0

        for cc in cost_codes:
            item = self._process_cost_code(cc)
            if item is None:
                continue

            items.append(item)

            # Track flagged items separately for PM review
            if item.variance_flag:
                flagged.append(item)

            # Accumulate totals
            if item.qty_budget is not None and item.bgt_cost_per_unit is not None:
                total_budget += item.qty_budget * item.bgt_cost_per_unit
            if item.qty_actual is not None and item.act_cost_per_unit is not None:
                total_actual += item.qty_actual * item.act_cost_per_unit

        return RateCardResult(
            job_number=job_number,
            job_name=job_name,
            items=items,
            flagged_items=flagged,
            total_budget=round(total_budget, 2) if total_budget else None,
            total_actual=round(total_actual, 2) if total_actual else None,
            generated_date=datetime.now(),
            data_source="hcss_api",
        )

    def _process_cost_code(self, cc: dict[str, Any] | HJCostCode) -> RateItemResult | None:
        """
        Process a single cost code into a rate item.

        Extracts values from either a Pydantic model or a dict,
        maps the discipline, calculates rates, and assesses confidence.

        Returns None if the cost code has no usable data.
        """
        # Normalize to dict for uniform access
        if isinstance(cc, HJCostCode):
            data = {
                "code": cc.code,
                "description": cc.description,
                "unit": cc.unit,
                "bgt_qty": cc.budgetQuantity,
                "bgt_labor_hrs": cc.budgetLaborHours,
                "bgt_labor_cost": cc.budgetLaborCost,
                "act_qty": cc.actualQuantity,
                "act_labor_hrs": cc.actualLaborHours,
                "act_labor_cost": cc.actualLaborCost,
                "pct_complete": cc.percentComplete,
            }
        else:
            data = cc

        code = data.get("code")
        if not code:
            return None

        # Map cost code to discipline
        discipline = self._mapper.map_code(code, data.get("description"))

        # Calculate labor rates
        rates = self._calc.calculate_labor_rate(
            budget_hours=data.get("bgt_labor_hrs"),
            actual_hours=data.get("act_labor_hrs"),
            budget_qty=data.get("bgt_qty"),
            actual_qty=data.get("act_qty"),
            budget_cost=data.get("bgt_labor_cost"),
            actual_cost=data.get("act_labor_cost"),
        )

        # Assess confidence
        has_budget = data.get("bgt_labor_hrs") is not None
        has_actual = data.get("act_labor_hrs") is not None
        confidence, confidence_reason = self._calc.assess_confidence(
            pct_complete=data.get("pct_complete"),
            has_budget=has_budget,
            has_actual=has_actual,
            actual_qty=data.get("act_qty"),
        )

        # Calculate variance on MH/unit rate
        variance_pct, variance_flag = self._calc.calculate_variance(
            rates["bgt_mh_per_unit"],
            rates["act_mh_per_unit"],
        )

        return RateItemResult(
            discipline=discipline,
            activity=code,
            description=data.get("description"),
            unit=data.get("unit"),
            bgt_mh_per_unit=rates["bgt_mh_per_unit"],
            bgt_cost_per_unit=rates["bgt_cost_per_unit"],
            act_mh_per_unit=rates["act_mh_per_unit"],
            act_cost_per_unit=rates["act_cost_per_unit"],
            rec_rate=rates["rec_rate"],
            rec_basis=rates["rec_basis"],
            qty_budget=data.get("bgt_qty"),
            qty_actual=data.get("act_qty"),
            confidence=confidence,
            confidence_reason=confidence_reason,
            variance_pct=variance_pct,
            variance_flag=variance_flag,
        )
