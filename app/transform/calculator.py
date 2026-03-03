"""
Unit Cost Calculator

Implements the rate calculation formulas that transform raw HCSS
cost code data into meaningful estimating rates.

Key formulas:
    Budget MH/Unit = budget_labor_hours / budget_quantity
    Actual MH/Unit = actual_labor_hours / actual_quantity
    Budget $/Unit  = budget_labor_cost / budget_quantity
    Actual $/Unit  = actual_labor_cost / actual_quantity

Recommended rate logic:
    If actual <= budget:  rec = actual + (budget - actual) * 0.2
        → 80% weight toward actual (they did better than planned)
    If actual > budget:   rec = budget + (actual - budget) * 0.5
        → 50% weight between (split the overrun, it might be site-specific)

Confidence assessment:
    strong   — >=90% complete, has budget AND actual, qty above threshold
    moderate — 50-89% complete, or has actual but limited comparison data
    limited  — has budget only, or <50% complete
    none     — insufficient data to calculate a meaningful rate

All thresholds come from config/hcss_config.yaml — no magic numbers.
"""

from __future__ import annotations

import os
from typing import Any

import yaml


# Default config path
DEFAULT_CONFIG_PATH = os.path.join("config", "hcss_config.yaml")


class UnitCostCalculator:
    """
    Calculates unit costs, recommended rates, confidence levels, and variances.

    All thresholds and weights are loaded from config — nothing is hard-coded.

    Usage:
        calc = UnitCostCalculator()

        result = calc.calculate_labor_rate(
            budget_hours=1400, actual_hours=1264,
            budget_qty=5000, actual_qty=5100,
            budget_cost=77000, actual_cost=72864,
        )
        # result = {
        #     'bgt_mh_per_unit': 0.28,
        #     'act_mh_per_unit': 0.248,
        #     'bgt_cost_per_unit': 15.40,
        #     'act_cost_per_unit': 14.29,
        #     'rec_rate': 0.254,
        #     'rec_basis': 'calculated',
        # }
    """

    def __init__(self, config_path: str | None = None):
        """
        Load calculation parameters from config.

        Args:
            config_path: Path to hcss_config.yaml.
        """
        config_path = config_path or DEFAULT_CONFIG_PATH

        # Load config if file exists, otherwise use defaults
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

        rate_config = config.get("rate_calculation", {})
        confidence_config = config.get("confidence", {})

        # Rate calculation parameters
        self.variance_threshold: float = rate_config.get("variance_threshold", 20.0)
        self.min_quantity_threshold: float = rate_config.get("min_quantity_threshold", 10.0)
        self.recommended_rate_bias: float = rate_config.get("recommended_rate_bias", 0.8)

        # Confidence thresholds
        self.strong_min_pct: float = confidence_config.get("strong_min_pct_complete", 90.0)
        self.moderate_min_pct: float = confidence_config.get("moderate_min_pct_complete", 50.0)

    def calculate_labor_rate(
        self,
        budget_hours: float | None = None,
        actual_hours: float | None = None,
        budget_qty: float | None = None,
        actual_qty: float | None = None,
        budget_cost: float | None = None,
        actual_cost: float | None = None,
    ) -> dict[str, Any]:
        """
        Calculate all labor rate metrics from raw cost code data.

        Handles None values and division by zero gracefully — returns None
        for any metric that can't be calculated from the available data.

        Args:
            budget_hours: Budgeted labor manhours.
            actual_hours: Actual labor manhours from field.
            budget_qty: Budgeted quantity (e.g., 5000 SF).
            actual_qty: Actual quantity completed.
            budget_cost: Budgeted labor cost in dollars.
            actual_cost: Actual labor cost in dollars.

        Returns:
            Dict with keys: bgt_mh_per_unit, act_mh_per_unit,
            bgt_cost_per_unit, act_cost_per_unit, rec_rate, rec_basis
        """
        # MH per unit (the key production rate — e.g., 0.28 MH/SF for wall forming)
        bgt_mh = self._safe_divide(budget_hours, budget_qty)
        act_mh = self._safe_divide(actual_hours, actual_qty)

        # Cost per unit ($/SF, $/CY, etc.)
        bgt_cost = self._safe_divide(budget_cost, budget_qty)
        act_cost = self._safe_divide(actual_cost, actual_qty)

        # Recommended rate (MH/unit) — this is the rate we'd use on a future bid
        rec_rate, rec_basis = self.calculate_recommended_rate(bgt_mh, act_mh)

        return {
            "bgt_mh_per_unit": bgt_mh,
            "act_mh_per_unit": act_mh,
            "bgt_cost_per_unit": bgt_cost,
            "act_cost_per_unit": act_cost,
            "rec_rate": rec_rate,
            "rec_basis": rec_basis,
        }

    def calculate_recommended_rate(
        self,
        budget_rate: float | None,
        actual_rate: float | None,
    ) -> tuple[float | None, str | None]:
        """
        Calculate the recommended rate from budget and actual.

        Logic:
            If actual <= budget (came in under — good performance):
                rec = actual + (budget - actual) * (1 - bias)
                With default bias=0.8: rec = actual + (budget - actual) * 0.2
                → Weights 80% toward actual (reward the performance)

            If actual > budget (overran — investigate why):
                rec = budget + (actual - budget) * 0.5
                → Splits the difference (might be site-specific, might be real)

            If only one exists, use that one.
            If neither exists, return None.

        Args:
            budget_rate: Budgeted rate (MH/unit or $/unit).
            actual_rate: Actual achieved rate.

        Returns:
            Tuple of (recommended_rate, basis_string).
            basis_string is one of: 'calculated', 'budget', 'actual', None.
        """
        has_budget = budget_rate is not None
        has_actual = actual_rate is not None

        if has_budget and has_actual:
            if actual_rate <= budget_rate:
                # Actual beat budget — weight toward actual (good performance)
                rec = actual_rate + (budget_rate - actual_rate) * (1 - self.recommended_rate_bias)
            else:
                # Actual exceeded budget — split the difference
                rec = budget_rate + (actual_rate - budget_rate) * 0.5
            return (round(rec, 4), "calculated")

        if has_actual:
            return (actual_rate, "actual")

        if has_budget:
            return (budget_rate, "budget")

        return (None, None)

    def assess_confidence(
        self,
        pct_complete: float | None,
        has_budget: bool,
        has_actual: bool,
        actual_qty: float | None = None,
        min_qty: float | None = None,
    ) -> tuple[str, str]:
        """
        Assess confidence level for a rate calculation.

        Levels:
            strong   — High confidence: job nearly complete, both data sources,
                       sufficient quantity for meaningful rate
            moderate — Decent data but some limitations
            limited  — Budget only or job still early
            none     — Can't calculate a meaningful rate

        Args:
            pct_complete: Job percent complete (0-100).
            has_budget: Whether budget data exists.
            has_actual: Whether actual data exists.
            actual_qty: Actual quantity completed.
            min_qty: Minimum quantity threshold (from config if not specified).

        Returns:
            Tuple of (confidence_level, reason_string).
        """
        min_qty = min_qty or self.min_quantity_threshold
        pct = pct_complete or 0

        # No data at all
        if not has_budget and not has_actual:
            return ("none", "No budget or actual data available")

        # Strong: job mostly done, both data sources, reasonable quantity
        if (
            pct >= self.strong_min_pct
            and has_budget
            and has_actual
            and (actual_qty or 0) >= min_qty
        ):
            return ("strong", f"Job {pct:.0f}% complete with budget and actual data")

        # Moderate: either good progress or has actual data
        if has_actual and (pct >= self.moderate_min_pct or has_budget):
            return ("moderate", f"Job {pct:.0f}% complete, has actual data")

        # Limited: budget only or very early in job
        if has_budget:
            return ("limited", "Budget data only, no actual performance data")

        # Actual data exists but very early
        if has_actual:
            return ("limited", f"Job only {pct:.0f}% complete, actual data may not be representative")

        return ("none", "Insufficient data for rate calculation")

    def calculate_variance(
        self,
        budget_value: float | None,
        actual_value: float | None,
    ) -> tuple[float | None, bool]:
        """
        Calculate budget-to-actual variance percentage.

        Variance = ((actual - budget) / budget) * 100
        Positive variance = over budget (bad)
        Negative variance = under budget (good)

        Flagged if absolute variance exceeds the configured threshold (default 20%).

        Args:
            budget_value: Budget amount (rate, cost, hours, etc.).
            actual_value: Actual amount.

        Returns:
            Tuple of (variance_pct, is_flagged).
            Returns (None, False) if either value is missing or budget is zero.
        """
        if budget_value is None or actual_value is None:
            return (None, False)

        if budget_value == 0:
            # Can't calculate variance from zero budget
            return (None, False)

        variance_pct = ((actual_value - budget_value) / budget_value) * 100
        variance_pct = round(variance_pct, 2)
        is_flagged = abs(variance_pct) > self.variance_threshold

        return (variance_pct, is_flagged)

    @staticmethod
    def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
        """
        Safe division that handles None and zero gracefully.

        Returns None if either value is None or denominator is zero.
        Rounds to 4 decimal places for clean output.
        """
        if numerator is None or denominator is None or denominator == 0:
            return None
        return round(numerator / denominator, 4)
