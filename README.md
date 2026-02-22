# Wollam Estimating Intelligence System (WEIS)

**Wollam Construction — Internal Tool — Confidential**

---

## What This Is

WEIS is an AI-powered estimating application built for Wollam Construction, a Utah-based industrial heavy civil contractor. It transforms the company's accumulated project experience and historical cost data into an active intelligence layer that supports every stage of the estimating process — from RFP intake through proposal submission.

The system is designed for estimators, project managers, and the chief estimator. It does not require any understanding of AI to use. The complexity is entirely in the backend.

---

## Repository Structure

```
weis/
├── README.md                  # This file
├── VISION.md                  # Full system vision and end goal
├── MVP_SPEC.md                # Phase 1 build specification
├── ARCHITECTURE.md            # Technical architecture and decisions
├── DATA_SCHEMA.md             # Database schema for all JCD data
├── AGENTS.md                  # Agent roster, roles, and orchestration
├── ROADMAP.md                 # Phased development plan
│
├── data/
│   ├── jcd/                   # Job Cost Data markdown files (source)
│   └── db/                    # SQLite database (generated)
│
├── scripts/
│   ├── ingest_jcd.py          # Parse JCD markdown → database
│   └── seed_db.py             # Seed database from existing JCDs
│
├── app/
│   ├── main.py                # Application entry point
│   ├── chat.py                # Conversation layer (Phase 1)
│   ├── dashboard.py           # Command center UI (Phase 2)
│   └── agents/                # Agent modules (Phase 3)
│
└── tests/
    └── test_queries.py        # Test historical data queries
```

---

## Build Phases

| Phase | What Gets Built | Status |
|-------|----------------|--------|
| 1 — Data Layer | Database schema, JCD ingestion scripts, data validation | 🔲 Not Started |
| 2 — Conversation Layer | Chat interface querying historical data | 🔲 Not Started |
| 3 — Command Center | Dashboard UI, workflow tracking, estimate status | 🔲 Not Started |
| 4 — Agent Layer | Role-based agents, chief estimator orchestration | 🔲 Not Started |
| 5 — Full System | RFP intake through proposal, complete lifecycle | 🔲 Not Started |

**Start with Phase 1. Do not skip ahead.**

---

## Current Data Assets

The following Job Cost Data documents already exist and are ready for ingestion:

| Job # | Project Name | Status | Disciplines |
|-------|-------------|--------|-------------|
| 8553 | RTK SPD Pump Station | ✅ Complete | Earthwork, Concrete, Structural Steel, Piping, Mechanical, Electrical, Building Erection, General Conditions |
| 8576 | RTKC 5600 Pump Station | 🔄 In Progress | TBD |

---

## Quick Start (Phase 1)

```bash
# Clone and set up environment
git clone [repo]
cd weis
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Initialize database
python scripts/seed_db.py

# Test a query
python scripts/test_query.py "20-inch flanged joint production rate"
```

---

## Key Contacts

| Role | Person | Responsibility |
|------|--------|---------------|
| System Owner | Travis | Architecture decisions, data validation, build direction |
| Data Entry | Project Managers | Cataloging completed jobs post-closeout |

---

## Important Constraints

- This is an internal tool. No external data leaves the system.
- All rate data is proprietary to Wollam Construction.
- The AI layer must be explainable — every recommendation must cite its source job and cost code.
- The UI must be usable by someone with no AI knowledge.

---

*WEIS v0.1 — Phase 1 Development*
*Wollam Construction — Internal Use Only*
