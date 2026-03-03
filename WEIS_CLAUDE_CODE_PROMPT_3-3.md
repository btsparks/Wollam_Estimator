# WEIS Phase A — Claude Code Implementation Prompt
## Wollam Estimating Intelligence System
### Date: March 3, 2026

---

## WHO YOU ARE

You are building WEIS (Wollam Estimating Intelligence System) for Wollam Construction, a Utah-based industrial heavy civil contractor. Travis (Chief Estimator and Project Executive) is the system owner. He is building this himself using you (Claude Code) rather than hiring developers. He has deep construction estimating domain expertise but is not a professional software developer — write clean, well-commented code that he can understand and maintain.

---

## WHAT EXISTS RIGHT NOW

### Repository State
The WEIS repo has a working v1.3 system with:
- SQLite database with flat JCD-based schema
- 6 operational AI agents (Cataloger, Estimator, and 4 others)
- CLI interface (app/main.py)
- Streamlit web UI (app/web.py)
- JCD ingestion scripts (scripts/ingest_jcd.py, scripts/seed_db.py)
- Two jobs manually cataloged: Job 8553 (complete, 8 JCDs) and Job 8576 (partial, 5 JCDs)

### Documentation Files — READ THESE FIRST

Before writing any code, read these files in this order:

1. **WEIS_HCSS_API_INTEGRATION_SPEC.md** — THE MASTER REFERENCE. This is the definitive technical specification. It contains the complete HCSS API documentation, database schema v2.0, all Python code specifications, Pydantic models, transformation logic, PM interview workflow, configuration templates, and implementation phases. When any other document conflicts with this spec, this spec wins.

2. **CLAUDE_v2.md** — Your operating instructions. Domain context, module structure, cost code mapping, unit cost formulas, terminology glossary.

3. **ARCHITECTURE_v2.md** — System architecture with three-tier database, data flow diagrams, key architectural decisions, technology stack, module responsibilities.

4. **DATA_SCHEMA_v2.md** — Complete SQL for all three database tiers (raw, transformed, knowledge base). Table definitions, relationships, validation rules, sample queries.

5. **ROADMAP_v2.md** — Phase A task list with specific deliverables and definition of done.

6. **VISION_v2.md** — The north star. What the system does, who uses it, how it works at a high level. Read this so you understand why you are building what you are building.

7. **AGENTS_v2.md** — Agent roster and orchestration. You are not building agents yet, but the data layer you are building must support them.

8. **README_v2.md** — Repo structure and current state overview.

---

## WHAT YOU ARE BUILDING (Phase A)

Phase A builds the complete framework for HCSS API integration WITHOUT live API access. Everything compiles, everything has a test harness, and the data model is proven. When API credentials arrive, we plug them in and go.

### Critical Constraint
**Do not break the existing v1.3 system.** All new code is additive. The existing database, agents, CLI, and Streamlit UI must continue to work. New v2.0 tables are created alongside v1.3 tables. New modules are added in new directories.

---

## PHASE A TASK LIST — BUILD IN THIS ORDER

### Task 1: Project Structure Setup

Create the new directory structure alongside existing code:

```
app/
  hcss/                    # NEW — HCSS API integration
    __init__.py
    auth.py                # OAuth token management
    client.py              # Base API client
    heavyjob.py            # HeavyJob API wrapper
    heavybid.py            # HeavyBid API wrapper
    models.py              # Pydantic response models
    sync.py                # Sync orchestration (stub for Phase D)

  transform/               # NEW — Data transformation
    __init__.py
    mapper.py              # Cost code to discipline mapping
    calculator.py          # Unit cost calculations
    rate_card.py           # Rate card generation
    validator.py           # Data validation and outlier detection

  catalog/                 # NEW — Evolved cataloger
    __init__.py
    interview.py           # PM interview workflow (stub for Phase D)
    lessons.py             # Lessons learned capture (stub)
    review.py              # Rate card review/approval (stub)
    export.py              # Export to markdown/Excel (stub)

config/
  hcss_config.yaml         # HCSS API configuration template
  discipline_map.yaml      # Cost code to discipline mapping rules
  rate_thresholds.yaml     # Validation thresholds

scripts/
  migrate_v2.py            # Database migration script (v1.3 to v2.0)

tests/
  mock_data/               # For Phase B
    heavyjob/
    heavybid/
  test_hcss_client.py
  test_transform.py
  test_rate_calculation.py
```

Add new dependencies to requirements.txt:
- httpx>=0.25.0
- pydantic>=2.0.0
- pyyaml>=6.0

### Task 2: Database Schema v2.0

**File: scripts/migrate_v2.py**

Write a migration script that:
1. Connects to the existing SQLite database (data/weis.db)
2. Creates ALL v2.0 tables from DATA_SCHEMA_v2.md alongside existing tables
3. Does NOT drop, rename, or modify any existing v1.3 tables
4. Is idempotent — safe to run multiple times (use CREATE TABLE IF NOT EXISTS)
5. Prints a summary of what was created

Tables to create (from DATA_SCHEMA_v2.md):

**Tier 1 — Raw Data:**
- sync_metadata
- business_unit
- job
- hj_costcode
- hj_timecard
- hj_change_order
- hj_material
- hj_subcontract
- hb_estimate
- hb_biditem
- hb_activity
- hb_resource

**Tier 2 — Transformed:**
- rate_card
- rate_item
- crew_config
- lesson_learned

**Tier 3 — Knowledge Base:**
- rate_library
- benchmark

Include appropriate indexes:
- job.job_number (frequent lookup)
- hj_costcode.job_id + hj_costcode.code (unique constraint)
- hj_costcode.discipline (filtering)
- rate_item.card_id + rate_item.activity (unique constraint)
- rate_item.discipline (filtering)
- rate_library.discipline + rate_library.activity (unique constraint)
- lesson_learned.job_id + lesson_learned.discipline (filtering)

### Task 3: Pydantic Models

**File: app/hcss/models.py**

Define Pydantic v2 models for all HCSS API responses. These models serve two purposes: (1) validate API responses at the deserialization boundary, and (2) provide typed objects for the transformation layer.

Refer to WEIS_HCSS_API_INTEGRATION_SPEC.md Section 4 for the complete model definitions. Key models:

HeavyJob models:
- HJJob — Job record with status, dates, contract info
- HJCostCode — Cost code with budget/actual hours, costs, quantities
- HJTimeCard — Time card entry with employee, hours, date, cost code
- HJChangeOrder — Change order with amount, status, category
- HJMaterial — Material receipt with vendor, quantity, unit cost
- HJSubcontract — Subcontract record with vendor, scope, amounts

HeavyBid models:
- HBEstimate — Estimate header with bid date, total cost/price
- HBBidItem — Bid item with quantity, unit, cost, price
- HBActivity — Activity (cost buildup) with hours, costs by category
- HBResource — Labor/equipment resource with rate and hours

Internal models (transformation layer output):
- RateItem — Single calculated rate with confidence and variance
- RateCard — Collection of rates for one job
- CrewConfig — Crew configuration
- LessonLearned — Lessons learned entry

Important Pydantic v2 patterns:
- Use model_config = ConfigDict(from_attributes=True) for ORM compatibility
- Use Optional[...] with None defaults for nullable API fields
- Use field validators for data cleaning (strip whitespace from strings)
- Use Field(alias=...) if HCSS API field names differ from Python conventions
- Include model_validator for cross-field validation where needed

### Task 4: HCSS API Client

**File: app/hcss/auth.py**

OAuth 2.0 client credentials flow:
- Load client_id and client_secret from environment variables (HCSS_CLIENT_ID, HCSS_CLIENT_SECRET)
- Token endpoint: configurable, default https://api.hcss.com/identity/connect/token
- Token has ~1 hour expiry — cache token and refresh 5 minutes before expiry
- Raise clear error if credentials are not set (do not fail silently)

Class HCSSAuth with methods:
- __init__(client_id, client_secret, token_url)
- async get_token() -> str
- async refresh_if_needed() -> str
- property is_configured -> bool

**File: app/hcss/client.py**

Base API client with:
- Authenticated GET/POST using bearer token from HCSSAuth
- Automatic pagination (HCSS uses skip/take pattern, 100 records per page)
- Retry with exponential backoff (3 retries, 1s/2s/4s)
- Timeout handling (30s default)
- Detailed error logging (status code, endpoint, response body on error)
- Rate limiting awareness (respect 429 responses)

Class HCSSClient with methods:
- __init__(auth, base_url)
- async get(endpoint, params) -> dict
- async get_paginated(endpoint, params) -> list
- async post(endpoint, data) -> dict

**File: app/hcss/heavyjob.py**

HeavyJob API wrapper. Each method returns typed Pydantic models.

Class HeavyJobAPI with methods:
- __init__(client, business_unit_id)
- async get_jobs(status) -> list[HJJob]
- async get_job(job_id) -> HJJob
- async get_cost_codes(job_id) -> list[HJCostCode]
- async get_timecards(job_id, start_date, end_date) -> list[HJTimeCard]
- async get_employee_hours(job_id) -> list
- async get_equipment_hours(job_id) -> list
- async get_change_orders(job_id) -> list[HJChangeOrder]
- async get_forecasts(job_id) -> list
- async get_materials(job_id) -> list[HJMaterial]
- async get_subcontracts(job_id) -> list[HJSubcontract]

Key HeavyJob endpoints (from WEIS_HCSS_API_INTEGRATION_SPEC.md Section 2):
- GET /api/v1/jobs — List jobs for business unit
- GET /api/v1/costCodes?jobId={id} — Cost codes with budget/actual
- GET /api/v1/timecards?jobId={id} — Time card entries
- GET /api/v1/employeeHours?jobId={id} — Employee hour summaries
- GET /api/v1/equipmentHours?jobId={id} — Equipment hour summaries
- GET /api/v1/changeOrders?jobId={id} — Change orders
- GET /api/v1/forecasts?jobId={id} — Forecasts
- GET /api/v1/materials?jobId={id} — Material data
- GET /api/v1/subcontracts?jobId={id} — Subcontract data

**File: app/hcss/heavybid.py**

HeavyBid API wrapper.

Class HeavyBidAPI with methods:
- __init__(client, business_unit_id)
- async get_estimates() -> list[HBEstimate]
- async get_estimate(estimate_id) -> HBEstimate
- async get_biditems(estimate_id) -> list[HBBidItem]
- async get_activities(estimate_id) -> list[HBActivity]
- async get_resources(estimate_id) -> list[HBResource]
- async get_materials(estimate_id) -> list
- async get_activity_codebook() -> list
- async get_material_codebook() -> list

Key HeavyBid endpoints:
- GET /api/v1/estimates — List estimates for business unit
- GET /api/v1/estimates/{id}/biditems — Bid items
- GET /api/v1/estimates/{id}/activities — Activities with cost buildup
- GET /api/v1/estimates/{id}/resources — Labor and equipment resources
- GET /api/v1/estimates/{id}/materials — Material items
- GET /api/v1/activityCodebook — Activity code reference
- GET /api/v1/materialCodebook — Material code reference

### Task 5: Configuration Files

**File: config/hcss_config.yaml**

```yaml
hcss:
  identity_url: "https://api.hcss.com/identity"
  heavyjob_url: "https://api.hcss.com/heavyjob"
  heavybid_url: "https://api.hcss.com/heavybid"
  # Credentials loaded from environment variables:
  # HCSS_CLIENT_ID
  # HCSS_CLIENT_SECRET
  default_business_unit: ""  # Set after first API connection

sync:
  lookback_days: 365
  min_job_value: 50000
  auto_sync_interval: 0       # 0 = manual only
  batch_size: 10

rate_calculation:
  default_labor_rate: 55.00   # $/MH blended rate for MH estimation from dollar data
  variance_threshold: 20      # percent variance that triggers PM interview question
  min_quantity_threshold: 10  # minimum quantity for rate to be meaningful
  recommended_rate_bias: 0.8  # weight toward actual when actual < budget (0 to 1)

confidence:
  strong_min_pct_complete: 90
  moderate_min_pct_complete: 50
  min_data_points_for_strong: 2
```

**File: config/discipline_map.yaml**

```yaml
# Wollam Construction — Cost Code to Discipline Mapping
# Used by app/transform/mapper.py

disciplines:
  general_conditions:
    name: "General Conditions"
    code_prefixes: ["10", "20"]
    subcategories:
      management: ["1005", "1010", "1019", "1026"]
      site: ["1030", "1035", "1040", "1060", "1098"]
      training: ["2035", "2036"]

  earthwork:
    name: "Earthwork"
    code_prefixes: ["21"]
    material_prefixes: ["31"]
    subcategories:
      excavation: ["2110"]
      backfill: ["2115"]
      structural_fill: ["2120"]

  concrete:
    name: "Concrete"
    code_prefixes: ["22", "23"]
    material_prefixes: ["33"]
    sub_prefixes: ["40"]
    subcategories:
      rebar: ["2200"]
      forming: ["2205", "2215"]
      pouring: ["2210", "2220"]
      accessories: ["2225", "2235"]
      vaults: ["2240"]
      cold_weather: ["2202"]
      site_equipment: ["2203"]
      escort: ["2201"]

  structural_steel:
    name: "Structural Steel"
    code_prefixes: ["24"]
    material_prefixes: ["34"]
    sub_prefixes: ["42"]

  mechanical_piping:
    name: "Mechanical / Piping"
    code_prefixes: ["26", "27"]
    material_prefixes: ["32"]
    subcategories:
      hdpe: ["2305"]
      structural_steel_install: ["2310"]
      pumps: ["2330"]
      ehouse: ["2335"]
      ss_header: ["2340"]
      l_panels: ["2365"]
      site_equipment: ["2300"]
      touch_up_paint: ["2320"]

  ss_pipe_conveyance:
    name: "Stainless Steel Pipe Conveyance"
    specific_codes: ["2405", "2410", "2415"]
    subcategories:
      excavation_backfill: ["2405"]
      haul_string: ["2410"]
      welding: ["2415"]

  electrical:
    name: "Electrical"
    code_prefixes: ["28"]
    sub_prefixes: ["41"]

  change_orders:
    name: "Change Orders / Extra Work"
    code_prefixes: ["50", "51", "52", "53", "54"]

# Manual overrides for specific cost codes that do not follow prefix rules
overrides:
  "2036": "general_conditions"
  "3015": "concrete"
  "4040": "concrete"
  "5100": "ss_pipe_conveyance"
  "5105": "ss_pipe_conveyance"
  "5110": "mechanical_piping"
  "5115": "mechanical_piping"
  "5120": "mechanical_piping"
```

**File: config/rate_thresholds.yaml**

```yaml
# Validation thresholds for rate calculations

labor_mh_per_unit:
  min: 0.01
  max: 100.0

cost_per_unit:
  max_ratio: 10.0

production_rates:
  min_quantity: 10
  min_hours: 8

concrete:
  forming_mh_sf:
    min: 0.05
    max: 1.0
    typical: 0.25
  pour_mh_cy:
    min: 0.10
    max: 3.0
    typical: 0.80

earthwork:
  excavation_cost_cy:
    min: 0.50
    max: 25.0
    typical: 5.00

piping:
  weld_mh_joint:
    min: 0.5
    max: 25.0
```

### Task 6: Transformation Layer

**File: app/transform/mapper.py**

DisciplineMapper class that reads config/discipline_map.yaml and maps cost codes to disciplines.

Method map_code(cost_code, description) -> str with this priority:
1. Check overrides dict (exact code match)
2. Check specific_codes in each discipline
3. Check subcategories in each discipline
4. Match by 2-digit prefix to code_prefixes
5. Return "unmapped" if no match (flag for manual review)

Also include:
- get_subcategory(cost_code) -> str or None
- get_all_codes_for_discipline(discipline) -> list[str]

**File: app/transform/calculator.py**

UnitCostCalculator class implementing the formulas from the spec.

Method calculate_labor_rate with inputs: budget_hours, actual_hours, budget_qty, actual_qty, budget_cost, actual_cost. Returns dict with bgt_mh_per_unit, act_mh_per_unit, bgt_cost_per_unit, act_cost_per_unit, rec_rate, rec_basis. Must handle division by zero and null inputs gracefully.

Method calculate_recommended_rate(budget_rate, actual_rate) -> (rate, basis):
- If actual <= budget: recommended = actual + (budget - actual) * 0.2 (80% toward actual)
- If actual > budget: recommended = budget + (actual - budget) * 0.5 (50% between)
- If only one exists, use that one
- If neither exists, return None

Method assess_confidence(pct_complete, has_budget, has_actual, actual_qty, min_qty) -> (level, reason):
- strong: >=90% complete, has budget AND actual, qty > threshold
- moderate: 50-89% complete, or has actual but limited comparison
- limited: has budget only, or <50% complete
- none: insufficient data

Method calculate_variance(budget_value, actual_value) -> (variance_pct, is_flagged):
- Flagged if abs(variance) > config threshold (default 20%)

**File: app/transform/rate_card.py**

RateCardGenerator class that assembles rate cards from cost code data.

Define dataclasses RateItemResult and RateCardResult (see WEIS_HCSS_API_INTEGRATION_SPEC.md Section 6).

Method generate_rate_card(job, cost_codes, estimate=None) -> RateCardResult:
1. Map each cost code to discipline using DisciplineMapper
2. Calculate unit costs for each code using UnitCostCalculator
3. Assess confidence for each rate
4. Calculate variances and flag items >20%
5. Assemble into RateCardResult with separate flagged_items list

**File: app/transform/validator.py**

DataValidator class that reads config/rate_thresholds.yaml.

Method validate_rate_item(item) -> list[str] — returns warning messages
Method validate_rate_card(card) -> dict with warnings, errors, valid keys
Method check_outlier(value, discipline, metric) -> bool

### Task 7: Sync Orchestrator (Stub)

**File: app/hcss/sync.py**

HCSSSyncOrchestrator class — stub for Phase D. Define the class and all method signatures with docstrings explaining what each method will do. Implement only match_estimate_to_job (looks for job_number in estimate name). All other methods raise NotImplementedError("Phase D — requires API credentials").

Methods:
- sync_all_closed_jobs() -> dict
- sync_job(job_id) -> dict
- sync_incremental(since) -> dict
- match_estimate_to_job(job_number, estimates) -> HBEstimate or None

### Task 8: Catalog Module Stubs

**File: app/catalog/interview.py**

PMInterviewWorkflow class — stub for Phase D. Define method signatures with detailed docstrings explaining the four question types (VARIANCE, LESSONS, CONTEXT, RATE_CONFIRM). All methods raise NotImplementedError.

**File: app/catalog/lessons.py, review.py, export.py**

Stub files with class definitions and method signatures. Not implemented until Phase D.

### Task 9: Basic Tests

**File: tests/test_transform.py**

Write tests for the transformation layer using hardcoded values from the existing JCDs:

- test_discipline_mapper_prefixes — all known Wollam cost code prefixes map correctly (1005 -> general_conditions, 2215 -> concrete, 2405 -> ss_pipe_conveyance, 5100 -> ss_pipe_conveyance via override, 9999 -> unmapped)
- test_unit_cost_calculator_basic — basic rate calculation with known inputs
- test_recommended_rate_actual_under_budget — when actual < budget, recommended = actual + (budget - actual) * 0.2
- test_recommended_rate_actual_over_budget — when actual > budget, recommended = budget + (actual - budget) * 0.5
- test_confidence_assessment — all four levels with appropriate inputs
- test_variance_flagging — flagged at >20%, not flagged at <=20%
- test_division_by_zero_handling — zero quantities return None, no exceptions

**File: tests/test_hcss_client.py**

Basic structural tests (no live API):
- test_auth_not_configured — empty credentials returns is_configured = False
- test_heavyjob_api_instantiation — wrapper instantiates without errors
- test_heavybid_api_instantiation — wrapper instantiates without errors

---

## DEFINITION OF DONE — PHASE A

When you are finished, all of these must be true:

- [ ] All directories and files created per Task 1
- [ ] scripts/migrate_v2.py runs successfully, creating all 16 v2.0 tables
- [ ] Existing v1.3 tables and data are untouched
- [ ] All Pydantic models defined with appropriate types and validators
- [ ] Auth module reads credentials from environment variables
- [ ] Base client handles pagination, retry, and error logging
- [ ] HeavyJob wrapper has all endpoint methods with correct signatures
- [ ] HeavyBid wrapper has all endpoint methods with correct signatures
- [ ] All three config YAML files created and documented
- [ ] DisciplineMapper correctly maps all known Wollam cost code prefixes
- [ ] UnitCostCalculator passes all arithmetic tests including edge cases
- [ ] RateCardGenerator class structure is complete with generate_rate_card method
- [ ] DataValidator reads thresholds from config
- [ ] Sync orchestrator stub defines all method signatures
- [ ] PM interview stub defines all method signatures
- [ ] All tests in test_transform.py pass
- [ ] All tests in test_hcss_client.py pass
- [ ] No existing functionality is broken
- [ ] Code has docstrings and comments explaining the "why" not just the "what"

---

## CODING STANDARDS

1. **Python 3.11+** — Use modern syntax (match statements, type hints, X | Y union syntax)
2. **Async where appropriate** — All HCSS API calls should be async (httpx). Database operations can be sync.
3. **Type hints everywhere** — Every function signature should have complete type hints
4. **Docstrings** — Every class and public method gets a docstring explaining purpose and behavior
5. **Comments for domain logic** — Add comments explaining construction industry concepts (why MH/SF matters, what a cost code prefix means)
6. **No magic numbers** — All thresholds and defaults come from config files
7. **Graceful degradation** — If API credentials are not set, the system should still work for manual JCD operations. Never crash on missing config.
8. **Idempotent operations** — Database migration and sync operations must be safe to run multiple times

---

## WHAT NOT TO DO

- Do NOT modify any existing v1.3 files
- Do NOT build a UI for this phase — that is Phase D
- Do NOT attempt to call live HCSS APIs — credentials are not available yet
- Do NOT create mock data files yet — that is Phase B
- Do NOT build the PM interview logic — that is Phase D
- Do NOT build the knowledge base aggregation logic — that is Phase D
- Do NOT over-engineer — keep it simple, make it work, make it right later
- Do NOT add dependencies beyond httpx, pydantic, and pyyaml unless absolutely necessary

---

## DOMAIN TERMINOLOGY QUICK REFERENCE

These terms appear throughout the codebase and documentation:

- **MH** — Manhours. The fundamental unit of labor measurement. MH/SF (manhours per square foot) and MH/CY (manhours per cubic yard) are the most common production rates.
- **CY** — Cubic yards. Used for concrete, earthwork, pipe trench volumes.
- **SF** — Square feet. Used for forming, floor area, building area.
- **LF** — Linear feet. Used for pipe, conduit, waterstop.
- **JT** — Joint. Used for pipe welding (flanged or butt-weld connections).
- **EA** — Each. Used for pumps, vaults, L-panels, embeds.
- **LS** — Lump Sum. Fixed price for a scope of work regardless of quantity.
- **F/S** — Form and Strip. Building concrete forms, pouring concrete, then removing (stripping) the forms.
- **D/L/B** — Deliver, Lay, Backfill. Full pipe installation cycle.
- **EX/BF** — Excavate/Backfill. Dig a trench and fill it back in (typically around pipe).
- **P/C** — Place and Compact. Structural fill placed in lifts and compacted.
- **SS** — Stainless Steel. 24" SS pipe was a major scope item on Jobs 8553 and 8576.
- **HDPE** — High Density Polyethylene pipe. Fused (welded) connections.
- **CO** — Change Order. Additional scope not in the original contract.
- **DD** — Design Development. Change orders driven by incomplete or evolving design.
- **SC** — Scope Change. Change orders driven by owner-directed scope additions.
- **FF** — Fixed Fee. Contract type where the fee (profit) is a fixed amount regardless of cost.
- **JCD** — Job Cost Data. Wollam's standardized format for cataloged project data.
- **CPI** — Cost Performance Index. Budget / Actual. Above 1.0 = under budget.
- **RTKC** — Rio Tinto Kennecott Copper. Wollam's primary mine site client.
- **HCSS** — Heavy Construction Systems Specialists. Vendor of HeavyJob, HeavyBid, Foundation.
- **HeavyJob** — Field cost tracking system. Source of actual costs, hours, quantities.
- **HeavyBid** — Estimating system. Source of bid assumptions, planned rates, cost buildup.
- **Foundation** — Accounting system. Source of material invoices, AP, vendor data.

---

## AFTER PHASE A

When Phase A is complete, Travis will review the code and then we move to Phase B: creating mock HCSS API response data from the existing JCD files (Jobs 8553 and 8576), running the full transformation pipeline against that mock data, and validating that the calculated rates match the manually-produced JCD rates within defined tolerances. That is the proof point — if the automated pipeline produces the same rates as 3-4 hours of manual cataloging work, the system works.

Phase B validation targets (rates must match within tolerance):

| Activity | Source Job | Expected Rate | Tolerance |
|----------|-----------|---------------|-----------|
| Wall Form/Strip | 8553 | 0.28 MH/SF | +/- 0.02 |
| Wall Form/Strip | 8576 | 0.20 MH/SF | +/- 0.02 |
| Mat Pour | 8553 | 0.15 MH/CY | +/- 0.02 |
| Pour Floor | 8576 | 0.67 MH/CY | +/- 0.05 |
| All-In Concrete | 8553 | $867/CY | +/- $50 |
| All-In Concrete | 8576 | $965/CY | +/- $50 |
| Flanged Joint 20-28 inch | 8553 | 7 MH/JT | +/- 0.5 |
| SS Pipe EX/BF | 8576 | $3.08/CY | +/- $0.25 |
| SS Pipe All-In Install | 8576 | $169/LF | +/- $10 |
| GC Percentage | 8576 | 15.0% | +/- 1.0% |

These are your acceptance criteria for Phase B. Build Phase A so that when mock data is plugged in during Phase B, these numbers come out the other end.

---

*WEIS Phase A — Claude Code Implementation Prompt*
*March 3, 2026*
