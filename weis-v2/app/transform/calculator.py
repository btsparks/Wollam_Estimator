"""
Field Intelligence Calculator

Calculates production rates and crew analysis from actual timecard data.
This is NOT a budget-vs-actual variance tool — it's a field data analysis
engine that tells estimators what really happened on each cost code.

Key outputs per cost code:
    MH/unit    — actual man-hours per unit of production
    $/unit     — actual (labor + equipment) cost per unit
    Crew/day   — average daily crew size and composition
    Qty/day    — average and peak daily production
    Confidence — based on data richness (timecard count), not % complete

Confidence tiers (based on timecard activity):
    HIGH     — 20+ timecard entries, 10+ work days
    MODERATE — 5-19 timecard entries
    LOW      — 1-4 timecard entries (thin data, use with caution)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# Confidence thresholds
HIGH_TC_MIN = 20
HIGH_DAYS_MIN = 10
MODERATE_TC_MIN = 5


@dataclass
class FieldIntelItem:
    """
    Field intelligence for one cost code on one job.

    This replaces the old RateItemResult. Every field is derived from
    actual timecard data — no budget comparisons.
    """
    discipline: str
    activity: str                              # Cost code
    description: str | None = None
    unit: str | None = None

    # Core rates (from actuals only)
    act_mh_per_unit: float | None = None       # Total labor hours / total qty
    act_cost_per_unit: float | None = None     # (Labor $ + Equipment $) / total qty

    # Totals
    total_hours: float | None = None           # Sum of all labor hours
    total_qty: float | None = None             # Sum of actual quantity
    total_labor_cost: float | None = None
    total_equip_cost: float | None = None

    # Activity level
    timecard_count: int = 0                    # Number of timecard entries
    work_days: int = 0                         # Distinct dates with activity
    crew_size_avg: float | None = None         # Avg distinct workers per day

    # Daily production profile
    daily_qty_avg: float | None = None         # Avg qty per work day
    daily_qty_peak: float | None = None        # Max qty in a single day

    # Crew breakdown (JSON string for DB storage)
    crew_breakdown: str | None = None          # e.g., {"OE4": 2, "LA1": 3, "equip": ["375EXC", "40T HT"]}

    # Confidence
    confidence: str = "low"
    confidence_reason: str | None = None


@dataclass
class FieldIntelCard:
    """
    Complete field intelligence card for one job.

    Contains all analyzed cost code items, sorted by activity level.
    """
    job_number: str
    job_name: str
    items: list[FieldIntelItem] = field(default_factory=list)

    total_labor_hours: float | None = None
    total_labor_cost: float | None = None
    total_equip_cost: float | None = None

    data_source: str = "hcss_api"
    generated_date: Any = None


def assess_confidence(
    timecard_count: int,
    work_days: int,
) -> tuple[str, str]:
    """
    Assess confidence based on data richness, not budget tracking.

    More timecards = more confidence that the rate is representative.
    A cost code with 1 timecard could be a fluke (bad weather, misposted time).
    A cost code with 50 timecards across 20 days is solid production data.
    """
    if timecard_count >= HIGH_TC_MIN and work_days >= HIGH_DAYS_MIN:
        return ("high", f"{timecard_count} timecards across {work_days} days")

    if timecard_count >= MODERATE_TC_MIN:
        return ("moderate", f"{timecard_count} timecards across {work_days} days")

    if timecard_count > 0:
        return ("low", f"Only {timecard_count} timecard(s) — thin data, use with caution")

    return ("none", "No timecard data")


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    """Safe division — returns None if either value is None or denominator is zero."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return round(numerator / denominator, 4)
