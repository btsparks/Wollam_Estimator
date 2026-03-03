"""
Pydantic v2 Models for HCSS API Responses and Internal Data

Two categories of models:
    1. API Response Models — validate data from HeavyJob and HeavyBid APIs.
       These catch schema changes at the deserialization boundary.
    2. Internal Models — typed objects for the transformation layer output
       (rate items, rate cards, crew configs, lessons learned).

All models use:
    - ConfigDict(from_attributes=True) for ORM compatibility
    - Optional[...] with None defaults for nullable API fields
    - Field validators for data cleaning (strip whitespace)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ─────────────────────────────────────────────────────────────
# Shared Validators
# ─────────────────────────────────────────────────────────────

def _strip_str(v: str | None) -> str | None:
    """Strip whitespace from string fields. Handles None gracefully."""
    if isinstance(v, str):
        return v.strip()
    return v


# ─────────────────────────────────────────────────────────────
# HeavyJob API Response Models
#
# HeavyJob is the field cost tracking system. It contains what
# actually happened: real hours, real costs, real quantities.
# ─────────────────────────────────────────────────────────────

class HJJob(BaseModel):
    """
    HeavyJob job record.

    Represents a single construction project. 'Active' jobs are in progress,
    'Closed' jobs are complete and ready for rate card generation.
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None                   # HCSS UUID
    jobNumber: Optional[str] = None            # e.g., '8553'
    description: Optional[str] = None          # e.g., 'RTK SPD Pump Station'
    status: Optional[str] = None               # 'Active', 'Closed', 'Pending'
    startDate: Optional[date] = None
    endDate: Optional[date] = None
    businessUnitId: Optional[str] = None

    # Contract fields — not always present in API response
    ownerClient: Optional[str] = None
    contractType: Optional[str] = None
    projectType: Optional[str] = None
    location: Optional[str] = None

    _strip_description = field_validator("description", mode="before")(_strip_str)
    _strip_job_number = field_validator("jobNumber", mode="before")(_strip_str)


class HJCostCode(BaseModel):
    """
    HeavyJob cost code with budget and actual values.

    This is the fundamental data unit for rate calculation. Each cost code
    represents a specific activity (e.g., '2215' = wall form/strip) with
    both budget (estimated) and actual (field-reported) hours, costs, and quantities.

    The delta between budget and actual is where the estimating intelligence lives.
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None                   # HCSS UUID
    jobId: Optional[str] = None
    code: Optional[str] = None                 # e.g., '2215'
    description: Optional[str] = None          # e.g., 'C_F/S Walls'
    unit: Optional[str] = None                 # 'SF', 'CY', 'LF', 'EA', 'LS'

    # Budget values (what was estimated)
    budgetQuantity: Optional[float] = None
    budgetLaborHours: Optional[float] = None
    budgetLaborCost: Optional[float] = None
    budgetEquipmentHours: Optional[float] = None
    budgetEquipmentCost: Optional[float] = None
    budgetMaterialCost: Optional[float] = None
    budgetSubcontractCost: Optional[float] = None
    budgetTotalCost: Optional[float] = None

    # Actual values (what happened in the field)
    actualQuantity: Optional[float] = None
    actualLaborHours: Optional[float] = None
    actualLaborCost: Optional[float] = None
    actualEquipmentHours: Optional[float] = None
    actualEquipmentCost: Optional[float] = None
    actualMaterialCost: Optional[float] = None
    actualSubcontractCost: Optional[float] = None
    actualTotalCost: Optional[float] = None

    # Progress (0-100, from foreman daily reporting)
    percentComplete: Optional[float] = None

    _strip_code = field_validator("code", mode="before")(_strip_str)
    _strip_description = field_validator("description", mode="before")(_strip_str)
    _strip_unit = field_validator("unit", mode="before")(_strip_str)


class HJTimeCard(BaseModel):
    """
    HeavyJob time card entry.

    Daily record of who worked, how many hours, on what cost code.
    Used for crew analysis and production rate calculation.
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    jobId: Optional[str] = None
    costCodeId: Optional[str] = None
    costCode: Optional[str] = None             # Denormalized code string
    date: Optional[date] = None
    employeeId: Optional[str] = None
    employeeName: Optional[str] = None
    hours: Optional[float] = None
    equipmentId: Optional[str] = None
    equipmentHours: Optional[float] = None
    foremanId: Optional[str] = None
    status: Optional[str] = None               # 'Approved', 'Pending'
    quantity: Optional[float] = None           # Production quantity that day

    _strip_name = field_validator("employeeName", mode="before")(_strip_str)


class HJChangeOrder(BaseModel):
    """
    HeavyJob change order.

    Tracks scope changes and design development changes. Categories:
        SC = Scope Change (owner-directed additions)
        DD = Design Development (incomplete/evolving design)

    On Job 8576, DD-driven COs averaged 61% of total CO value — a key
    risk indicator for future bids on similar work.
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    jobId: Optional[str] = None
    changeOrderNumber: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    status: Optional[str] = None               # 'Approved', 'Pending', 'Rejected'
    approvedDate: Optional[date] = None
    category: Optional[str] = None             # 'SC', 'DD'
    scheduleImpact: Optional[str] = None

    _strip_description = field_validator("description", mode="before")(_strip_str)


class HJMaterial(BaseModel):
    """
    HeavyJob material receipt.

    Records materials received on-site with vendor, quantity, and cost.
    Used for material cost benchmarking (e.g., concrete at $265/CY mine site).
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    jobId: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unitCost: Optional[float] = None
    totalCost: Optional[float] = None
    vendor: Optional[str] = None
    poNumber: Optional[str] = None
    dateReceived: Optional[date] = None

    _strip_description = field_validator("description", mode="before")(_strip_str)


class HJSubcontract(BaseModel):
    """
    HeavyJob subcontract record.

    Tracks subcontractor scope, contract amounts, and actual costs.
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    jobId: Optional[str] = None
    vendor: Optional[str] = None
    scope: Optional[str] = None
    contractAmount: Optional[float] = None
    actualAmount: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None

    _strip_vendor = field_validator("vendor", mode="before")(_strip_str)


# ─────────────────────────────────────────────────────────────
# HeavyBid API Response Models
#
# HeavyBid is the estimating system. It contains what was planned:
# bid assumptions, cost buildup, resource rates, material takeoffs.
# Comparing HeavyBid (planned) to HeavyJob (actual) is the core
# of estimating intelligence.
# ─────────────────────────────────────────────────────────────

class HBEstimate(BaseModel):
    """
    HeavyBid estimate record.

    Represents a bid for a project. Links to bid items (pay items),
    activities (cost buildup), and resources (labor/equipment rates).
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None                   # HCSS UUID
    name: Optional[str] = None
    description: Optional[str] = None
    bidDate: Optional[date] = None
    status: Optional[str] = None               # 'Won', 'Lost', 'Pending'
    totalCost: Optional[float] = None
    totalPrice: Optional[float] = None
    businessUnitId: Optional[str] = None

    _strip_name = field_validator("name", mode="before")(_strip_str)


class HBBidItem(BaseModel):
    """
    HeavyBid bid item (pay item / scheduled value).

    The owner's line items — what the owner pays us for.
    Each bid item is backed by one or more activities (cost buildup).
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    estimateId: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    totalCost: Optional[float] = None
    totalPrice: Optional[float] = None

    _strip_description = field_validator("description", mode="before")(_strip_str)


class HBActivity(BaseModel):
    """
    HeavyBid activity (cost buildup).

    The estimator's detail — how each bid item is priced. Breaks cost down
    into labor, equipment, material, and subcontract components. The production
    rate field tells you how fast the estimator assumed the crew would work.
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    estimateId: Optional[str] = None
    bidItemId: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    laborHours: Optional[float] = None
    laborCost: Optional[float] = None
    equipmentHours: Optional[float] = None
    equipmentCost: Optional[float] = None
    materialCost: Optional[float] = None
    subcontractCost: Optional[float] = None
    totalCost: Optional[float] = None
    productionRate: Optional[float] = None

    _strip_description = field_validator("description", mode="before")(_strip_str)


class HBResource(BaseModel):
    """
    HeavyBid resource (labor or equipment).

    The rate book — what rate was assumed for each worker type or piece
    of equipment in the estimate.
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    estimateId: Optional[str] = None
    type: Optional[str] = None                 # 'Labor', 'Equipment'
    code: Optional[str] = None
    description: Optional[str] = None
    rate: Optional[float] = None
    hours: Optional[float] = None
    cost: Optional[float] = None

    _strip_description = field_validator("description", mode="before")(_strip_str)


# ─────────────────────────────────────────────────────────────
# Internal Models — Transformation Layer Output
#
# These models represent the calculated, validated data that
# the transformation layer produces from raw HCSS data.
# ─────────────────────────────────────────────────────────────

class RateItem(BaseModel):
    """
    A single calculated rate for one cost code on one job.

    This is the core output of the transformation layer. For each cost code,
    we calculate budget and actual rates (MH/unit and $/unit), determine a
    recommended rate, assess confidence, and flag significant variances.

    Confidence levels:
        strong   — >=90% complete, has budget AND actual, reasonable quantities
        moderate — 50-89% complete, or has actual but limited comparison
        limited  — has budget only, or <50% complete
        none     — insufficient data for rate calculation
    """
    model_config = ConfigDict(from_attributes=True)

    discipline: str
    activity: str                              # Cost code (e.g., '2215')
    description: str | None = None
    unit: str | None = None                    # 'SF', 'CY', 'LF', etc.

    # Budget rates
    bgt_mh_per_unit: float | None = None       # MH/SF, MH/CY, etc.
    bgt_cost_per_unit: float | None = None     # $/SF, $/CY, etc.

    # Actual rates
    act_mh_per_unit: float | None = None
    act_cost_per_unit: float | None = None

    # Recommended rate (weighted between budget and actual)
    rec_rate: float | None = None
    rec_basis: str | None = None               # 'budget', 'actual', 'calculated', 'pm_override'

    # Quantities
    qty_budget: float | None = None
    qty_actual: float | None = None

    # Confidence
    confidence: str = "moderate"
    confidence_reason: str | None = None

    # Variance
    variance_pct: float | None = None
    variance_flag: bool = False                # True if >20% variance


class RateCard(BaseModel):
    """
    A complete rate card for one job.

    Contains all calculated rate items, summary metrics, and review status.
    Lifecycle: draft → pending_review → approved

    PM review is required before rates enter the knowledge base. The PM
    explains variances, captures lessons learned, and confirms/overrides
    recommended rates.
    """
    model_config = ConfigDict(from_attributes=True)

    job_number: str
    job_name: str
    items: list[RateItem] = Field(default_factory=list)
    flagged_items: list[RateItem] = Field(default_factory=list)  # Items with >20% variance

    # Summary metrics
    total_budget: float | None = None
    total_actual: float | None = None
    cpi: float | None = None                   # Cost Performance Index (budget / actual)

    # Status
    status: str = "draft"                      # 'draft', 'pending_review', 'approved'
    data_source: str = "hcss_api"
    generated_date: datetime | None = None


class CrewConfig(BaseModel):
    """
    Crew configuration for a specific activity.

    Extracted from timecard analysis — tells future estimators what crew
    size and composition actually worked for a given activity.
    """
    model_config = ConfigDict(from_attributes=True)

    discipline: str
    activity: str | None = None
    crew_size: int | None = None
    composition: dict | None = None            # {"foreman": 1, "carpenter": 3, "laborer": 2}
    production_rate: float | None = None       # Units per crew-hour
    production_unit: str | None = None         # e.g., 'SF/day', 'CY/hr'
    days_worked: int | None = None
    notes: str | None = None


class LessonLearned(BaseModel):
    """
    Lessons learned entry from PM interview or auto-detection.

    Categories:
        variance — explains a budget-to-actual variance (required for flagged items)
        success  — what went well, should be repeated
        risk     — what went wrong or was risky, watch for on future bids
        process  — process improvements or workflow changes
    """
    model_config = ConfigDict(from_attributes=True)

    discipline: str | None = None
    category: str                              # 'variance', 'success', 'risk', 'process'
    description: str
    impact: str | None = None                  # 'high', 'medium', 'low'
    recommendation: str | None = None
    pm_name: str | None = None
    source: str = "pm_interview"               # 'pm_interview', 'jcd_manual', 'auto'
