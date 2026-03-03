# WEIS — System Vision
## Wollam Estimating Intelligence System

---

## The Problem

Construction estimating at the industrial heavy civil level is deeply dependent on experienced people. Production rates, crew configurations, subcontractor relationships, contract risk awareness, and the instinct to know what a job will actually cost — this knowledge lives in the heads of a small number of senior estimators. When those people leave, retire, or are unavailable during a critical bid period, institutional knowledge walks out the door with them.

At the same time, Wollam has hundreds of completed projects tracked in HCSS HeavyJob and HeavyBid — each containing cost codes with manhours, unit costs, production rates, crew data, equipment hours, material purchases, and subcontractor records. That data is the company's estimating DNA. But it's locked behind manual report exports, inconsistent cost code naming, and the fact that interpreting a completed job's data requires the same experience the system is trying to preserve.

The result: estimates that are only as good as the people available to build them, a company whose competitive capability is fragile, and a goldmine of historical data that nobody can efficiently access.

---

## The Vision

**Any estimator at Wollam should be able to describe a scope in plain English and receive a comprehensive, Wollam-calibrated estimate framework — with production rates, crew recommendations, material cost benchmarks, and confidence indicators — drawn directly from the company's own project history.**

This is not a generic estimating tool. It is not powered by industry averages. It is calibrated to Wollam's actual performance on Wollam's actual projects. The data comes from HCSS through direct API connection. The intelligence comes from systematic transformation of that data into validated rate cards, enriched by PM-captured lessons learned.

---

## The North Star

A user sits down to estimate a new pump station project for Kennecott. They type:

> "I need an estimate framework for a concrete pump station structure, 200 CY walls, 100 CY floor, 5,000 SF wall forming, mine site with escort requirements. Include earthwork, mechanical (4 pumps, 15,000 LBS steel), and 1,200 LF of 24" SS pipe installation."

The system responds with:

- **Unit costs by activity** — wall forming at 0.25 MH/SF, wall pour at 0.90 MH/CY, SS pipe install at $200/LF — each citing the source jobs (8553, 8576) and noting whether the rate is based on 1 job or 5
- **Crew configurations** — typical concrete crew (1 foreman, 3-4 carpenters, 2 laborers), pipe crew (1 foreman, 2-3 certified pipefitters, 1-2 laborers)
- **Material benchmarks** — concrete at $265/CY for mine site delivery, structural steel at $1.50/LB installed
- **General conditions framework** — 14-15% of job value for mine site, with specific line items for blast delays, site training, supervision
- **Risk flags** — mine site training typically runs 1.5x standard, confirm pump station construction method (on-grade vs excavated, drives earthwork by 3-5x), verify SS welder certifications before mobilization
- **Change order context** — similar projects averaged 18% CO rate, design development changes drove 61% of CO value
- **Confidence indicators** — "strong" for concrete and SS pipe (multiple job data points), "moderate" for earthwork (single job with scope change)

Every number traces back to a specific job, cost code, and actual outcome. Nothing is invented. Nothing is a generic industry benchmark.

---

## How It Works — The Three Layers

### Layer 1: Raw Data (HCSS API → Database)

WEIS connects directly to HeavyJob and HeavyBid through their published APIs. On a scheduled or on-demand basis, it extracts:

- **From HeavyJob:** Every closed job's cost codes (budget vs actual costs, hours, quantities), time cards, equipment hours, change orders, material receipts, and subcontract data
- **From HeavyBid:** Every estimate's bid items, activities, resources (labor and equipment rates), material takeoffs, and production assumptions

This raw data is stored in its native structure. No interpretation, no transformation — just a clean mirror of what's in HCSS.

### Layer 2: Transformed Data (Rate Cards + Lessons Learned)

The transformation layer does the work that used to require an experienced estimator:

1. **Discipline mapping** — Cost codes are mapped to disciplines (concrete, earthwork, piping, etc.) using Wollam's code structure with AI-assisted interpretation for edge cases
2. **Unit cost calculation** — Budget and actual costs are divided by quantities to produce $/unit and MH/unit rates for every activity
3. **Production rate extraction** — Time card data is analyzed to determine daily production rates and typical crew sizes
4. **Variance flagging** — Activities with >20% budget-to-actual variance are flagged for PM explanation
5. **Rate card generation** — Each completed job produces a structured rate card with recommended rates, confidence levels, and source tracking
6. **PM interview capture** — Project managers are guided through a structured interview to explain variances, capture lessons learned, and confirm recommended rates

### Layer 3: Estimator Knowledge Base (Aggregated Intelligence)

The knowledge base is the compound asset. It aggregates rate cards from all cataloged jobs into:

- **Rate library** — Recommended rates for every activity Wollam performs, weighted by recency, confidence, and number of data points
- **Benchmarks** — Statistical ranges (mean, low, high, standard deviation) for key metrics across project types
- **Crew templates** — Validated crew configurations by discipline and activity
- **Lessons learned index** — Searchable catalog of what went right, what went wrong, and what to watch for

This is the layer the Estimator Agent queries. It grows with every completed job.

---

## What Changed (February → March 2026)

The original WEIS architecture (v1.0, February 2026) was designed around manual data ingestion — export 6 reports from HCSS, process them through a Cataloger Agent in a Claude Project, and produce JCD markdown files that would be parsed into a SQLite database.

That approach proved the concept. Jobs 8553 and 8576 were successfully cataloged and produced validated rate libraries. But it also exposed the limitation: manual processing takes 3-4 hours per job, can only handle one job at a time, and depends on a single person (Travis) who knows how to navigate the export settings.

The HCSS API changes everything:

| Dimension | Manual (v1.0) | API-Driven (v2.0) |
|-----------|---------------|-------------------|
| Data extraction | 3-4 hours/job, manual exports | Minutes, bulk automated |
| Jobs processable | 1 at a time | All closed jobs at once |
| Data completeness | Limited to 6 specific reports | Full API access to all fields |
| Update frequency | Manual trigger, requires Travis | Scheduled/automatic |
| Error rate | Transcription errors from PDF/Excel | Programmatic accuracy |
| Scalability | Doesn't scale beyond a few jobs | Scales to entire job history |

The JCD markdown files and Cataloger Agent workflow remain valuable as the reference standard — they define what "good" output looks like. But the production data pipeline is now API-driven.

---

## The Estimating Team as AI Agents

The system models Wollam's estimating process as a team of functional AI agents, each responsible for a specific domain. The Chief Estimator agent orchestrates the team, and the human chief estimator reviews and approves decisions at defined checkpoints.

| # | Agent | Role |
|---|-------|------|
| 1 | Chief Estimator | Orchestrator — directs all agents, assembles final estimate |
| 2 | Legal/Contract | Contract risk, insurance, bonding, compliance |
| 3 | Quality Manager | Spec reading, QA/QC requirements |
| 4 | Safety Manager | Site safety requirements, hazard identification |
| 5 | Takeoff Engineer | Quantity extraction from drawings and specs |
| 6 | Estimator(s) | Discipline-specific cost estimation (concrete, steel, piping, etc.) |
| 7 | Subcontract/Procurement | Sub bid solicitation, material procurement, quote validation |
| 8 | Scheduler | Duration estimation, resource loading, critical path |
| 9 | Shadow PM | Constructability review, execution planning |
| 10 | Document Control | RFP management, addenda tracking, submittal coordination |

The agents are detailed in AGENTS.md. The agent architecture is designed to be built incrementally — the data layer and transformation layer must be solid before agents are developed.

---

## Who Uses It

### Primary Users
- **Chief Estimator (Travis)** — Reviews AI-generated estimate frameworks, makes final pricing decisions, validates rates against experience
- **Estimators** — Query historical data for specific activities, get rate recommendations for new bids, validate subcontractor quotes
- **Project Managers** — Participate in PM interviews at project closeout, providing context and lessons learned that enrich the knowledge base

### Secondary Users
- **Project Executives** — Review estimate summaries and confidence levels
- **Operations** — Reference crew configurations and production rates for scheduling

### Design Principle
The users who interact with WEIS should never need to understand AI, APIs, databases, or cost code mapping. They describe what they need in plain English. The system handles the complexity.

---

*WEIS Vision v2.0*
*Last Updated: March 2026*
