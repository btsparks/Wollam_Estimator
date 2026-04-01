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

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


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

    Represents a single construction project. Real API field names used.
    Status values from API: 'active', 'inactive', 'completed'.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: Optional[str] = None                   # HCSS UUID
    code: Optional[str] = Field(None, alias="jobNumber")  # Job number, e.g., '8553'
    description: Optional[str] = None          # e.g., 'RTK SPD Pump Station'
    status: Optional[str] = None               # 'active', 'inactive', 'completed'
    createdDate: Optional[str] = None          # ISO datetime string
    businessUnitId: Optional[str] = None
    legacyId: Optional[str] = None
    isDeleted: Optional[bool] = None
    payItemSetupType: Optional[str] = None
    relatedEstimateCodes: Optional[list[str]] = None

    # Convenience alias for downstream code that uses jobNumber
    @property
    def jobNumber(self) -> str | None:
        return self.code

    _strip_description = field_validator("description", mode="before")(_strip_str)
    _strip_code = field_validator("code", mode="before")(_strip_str)


class HJCostCode(BaseModel):
    """
    HeavyJob cost code with budget values.

    Real API returns a single set of hours/dollars per cost code — these are
    budget values from the estimate. Actual values come from timecard aggregation.

    Fields match the HCSS HeavyJob /api/v1/costCodes endpoint response.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    # AliasChoices lets us accept BOTH HCSS API field names AND mock/legacy names.
    # With populate_by_name=True, the field name itself also works.

    id: Optional[str] = None                   # HCSS UUID
    jobId: Optional[str] = None
    jobCode: Optional[str] = None              # Denormalized job number
    code: Optional[str] = None                 # e.g., '2215'
    description: Optional[str] = None          # e.g., 'C_F/S Walls'
    unitOfMeasure: Optional[str] = Field(
        None, validation_alias=AliasChoices("unitOfMeasure", "unit"),
    )
    status: Optional[str] = None               # 'active', 'completed'
    quantity: Optional[float] = Field(
        None, validation_alias=AliasChoices("quantity", "budgetQuantity"),
    )

    # Budget values (from estimate)
    laborHours: Optional[float] = Field(
        None, validation_alias=AliasChoices("laborHours", "budgetLaborHours"),
    )
    equipmentHours: Optional[float] = Field(
        None, validation_alias=AliasChoices("equipmentHours", "budgetEquipmentHours"),
    )
    laborDollars: Optional[float] = Field(
        None, validation_alias=AliasChoices("laborDollars", "budgetLaborCost"),
    )
    equipmentDollars: Optional[float] = Field(
        None, validation_alias=AliasChoices("equipmentDollars", "budgetEquipmentCost"),
    )
    materialDollars: Optional[float] = Field(
        None, validation_alias=AliasChoices("materialDollars", "budgetMaterialCost"),
    )
    subcontractDollars: Optional[float] = Field(
        None, validation_alias=AliasChoices("subcontractDollars", "budgetSubcontractCost"),
    )
    customCostTypeDollars: Optional[list] = None
    budgetTotalCostRaw: Optional[float] = Field(
        None, validation_alias="budgetTotalCost", exclude=True,
    )

    # Metadata
    businessUnitId: Optional[str] = None
    businessUnitCode: Optional[str] = None
    historicalActivityCode: Optional[str] = None
    historicalBiditem: Optional[str] = None
    heavyBidEstimateCode: Optional[str] = None
    isDeleted: Optional[bool] = None
    isCapExpected: Optional[bool] = None
    isTm: Optional[bool] = None

    # Actual values — NOT populated by the HCSS costCodes endpoint.
    # Populated from timecard aggregation, file imports, or test fixtures.
    actualQuantity: Optional[float] = None
    actualLaborHours: Optional[float] = None
    actualLaborCost: Optional[float] = None
    actualEquipmentHours: Optional[float] = None
    actualEquipmentCost: Optional[float] = None
    actualMaterialCost: Optional[float] = None
    actualSubcontractCost: Optional[float] = None
    actualTotalCostRaw: Optional[float] = Field(
        None, validation_alias="actualTotalCost", exclude=True,
    )
    percentComplete: Optional[float] = None

    # Convenience aliases for downstream code
    @property
    def unit(self) -> str | None:
        return self.unitOfMeasure

    @property
    def budgetQuantity(self) -> float | None:
        return self.quantity

    @property
    def budgetLaborHours(self) -> float | None:
        return self.laborHours

    @property
    def budgetLaborCost(self) -> float | None:
        return self.laborDollars

    @property
    def budgetEquipmentHours(self) -> float | None:
        return self.equipmentHours

    @property
    def budgetEquipmentCost(self) -> float | None:
        return self.equipmentDollars

    @property
    def budgetMaterialCost(self) -> float | None:
        return self.materialDollars

    @property
    def budgetSubcontractCost(self) -> float | None:
        return self.subcontractDollars

    @property
    def budgetTotalCost(self) -> float | None:
        # Prefer explicit total from data source (may include costs not broken into components)
        if self.budgetTotalCostRaw is not None:
            return self.budgetTotalCostRaw
        parts = [self.laborDollars, self.equipmentDollars,
                 self.materialDollars, self.subcontractDollars]
        vals = [p for p in parts if p is not None]
        return sum(vals) if vals else None

    @property
    def actualTotalCost(self) -> float | None:
        # Prefer explicit total from data source (may include costs not broken into components)
        if self.actualTotalCostRaw is not None:
            return self.actualTotalCostRaw
        parts = [self.actualLaborCost, self.actualEquipmentCost,
                 self.actualMaterialCost, self.actualSubcontractCost]
        vals = [p for p in parts if p is not None]
        return sum(vals) if vals else None

    _strip_code = field_validator("code", mode="before")(_strip_str)
    _strip_description = field_validator("description", mode="before")(_strip_str)
    _strip_unit = field_validator("unitOfMeasure", mode="before")(_strip_str)


class HJTimeCard(BaseModel):
    """
    HeavyJob time card entry (flattened).

    One row = one employee's hours on one cost code for one day.
    Flattened from the nested API response (timecard -> employees -> hours -> cost codes).
    Used for actual MH/unit calculation and crew analysis.
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None                   # HCSS timecard UUID
    jobId: Optional[str] = None
    costCodeId: Optional[str] = None           # HCSS cost code UUID
    costCode: Optional[str] = None             # Denormalized code string
    tc_date: Optional[str] = None              # ISO date string (YYYY-MM-DD)
    employeeId: Optional[str] = None
    employeeName: Optional[str] = None
    employeeCode: Optional[str] = None         # Employee code (typically name in HCSS)
    payClassCode: Optional[str] = None         # Trade code (e.g., FORE, OPR1, LAB1)
    payClassDesc: Optional[str] = None         # Trade description (e.g., Foreman, Operator)
    hours: Optional[float] = None              # Total hours (regular + OT + DOT)
    equipmentId: Optional[str] = None
    equipmentHours: Optional[float] = None
    foremanId: Optional[str] = None
    foremanName: Optional[str] = None          # Foreman description from timecard
    status: Optional[str] = None               # 'Approved', 'Pending'
    quantity: Optional[float] = None           # Production quantity that day
    notes: Optional[str] = None                # Foreman's cost code note (privateNotes)

    _strip_name = field_validator("employeeName", mode="before")(_strip_str)


class HJEquipmentEntry(BaseModel):
    """
    HeavyJob equipment entry from a timecard.

    One row = one piece of equipment on one cost code for one day.
    Captured from the equipment array in the timecard detail response.
    """
    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None                   # HCSS timecard UUID
    jobId: Optional[str] = None
    costCodeId: Optional[str] = None
    costCode: Optional[str] = None
    tc_date: Optional[str] = None
    equipmentId: Optional[str] = None
    equipmentCode: Optional[str] = None        # Equipment number (e.g., 375EXC)
    equipmentDesc: Optional[str] = None        # Equipment description
    hours: Optional[float] = None


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

class HBEstimateFilters(BaseModel):
    """Nested filters object from HeavyBid estimate response."""
    model_config = ConfigDict(from_attributes=True)

    projectName: Optional[str] = None
    projectNumber: Optional[str] = None
    status: Optional[str] = None
    engineer: Optional[str] = None
    estimator: Optional[str] = None
    owner: Optional[str] = None
    bidDate: Optional[str] = None
    startDate: Optional[str] = None
    reviewDate: Optional[str] = None
    createdDate: Optional[str] = None
    modifiedDate: Optional[str] = None
    state: Optional[str] = None
    typeOfWork: Optional[str] = None
    estimateTag1: Optional[str] = None
    estimateTag2: Optional[str] = None
    estimateTag3: Optional[str] = None
    estimateTag4: Optional[str] = None


class HBEstimateTotals(BaseModel):
    """Nested totals object from HeavyBid estimate response."""
    model_config = ConfigDict(from_attributes=True)

    # Labor
    baseLabor_Direct: Optional[float] = None
    baseLabor_Indirect: Optional[float] = None
    baseLabor_Total: Optional[float] = None
    burden_Direct: Optional[float] = None
    burden_Indirect: Optional[float] = None
    burden_Total: Optional[float] = None
    totalLabor_Direct: Optional[float] = None
    totalLabor_Indirect: Optional[float] = None
    totalLabor_Total: Optional[float] = None
    # Material
    permanentMaterial_Direct: Optional[float] = None
    permanentMaterial_Indirect: Optional[float] = None
    permanentMaterial_Total: Optional[float] = None
    constructionMaterial_Direct: Optional[float] = None
    constructionMaterial_Indirect: Optional[float] = None
    constructionMaterial_Total: Optional[float] = None
    # Subcontract
    subcontract_Direct: Optional[float] = None
    subcontract_Indirect: Optional[float] = None
    subcontract_Total: Optional[float] = None
    # Equipment
    equipmentOperatingExpense_Direct: Optional[float] = None
    equipmentOperatingExpense_Indirect: Optional[float] = None
    equipmentOperatingExpense_Total: Optional[float] = None
    companyEquipment_Direct: Optional[float] = None
    companyEquipment_Indirect: Optional[float] = None
    companyEquipment_Total: Optional[float] = None
    rentedEquipment_Direct: Optional[float] = None
    rentedEquipment_Indirect: Optional[float] = None
    rentedEquipment_Total: Optional[float] = None
    # Equipment totals
    totalEqp_Direct: Optional[float] = None
    totalEqp_Indirect: Optional[float] = None
    totalEqp_Total: Optional[float] = None
    # Entry cost
    totalEntryCost_Takeoff_Direct: Optional[float] = None
    totalEntryCost_Takeoff_Indirect: Optional[float] = None
    totalEntryCost_Takeoff_Total: Optional[float] = None
    totalEntryCost_Bid_Direct: Optional[float] = None
    totalEntryCost_Bid_Indirect: Optional[float] = None
    totalEntryCost_Bid_Total: Optional[float] = None
    # Markup & bid
    balMarkup_Bid: Optional[float] = None
    actualMarkup_Bid: Optional[float] = None
    balancedBid_Bid: Optional[float] = None
    bidTotal_Bid: Optional[float] = None
    # Manhours
    manhours_Direct: Optional[float] = None
    manhours_Indirect: Optional[float] = None
    manhours_Total: Optional[float] = None
    # Addons
    addonBondTotal: Optional[float] = None
    addon_Cost: Optional[float] = None
    bond: Optional[float] = None
    addon_Markup: Optional[float] = None
    addon_Total: Optional[float] = None
    # Misc
    misc1_Total: Optional[float] = None
    misc2_Total: Optional[float] = None
    misc3_Total: Optional[float] = None
    totalCost_Takeoff: Optional[float] = None
    totalCost_Bid_LessPassThrough: Optional[float] = None
    job_Duration: Optional[float] = None


class HBEstimate(BaseModel):
    """
    HeavyBid estimate record.

    Represents a bid for a project. Links to bid items (pay items),
    activities (cost buildup), and resources (labor/equipment rates).
    The estimate code typically starts with a job number (e.g. "8553-CO-WEIR")
    which links to the corresponding HeavyJob project.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: Optional[str] = None
    partitionId: Optional[str] = None
    businessUnitId: Optional[str] = None
    businessUnitCode: Optional[str] = None
    heavyBidDivision: Optional[str] = None
    code: Optional[str] = None                 # e.g. "8553-CO-WEIR"
    name: Optional[str] = None                 # e.g. "SPD Pump Base Welding"
    processedStatus: Optional[int] = None
    description: Optional[str] = None
    estimateVersion: Optional[str] = None
    filters: Optional[HBEstimateFilters] = None
    totals: Optional[HBEstimateTotals] = None

    _strip_name = field_validator("name", mode="before")(_strip_str)


class HBBidItem(BaseModel):
    """
    HeavyBid bid item (pay item / scheduled value).

    The owner's line items — what the owner pays us for.
    Each bid item is backed by one or more activities (cost buildup).
    Full cost breakdown stored at this level for chat query granularity.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: Optional[str] = None
    estimateId: Optional[str] = None
    estimateCode: Optional[str] = None
    lastModified: Optional[str] = None
    biditemCode: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None                 # "D" = direct, "I" = indirect
    quantity: Optional[float] = None
    bidQuantity: Optional[float] = None
    units: Optional[str] = None
    bidPrice: Optional[float] = None
    # Cost breakdown
    labor: Optional[float] = None
    burden: Optional[float] = None
    permanentMaterial: Optional[float] = None
    constructionMaterial: Optional[float] = None
    subcontract: Optional[float] = None
    equipmentOperatingExpense: Optional[float] = None
    companyEquipment: Optional[float] = None
    rentedEquipment: Optional[float] = None
    misc1: Optional[float] = None
    misc2: Optional[float] = None
    misc3: Optional[float] = None
    directTotal: Optional[float] = None
    indirectTotal: Optional[float] = None
    totalCost: Optional[float] = None
    manhours: Optional[float] = None
    markup: Optional[float] = None
    totalTakeoff: Optional[float] = None
    totalBalanced: Optional[float] = None
    addonBond: Optional[float] = None
    # Metadata
    clientNumber: Optional[str] = None
    wbsCode: Optional[str] = None
    pricingStatus: Optional[str] = None
    costNotes: Optional[str] = None
    bidNotes: Optional[str] = None
    folder: Optional[str] = None
    reviewFlag: Optional[str] = None
    sortCode: Optional[str] = None

    _strip_description = field_validator("description", mode="before")(_strip_str)


class HBActivity(BaseModel):
    """
    HeavyBid activity (cost buildup).

    The estimator's detail — how each bid item is priced. Includes production
    assumptions, crew configuration, duration, and the estimator's notes
    explaining the reasoning behind the numbers.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: Optional[str] = None
    estimateId: Optional[str] = None
    estimateCode: Optional[str] = None
    lastModified: Optional[str] = None
    biditemId: Optional[str] = None
    biditemCode: Optional[str] = None
    activityCode: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    units: Optional[str] = None
    # Production
    productionType: Optional[str] = None       # "UH" = units/hour
    productionRate: Optional[float] = None
    hoursPerDay: Optional[float] = None
    crew: Optional[str] = None
    crewHours: Optional[float] = None
    crewPercent: Optional[float] = None
    manHours: Optional[float] = None
    calculatedDuration: Optional[float] = None
    efficientPercent: Optional[float] = None
    # Cost breakdown
    labor: Optional[float] = None
    burden: Optional[float] = None
    permanentMaterial: Optional[float] = None
    constructionMaterial: Optional[float] = None
    subcontract: Optional[float] = None
    equipmentOperatingExpense: Optional[float] = None
    companyEquipment: Optional[float] = None
    rentedEquipment: Optional[float] = None
    misc1: Optional[float] = None
    misc2: Optional[float] = None
    misc3: Optional[float] = None
    directTotal: Optional[float] = None
    crewCost: Optional[float] = None
    crewCost_WithMaterial: Optional[float] = None
    # Estimator notes — critical context
    notes: Optional[str] = None
    # Metadata
    workersCompCode: Optional[str] = None
    calendar: Optional[str] = None
    factorable: Optional[str] = None
    factor: Optional[float] = None
    nonAdditive: Optional[str] = None
    # HeavyJob mapping fields (from export, may be empty)
    heavyJobCode: Optional[str] = None
    heavyJobDescription: Optional[str] = None
    heavyJobQuantity: Optional[float] = None
    heavyJobUnit: Optional[str] = None
    # Accounting
    accountingJCCode1: Optional[str] = None
    accountingJCCode2: Optional[str] = None
    accountingRevenueCode: Optional[str] = None

    _strip_description = field_validator("description", mode="before")(_strip_str)


class HBResource(BaseModel):
    """
    HeavyBid resource (labor, equipment, or material).

    Individual line items within an activity — the crew members, equipment,
    and materials that make up the cost buildup.
    """
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: Optional[str] = None
    estimateId: Optional[str] = None
    estimateCode: Optional[str] = None
    biditemId: Optional[str] = None
    activityId: Optional[str] = None
    lastModified: Optional[str] = None
    resourceCode: Optional[str] = None
    activityCode: Optional[str] = None
    biditemCode: Optional[str] = None
    description: Optional[str] = None
    typeCost: Optional[str] = None             # "L" = labor, "E" = equipment, "P" = permanent material
    typeOfEquipmentRent: Optional[str] = None
    subType: Optional[str] = None
    quantity: Optional[float] = None
    units: Optional[str] = None
    percent: Optional[float] = None
    unitPrice: Optional[float] = None
    currency: Optional[str] = None
    subTypeCost: Optional[float] = None
    total: Optional[float] = None
    pieces: Optional[float] = None
    factorable: Optional[str] = None
    factor: Optional[float] = None
    skipCost: Optional[str] = None
    operatingPercent: Optional[float] = None
    rentPercent: Optional[float] = None
    crewCode: Optional[str] = None
    equipmentOperatorCode: Optional[str] = None
    supplementalDescription: Optional[str] = None
    manHourUnit: Optional[float] = None

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
