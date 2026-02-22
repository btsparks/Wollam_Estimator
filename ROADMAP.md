# WEIS — Development Roadmap
## Wollam Estimating Intelligence System

---

## Guiding Principle

**The data layer is the asset. Build the foundation before the features.**

Every phase must be fully functional and delivering real value before the next phase begins. No phase gets started until the previous one is complete and validated in real use.

---

## Phase Summary

| Phase | Name | Core Deliverable | Status |
|-------|------|-----------------|--------|
| 0 | Data Collection | Historical JCD library | 🔄 In Progress |
| 1 | Data Layer | Structured database + ingestion | 🔲 Not Started |
| 2 | Conversation Layer | Chat interface for historical queries | 🔲 Not Started |
| 3 | Command Center | Dashboard UI + workflow tracking | 🔲 Not Started |
| 4 | Agent Layer | Role-based agents + orchestration | 🔲 Not Started |
| 5 | Full Lifecycle | RFP intake through proposal | 🔲 Not Started |

---

## Phase 0 — Data Collection
**Status: In Progress**
**Owner: Travis (transitioning to PM responsibility)**

### What This Is
Building the historical job cost data library that feeds everything else. This phase is ongoing — every completed project adds to the library.

### Work Remaining
- Complete Job 8576 (RTKC 5600 Pump Station) cataloging
- Continue cataloging additional completed jobs
- Target: minimum 5 fully cataloged jobs before Phase 1 completion
- Establish PM cataloging workflow for project closeout

### Definition of Done for Phase 0 Foundation
- [ ] Job 8553 — All 8 JCD sections + Master Summary complete ✅
- [ ] Job 8576 — All JCD sections + Master Summary complete
- [ ] At least 3 additional jobs cataloged (different project types if possible)
- [ ] Cataloger Agent system prompt documented and tested
- [ ] PM cataloging guide written (how to do this without Travis)

### Ongoing After Phase 0
Phase 0 never fully closes. PMs catalog jobs at closeout indefinitely. Every new job strengthens the database.

---

## Phase 1 — Data Layer
**Estimated Duration: 2-4 weeks**
**Primary Tool: Claude Code**

### Goal
Get all existing JCD data out of markdown files and into a structured, queryable database.

### Deliverables

**1.1 Database Setup**
- SQLite database created with full schema (see DATA_SCHEMA.md)
- All tables created with indexes
- Schema validated against all existing JCD documents
- Migration scripts written for schema changes

**1.2 Ingestion Scripts**
- `ingest_jcd.py` — Parses JCD markdown → database records
- `seed_db.py` — Runs full ingestion of all existing JCDs
- `validate_db.py` — Data quality report
- All scripts tested and documented

**1.3 Data Validation**
- All Job 8553 data ingested and validated
- Validation report shows >95% coverage
- Spot checks: 20 random records verified against source JCD documents
- Data quality flags documented

**1.4 Basic Query Functions**
- Query by activity name (unit costs, production rates)
- Query by discipline
- Query by project type
- Query for lessons learned by category
- All functions return results with source citations

### Definition of Done
- [ ] Database created and fully populated with Job 8553 data
- [ ] Ingestion script runs cleanly on all existing JCDs
- [ ] Validation report confirms >95% data coverage
- [ ] 20 spot-check records verified against source documents
- [ ] Query functions working for all data types
- [ ] README updated with setup instructions

### Success Test
Run this query: *"What are all unit costs for concrete work on Job 8553?"*
Expected: Complete list of concrete unit costs with cost codes, budget rates, actual rates, and recommended rates.

---

## Phase 2 — Conversation Layer
**Estimated Duration: 3-6 weeks**
**Primary Tool: Claude Code + Anthropic API**
**Prerequisite: Phase 1 complete and validated**

### Goal
A simple interface where any team member can ask a question in plain English and get a sourced answer from the historical database.

### Deliverables

**2.1 Query Engine**
- Natural language → database query translation via Claude API
- Context management (database schema always in context)
- Multi-part question handling
- Response formatting with source citations and confidence levels
- Graceful handling of questions the data can't answer

**2.2 Chat Interface — Phase 2a: CLI**
- Terminal-based chat interface
- Conversation history within a session
- Clear, formatted output with citations
- Command for data validation report (`/status`)
- Command for available disciplines (`/disciplines`)

**2.3 Chat Interface — Phase 2b: Streamlit (if needed)**
- Simple web interface
- Chat history display
- Source citation display
- Runs locally on user's machine
- No authentication required for Phase 2

**2.4 Active Bid Document Layer**
- Simple file intake for active bid RFP documents
- Chat can query both historical data AND current bid documents
- Context switching: "based on this project's specs..." vs "based on our history..."

### Definition of Done
- [ ] 30 representative test questions answered correctly
- [ ] All answers include source job, cost code, discipline
- [ ] All answers include confidence level
- [ ] Questions with no data produce "insufficient data" response, not hallucination
- [ ] Non-technical user can operate interface without instruction
- [ ] Interface runs locally without internet (API call excepted)

### Test Question Set (must all pass)
1. What did we pay for 20-inch flanged joints?
2. What was our concrete material cost per CY on pump station work?
3. What crew did we use for mat pours?
4. What production rate did we achieve on structural excavation?
5. What did steel erection cost per ton?
6. What was our general conditions percentage?
7. What lessons did we learn about piping on Job 8553?
8. What subcontractor did we use for rebar and at what cost per pound?
9. What was the all-in cost per CY for concrete?
10. What was the electrical subcontractor cost per SF?
[...10 more discipline-specific, 10 more lessons learned]

---

## Phase 3 — Command Center
**Estimated Duration: 8-12 weeks**
**Primary Tool: Claude Code**
**Prerequisite: Phase 2 complete and in active use**

### Goal
A visual dashboard that tracks estimate progress, shows agent status, and guides the chief estimator through each step.

### Deliverables

**3.1 Estimate State Management**
- Database tables for active estimates (separate from historical data)
- Estimate creation workflow (new estimate from RFP)
- Discipline status tracking
- Agent/role status tracking
- Decision log

**3.2 Dashboard UI**
- Estimate overview (project name, bid date, current status)
- Discipline lanes (status per discipline: Not Started → In Progress → Complete)
- Agent status (what each role has produced)
- Decision queue (what chief estimator needs to decide)
- Recent activity feed
- Days until bid deadline (prominent)

**3.3 Document Register**
- Active bid document upload and organization
- Addendum tracking with impact flags
- RFI log
- Version control (current vs superseded documents)

**3.4 Basic Workflow Enforcement**
- Quantities must be entered before rates are applied
- Sub scope split must be approved before RFQs go out
- Chief estimator sign-off required before estimate is locked

### Definition of Done
- [ ] Dashboard displays correctly for a test estimate
- [ ] Workflow enforcement prevents out-of-sequence steps
- [ ] Document register tracks addenda and flags changes
- [ ] Non-technical user can navigate without instruction
- [ ] Works on standard company laptop/browser

---

## Phase 4 — Agent Layer
**Estimated Duration: 12-20 weeks**
**Primary Tool: Claude Code + Anthropic API**
**Prerequisite: Phase 3 complete and validated on real bids**

### Goal
Each estimating role is implemented as an AI agent with defined inputs, outputs, and handoffs.

### Agent Build Sequence
1. Document Control agent (most mechanical, lowest risk)
2. Quality Manager agent (spec reading, well-defined output)
3. Safety Manager agent (similar to quality, narrower scope)
4. Estimator agents by discipline (core value, build on Phase 1-2 foundation)
5. Legal/Contract agent (requires careful validation)
6. Subcontract/Procurement agent (complex workflow)
7. Scheduler agent
8. Shadow PM agent
9. Chief Estimator orchestrator (last — depends on all others)

### Definition of Done
- [ ] All 10 agents implemented and tested
- [ ] Orchestration flow works end-to-end on a test estimate
- [ ] Each agent output is stored and auditable
- [ ] Chief estimator decision queue surfaces items correctly
- [ ] System tested on a real live bid

---

## Phase 5 — Full Lifecycle
**Estimated Duration: Ongoing**
**Prerequisite: Phase 4 in active use**

### Goal
Complete RFP-to-proposal capability with continuous improvement as more jobs are cataloged.

### Deliverables
- Proposal assembly (cover letter, exec summary, project approach)
- Sub RFQ generation and management
- Bid leveling module
- Multi-estimate comparison (value evaluation)
- Go/no-go scoring framework
- PM cataloging portal (self-serve job closeout)
- Performance analytics (how accurate have our estimates been?)

---

## What Not to Build (Ever)

- Integration with Heavy Job, Foundation, or Heavy Bid APIs (too complex, too fragile)
- Mobile app
- Real-time collaboration (multi-user simultaneous editing)
- Automated proposal submission
- Anything that sends data outside Wollam's control without explicit approval

---

## Decision Points

| Decision | When | Who Decides |
|----------|------|-------------|
| SQLite → PostgreSQL migration | When >20 jobs cataloged OR multi-user needed | Travis |
| CLI → Streamlit upgrade | After Phase 2a testing | Travis |
| Cloud deployment | Phase 3+ if multi-user required | Travis |
| Expand to other project types | After 10+ jobs cataloged | Travis |
| Share system company-wide | After Phase 3 validated on real bids | Leadership |

---

*WEIS Roadmap v1.0*
*Last Updated: February 2026*
