"""
Data Validator — Rate Validation and Outlier Detection

Validates rate calculations against configurable thresholds from
config/rate_thresholds.yaml. Catches data entry errors, API anomalies,
and rates that fall outside expected ranges.

A rate outside bounds isn't necessarily wrong — it just gets flagged
for human review. Context matters: a concrete pour rate of 2.5 MH/CY
might be perfectly reasonable for a small complex pour but would be
an outlier for a large mat pour.

Validation levels:
    error   — Something is definitely wrong (negative hours, impossible values)
    warning — Value is outside expected range, needs human review
    info    — Notable but not necessarily problematic
"""

from __future__ import annotations

import os
from typing import Any

import yaml

from app.transform.rate_card import RateItemResult


# Default config path
DEFAULT_CONFIG_PATH = os.path.join("config", "rate_thresholds.yaml")


class DataValidator:
    """
    Validates rate items against configurable thresholds.

    Reads thresholds from config/rate_thresholds.yaml and validates
    individual rate items and complete rate cards.

    Usage:
        validator = DataValidator()
        warnings = validator.validate_rate_item(item)
        report = validator.validate_rate_card(card)
    """

    def __init__(self, config_path: str | None = None):
        """
        Load validation thresholds from YAML config.

        Args:
            config_path: Path to rate_thresholds.yaml.
        """
        config_path = config_path or DEFAULT_CONFIG_PATH

        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = {}

        # General thresholds
        labor = self._config.get("labor_mh_per_unit", {})
        self._mh_min = labor.get("min", 0.01)
        self._mh_max = labor.get("max", 100.0)

        cost = self._config.get("cost_per_unit", {})
        self._cost_max_ratio = cost.get("max_ratio", 10.0)

        production = self._config.get("production_rates", {})
        self._min_qty = production.get("min_quantity", 10)
        self._min_hours = production.get("min_hours", 8)

    def validate_rate_item(self, item: RateItemResult | dict[str, Any]) -> list[str]:
        """
        Validate a single rate item against thresholds.

        Returns a list of warning/error messages. Empty list = valid.

        Args:
            item: RateItemResult or dict with rate item fields.

        Returns:
            List of warning/error message strings.
        """
        warnings: list[str] = []

        # Normalize to dict
        if isinstance(item, RateItemResult):
            data = {
                "activity": item.activity,
                "description": item.description,
                "discipline": item.discipline,
                "bgt_mh_per_unit": item.bgt_mh_per_unit,
                "act_mh_per_unit": item.act_mh_per_unit,
                "bgt_cost_per_unit": item.bgt_cost_per_unit,
                "act_cost_per_unit": item.act_cost_per_unit,
                "qty_budget": item.qty_budget,
                "qty_actual": item.qty_actual,
            }
        else:
            data = item

        code = data.get("activity", "unknown")

        # Check MH/unit rates against bounds
        for field_name, label in [
            ("bgt_mh_per_unit", "Budget MH/unit"),
            ("act_mh_per_unit", "Actual MH/unit"),
        ]:
            value = data.get(field_name)
            if value is not None:
                if value < 0:
                    warnings.append(f"ERROR: {code} {label} is negative ({value})")
                elif value < self._mh_min:
                    warnings.append(f"WARNING: {code} {label} ({value:.4f}) below minimum ({self._mh_min})")
                elif value > self._mh_max:
                    warnings.append(f"WARNING: {code} {label} ({value:.4f}) above maximum ({self._mh_max})")

        # Check if budget and actual cost are wildly different
        bgt_cost = data.get("bgt_cost_per_unit")
        act_cost = data.get("act_cost_per_unit")
        if bgt_cost and act_cost and bgt_cost > 0:
            ratio = act_cost / bgt_cost
            if ratio > self._cost_max_ratio:
                warnings.append(
                    f"WARNING: {code} actual cost is {ratio:.1f}x budget "
                    f"(${act_cost:.2f} vs ${bgt_cost:.2f})"
                )

        # Check for low quantity (rate might not be meaningful)
        for qty_field, label in [
            ("qty_budget", "Budget qty"),
            ("qty_actual", "Actual qty"),
        ]:
            value = data.get(qty_field)
            if value is not None and 0 < value < self._min_qty:
                warnings.append(
                    f"INFO: {code} {label} ({value:.1f}) below minimum "
                    f"for meaningful rate ({self._min_qty})"
                )

        # Discipline-specific checks
        discipline = data.get("discipline", "")
        self._check_discipline_thresholds(data, discipline, warnings)

        return warnings

    def validate_rate_card(self, card: Any) -> dict[str, Any]:
        """
        Validate a complete rate card.

        Returns a summary dict with warnings, errors, and valid item counts.

        Args:
            card: RateCardResult with items list.

        Returns:
            Dict with keys: warnings (list), errors (list), valid_count (int),
            total_count (int), flagged_count (int).
        """
        all_warnings: list[str] = []
        all_errors: list[str] = []
        valid_count = 0

        items = getattr(card, "items", [])

        for item in items:
            item_warnings = self.validate_rate_item(item)

            errors = [w for w in item_warnings if w.startswith("ERROR")]
            warnings = [w for w in item_warnings if not w.startswith("ERROR")]

            all_errors.extend(errors)
            all_warnings.extend(warnings)

            if not errors:
                valid_count += 1

        return {
            "warnings": all_warnings,
            "errors": all_errors,
            "valid_count": valid_count,
            "total_count": len(items),
            "flagged_count": len(getattr(card, "flagged_items", [])),
        }

    def check_outlier(self, value: float, discipline: str, metric: str) -> bool:
        """
        Check if a value is an outlier for a given discipline and metric.

        Uses discipline-specific thresholds from config. If no threshold
        is defined for the discipline/metric, returns False (not an outlier).

        Args:
            value: The value to check.
            discipline: Discipline key (e.g., 'concrete', 'earthwork').
            metric: Metric key (e.g., 'forming_mh_sf', 'excavation_cost_cy').

        Returns:
            True if the value is outside the configured range.
        """
        disc_config = self._config.get(discipline, {})
        metric_config = disc_config.get(metric, {})

        if not metric_config:
            return False

        min_val = metric_config.get("min")
        max_val = metric_config.get("max")

        if min_val is not None and value < min_val:
            return True
        if max_val is not None and value > max_val:
            return True

        return False

    def _check_discipline_thresholds(
        self,
        data: dict[str, Any],
        discipline: str,
        warnings: list[str],
    ) -> None:
        """
        Apply discipline-specific threshold checks.

        Reads thresholds from config (e.g., concrete.forming_mh_sf.min/max)
        and flags values outside the expected range.
        """
        code = data.get("activity", "unknown")
        act_mh = data.get("act_mh_per_unit")

        if act_mh is None:
            return

        disc_config = self._config.get(discipline, {})
        if not disc_config:
            return

        # Check each metric threshold in the discipline config
        for metric_name, bounds in disc_config.items():
            if not isinstance(bounds, dict):
                continue

            min_val = bounds.get("min")
            max_val = bounds.get("max")

            if min_val is not None and act_mh < min_val:
                warnings.append(
                    f"WARNING: {code} actual MH/unit ({act_mh:.4f}) below "
                    f"{discipline}.{metric_name} minimum ({min_val})"
                )
            elif max_val is not None and act_mh > max_val:
                warnings.append(
                    f"WARNING: {code} actual MH/unit ({act_mh:.4f}) above "
                    f"{discipline}.{metric_name} maximum ({max_val})"
                )
