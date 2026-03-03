# Wollam Estimating Intelligence System (WEIS)

**Wollam Construction — Internal Tool — Confidential**

---

## What This Is

WEIS is an AI-powered estimating application built for Wollam Construction, a Utah-based industrial heavy civil contractor. It transforms the company's accumulated project experience and historical cost data into an active intelligence layer that supports every stage of the estimating process — from RFP intake through proposal submission.

The system connects directly to Wollam's HCSS HeavyJob and HeavyBid systems via API, automatically extracting cost data, production rates, and bid assumptions from every completed project. That raw data is transformed into validated rate cards, benchmarked against historical performance, and enriched with PM-captured lessons learned — creating a growing knowledge base that makes every future estimate faster, more accurate, and defensible.

The system is designed for estimators, project managers, and the chief estimator. It does not require any understanding of AI to use. The complexity is entirely in the backend.

---

## Current State (v1.3 → v2.0 Migration)

| Component | Status | Notes |
|-----------|--------|-------|
| SQLite Database (v1.3) | ✅ Operational | JCD-based schema, 6 agents functional |
| CLI Interface | ✅ Operational | Text-based query interface |
| Streamlit UI | ✅ Operational | Web-based dashboard |
| Job 8553 (SPD Pump Station) | ✅ Fully cataloged | 8 JCD sections + Master Summary |
| Job 8576 (5600 Pump Station) | ✅ Partially cataloged | 5 JCD sections + Master Summary |
| HCSS API Integration | 🔄 Phase A | Architecture & schema design |
| Database v2.0 Migration | 🔲 Not Started | API-native relational schema |
| PM Interview Module | 🔲 Not Started | Lessons learned capture workflow |

---

## Repository Structure

```
weis/
├── README.md                  # This file
├── VISION.md                  # Full system vision and end goal
├── ARCHITECTURE.md            # Technical architecture (v2.0)
├── DATA_SCHEMA.md             # Database schema — raw, transformed, knowledge base
├── AGENTS.md                  # Agent roster, roles, and orchestration
├── ROADMAP.md                 # Phased development plan (A through D)
├── PRODUCT_DESCRIPTION.md     # Non-technical system description
│
├── WEIS_HCSS_API_INTEGRATION_SPEC.md  # HCSS API technical specification (master reference)
│
├── config/
│   ├── hcss_config.yaml       # HCSS API configuration
│   ├── discipline_map.yaml    # Cost code → discipline mapping rules
│   └── rate_thresholds.yaml   # Validation thresholds
│
├── app/
│   ├── main.py                # CLI entry point
│   ├── web.py                 # Streamlit UI
│   │
│   ├── hcss/                  # HCSS API integration module
│   │   ├── __init__.py
│   │   ├── auth.py            # OAuth token management
│   │   ├── client.py          # Base API client
│   │   ├── heavyjob.py        # HeavyJob API wrapper
│   │   ├── heavybid.py        # HeavyBid API wrapper
│   │   ├── models.py          # Pydantic models for API responses
│   │   └── sync.py            # Sync orchestration
│   │
│   ├── transform/             # Data transformation module
│   │   ├── __init__.py
│   │   ├── mapper.py          # Cost code → discipline mapping
│   │   ├── calculator.py      # Unit cost calculations
│   │   ├── rate_card.py       # Rate card generation
│   │   └── validator.py       # Data validation & outlier detection
│   │
│   ├── catalog/               # Cataloger module (evolved)
│   │   ├── __init__.py
│   │   ├── interview.py       # PM interview workflow
│   │   ├── lessons.py         # Lessons learned capture
│   │   ├── review.py          # Rate card review/approval
│   │   └── export.py          # Export to various formats
│   │
│   ├── agents/                # AI agent modules
│   ├── database/              # Database layer (v1.3 → v2.0)
│   └── ui/                    # Streamlit pages
│
├── data/
│   ├── jcd/                   # Legacy JCD markdown files
│   └── weis.db                # SQLite database
│
├── tests/
│   ├── mock_data/             # Mock HCSS API responses
│   │   ├── heavyjob/
│   │   └── heavybid/
│   ├── test_hcss_client.py
│   ├── test_transform.py
│   └── test_rate_calculation.py
│
└── scripts/
    ├── ingest_jcd.py          # Legacy: parse JCD markdown → database
    ├── seed_db.py             # Legacy: seed from existing JCDs
    └── migrate_v2.py          # Migration script: v1.3 → v2.0
```

---

## Build Phases

| Phase | What Gets Built | Status |
|-------|----------------|--------|
| A — Architecture & Schema | Database v2.0, API client framework, transformation layer | 🔄 Current |
| B — Mock Data & Validation | Mock HCSS data from existing JCDs, validate transformation logic | 🔲 Next |
| C — API Connection | Live HCSS API connection, real data extraction | 🔲 Blocked (credentials) |
| D — Full Integration | Sync orchestration, PM interview UI, agent integration | 🔲 Planned |

**Current focus is Phase A. See ROADMAP.md for full detail.**

---

## Data Assets

### Cataloged Jobs (Manual JCD Process)

| Job # | Project | Owner | Type | Contract | Status |
|-------|---------|-------|------|----------|--------|
| 8553 | RTK SPD Pump Station | RTKC | Pump Station, Mining | Sub to Kiewit | ✅ Complete (8 JCDs) |
| 8576 | RTKC 5600 Pump Station | RTKC | Pump Station, Mining | Sub to Kiewit/RTKC FF | ✅ Partial (5 JCDs) |

### Target: API-Driven Extraction
Once HCSS API credentials are obtained, all closed jobs in HeavyJob will be bulk-extracted and cataloged programmatically — replacing the manual process for future jobs and backfilling historical data.

---

## Key Contacts

| Role | Person | Responsibility |
|------|--------|---------------|
| System Owner / Chief Estimator | Travis | Architecture, data validation, build direction |
| Data Source | Project Managers | PM interviews for lessons learned and context |

---

## Important Constraints

- This is an internal tool. No external data leaves the system.
- All rate data is proprietary to Wollam Construction.
- The AI layer must be explainable — every recommendation must cite its source job and cost code.
- The UI must be usable by someone with no AI knowledge.
- HCSS API credentials are stored as environment variables, never in source code.

---

## Master Reference

The `WEIS_HCSS_API_INTEGRATION_SPEC.md` file is the definitive technical specification for the HCSS integration architecture. All other documentation files align to it. When in doubt, that spec is the source of truth.

---

*WEIS v2.0 — Architecture Phase*
*Wollam Construction — Internal Use Only*
