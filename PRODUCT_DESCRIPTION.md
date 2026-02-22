# WEIS — Product Description
## Wollam Estimating Intelligence System

---

## What It Is

WEIS is an internal AI-powered estimating application built exclusively for Wollam Construction. It converts the company's accumulated project experience — historical costs, production rates, crew configurations, lessons learned — into an active intelligence layer that supports the full estimating lifecycle from RFP intake through proposal submission.

The system is not a generic estimating tool. It is calibrated entirely to Wollam's actual field performance, built on Wollam's actual cost data, and designed around the way Wollam actually builds work.

---

## The Problem It Solves

**Estimating expertise is fragile.** The knowledge required to build a credible industrial heavy civil estimate — what a pump station should cost per CY of concrete, what crew to use for large-diameter pipe installation, how long structural steel erection takes for a 200-ton building — lives in the heads of a small number of experienced people. When those people are unavailable, the quality of estimates suffers.

**Every estimate starts from scratch.** There is no systematic way to leverage what was learned on past projects when building a new estimate. Historical rates exist in spreadsheets and documents scattered across completed job files. Finding and validating them takes more time than most bid schedules allow.

**Estimates get compared on completeness, not value.** The question that matters — "is this job worth bidding, and at what price?" — is harder to answer than "did we cover all the scope?" WEIS is designed to make the value question answerable quickly.

---

## Who Uses It

| User | How They Use It |
|------|----------------|
| Chief Estimator | Orchestrates the bid, makes key decisions, reviews agent outputs, approves final number |
| Project Estimators | Build discipline estimates using AI-recommended rates from historical data |
| Project Manager (Bidding) | Contributes constructability knowledge, reviews estimate assumptions |
| Specialty Reviewers (Legal, QC, Safety) | Use agent outputs to review RFP documents through their lens |
| Project Manager (Closeout) | Catalogs completed job to enrich the historical database |

**None of these users need to understand AI to use the system.** The application looks and feels like a construction management tool. The AI is invisible infrastructure.

---

## Core Capabilities

### Historical Data Engine
Every completed project, cataloged systematically — unit costs, production rates, crew configurations, material costs, subcontractor data, lessons learned. All of it queryable by any team member in plain English.

*"What did we pay for 20-inch flanged joints on pump station work?"*
*"What crew did we use for mat pours and what production did we achieve?"*
*"What lessons did we learn about earthwork at high-altitude mining sites?"*

### Intelligent Estimate Framework
Take any quantity takeoff and generate a structured work breakdown with Wollam-calibrated rates. Every rate cites its source — which job, which cost code, what conditions. Every rate comes with a confidence indicator — HIGH when data is strong, ASSUMPTION when it isn't.

### Workflow Management
A visual dashboard that tracks every discipline, every agent role, every decision from bid kickoff to proposal submission. The chief estimator always knows what's done, what's in progress, what's blocked, and what needs a decision.

### Specialist Agent Reviews
Each estimating role — legal, quality, safety, procurement, scheduling — has a corresponding AI agent that reads the RFP documents through that lens and produces a structured output. Contract risk flags. Quality cost implications. Site-specific safety requirements. All available before the number gets built.

### Living Document Management
RFP documents arrive and change throughout the bid period. WEIS tracks every addendum, logs every RFI, and flags when document changes affect work already estimated. The team always works from current information.

---

## What Makes It Different From Generic AI

Every AI tool can estimate generically. WEIS estimates the way Wollam builds.

When WEIS recommends a concrete forming rate, it's because Wollam achieved 0.28 MH/SF on Job 8553 under specific conditions — and it tells you that. When it flags a concern about a contract clause, it's informed by actual contract issues Wollam has encountered on previous projects. When it identifies a scope item that's commonly missed in pump station estimates, it's because it was missed before and logged as a lesson learned.

The system compounds in value over time. Every completed job that gets cataloged makes every future estimate better.

---

## What It Is Not

- It is not an accounting system. It does not replace Foundation.
- It is not a project management tool. It does not replace Procore.
- It is not an estimating software. It does not replace Heavy Bid.
- It is not a time tracking system. It does not replace Heavy Job.

WEIS sits alongside these systems, informed by their outputs, and makes the estimating process faster and smarter. It does not replace any existing tool.

---

## Technology

The application is built with Python, a SQLite database (migrating to PostgreSQL as the data grows), and the Anthropic Claude API for natural language intelligence. The frontend is a clean web interface built with Streamlit in Phase 2, migrating to a custom web application as Phase 3 matures.

All data stays within Wollam's control. The only external service is the Anthropic API, which processes questions and generates responses but does not retain project data.

---

## Build Approach

WEIS is being built iteratively using AI-assisted software development (Claude Code). This approach means:
- Travis drives every architectural and product decision
- The system can be iterated quickly without external developer dependency
- Features are built exactly as needed, not as interpreted by a third party
- The system evolves based on real use on real bids

---

## Confidentiality

All data in WEIS is proprietary to Wollam Construction. Historical cost data, production rates, and project details represent significant competitive advantage. The system is for internal use only. No data is shared outside the company.

---

*WEIS Product Description v1.0*
*Wollam Construction — Internal Use Only*
*February 2026*
