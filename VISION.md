# WEIS — System Vision
## Wollam Estimating Intelligence System

---

## The Problem

Construction estimating at the industrial heavy civil level is deeply dependent on experienced people. Production rates, crew configurations, subcontractor relationships, contract risk awareness, and the instinct to know what a job will actually cost — this knowledge lives in the heads of a small number of senior estimators. When those people leave, retire, or are unavailable during a critical bid period, institutional knowledge walks out the door with them.

At the same time, every estimate is built under time pressure. RFP packages arrive with strict bid deadlines. Documents change throughout the bid period. Questions get answered at inconvenient times. Multiple disciplines need to be evaluated simultaneously. The current process is largely manual, sequential, and person-dependent.

The result: estimates that are only as good as the people available to build them, and a company whose competitive capability is fragile.

---

## The Vision

**A complete AI-powered estimating toolkit that takes any RFP package as input and produces a defensible, Wollam-calibrated estimate framework — fast — so the team can evaluate whether a job is worth pursuing and at what price.**

This is not a generic estimating tool. It is distinctly Wollam — fed by the company's own historical project data, calibrated to the company's actual production rates, crew configurations, and cost experience, and structured around the way Wollam actually builds work.

The system democratizes estimating expertise. A newer estimator with this system produces work that reflects the company's collective intelligence. A project manager cataloging a completed job is contributing to the knowledge base that makes every future estimate better.

The end state is a clean, simple application that any estimator can use without understanding anything about AI. The complexity is invisible. The value is immediate.

---

## The Two Layers

### Layer 1 — The Command Center
A structured, visual, trackable dashboard. The chief estimator opens it and immediately knows:
- Where the estimate stands
- What is blocking progress
- What decision needs to be made next
- Which agent or team member needs input

Every estimating role has a status lane. Deliverables move through defined states: Not Started → In Progress → Needs Input → Complete. Nothing gets skipped. Dependencies are enforced. The process is rigorous.

This is the rigid layer. It holds the discipline of the estimating process regardless of how different each project is.

### Layer 2 — The Conversation Layer
A chat interface that any team member can use at any point during the bid period. Ask a question in plain English, get an answer sourced from real Wollam job data and current RFP documents.

Examples:
- *"What did we pay for 20-inch flanged joints on pump station work?"*
- *"Does this spec require hydrostatic testing on all process lines?"*
- *"What crew did we use for mat pours on Job 8553?"*
- *"Has the owner responded to RFI #14 yet?"*

This is the flexible layer. It operates independently of the workflow and is available throughout the bid period for any question, at any time.

The two layers are not separate tools. A question in the conversation layer can trigger a flag in the command center. A gap identified in the command center spawns a conversation thread to resolve it.

---

## The Estimating Team as Agents

The system models a complete estimating team, with each role implemented as a functional AI agent. Each agent consumes the RFP package and historical data, and produces a specific deliverable that feeds the chief estimator's final number.

### The Roster

**Chief Estimator — Orchestrator**
Owns the estimate from kickoff to submission. Sets bid strategy. Makes final calls on contingency and markup. Decides self-perform versus sub. Accountable for the number that goes out the door. In the system, this is the orchestrating agent — it synthesizes all other agent outputs and guides the human chief estimator through each decision point.

**Legal / Contract Manager**
Reads the contract language. Flags liquidated damages, indemnification clauses, differing site conditions language, payment terms, retainage, dispute resolution, and termination provisions. Produces a risk register of contract exposures. Flags missing provisions Wollam would typically require. Output: Contract Risk Report.

**Quality Manager**
Reads the specification front-to-back. Identifies QC plan requirements, ITPs, required testing, submittals and their lead times, special inspection requirements, certified personnel requirements. Flags quality-related cost items that are commonly missed in estimates. Output: Quality Requirements Summary with cost implications.

**Safety Manager / Consultant**
Extracts site-specific safety requirements from the RFP. Gas monitoring, fit testing, clean-shaven policies, drug testing, PPE standards above baseline, owner-imposed safety officer ratios, third-party audit requirements. Output: Safety Requirements Summary with general conditions cost impact.

**Takeoff Engineer / Quantity Surveyor**
Owns the drawings. Produces quantities. Identifies drawing conflicts, missing information, and generates the RFI list. Provides a quantity template based on similar past projects so nothing gets missed. This role is human-led — the AI supports with templates, checklists, and gap identification, but the actual takeoff requires human judgment. Output: Quantity Takeoff Sheet by discipline.

**Estimator(s) — Discipline Specific**
Takes quantities from takeoff and applies production rates, crew configurations, equipment, and durations from the historical database. Generates a structured WBS that maps to the owner's scheduled values. Flags confidence levels — strong data versus assumption. Output: Estimate Framework by discipline with sourced rates.

**Subcontract / Procurement Manager**
Defines the sub scope split. Builds scope sheets for each sub package. Manages the RFQ process — who gets invited, when quotes are due, how they get leveled. Manages vendor quotes for major equipment, materials, and fabricated items. Tracks bid list and follows up. Output: Sub scope sheets, RFQ packages, bid leveling matrix.

**Scheduler**
Produces the bid schedule. Identifies critical path, resource constraints, and sequence dependencies. Duration directly affects general conditions cost. Output: Bid schedule with duration and sequence assumptions.

**Project Manager (Shadow)**
The PM who would run this job if won. Brings constructability knowledge. Flags scope items the estimate is missing. Challenges production assumptions. Identifies execution risks. Output: Constructability review and risk list.

**Document Control / Bid Coordinator**
Manages the living RFP document set throughout the bid period. Tracks addenda, logs RFIs, maintains the master document register, ensures the team is always working from current drawings. Output: Living document register with change log.

---

## The Data Engine

The intelligence of the entire system rests on one foundation: Wollam's historical project data, systematically cataloged and stored in a queryable database.

### What Gets Cataloged
For every completed project, the following gets extracted and stored:
- Unit costs by activity and discipline
- Production rates (MH/unit, units/hour)
- Crew configurations by activity type
- Equipment utilization and type
- Material costs by vendor and material type
- Subcontractor costs and scope definitions
- General conditions breakdown
- Budget versus actual performance
- Lessons learned

### How It Gets Cataloged
The Cataloger Agent (separate Claude Project) processes completed jobs using six required documents from Heavy Job, Foundation, and Heavy Bid. Output is a set of structured Job Cost Data (JCD) documents by discipline, plus a master summary. These feed directly into the WEIS database.

### Who Catalogs
Project managers are responsible for cataloging their jobs at project closeout. This makes the system a living asset — every completed job makes every future estimate better.

---

## Design Principles

**Simple surface, complex backend.** The user never sees the AI. They see a dashboard and a chat window.

**Every recommendation cites its source.** No rate gets recommended without showing which job it came from, what the actual conditions were, and how confident the system is.

**Enforce process, allow flexibility.** The command center enforces the estimating workflow. The conversation layer is available for anything, anytime.

**Calibrated to Wollam, not generic.** The system is only as good as the data behind it. Generic AI can estimate generically. This system estimates the way Wollam builds.

**Built to scale.** What starts as one person's tool becomes company-wide intellectual property. Every PM who catalogs a job is investing in the system.

---

## What Success Looks Like

A chief estimator receives an RFP package on Monday morning. By end of day, the system has:
- Summarized the project scope, key dates, and contract terms
- Flagged three contract risk items for legal review
- Identified the site-specific safety requirements
- Generated a quantity template for the takeoff team based on similar past projects
- Pre-populated a WBS framework with Wollam historical rates for the disciplines involved

The chief estimator knows exactly what needs to happen next, who needs to do it, and what questions need to be answered before the number gets built. The estimate that comes out is defensible, sourced, and distinctly Wollam.

That is the goal.

---

*WEIS Vision Document v1.0*
*Wollam Construction — Internal Use Only*
