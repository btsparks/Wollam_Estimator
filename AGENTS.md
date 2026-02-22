# WEIS — Agent Roster & Orchestration
## The Estimating Team as AI Agents

---

## Overview

The estimating team is modeled as a set of functional AI agents, each responsible for a specific domain within the estimate. The Chief Estimator agent serves as orchestrator — directing each specialist agent, synthesizing their outputs, and guiding the human chief estimator through every decision point.

Every agent has:
- A defined role
- Specific inputs it consumes
- Specific outputs it produces
- Clear handoff points to other agents
- A set of questions it must answer before its work is complete

Agents are not built in Phase 1 or Phase 2. This document defines them for Phase 3+ development. It is written now so the data schema and conversation layer are designed to support the eventual agent architecture.

---

## The Roster

### 1. Chief Estimator — Orchestrator

**Role:** Owns the estimate from kickoff to submission. Directs all other agents. Makes or escalates all key decisions. Guides the human chief estimator through every step.

**Inputs:**
- RFP package (all documents)
- Outputs from all specialist agents
- Historical project data (for bid strategy context)
- Current estimate state

**Outputs:**
- Bid go/no-go recommendation
- Estimate strategy document (self-perform vs sub split, key assumptions)
- Final markup and contingency decisions
- Decision log (what was decided, when, by whom)
- Chief estimator task list (what needs to happen next, in order)

**Orchestration Logic:**
1. On RFP receipt: trigger Document Control agent to intake and organize documents
2. Parallel trigger: Legal, Quality, Safety agents begin document review
3. When document review complete: brief chief estimator on flags and risks
4. Trigger Takeoff Engineer to begin quantity development
5. When quantities complete: trigger Estimator agents by discipline
6. Parallel trigger: Subcontract/Procurement agent begins scope split and RFQ process
7. Trigger Scheduler to develop bid schedule
8. Trigger Shadow PM for constructability review
9. As sub quotes arrive: trigger leveling and incorporation
10. Final assembly: compile all inputs into complete estimate
11. Present summary to chief estimator for markup and approval
12. Coordinate proposal assembly

**Decision Queue (what the chief estimator sees):**
- Items requiring a decision are surfaced in order of urgency
- Each item shows: what the decision is, what the agent recommends, what information it's based on, and what the consequence of each choice is

---

### 2. Legal / Contract Manager

**Role:** Reads all contract documents and identifies risk items that affect the estimate or the company's exposure.

**Inputs:**
- Contract documents (general conditions, special conditions, T&Cs)
- Insurance requirements
- Bond requirements
- Payment terms
- Liquidated damages schedule
- Dispute resolution clauses
- Historical lessons learned tagged as "contract risk"

**Outputs — Contract Risk Report:**
- Liquidated damages: amount, trigger conditions, estimated exposure
- Indemnification: scope of Wollam's obligation
- Differing site conditions: is clause present? favorable or unfavorable?
- Payment terms: net days, retainage %, release conditions
- Retention: amount, release triggers
- Dispute resolution: type, venue, cost allocation
- Termination provisions: for convenience vs for cause, compensation
- Insurance requirements: required coverages vs Wollam standard
- Missing provisions: items Wollam would typically require that are absent
- Overall risk rating: LOW / MEDIUM / HIGH / DO NOT BID
- Recommended clarifications or exceptions to include in proposal

**Triggers next:** Chief Estimator reviews and decides which risks to price, which to take exception to, and which are dealbreakers.

---

### 3. Quality Manager

**Role:** Reads the technical specifications and identifies quality requirements that have cost and schedule implications.

**Inputs:**
- Technical specifications (all divisions)
- Project type context (nuclear, mining, refinery, industrial)
- Owner QC requirements
- Historical lessons learned tagged as "quality"

**Outputs — Quality Requirements Summary:**
- QC plan requirements: type, level, owner review/approval required?
- Inspection and test plan (ITP): required? owner-witnessed hold points?
- Third-party inspection: required? who provides? who pays?
- Special inspections: welding, NDE, concrete, steel — type and frequency
- Material certifications: mill certs, test reports, traceability requirements
- Submittal schedule: list of required submittals with lead times
- Personnel qualifications: certified welders, inspectors, QC managers required
- Record keeping: as-built requirements, data books, turnover package scope
- Cost-impacting items summary with estimated cost for each
- Comparison to Wollam standard practice — what's above and beyond?

**Triggers next:** Estimator agents incorporate quality costs into GC and discipline estimates.

---

### 4. Safety Manager / Consultant

**Role:** Extracts site-specific safety requirements and translates them into general conditions costs.

**Inputs:**
- Safety sections of the specification
- Site-specific health and safety plan requirements
- Owner safety program requirements
- Historical lessons learned tagged as "safety"

**Outputs — Safety Requirements Summary:**
- Air monitoring requirements: type, frequency, who provides equipment
- Respiratory protection: fit testing required? SCBA vs APF?
- Site access requirements: orientation, badging, escort requirements
- Drug testing: pre-hire, random, post-incident — owner-mandated vs standard
- PPE: requirements above Wollam standard (cost delta)
- Safety officer requirements: owner-mandated ratio of safety staff to workers
- Safety plan: formal SSSP required? Third-party review?
- Incident reporting: requirements and timelines
- Safety pre-qualification: owner safety stats required? EMR threshold?
- Third-party audits: required? frequency? who pays?
- Cost impact summary: additional $ for safety requirements above Wollam baseline
- Flag items that may affect workforce availability (e.g., clean-shaven for fit testing, site-specific certifications)

**Triggers next:** General Conditions estimator incorporates safety costs.

---

### 5. Document Control / Bid Coordinator

**Role:** Manages the living document set throughout the bid period. Ensures the team always works from current documents.

**Inputs:**
- Initial RFP package
- All addenda as received
- All RFI responses as received
- Any clarification documents from owner

**Outputs:**
- Master document register (current version of every document)
- Addendum log (what changed, when, impact assessment)
- RFI log (question asked, date submitted, date answered, response)
- Change impact flags (when an addendum affects work already estimated)
- Bid deadline tracker (proposal due date, any extensions)

**Continuous operation:** This agent runs throughout the bid period, not just at kickoff. Every new document received triggers an update.

**Critical function:** When an addendum changes scope, this agent flags the affected estimate sections and triggers re-evaluation by the relevant agents.

---

### 6. Takeoff Engineer / Quantity Surveyor

**Role:** Supports the human takeoff process with templates, checklists, and gap identification. Receives completed quantities and validates them.

**Note:** The actual takeoff requires human judgment and interaction with drawings. This agent supports and validates, but does not replace, the human takeoff.

**Inputs:**
- Drawing list from document register
- Spec sections defining scope
- Similar past project takeoff quantities (for comparison/validation)
- Completed quantity sheets from human estimator

**Outputs:**
- Quantity template by discipline (pre-populated based on similar projects)
- Missing scope checklist (items that should be quantified — don't miss these)
- RFI list (drawing conflicts, unclear scope, missing information)
- Validated quantity sheet (with comparison to similar past projects)
- Quantity summary by discipline for handoff to Estimator agents

**Validation logic:** When quantities are submitted, compare to Job 8553 and other historical projects. Flag quantities that are significantly different without an obvious explanation (scope difference, project size, etc.).

---

### 7. Estimator Agents (Discipline-Specific)

**Role:** Takes validated quantities and applies historical Wollam rates to build the discipline estimate.

**One agent per discipline:**
- Earthwork Estimator
- Concrete Estimator
- Structural Steel Estimator
- Piping Estimator
- Mechanical Equipment Estimator
- Electrical Estimator
- Building Erection Estimator
- General Conditions Estimator

**Inputs (per discipline):**
- Validated quantities from Takeoff Engineer
- Historical unit costs from database (sourced, cited)
- Historical production rates from database
- Historical crew configurations from database
- Quality and Safety agent outputs (for GC estimator)
- Current material and sub quotes (when available)

**Outputs (per discipline):**
- Estimate framework (WBS mapped to owner's scheduled values)
- Labor cost by activity (crew, MH, rate, total)
- Material cost by activity (quantity, unit, rate, source)
- Subcontract cost by scope (if applicable)
- Equipment cost by activity
- Confidence summary (HIGH/MEDIUM/LOW/ASSUMPTION per line item)
- Assumptions list (what was assumed where data was limited)
- Risk flags (where estimate is most sensitive to assumption changes)

**Rate sourcing logic:**
1. Query database for exact activity match on similar project type
2. If match found with HIGH confidence: use recommended rate, cite source
3. If match found with MEDIUM confidence: use rate with flag, cite source
4. If no match: use benchmark rate with ASSUMPTION flag, note gap
5. Never leave a line item without a rate — always have a number with appropriate confidence

---

### 8. Subcontract / Procurement Manager

**Role:** Defines the sub/self-perform split, develops scope sheets, manages the RFQ process, and levels bids.

**Inputs:**
- Validated quantities by discipline
- Historical subcontractor data (who we've used, at what cost)
- Spec sections defining sub-eligible scope
- Owner requirements for sub qualification
- Market conditions (Phase 3+ — may require manual input initially)

**Outputs:**
- Sub/self-perform split recommendation by discipline
- Scope sheets for each sub package (ready to send)
- Bid list for each package (qualified subs and vendors)
- RFQ packages (scope, drawings, deadline, instructions to bidders)
- Bid leveling matrix (when quotes received — apples to apples comparison)
- Recommended sub award by package with justification
- Budget plug rates for sub packages pending quotes

**Key scope packages to manage:**
- Rebar (furnish and install)
- Concrete pumping
- Structural steel erection
- Electrical
- Building erection
- Survey
- Testing and inspection
- Crane and rigging
- Specialty equipment (if owner-designed items require sub install)

---

### 9. Scheduler

**Role:** Develops the bid schedule and translates duration assumptions into general conditions costs.

**Inputs:**
- Validated quantities by discipline
- Historical production rates and crew configs
- Project-specific constraints from RFP (milestone dates, phasing, access)
- Historical project durations for similar scope

**Outputs:**
- Bid schedule (bar chart or CPM — level appropriate for bid)
- Critical path identification
- Key milestone dates
- Duration assumptions by discipline
- Resource loading summary (peak crew sizes, equipment needs)
- General conditions duration (drives site overhead cost)
- Schedule risk flags (what could extend the project?)
- Comparison to similar historical projects

---

### 10. Shadow PM

**Role:** Constructability review from the perspective of the PM who would run the job.

**Inputs:**
- Estimate framework from all Estimator agents
- Scope description and drawings summary
- Historical lessons learned (especially production variances and scope gaps)
- Site-specific information from RFP

**Outputs:**
- Constructability review (how would we actually build this?)
- Scope gap list (what's in the drawings but not in the estimate?)
- Production rate challenges (where are the assumed rates unrealistic?)
- Execution risk list (what are the top 5 things that could go wrong?)
- Opportunity list (where could we beat the estimate if we're smart?)
- Recommended contingency level and basis

---

## Orchestration Flow

```
RFP Received
     │
     ▼
Document Control ──────────────────────────────────────────────┐
(Intake & Register)                                            │ (Continuous)
     │                                                         │
     ├──────────────────────────────────────────────────────  │
     │                                                         │
     ▼          ▼           ▼                                  │
  Legal      Quality      Safety                               │
  Review     Review       Review                               │
     │          │           │                                  │
     └──────────┴───────────┘                                  │
                │                                              │
                ▼                                              │
     Chief Estimator Brief                                     │
     (Flags, Risks, Go/No-Go Check)                           │
                │                                              │
                ▼                                              │
         Takeoff Support ◄──── Human Takeoff ────►            │
         (Templates, RFIs)    (Engineer/PM)                    │
                │                                              │
                ▼                                              │
     Quantities Validated                                      │
                │                                              │
     ┌──────────┴──────────────────────┐                      │
     │                                 │                      │
     ▼                                 ▼                      │
Discipline Estimators          Sub/Procurement                 │
(All disciplines parallel)     (Scope split + RFQs)           │
     │                                 │                      │
     │                    Sub Quotes Received ◄───────────────┘
     │                                 │
     └──────────┬──────────────────────┘
                │
                ▼
          Scheduler
          (Duration + GC cost)
                │
                ▼
           Shadow PM
           (Constructability Review)
                │
                ▼
     Chief Estimator Final Assembly
     (Markup, Contingency, Final Number)
                │
                ▼
         Proposal Assembly
```

---

## Phase 3 Build Notes

When building agents in Phase 3:

- Each agent is a separate module with a defined system prompt
- The Chief Estimator agent has access to all other agents' outputs
- Agents communicate through the shared database and a job-specific state object
- The human chief estimator interacts through the Command Center UI, not directly with individual agents
- Every agent output is stored and versioned — estimates are auditable

---

*WEIS Agents Document v1.0*
