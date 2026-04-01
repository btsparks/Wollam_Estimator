# WEIS v2 — Complete Product Vision

**Wollam Estimating Intelligence System**
*Document created: March 25, 2026*
*Authors: Travis Sparks & Claude (Brainstorm Session)*

---

## Executive Summary

WEIS is a pre-estimating intelligence platform purpose-built for Wollam Construction. Its mission is to transform raw RFP packages into fully prepared, data-backed briefings that experienced estimators can work from efficiently and confidently. WEIS does not replace the estimator — it eliminates the hours of digging, searching, and guessing that happen before the estimator starts building the bid in HCSS HeavyBid.

At full maturity, WEIS follows an estimate through its complete lifecycle: from the moment an RFP arrives, through document analysis, historical intelligence gathering, estimate preparation, proposal generation, and ultimately feeding completed project data back into the system for future bids. The cycle is self-reinforcing — every completed project makes the intelligence richer for the next bid.

---

## The Problem WEIS Solves

Wollam Construction consistently responds to Requests for Proposals (RFPs) from clients such as Rio Tinto, Northrop Grumman, Chevron, and a wide variety of other owners. Each RFP arrives in a unique format. Each project is one of a kind. The documents are unique, the scope is unique, and the construction complexity varies dramatically from bid to bid. This means Wollam cannot rely on a fixed bid template with modified variables to produce a qualified estimate — every estimate must be built from scratch.

Today, the process of preparing an estimate involves:

- Manually reviewing hundreds of pages of specs, drawings, and contract documents
- Digging through past project files to find comparable work and historical costs
- Relying on individual estimator knowledge and memory for activity structures and production rates
- Manually assembling subcontractor scope packages and tracking their clarifications
- Building proposal letters and project showcases by hand from scattered sources
- No standardized activity structure across bids, leading to inconsistency between estimators

WEIS addresses all of these pain points by creating a unified intelligence layer that organizes institutional knowledge, automates document analysis, and presents everything the estimator needs in a structured, consistent format.

---

## Core Design Philosophy

### The Estimator Remains the Decision-Maker

WEIS is not a bidding software. WEIS is not replacing HeavyBid. The actual estimating — the judgment calls about pricing, risk, and approach — happens in HeavyBid, driven by the estimator's experience and intuition. The estimator is the person who did the takeoff, who knows the drawings better than anyone, who understands the mechanical complexity of the work and the challenges of the geographical location.

WEIS's role is to ensure that when the estimator sits down to build the bid, they have everything they need: the historical data, the spec requirements, the contract risk flags, the sub pricing, the material cost benchmarks, and the recommended activity structures. They're never starting from a blank page, but they're always making the final call.

### The Bid Schedule of Values Is the Governing Document

Every RFP includes a bid schedule of values — the pricing structure the owner expects in the final proposal. This document is the anchor for the entire estimating process. Every piece of intelligence WEIS generates — from spec analysis to historical rates to sub pricing — maps back to specific line items on the bid schedule. The RFP scope document should be detailed enough to match the bid schedule of values. In order to populate those values, the estimator needs to understand all documents and potential cost impacts clearly.

### Consistency Through Structure

One of WEIS's most important contributions is standardizing the activity structures underneath bid items. When Wollam bids pipe work, the system recommends the same activity breakdown every time (fusing, dig-lay-backfill, material procurement) because that's how it was structured on past bids. This creates consistency across estimators and across bids without requiring excessive interpretation or creativity — the estimator focuses on the numbers, not on reinventing the structure.

### The Cycle Is Self-Reinforcing

Every completed project feeds back into the intelligence layer. HeavyJob actuals, PM context interviews, Dropbox project documents, and Bill.com invoices all enrich the database for future bids. The system gets smarter with every job Wollam completes.

---

## Phase 1: Institutional Memory (The Intelligence Foundation)

### Purpose

Build the most complete institutional memory possible by indexing four primary data sources that together provide a 360-degree view of every past project. This is the foundation that every subsequent phase draws from.

### Current State

Phase 1 is approximately 70% complete. The HeavyJob integration, PM Context Interview, Diary Import & Synthesis, Document Intelligence (manual upload), Rate Settings & Cost Recalculation, and the general-purpose AI Chat are all built and functional. What remains is HeavyBid integration, Dropbox automation, Bill.com integration, and chat improvements.

### Data Source 1: HCSS HeavyJob (Built)

**What it provides:** Actual field data — what really happened on every project.

- Actual man-hours per unit by cost code
- Actual dollars per unit
- Crew compositions (who was on site, what trades)
- Equipment usage (what machines, how many hours)
- Production rates (units installed per day/hour)
- Daily timecards with employee, cost code, hours, and quantities
- Foreman diary notes (imported and AI-synthesized)

**Current implementation:**
- Complete HCSS HeavyJob API integration (OAuth, pagination, retry, rate limiting) in `app/hcss/`
- Database populated with jobs, cost codes, timecards, equipment entries, employees, pay items, forecasts
- Rate card generation calculating MH/unit, $/unit, crew size, daily production, and confidence per cost code per job
- Diary parser (state machine) importing foreman notes from HeavyJob diary exports
- AI synthesis of diary entries into structured PM context using Claude Haiku

### Data Source 2: HCSS HeavyBid (Needs to Be Built)

**What it provides:** The estimated bid structure — what was planned and priced before the work started.

- Bid items (matching the owner's schedule of values)
- Activities underneath each bid item (the detailed work breakdown)
- Resource assignments per activity (labor, equipment, materials, subs)
- Production rate assumptions used at bid time
- Bid quantities and unit prices

**Why this matters:** HeavyBid data is critical for two reasons:

1. **Bid vs. Actual comparison.** Pairing HeavyBid estimates with HeavyJob actuals gives the estimator a side-by-side view of what was estimated versus what actually happened. This is enormously valuable for calibrating future estimates.

2. **Activity template library.** The activity structures from past bids become the recommended framework for new bids. For example, if Wollam is fusing pipe, the system can show that every past pipe bid included three activities: fusing, dig-lay-backfill, and buy pipe materials. This standardizes bid structure across estimators and across projects.

**Implementation approach:** Integrate with the HCSS HeavyBid API to pull bid structures (bid items, activities, resources) and link them to jobs already in the database. Store in new database tables that mirror HeavyBid's hierarchy (bid → bid items → activities → resources).

### Data Source 3: Dropbox Project Documents (Partially Built — Needs Automation)

**What it provides:** The project documentation context that explains the "why" behind the numbers.

- Specifications and technical requirements
- Change orders and their cost/scope impact
- RFI logs showing what questions were raised and resolved
- Submittal logs
- KPI reports and project performance documents
- Material tracking sheets
- Any other project-specific documentation

**Why this matters:** Every project in the WEIS database already has a corresponding project folder in Dropbox at `C:\Users\Travis Sparks\Dropbox (Wollam)`. These folders contain rich context about why costs were what they were — maybe the spec required additional testing, or a change order expanded the scope, or site conditions were different than expected. Today, nobody goes back and reads these files after the job is done. Automating the ingestion means this context becomes searchable and available to the AI without any manual effort from PMs.

**Current implementation:**
- A Dropbox scanner CLI script exists (`scripts/scan_dropbox.py`) that can walk Dropbox, catalog documents by job number, extract text from Excel/PDF/CSV/TXT files, and run AI enrichment
- Manual document upload to the platform works via the Documents feature
- Document text extraction works for PDF, Excel, CSV, TXT, DOCX

**What needs to happen:**
- Move Dropbox scanning from CLI script to automated pipeline (REST API endpoints, scheduled scanning)
- Build a RAG (Retrieval-Augmented Generation) database that indexes all project documents semantically, allowing the AI chat to find relevant context even when the user doesn't use exact keywords
- Automate the association of documents to jobs based on folder structure and naming conventions
- Eliminate the need for PMs to manually upload documents — the system should pull from Dropbox automatically

### Data Source 4: Bill.com Invoices (Needs to Be Built)

**What it provides:** Real material costs from vendor and subcontractor invoices.

- Material pricing tied to specific cost codes and job numbers
- Vendor and subcontractor invoice amounts
- Actual material cost per unit for items like pipe, concrete, steel, aggregates
- Historical pricing trends over time

**Why this matters:** HeavyJob tracks labor and equipment costs, but material pricing lives in the accounting/invoicing system. Bill.com is where Wollam processes all incoming invoices from vendors and subcontractors. Each invoice is already coded to a cost code and job number that matches the projects in WEIS. Integrating Bill.com closes the material cost gap and means the system can answer questions like "what do we typically pay for carbon steel pipe per linear foot" with real invoice data, not estimates.

**Implementation approach:** Integrate with the Bill.com API to pull invoices by job code and cost code. Parse invoice line items and associate material costs with the corresponding cost codes in the WEIS database. Store in new database tables (e.g., `vendor_invoice`, `invoice_line_item`).

### PM Context Interview (Built)

**What it provides:** Human insight from the project managers who actually ran the jobs.

- Project-level context: site conditions, key challenges, key successes, lessons learned
- Cost-code-level context: what scope was included/excluded, conditions that affected costs, notes on unusual circumstances

**Current implementation:** Fully built and functional. PMs can walk through their jobs cost code by cost code and provide context. This context is stored in `pm_context` and `cc_context` tables and is available to the AI chat.

### General-Purpose AI Chat (Built — Needs Improvements)

**What it provides:** A multi-purpose conversational interface for querying institutional knowledge.

The chat is not tied to a specific estimate or bid. It serves as a quick-reference tool for anyone at Wollam who wants to know something about past projects, costs, or operations. Examples:

- "What do we typically pay for carbon steel pipe by the linear foot?"
- "How did we structure the bid on the last highway job?"
- "What were the site challenges on the Rio Tinto project?"
- "What's our average production rate for 657 scrapers on mass earthwork?"
- "Compare our bid vs. actual on the last three concrete jobs."

**Current implementation:**
- Intent parsing with discipline and rate type detection
- Multi-strategy search (job number, job name, discipline keywords)
- Context assembly from rate items, PM context, diary notes, crew breakdowns, equipment data
- Claude API integration with conversation management
- Source citation extraction with job, cost code, and confidence metadata

**What needs to improve:**
- Better source attribution — the estimator needs to clearly see which specific projects data is coming from and trace back to the source
- Integration with all four data sources (currently only queries HeavyJob-derived data)
- RAG-based semantic search to supplement keyword/SQL queries
- Ability to query HeavyBid activity structures, Dropbox documents, and Bill.com material pricing

---

## Phase 2: RFP Analysis (Multi-Agent Document Intelligence)

### Purpose

When a new bid opportunity arrives, a team of specialized AI agents analyzes the entire RFP package and organizes their findings against the bid schedule of values. This phase transforms raw project documents into structured, actionable intelligence for the estimator.

### The Workflow

1. A client provides Wollam with an RFP and a deadline for proposal submission.
2. The estimating team downloads all documentation: contract details, drawings, specifications, the RFP scope document, and the bid schedule of values.
3. This documentation is stored in a Dropbox folder labeled with an estimate number.
4. The estimator performs a manual takeoff using Bluebeam to understand quantities and the physical scope of work. This is a manual process that requires human expertise and cannot be automated in the near term.
5. The AI agent team activates and begins analyzing the RFP package.

### Agent 1: Document Control Manager

**Role:** The communication hub and organizational backbone of the agent team.

**Responsibilities:**
- Watch the estimate's Dropbox folder for any changes to documents
- Detect and catalog new documents, addendums, clarifications, and RFI responses as they arrive
- Perform document diffing — identify exactly what changed between versions
- Conduct impact analysis — determine which bid items, sub packages, and other agents are affected by changes
- Propagate change notifications to affected agents and (via the Subcontract Manager) to external subcontractors
- Maintain a master document log with version history and change tracking
- Organize documents by type and relevance to bid schedule items

**Why this agent is critical:** RFP packages are living documents. Addendums arrive, clarifications are issued, RFIs get answered, and specs change. If these changes aren't caught and communicated, the bid is built on outdated information. This agent ensures nothing falls through the cracks.

### Agent 2: QA/QC Manager

**Role:** Specification and quality requirements specialist.

**Responsibilities:**
- Review all technical specifications in the RFP package
- Identify testing requirements (concrete testing, soil compaction testing, weld inspection, etc.) and their cost implications
- Catalog quality control obligations by bid item
- Flag unusual or onerous QA/QC requirements that may affect pricing
- Identify required certifications, qualifications, or pre-qualification requirements
- Map quality requirements to specific bid schedule line items so the estimator knows which activities carry QA/QC cost burdens

### Agent 3: Legal / Contract Analyst

**Role:** Contract risk and commercial terms specialist.

**Responsibilities:**
- Analyze the contract for bid type: lump sum, time and materials, unit price, GMP, cost-plus, or hybrid
- Identify liquidated damages clauses and their financial exposure
- Review bonding requirements (bid bond, performance bond, payment bond) and their cost implications
- Flag indemnification, insurance, and liability provisions
- Identify payment terms, retainage, and cash flow implications
- Review change order provisions — how are changes priced and approved?
- Catalog other contractual obligations: safety requirements, reporting requirements, schedule milestones, owner-furnished items
- Summarize key risks and obligations in plain language for the estimator

### Agent 4: Subcontract Manager

**Role:** Subcontractor scope packaging and bid management specialist.

**Responsibilities:**
- Identify which disciplines or portions of the scope will be subcontracted vs. self-performed
- Build detailed scope packages for each subcontract bid, including:
  - Relevant specification sections
  - Drawing references
  - Quantities (from the estimator's takeoff)
  - Schedule expectations
  - Contract flow-down requirements (from the Legal agent)
  - QA/QC requirements applicable to that sub's work (from the QA/QC agent)
- Distribute scope packages to qualified subcontract bidders for pricing
- Track sub bid submissions, pricing, clarifications, inclusions, and exclusions
- Communicate with the Document Control agent to stay current on changes
- When documents change, assess impact on outstanding sub packages and communicate updates to subcontractors
- Compile sub bid comparisons for the estimator's review
- Aggregate sub clarifications, assumptions, inclusions, and exclusions for inclusion in the final proposal

**Why this agent is the most complex:** It's outward-facing. Unlike the other agents that analyze documents internally, the Subcontract Manager produces deliverables (scope packages) and manages a communication loop with external parties (subcontractors). Changes in documents ripple through to sub packages, which must be updated and re-communicated.

### Additional Agents (Future Consideration)

The agent framework should be extensible. Other specialized agents may be valuable depending on the project type:

- **Safety Manager Agent** — reviews safety requirements, identifies OSHA compliance obligations, flags high-risk activities
- **Schedule/Logistics Agent** — analyzes schedule constraints, milestones, phasing requirements, and mobilization/demobilization needs
- **Environmental/Permitting Agent** — identifies environmental compliance requirements, permit obligations, and regulatory constraints
- **Insurance/Risk Agent** — reviews insurance requirements, identifies unusual coverage needs, flags risk transfer provisions

### Inter-Agent Communication

All agents share a common data model anchored to the bid schedule of values. Each agent tags their findings to specific bid items so that when the estimator reviews a line item, they see everything relevant from every perspective. The Document Control agent serves as the communication hub, ensuring that when information changes, all affected agents and processes are updated.

---

## Phase 3: The Estimating Workspace

### Purpose

Provide a unified interface where the estimator works through the bid, item by item, with all intelligence from Phase 1 and Phase 2 organized and presented for decision-making. This is the environment where the estimator thinks through the estimate before building it in HeavyBid.

### The User Experience

The estimator has WEIS open on one screen and HeavyBid on the other. They work through the bid schedule of values item by item. For each bid item, WEIS presents:

#### 1. Recommended Activity Structure (from HeavyBid Historical Data)

Based on past bids for similar work, WEIS recommends the activities that should roll up under this bid item. For example, for a "Load and Haul Aggregates" bid item:

- **Activity 1:** Load aggregates — includes loader, operator, support resources
- **Activity 2:** Haul aggregates — includes haul trucks, operators, fuel
- **Activity 3:** Spread and compact — includes dozer, roller, operators

Each activity shows how it was structured on comparable past bids, creating consistency and preventing the estimator from missing components.

#### 2. Historical Production Rates and Costs (from HeavyJob + Rate Intelligence)

For each activity, the system presents relevant historical data:

- Man-hours per unit from comparable jobs, with confidence levels
- Dollar per unit costs (labor, equipment, materials) from actual field data
- Crew compositions that were used on similar work
- Equipment utilization rates
- Production variables (units per hour, units per shift)
- Bid vs. actual comparisons showing estimating accuracy on past jobs

All data is cited with source — which job, which cost code, what confidence level, and any PM context about why the numbers are what they are.

#### 3. Specification and Contract Requirements (from Phase 2 Agents)

- QA/QC requirements applicable to this bid item (testing, inspections, certifications)
- Contract risk flags (LD exposure, bonding requirements, special provisions)
- Relevant spec sections and their key requirements
- Any addendums or clarifications that affect this bid item

#### 4. Subcontractor Pricing (from Phase 2 Subcontract Manager)

For subcontracted portions of the work:

- Sub bid comparison matrix
- Sub clarifications, inclusions, and exclusions
- Recommended sub selection with supporting rationale

#### 5. Material Cost Benchmarks (from Bill.com)

- Actual material costs from past invoices for comparable materials
- Vendor pricing trends
- Unit costs for key materials (pipe per LF, concrete per CY, steel per ton, etc.)

### How the Estimator Works

The estimator reviews all of this intelligence, applies their own judgment about the specific project conditions (difficulty of the work, site complexity, geographic challenges, schedule pressure), and makes their decisions. They then build the activities and input the final numbers in HeavyBid. WEIS provides the information; the estimator provides the judgment.

### Relationship to HeavyBid

WEIS is not a replacement for HeavyBid. The actual estimate is built in HeavyBid, which is HCSS's robust bidding software. WEIS is the intelligence and preparation layer that sits upstream. The workflow is:

1. Estimator reviews bid item in WEIS → sees all relevant intelligence
2. Estimator opens corresponding bid item in HeavyBid → creates activities
3. Estimator uses WEIS intelligence to inform their inputs → production rates, crew sizes, material costs
4. Estimator applies their judgment → adjustments for project-specific conditions
5. Repeat for each bid item on the schedule of values

Future enhancement: explore whether WEIS can generate an export format that pre-populates HeavyBid activity structures, reducing manual re-entry.

---

## Phase 4: Proposal Generation & Project Showcases

### Purpose

After the estimate is built in HeavyBid, WEIS produces the deliverables that accompany the final proposal submission. This includes a comprehensive proposal letter, subcontractor documentation, and personalized project showcases that demonstrate Wollam's relevant experience.

### Deliverable 1: Comprehensive Proposal Letter

HeavyBid outputs a populated pricing sheet (the bid schedule of values with prices filled in). But a qualified proposal requires much more than a price. The proposal letter is the narrative that accompanies the pricing and demonstrates to the owner that Wollam understood the project, thought through the complexity, and priced it responsibly.

**The proposal letter includes:**

- **Complete breakdown of every assumption** — what the estimate is based on, what conditions were assumed, what production rates were used
- **Clarifications on individual bid items** — where the scope was ambiguous, what interpretation Wollam used, and any items that may need further discussion
- **Overall project approach** — how Wollam plans to execute the work, high-level sequencing, key methods, and mobilization strategy
- **Acknowledgement of project specifics** — demonstrates to the owner that Wollam read and understood the RFP documents, the site conditions, the schedule requirements, and the contract terms
- **Subcontractor clarifications and requirements** — all sub assumptions, inclusions, and exclusions rolled up into the proposal so the owner has full transparency on what's being priced. Sub clarifications come in a variety of formats and need to be normalized and incorporated clearly
- **Inclusions and exclusions** — a clear, comprehensive list of what is and is not included in Wollam's price. This is critical for protecting Wollam if the bid is won — it creates a documented record of the pricing basis

**Why this matters:** The proposal letter builds owner confidence that Wollam understood the project. It also creates essential documentation that protects Wollam post-award. If there's ever a dispute about scope, the proposal letter is the reference point for what was included and excluded.

**How WEIS generates it:** The system draws from everything it has assembled during the estimating process:

- The Phase 2 agents provide the contract analysis, spec requirements, and sub clarifications
- The estimator's activity structure and pricing decisions inform the assumptions
- The historical intelligence informs the project approach
- The document analysis informs the inclusions/exclusions

### Deliverable 2: Project Showcase Slides

To differentiate Wollam's proposal, the system generates personalized project showcase materials that highlight Wollam's relevant experience for the specific type of work being bid.

**Each project showcase is a presentation slide that includes:**

- Project name and client
- Overview of project details and scope
- Key quantities and accomplishments (e.g., "Moved 500,000 yd³ across site using 657 scrapers")
- Project specifics that demonstrate relevant experience
- Space for project photos
- Details that match the type of work in the current RFP

**How WEIS generates showcases:**

- The system identifies completed projects in the database that are similar to the current bid (matching disciplines, work types, scale)
- For each relevant project, it pulls accomplishment data from HeavyJob (quantities, production achievements), PM context (project summaries, challenges overcome), and Dropbox documents (additional project details)
- It generates presentation slides formatted to Wollam's brand standards (using the existing Wollam PPTX skill)
- The estimator/proposal team can review, add photos, and customize before submission

**Why this matters:** Owners want to see that the contractor has done similar work before. Manually assembling project showcases requires digging through old project files, finding photos, calculating accomplishment quantities, and writing summaries. WEIS automates this because all of that information already lives in the intelligence layer.

### Deliverable 3: Inclusions & Exclusions Summary

A standalone, clearly formatted document that enumerates:

- Everything included in Wollam's price, organized by bid item
- Everything explicitly excluded
- All assumptions that underlie the pricing
- All sub clarifications and their specific inclusions/exclusions
- Any qualifications or conditions on the bid

This document protects Wollam post-award and ensures there's no ambiguity about what was priced.

---

## The Self-Reinforcing Cycle

When Wollam wins a project and completes it, the data flows back into Phase 1:

1. **HeavyJob actuals** from the completed project enrich the historical database with new production rates, crew data, and cost information
2. **PM Context Interviews** capture the project manager's insights about what went well, what was challenging, and what they'd do differently
3. **Dropbox project documents** (close-out docs, final change orders, as-built records) get indexed into the RAG database
4. **Bill.com invoices** from the completed project add real material costs to the historical record
5. **HeavyBid bid vs. actual** comparison data shows how accurate the estimate was, helping calibrate future bids

Every completed project makes WEIS smarter and more valuable for the next bid. The system continuously improves with use.

---

## Technical Architecture Summary

### Phase 1 Components

| Component | Status | Technology |
|-----------|--------|------------|
| HeavyJob API Integration | Built | Python httpx, OAuth 2.0 |
| HeavyBid API Integration | Needs to be built | HCSS API (TBD) |
| Dropbox Automated Scanning | Partially built (CLI) | Python, needs REST API + scheduler |
| RAG Database | Needs to be built | Vector embeddings (TBD — likely ChromaDB or similar) |
| Bill.com API Integration | Needs to be built | Bill.com API |
| PM Context Interview | Built | FastAPI + vanilla JS |
| Diary Import & Synthesis | Built | State machine parser + Claude Haiku |
| Document Intelligence | Built (manual upload) | PDF/Excel/CSV extraction + Claude enrichment |
| Rate Settings & Cost Recalc | Built | SQLite + calculation engine |
| General-Purpose AI Chat | Built (needs improvements) | Claude API + FastAPI |
| Database | Built (schema v2.6) | SQLite |
| Frontend | Built | Vanilla JS + Tailwind CSS |

### Phase 2 Components

| Component | Status | Technology |
|-----------|--------|------------|
| Document Control Agent | Needs to be built | Dropbox API watch + document diffing |
| QA/QC Manager Agent | Needs to be built | Claude API + spec parsing |
| Legal/Contract Analyst Agent | Needs to be built | Claude API + contract parsing |
| Subcontract Manager Agent | Needs to be built | Claude API + scope packaging |
| Inter-Agent Communication | Needs to be designed | Shared data model on bid schedule |
| Bid Schedule of Values Parser | Needs to be built | Document extraction + structured mapping |

### Phase 3 Components

| Component | Status | Technology |
|-----------|--------|------------|
| Estimating Workspace UI | Needs to be designed | TBD |
| Bid Item / Activity Browser | Needs to be built | Tied to HeavyBid data model |
| Intelligence Assembly per Bid Item | Needs to be built | Aggregates all data sources |
| HeavyBid Export (future) | Not started | TBD |

### Phase 4 Components

| Component | Status | Technology |
|-----------|--------|------------|
| Proposal Letter Generator | Needs to be built | Claude API + document templates |
| Project Showcase Generator | Needs to be built | PPTX generation (existing Wollam skill) |
| Inclusions/Exclusions Compiler | Needs to be built | Aggregation from estimate + subs |
| Sub Clarification Normalizer | Needs to be built | Claude API + document parsing |

---

## Immediate Next Steps (Phase 1 Completion)

These are the remaining items to complete Phase 1 before moving to Phase 2:

1. **AI Chat Improvements** — Better source attribution and project referencing so estimators can trace data back to specific jobs clearly
2. **HCSS HeavyBid API Integration** — Pull bid structures (bid items, activities, resources) and link to existing jobs
3. **Dropbox Automation** — Move from CLI scanner to automated pipeline with REST API endpoints; build RAG database for semantic document search
4. **Bill.com Integration** — API integration to pull invoices by job code and cost code for material pricing
5. **Chat Multi-Source Querying** — Upgrade chat to query across all four data sources (HeavyJob, HeavyBid, Dropbox RAG, Bill.com) with clear source attribution

---

## Key Principles (Non-Negotiable)

1. **The estimator decides.** WEIS informs, the human judges. No automated bid generation.
2. **Every number has a source.** All data must cite its origin — job number, cost code, confidence level, data source.
3. **No hallucination.** If data doesn't exist, the system says so. No fabricated numbers, no guessing.
4. **PM context enriches but never overwrites actuals.** Human notes supplement the data; they don't replace it.
5. **The bid schedule of values governs everything.** All intelligence maps back to bid items.
6. **Consistency through structure.** Activity templates from past bids standardize how estimates are built.
7. **The cycle feeds itself.** Completed projects make the system smarter for future bids.
8. **Keep the human element.** Estimator intuition, field experience, and project comprehension are irreplaceable. WEIS amplifies these qualities — it doesn't substitute for them.
