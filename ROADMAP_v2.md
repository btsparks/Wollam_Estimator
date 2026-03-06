# WEIS — Development Roadmap
## Wollam Estimating Intelligence System

---

## Guiding Principle

**The data layer is the asset. Build the foundation before the features.**

Every phase must be fully functional and delivering real value before the next phase begins. The HCSS API integration is the critical path — it transforms WEIS from a manually-fed tool into an automatically-enriched knowledge base.

---

## Phase Summary

| Phase | Name | Core Deliverable | Duration | Status |
|-------|------|-----------------|----------|--------|
| A | Architecture & Schema | Database v2.0, API client framework, transformation layer | 1-2 weeks | ✅ Complete |
| B | Mock Data & Validation | Mock HCSS data from JCDs, validate transformation logic | 1-2 weeks | ✅ Complete |
| C | API Connection | Live HCSS API, real data extraction | When credentials arrive | 🔲 Blocked |
| D | Full Integration | Sync orchestration, PM interview UI, agent integration | 1-2 weeks after C | 🔲 Planned |

---

## Phase A — Architecture & Schema ✅

**Goal:** Build the complete framework without live API. Everything compiles, everything has a test harness, and the data model is proven.

### Deliverables

| Task | File | Status |
|------|------|--------|
| Define database schema v2.0 | `scripts/migrate_v2.py` | ✅ Complete |
| Create Pydantic models for API responses | `app/hcss/models.py` | ✅ Complete |
| Build base API client (auth, pagination, retry) | `app/hcss/client.py` | ✅ Complete |
| Build HeavyJob API wrapper | `app/hcss/heavyjob.py` | ✅ Complete |
| Build HeavyBid API wrapper | `app/hcss/heavybid.py` | ✅ Complete |
| Create discipline mapper (configurable) | `app/transform/mapper.py` | ✅ Complete |
| Create unit cost calculator | `app/transform/calculator.py` | ✅ Complete |
| Create rate card generator | `app/transform/rate_card.py` | ✅ Complete |
| Create data validator | `app/transform/validator.py` | ✅ Complete |
| Write discipline mapping config | `config/discipline_map.yaml` | ✅ Complete |
| Write HCSS config template | `config/hcss_config.yaml` | ✅ Complete |
| Write rate threshold config | `config/rate_thresholds.yaml` | ✅ Complete |

### Definition of Done
- [x] All modules created with complete function signatures
- [x] Database schema v2.0 tables created alongside v1.3
- [x] Unit cost calculator passes basic arithmetic tests
- [x] Discipline mapper correctly classifies all known Wollam cost code prefixes
- [x] Configuration files documented and validated

---

## Phase B — Mock Data & Validation ✅

**Goal:** Validate that the transformation logic produces the same rates as the manually-created JCDs. This is the proof point — if API-driven rate cards match manual JCDs, the system works.

**Note:** Phase B validates pipeline math correctness. JCDs are curated intelligence products (PM interviews, crew observations, estimating judgment) — NOT equivalent to raw HeavyJob/HeavyBid API output. Future Phase C+ validation should compare against raw API data, not JCD rates.

### Deliverables

| Task | File | Status |
|------|------|--------|
| Create mock HJ data from Job 8553 JCDs | `tests/mock_data/heavyjob/costcodes_8553.json` | ✅ Complete |
| Create mock HJ data from Job 8576 JCDs | `tests/mock_data/heavyjob/costcodes_8576.json` | ✅ Complete |
| Create mock HB data from proposal docs | `tests/mock_data/heavybid/` | ✅ Complete |
| Write validation tests vs 8553 rates | `tests/test_phase_b_validation.py` | ✅ Complete |
| Write validation tests vs 8576 rates | `tests/test_phase_b_validation.py` | ✅ Complete |
| Test discipline mapper against all cost codes | `tests/test_transform.py` | ✅ Complete |
| Test rate card generation end-to-end | `tests/test_phase_b_validation.py` | ✅ Complete |
| Fix transformation bugs | Working code | ✅ Complete |

### Validation Criteria (All 10/10 Passing ✅)

| Activity | Source | Expected Rate | Tolerance | Result |
|----------|--------|---------------|-----------|--------|
| Wall Form/Strip | 8553 | 0.28 MH/SF | ±0.02 | ✅ |
| Wall Form/Strip | 8576 | 0.20 MH/SF | ±0.02 | ✅ |
| Mat Pour | 8553 | 0.15 MH/CY | ±0.02 | ✅ |
| Pour Floor | 8576 | 0.67 MH/CY | ±0.05 | ✅ |
| All-In Concrete | 8553 | $867/CY | ±$50 | ✅ |
| All-In Concrete | 8576 | $965/CY | ±$50 | ✅ |
| Flanged Joint 20-28" | 8553 | 7 MH/JT | ±0.5 | ✅ |
| SS Pipe EX/BF | 8576 | $3.08/CY | ±$0.25 | ✅ |
| SS Pipe All-In | 8576 | $169/LF | ±$10 | ✅ |
| GC % | 8576 | 15.0% | ±1.0% | ✅ |

### Definition of Done
- [x] Mock data created for both jobs
- [x] All key validation rates match within tolerance
- [x] Rate card generation produces complete output for both jobs
- [x] No unhandled errors in transformation pipeline
- [x] Test suite runs green (111/111 passing)

---

## Phase C — API Connection (When Credentials Arrive)

**Goal:** Connect to live HCSS APIs, pull real data, and validate against mock data.

### Deliverables

| Task | File | Status |
|------|------|--------|
| Configure API credentials | `.env` + `config/hcss_config.yaml` | 🔲 Blocked |
| Test authentication flow | Token lifecycle | 🔲 Blocked |
| Test basic endpoints (business units, jobs) | Verified connectivity | 🔲 Blocked |
| Pull cost codes for a known job (8576) | Compare to JCD data | 🔲 Blocked |
| Compare API response to mock data schema | Fix field mapping | 🔲 Blocked |
| Pull all closed jobs | Database populated | 🔲 Blocked |
| Identify schema differences (mock vs real) | Updated models | 🔲 Blocked |

### Definition of Done
- [ ] Authentication works (token obtained and refreshed)
- [ ] At least one job's cost codes match JCD data
- [ ] All closed jobs pulled and stored in raw data layer
- [ ] Pydantic models validated against real API responses
- [ ] No breaking differences between mock and live schemas

---

## Phase D — Full Integration (1-2 weeks after C)

**Goal:** End-to-end workflow operational — sync jobs, generate rate cards, PM reviews, knowledge base populated.

### Deliverables

| Task | File | Status |
|------|------|--------|
| Build sync orchestrator | `app/hcss/sync.py` | 🔲 Not Started |
| Build PM interview UI (Streamlit) | `app/ui/interview.py` | 🔲 Not Started |
| Build rate card review page | `app/ui/rate_review.py` | 🔲 Not Started |
| Knowledge base aggregation logic | `app/transform/aggregate.py` | 🔲 Not Started |
| Integrate with existing Estimator agent | Updated agent queries | 🔲 Not Started |
| Test full workflow on live data | Documented results | 🔲 Not Started |
| Incremental sync (modified jobs only) | Working incremental | 🔲 Not Started |

### Definition of Done
- [ ] Full sync processes all closed jobs without error
- [ ] Rate cards generated for all synced jobs
- [ ] PM interview UI functional and tested
- [ ] At least 3 rate cards PM-reviewed and approved
- [ ] Knowledge base contains aggregated rates from approved cards
- [ ] Estimator agent successfully queries knowledge base
- [ ] Incremental sync works for newly closed jobs

---

## Beyond Phase D — Future Development

Once the HCSS integration pipeline is proven and the knowledge base is growing, the following become possible:

### Agent Development (Post Phase D)
Build the remaining agents in priority order (see AGENTS.md). Each agent depends on a solid knowledge base.

### Command Center Dashboard
Full project tracking UI with estimate status, agent lanes, and decision queue. Requires all agents to be functional.

### Scheduled Sync
Automatic daily/weekly sync of HCSS data. Requires Phase D to be stable in production.

### Foundation Accounting Integration
Material costs, vendor invoicing, and AP data from Foundation. Separate API or export integration.

### Multi-Estimate Comparison
Compare multiple bids for the same scope. Requires multiple estimates in the knowledge base.

### PM Cataloging Portal
Self-serve PM interview interface. PMs complete interviews at project closeout without Travis's involvement.

### Performance Analytics
How accurate have our estimates been? Track bid-to-actual across all cataloged jobs.

---

## Decision Points

| Decision | When | Who Decides |
|----------|------|-------------|
| Request HCSS API credentials | Phase A complete | Travis |
| SQLite → PostgreSQL migration | >50 jobs or multi-user needed | Travis |
| Scheduled auto-sync | After Phase D stable for 1 month | Travis |
| Cloud deployment | When multi-user access required | Travis |
| Share system company-wide | After knowledge base has 10+ approved jobs | Leadership |

---

## What Not to Build (Yet)

- Mobile app — desktop/web is sufficient for estimating workflow
- Real-time collaboration — single-user for now
- Automated proposal submission — human reviews final output
- Foundation API integration — separate effort after HCSS pipeline proven
- Custom frontend framework — Streamlit handles current needs

---

*WEIS Roadmap v2.0*
*Last Updated: March 2026*
