# WEIS — Product Description
## Wollam Estimating Intelligence System

---

## What It Is

WEIS is an internal AI-powered estimating application built exclusively for Wollam Construction. It connects directly to the company's HCSS HeavyJob and HeavyBid systems, automatically extracting cost data from every completed project and transforming it into a searchable, intelligent knowledge base that powers faster, more accurate estimates.

The system is not a generic estimating tool. It is not powered by industry averages or textbook rates. Every number in the system traces back to a specific Wollam project, a specific cost code, and a specific actual outcome. It is the company's estimating history, organized and made instantly accessible.

---

## What It Does

### For Estimators
- **Query historical rates:** "What did we achieve for wall forming on pump stations?" Returns MH/SF rates from Jobs 8553 and 8576 with confidence indicators.
- **Get estimate frameworks:** Describe a scope in plain English, receive a structured estimate with rates, crews, materials, and risk flags — all sourced from Wollam's own data.
- **Validate quotes:** Compare a subcontractor's bid against what Wollam has historically achieved on similar work.

### For Project Managers
- **Close out projects efficiently:** At project completion, the PM completes a 15-30 minute guided interview explaining key variances and capturing lessons learned. The system handles the rest.
- **Contribute to company knowledge:** Every PM interview enriches the knowledge base for future bids.

### For the Chief Estimator
- **See confidence levels:** Know which parts of an estimate are backed by strong data (5 similar jobs) versus limited data (1 job or budget-only).
- **Track estimating accuracy:** Over time, compare estimates to actual outcomes across all cataloged jobs.

---

## How It Works (Non-Technical)

1. **Data comes in automatically.** WEIS connects to HeavyJob and HeavyBid through secure APIs. When a job is closed, WEIS pulls all the cost data — budgets, actual costs, hours, quantities, change orders, materials, subs.

2. **The system calculates rates.** For every cost code on every job, WEIS calculates what was budgeted per unit, what was actually achieved per unit, and what the recommended rate should be going forward.

3. **PMs add context.** Any cost code that ran significantly over or under budget gets flagged. The PM explains why — was it a scope change, an error, a one-time condition, or a genuine efficiency gain? This context is critical.

4. **Rates enter the knowledge base.** Once PM-reviewed, the rates from each job are aggregated into the master rate library. More jobs = more data points = higher confidence.

5. **Estimators query the knowledge base.** When building a new estimate, the system provides rates, crews, material benchmarks, and lessons learned — all from Wollam's own history.

---

## What Makes It Different

**It's calibrated to Wollam.** Industry averages say concrete wall forming takes X MH/SF. Wollam's pump station crew achieves 0.20-0.28 MH/SF. That Wollam-specific rate, backed by actual project data, is what the system provides.

**It captures context, not just numbers.** A rate without context is dangerous. Wollam's $4.24/CY backfill rate on Job 8576 looks great — until you know it was site-sourced material at high volume. Imported fill on a smaller job would be $10/CY. The PM interview captures this distinction.

**It gets smarter with every job.** Each completed project adds data points. Confidence levels increase. Rate ranges tighten. The system becomes more valuable over time without any additional development work.

**It replaces manual work, not judgment.** The system handles the tedious parts — data extraction, rate calculation, cross-referencing. The estimator and PM still provide the judgment, context, and final decisions.

---

## Current Status

WEIS is operational with a manual data pipeline and transitioning to automated HCSS API integration.

- **Two jobs fully cataloged** (8553 and 8576) with validated rate libraries
- **Six AI agents operational** for estimating queries
- **CLI and web interfaces** functional
- **HCSS API integration** in architecture phase — will enable bulk extraction of all historical jobs

---

*WEIS Product Description v2.0*
*Wollam Construction — Internal Use Only*
