# WEIS — Agent Roster & Orchestration
## The Estimating Team as AI Agents

---

## Overview

The estimating team is modeled as a set of functional AI agents, each responsible for a specific domain within the estimate. The Chief Estimator agent serves as orchestrator — directing each specialist agent, synthesizing their outputs, and guiding the human chief estimator through every decision point.

Every agent has a defined role, specific inputs it consumes, specific outputs it produces, clear handoff points to other agents, and a set of questions it must answer before its work is complete.

Agents are built incrementally. The data layer (HCSS API integration, transformation, knowledge base) must be solid before agents are developed. The current six operational agents continue to function during the v2.0 migration.

---

## Agent Build Priority

Agents are built in this order, based on dependency chain and risk:

| Priority | Agent | Rationale |
|----------|-------|-----------|
| 1 | Cataloger (evolved) | Already operational. Evolves to consume API data + PM interviews |
| 2 | Document Control | Most mechanical, lowest risk. Manages RFP packages |
| 3 | Quality Manager | Spec reading, well-defined output |
| 4 | Safety Manager | Similar to quality, narrower scope |
| 5 | Estimator(s) | Core value — queries knowledge base for rates |
| 6 | Legal/Contract | Requires careful validation |
| 7 | Subcontract/Procurement | Complex workflow, depends on rate library |
| 8 | Scheduler | Depends on crew configs and production rates |
| 9 | Shadow PM | Constructability review, depends on all above |
| 10 | Chief Estimator | Last — orchestrates all others |

---

## The Roster

### 1. Chief Estimator — Orchestrator

**Role:** Owns the estimate from kickoff to submission. Directs all other agents. Makes or escalates all key decisions.

**Inputs:**
- RFP package (from Document Control)
- All agent outputs
- Human chief estimator's direction and approvals

**Outputs:**
- Estimate assembly (all disciplines consolidated)
- Decision queue (items requiring human judgment)
- Final pricing recommendation with confidence levels
- Bid/no-bid recommendation with rationale

**Key Questions:**
- Is this the right type of work for Wollam?
- What's the overall risk profile?
- Where are the data gaps and what confidence adjustments are needed?
- What's the recommended markup and contingency?

**Knowledge Base Queries:**
- Benchmark roll-ups by project type
- Historical CO rates and design development patterns
- GC percentage benchmarks
- Overall CPI trends across similar projects

---

### 2. Legal/Contract Agent

**Role:** Analyzes contract documents for risk, insurance requirements, bonding, compliance, and unusual terms.

**Inputs:**
- Contract documents, general conditions, special conditions
- Insurance requirements
- Bonding requirements

**Outputs:**
- Contract risk assessment (red/yellow/green items)
- Insurance cost estimate
- Bonding requirements and estimated cost
- Non-standard terms flagged for human review

---

### 3. Quality Manager Agent

**Role:** Reads specifications, identifies QA/QC requirements, flags testing and inspection needs.

**Inputs:**
- Project specifications
- Quality control sections of spec

**Outputs:**
- QA/QC requirements matrix
- Testing requirements (concrete, rebar, welding, etc.)
- Third-party inspection needs (cost impact)
- Submittal requirements list

**Knowledge Base Queries:**
- Historical QC testing costs as percentage of job
- Testing vendor costs by test type

---

### 4. Safety Manager Agent

**Role:** Identifies site safety requirements, owner-specific safety programs, hazard assessments.

**Inputs:**
- Project specifications (safety sections)
- Owner safety requirements (e.g., RTKC "Keep Each Other Safe")
- Site conditions

**Outputs:**
- Safety staffing requirements (full-time vs. part-time safety manager)
- Owner-specific training requirements and cost impact
- PPE and safety equipment budget
- Blast delay estimates (for mine sites)

**Knowledge Base Queries:**
- Safety management daily rates by project type
- Site training hours for specific owners (RTKC runs 1.5x standard)
- Blast delay hours by mine site

---

### 5. Takeoff Engineer Agent

**Role:** Extracts quantities from drawings and specifications.

**Inputs:**
- Drawing sets (plans, sections, details)
- Specifications (material specs, finish schedules)

**Outputs:**
- Quantity takeoff by discipline
- Material lists with quantities and units
- Scope clarification questions (for RFI)

**Notes:** This agent will evolve significantly as AI vision capabilities improve. Initial version may assist with quantity organization rather than extraction from drawings.

---

### 6. Estimator Agent(s) — Discipline-Specific

**Role:** Prices each discipline using rates from the knowledge base. One instance per discipline or one agent that handles all disciplines.

**Inputs:**
- Quantity takeoff (from Takeoff Engineer)
- Historical rates (from knowledge base)
- Specifications (material requirements, construction methods)
- Project context (location, owner, access conditions)

**Outputs:**
- Labor cost by activity (MH x rate, or $/unit x quantity)
- Equipment cost by activity
- Material cost by activity (benchmarked against knowledge base)
- Confidence indicators per line item
- Source citations for every rate used

**Knowledge Base Queries:**
- Rate library: recommended rates by activity and discipline
- Crew configurations: typical crews for each activity
- Material benchmarks: historical material costs by vendor and location
- Lessons learned: what to watch for on this type of work

**Key Design Decision:** The Estimator Agent does not invent rates. It queries the knowledge base and applies validated rates to the quantities. When the knowledge base has no applicable rate, it flags the item for human input and provides the closest available benchmark.

---

### 7. Subcontract/Procurement Agent

**Role:** Manages subcontractor scope packages and material procurement.

**Inputs:**
- Scope packages by discipline
- Historical sub pricing (from knowledge base)

**Outputs:**
- Sub RFQ packages
- Sub bid leveling matrix
- Material procurement list
- Budget estimates for sub work (pre-bid)
- Quote validation (is the sub's number reasonable based on history?)

**Knowledge Base Queries:**
- Historical sub costs (e.g., steel erection at $3,766/TON from 8553)
- Vendor pricing trends (concrete at $265/CY mine site vs $205/CY standard)

---

### 8. Scheduler Agent

**Role:** Develops project duration estimate and resource loading plan.

**Inputs:**
- Quantity takeoff
- Crew configurations (from knowledge base)
- Production rates (from knowledge base)
- Constraints (owner schedule, weather, site access)

**Outputs:**
- Activity durations
- Sequence and logic
- Resource loading (crew counts by week)
- Critical path identification

**Knowledge Base Queries:**
- Production rates: daily output by activity and crew size
- Historical project durations for similar scope

---

### 9. Shadow PM Agent

**Role:** Constructability review. Thinks about how the job will actually be built.

**Inputs:**
- Complete estimate framework (all disciplines)
- Drawing set
- Site conditions

**Outputs:**
- Constructability concerns
- Execution plan suggestions
- Mobilization/demobilization considerations
- Equipment strategy (rent vs. own, shared equipment opportunities)
- Site logistics (laydown, access, haul roads)

**Knowledge Base Queries:**
- Lessons learned from similar projects
- Equipment utilization data (shared equipment reduces dedicated needs by ~25%)
- CO patterns (design development drove 61% of CO value on 8576)

---

### 10. Document Control Agent

**Role:** Manages the bid document lifecycle — RFP intake, addenda tracking, submittal logs.

**Inputs:**
- RFP package (all documents)
- Addenda as received
- RFI responses

**Outputs:**
- Document register
- Addenda log with scope impact assessment
- RFI tracking
- Submittal requirements matrix
- Deadline tracking

---

## Agent Communication

Agents communicate through the shared database and a job-specific state object. The Chief Estimator agent has access to all other agents' outputs.

```
Human Chief Estimator
        |
        v
Chief Estimator Agent (Orchestrator)
        |
        +-- Document Control --> RFP Package Parsed
        |
        +-- Legal/Contract --> Risk Assessment
        |
        +-- Quality + Safety --> Requirements Matrix
        |
        +-- Takeoff Engineer --> Quantities
        |       |
        |       v
        +-- Estimator(s) --> Priced Estimate by Discipline
        |       |
        |       v
        +-- Sub/Procurement --> Sub Budget + RFQs
        |
        +-- Scheduler --> Duration + Resource Plan
        |
        +-- Shadow PM --> Constructability Review
                |
                v
     Chief Estimator Final Assembly
     (Markup, Contingency, Final Number)
                |
                v
         Proposal Assembly
```

Every agent output is stored and versioned. Estimates are auditable. The human chief estimator interacts through the Command Center UI, not directly with individual agents.

---

## Cataloger Agent — Evolution

The Cataloger Agent is unique — it feeds the knowledge base rather than consuming it.

### v1.0 (Current — Manual JCD Process)
- Consumes 6 manually exported reports
- Produces JCD markdown files by discipline
- Requires 3-4 hours per job
- Single-job processing

### v2.0 (API-Driven)
- Consumes raw HCSS API data from database
- Runs transformation logic (unit cost calculation, confidence assessment)
- Generates rate cards automatically
- Triggers PM interview workflow for variance explanations
- Bulk-processes all closed jobs

### PM Interview Workflow
The Cataloger's PM interview module auto-generates questions based on rate card data:

1. **Variance questions** — any cost code >20% over/under budget gets a "what drove this?" question
2. **Lessons learned** — one question per discipline: "what should future estimators know?"
3. **Context questions** — "what went well?" and "what were the challenges?"
4. **Rate confirmation** — PM reviews and can override recommended rates

The interview is designed to be completable in 15-30 minutes. Required questions (variance explanations) must be answered before the rate card can be approved. Optional questions are encouraged but not blocking.

---

*WEIS Agents v2.0*
*Last Updated: March 2026*
