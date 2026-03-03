# CLAUDE.md — Instructions for Claude Code
## WEIS Development Context

---

## Project Overview

You are working on WEIS (Wollam Estimating Intelligence System), an internal AI-powered estimating application for Wollam Construction, a Utah-based industrial heavy civil contractor. The system connects to HCSS HeavyJob and HeavyBid APIs to extract historical project cost data, transforms it into validated rate cards, and serves it through an AI-powered query interface.

---

## Architecture Summary

WEIS has a three-tier database architecture:

1. **Raw Data Layer** — Mirror of HCSS API data (jobs, cost codes, timecards, estimates, bid items). Stored exactly as received. No interpretation.
2. **Transformed Data Layer** — Calculated rate cards (budget/actual/recommended rates per cost code), crew configurations, and PM-captured lessons learned. Each rate card requires PM review before rates are trusted.
3. **Estimator Knowledge Base** — Aggregated rates across all approved rate cards. This is what the Estimator Agent queries.

Data flows: HCSS APIs → Raw Layer → Transformation → Rate Cards → PM Review → Knowledge Base

---

## Key Technical Decisions

- **Python 3.11+** with async support (httpx for API calls)
- **SQLite** database (migration path to PostgreSQL when scale requires it)
- **Pydantic v2** for all API response models
- **Streamlit** for web UI
- **YAML** for configuration (discipline mapping, rate thresholds, API settings)
- **pytest** for testing, with mock HCSS API responses based on existing JCD data

---

## Master Reference Document

`WEIS_HCSS_API_INTEGRATION_SPEC.md` is the definitive technical specification. It contains:
- Complete HCSS API endpoint documentation
- Database schema v2.0 (full SQL)
- Python code for API clients, transformation logic, and PM interview workflow
- Pydantic data models for all API responses
- Implementation phases (A through D)
- Configuration file templates

**When in doubt about architecture, data models, or API integration, refer to this spec.**

---

## Current State

- Database v1.3 is operational with JCD-based schema and 6 agents
- Jobs 8553 and 8576 are manually cataloged with validated rate libraries
- CLI and Streamlit interfaces are functional
- HCSS API credentials are not yet available (Phase C blocked)
- Phase A (architecture) and Phase B (mock data validation) can proceed without credentials

---

## Module Structure

```
app/
├── hcss/           # HCSS API integration (NEW - Phase A)
│   ├── auth.py     # OAuth token management
│   ├── client.py   # Base API client with pagination and retry
│   ├── heavyjob.py # HeavyJob endpoint wrappers
│   ├── heavybid.py # HeavyBid endpoint wrappers
│   ├── models.py   # Pydantic response models
│   └── sync.py     # Sync orchestration
│
├── transform/      # Data transformation (NEW - Phase A)
│   ├── mapper.py   # Cost code → discipline mapping
│   ├── calculator.py # Unit cost calculation ($/unit, MH/unit)
│   ├── rate_card.py  # Rate card generation
│   └── validator.py  # Outlier detection, data validation
│
├── catalog/        # Evolved Cataloger (Phase D)
│   ├── interview.py  # PM interview workflow
│   ├── lessons.py    # Lessons learned capture
│   ├── review.py     # Rate card review/approval
│   └── export.py     # Export to markdown/Excel
│
├── agents/         # Existing AI agents
├── database/       # Database layer (extending v1.3 → v2.0)
└── ui/             # Streamlit pages
```

---

## Cost Code Mapping

Wollam uses HCSS cost codes with these general prefixes. Mapping is configured in `config/discipline_map.yaml`:

```
10xx, 20xx  → General Conditions
21xx, 31xx  → Earthwork
22xx, 23xx, 33xx, 40xx → Concrete
24xx, 34xx, 42xx → Structural Steel
26xx, 27xx, 32xx → Mechanical / Piping
28xx, 41xx  → Electrical
2405-2415   → SS Pipe Conveyance (specific override)
50xx-54xx   → Change Orders (track by discipline)
```

Cost codes are NOT perfectly consistent across all jobs. The mapper must handle variations using the configurable rules plus AI-assisted interpretation for edge cases.

---

## Unit Cost Calculation

```python
# Budget rates
budget_mh_per_unit = budget_labor_hours / budget_quantity
budget_cost_per_unit = budget_labor_cost / budget_quantity

# Actual rates
actual_mh_per_unit = actual_labor_hours / actual_quantity
actual_cost_per_unit = actual_labor_cost / actual_quantity

# Recommended rate
if actual <= budget:
    recommended = actual + (budget - actual) * 0.2  # 80% toward actual
else:
    recommended = budget + (actual - budget) * 0.5  # 50% between
```

PM can override the recommended rate during interview.

---

## Testing Strategy

- Mock HCSS API responses are built from existing JCD data for Jobs 8553 and 8576
- Validation tests confirm that the transformation pipeline produces rates matching the manual JCDs
- Key validation: wall forming MH/SF, concrete $/CY, SS pipe $/LF, GC percentage must match within defined tolerances

---

## Development Priority

Current focus: **Phase A** — build the framework (schema, models, clients, transformation).
Next: **Phase B** — mock data and validation against known JCD outputs.
Blocked: **Phase C** — requires HCSS API credentials.
After C: **Phase D** — full integration with sync, PM interviews, and agent queries.

---

## Domain Context

- Wollam is an industrial heavy civil contractor in Utah
- Primary work: pump stations, mining infrastructure, piping, concrete structures
- Key client: Rio Tinto Kennecott Copper (RTKC) — mine site work has specific requirements (blast delays, escort requirements, safety training at 1.5x standard)
- HCSS products used: HeavyJob (field cost tracking), HeavyBid (estimating), Foundation (accounting)
- Industry terminology: MH = manhours, CY = cubic yards, SF = square feet, LF = linear feet, JT = joint, EA = each, LS = lump sum, F/S = form and strip, D/L/B = deliver/lay/backfill, EX/BF = excavate/backfill

---

*WEIS — Claude Code Instructions*
*Last Updated: March 2026*
