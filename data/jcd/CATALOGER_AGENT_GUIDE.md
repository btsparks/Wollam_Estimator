# CATALOGER AGENT - OPERATIONAL GUIDE
## Job Cost Data Analysis & Cataloging System

---

# REQUIRED DOCUMENTS CHECKLIST

**Every job catalog requires these 6 documents. Do not proceed without them.**

| # | Source | Report Name | Format | Special Settings |
|---|--------|-------------|--------|------------------|
| 1 | Heavy Job | Time Card Daily Report | FILE | — |
| 2 | Heavy Job | Cost Analysis | FILE | ☑️ Cap Expected at Budget, ☑️ Show unused cost codes |
| 3 | Foundation | Weekly Job Detail | Excel | — |
| 4 | Foundation | Job History Detail | Excel | — |
| 5 | Heavy Bid | Estimate Cost Report | PDF/HTML | — |
| 6 | Heavy Bid | Estimate Price Report | PDF/HTML | — |

---

# OVERVIEW

## Purpose
The Cataloger Agent systematically analyzes completed construction projects to extract validated unit costs, production rates, crew configurations, and lessons learned for use in future estimating.

## Output
For each job analyzed, the Cataloger produces:
1. Individual JCD (Job Cost Data) documents by discipline
2. Master Summary with consolidated unit costs
3. Recommended estimating rates for Heavy Bid

## Time Target
A complete job catalog should be achievable in **2-4 hours** of focused work, not days.

---

# PHASE 1: INITIAL INTAKE

## Step 1.1: Request Core Documents

**Every job catalog REQUIRES these 6 documents. Do not proceed without them.**

---

### HEAVY JOB REPORTS (2 Required)

#### A. Time Card Daily Report
| Field | Requirement |
|-------|-------------|
| **Report Name** | Time Card Daily Report |
| **Export Format** | FILE (not PDF) - this is critical, the report is large |
| **Purpose** | Contains every timecard for the job - crew names, hours, equipment, cost codes |
| **Use For** | Crew composition analysis, equipment utilization, labor distribution |

#### B. Cost Analysis Report
| Field | Requirement |
|-------|-------------|
| **Report Name** | Cost Analysis |
| **Export Format** | FILE |
| **Required Checkboxes** | ☑️ "Cap Expected at Budget" AND ☑️ "Show unused cost codes" |
| **Purpose** | Summarizes cost codes with budget vs actual costs AND quantities including MHs |
| **Use For** | Primary source for cost code costs, quantities, MH tracking |

---

### FOUNDATION REPORTS (2 Required)

#### C. Weekly Job Detail Report
| Field | Requirement |
|-------|-------------|
| **Report Name** | Weekly Job Detail |
| **Export Format** | Excel |
| **Purpose** | Actual accounting costs - this is the BOTTOM LINE cost that has hit the company |
| **Use For** | Material costs, subcontractor costs, margin calculations, cross-reference with HJ report |
| **Note** | Reference this WITH the HJ Cost Analysis for cost code reconciliation |

#### D. Job History Detail Report
| Field | Requirement |
|-------|-------------|
| **Report Name** | Job History Detail |
| **Export Format** | Excel |
| **Purpose** | Shows ALL individual invoices by cost code with vendor names |
| **Use For** | Specific material pricing, subcontractor invoice breakdown, vendor cost analysis |
| **Note** | VITAL for getting specific material and subcontractor pricing values |

---

### HEAVY BID REPORTS (2 Required)

#### E. Estimate Cost Report
| Field | Requirement |
|-------|-------------|
| **Report Name** | Estimate Cost Report |
| **Export Format** | PDF or HTML |
| **Purpose** | Complete breakdown of the ESTIMATED cost at bid time |
| **Contents** | Resources, activities, production expectations, equipment rates, anticipated MH per activity |
| **Use For** | Understanding bid assumptions, comparing planned vs actual production rates |

#### F. Estimate Price Report
| Field | Requirement |
|-------|-------------|
| **Report Name** | Estimate Price Report |
| **Export Format** | PDF or HTML |
| **Purpose** | Revenue expectations and client pricing breakdown |
| **Contents** | Pay application structure, expected margin percentage, spread details |
| **Use For** | Margin analysis, understanding how job was priced and structured |

---

### DOCUMENT REQUEST TEMPLATE

**Standard request to user:**

> "To catalog this job, I need the following 6 REQUIRED documents:
> 
> **From Heavy Job:**
> 1. **Time Card Daily Report** - Export as FILE (not PDF)
> 2. **Cost Analysis Report** - Export as FILE with both checkboxes checked:
>    - ☑️ Cap Expected at Budget
>    - ☑️ Show unused cost codes
> 
> **From Foundation:**
> 3. **Weekly Job Detail** - Export as Excel
> 4. **Job History Detail** - Export as Excel
> 
> **From Heavy Bid:**
> 5. **Estimate Cost Report** - Export as PDF or HTML
> 6. **Estimate Price Report** - Export as PDF or HTML
> 
> These 6 documents are required for every job catalog. Do you have all of these available?"

---

### DOCUMENT CROSS-REFERENCE GUIDE

| Analysis Task | Primary Source | Cross-Reference |
|---------------|----------------|-----------------|
| Cost code costs & MH | HJ Cost Analysis | Foundation Weekly Job Detail |
| Actual quantities | HJ Cost Analysis | — |
| Crew composition | HJ Time Card Daily Report | — |
| Equipment utilization | HJ Time Card Daily Report | — |
| Material costs | Foundation Job History Detail | Foundation Weekly Job Detail |
| Subcontractor costs | Foundation Job History Detail | Foundation Weekly Job Detail |
| Bottom line margin | Foundation Weekly Job Detail | HB Estimate Price Report |
| Bid assumptions | HB Estimate Cost Report | — |
| Production rate comparison | HJ Cost Analysis (actual) | HB Estimate Cost Report (planned) |
| Revenue/pricing | HB Estimate Price Report | — |

## Step 1.2: Gather Basic Project Info

**Ask the user:**
> "Please provide basic project information:
> 1. Job number and name
> 2. Owner/client
> 3. Project type (pump station, mining, industrial, etc.)
> 4. Contract type (prime, sub to Kiewit, etc.)
> 5. Approximate duration (start/end dates)
> 6. Building size (SF) if applicable
> 7. Any major scope changes or VE items?"

---

# PHASE 2: COST CODE ANALYSIS

## Step 2.1: Load and Analyze Cost Code Structure

**Upon receiving documents, immediately run cost code inventory:**

```python
# Standard analysis script
import pandas as pd

df = pd.read_excel('[WEEKLY_JOB_DETAIL].xlsx')
df = df[df['Cost Code'].notna()]

# Group by prefix (first 2 digits)
df['Prefix'] = (df['Cost Code'] // 100).astype(int)

# Summarize by prefix
for prefix in sorted(df['Prefix'].unique()):
    subset = df[df['Prefix'] == prefix]
    bud = subset['Budget Total Cost'].sum()
    act = subset['Actual Cost to Date'].sum()
    print(f"{prefix}xx: ${bud:,.0f} budget / ${act:,.0f} actual")
```

## Step 2.2: Identify Disciplines from Cost Codes

**Standard Wollam cost code structure:**

| Prefix | Category | Typical JCD |
|--------|----------|-------------|
| 10xx | General Conditions | General Conditions |
| 20xx | Site Work General | General Conditions or Earthwork |
| 21xx | Earthwork - Excavation/Backfill | Earthwork |
| 22xx | Earthwork - Structures | Earthwork |
| 23xx | Concrete | Concrete |
| 24xx | Structural Steel | Structural Steel |
| 25xx | Masonry | Masonry (if present) |
| 26xx | Mechanical/Equipment | Mechanical Equipment |
| 27xx | Piping | Piping |
| 28xx | Electrical | Electrical |
| 29xx | Cross-Job Work | General Conditions |
| 31xx | Buy/Haul Earthwork Materials | Earthwork |
| 32xx | Buy Pipe Materials | Piping |
| 33xx | Buy Concrete Materials | Concrete |
| 34xx | Buy Steel Materials | Structural Steel |
| 35xx | Buy Mechanical Equipment | Mechanical Equipment |
| 40xx | Concrete Subs (survey, rebar, pump) | Concrete |
| 41xx | Electrical Sub | Electrical |
| 42xx | Building/Steel Erection Sub | Building Erection |
| 43xx-47xx | Misc Subs | General Conditions |
| 50xx-54xx | Extra Work / Change Orders | Track separately |
| 80xx | Insurance/Standby | General Conditions |
| 99xx | Overhead Allocation | General Conditions |

## Step 2.3: Define JCDs to Create

**Based on cost code analysis, determine which JCDs are needed:**

**Present to user:**
> "Based on the cost code analysis, this job includes the following disciplines:
> 
> | JCD | Cost Codes | Budget | Actual |
> |-----|------------|--------|--------|
> | [List each] | [codes] | $X | $X |
> 
> I recommend creating the following JCD documents:
> 1. [List JCDs]
> 
> Does this align with the actual scope of work? Any disciplines to add or combine?"

---

# PHASE 3: ADDITIONAL DOCUMENT REQUESTS (Job-Specific)

## Step 3.1: Request Discipline-Specific Documents

**The 6 core documents (Phase 1) are REQUIRED for every job. The documents below are ADDITIONAL and job-specific - request as needed to fill gaps or get more detail.**

### For ALL JCDs:
- ✅ 6 Core Documents (already have from Phase 1)

### For EARTHWORK (Additional/Optional):
| Document | Purpose | Priority |
|----------|---------|----------|
| Material delivery tickets | Actual tonnage/CY delivered | OPTIONAL |
| Equipment rental invoices | Rental rates validation | OPTIONAL |
| Geotechnical reports | Soil conditions, slope analysis | IF APPLICABLE |

### For CONCRETE (Additional/Optional):
| Document | Purpose | Priority |
|----------|---------|----------|
| Concrete batch tickets | Actual CY placed, mix designs | OPTIONAL |
| Rebar sub invoices (if not in Job History) | $/LB validation | OPTIONAL |
| Pump sub invoices (if not in Job History) | $/CY pumping cost | OPTIONAL |

### For STRUCTURAL STEEL (Additional/Optional):
| Document | Purpose | Priority |
|----------|---------|----------|
| Steel erection sub invoices (if not in Job History) | $/TON erection | OPTIONAL |
| Steel material invoices (if not in Job History) | $/TON delivered | OPTIONAL |
| Shop drawings | Piece counts, weights | OPTIONAL |

### For PIPING (Additional/Optional):
| Document | Purpose | Priority |
|----------|---------|----------|
| Pipe material invoices (line-item detail) | $/LF by type and size | OPTIONAL |
| Valve/fitting invoices (line-item detail) | Individual item costs | OPTIONAL |
| Hydrotest records | Test dates, durations | OPTIONAL |
| Weld maps/logs | Joint counts by size | OPTIONAL |

### For ELECTRICAL (Additional/Optional):
| Document | Purpose | Priority |
|----------|---------|----------|
| Electrical sub scope of work | What's included in sub price | OPTIONAL |
| One-line diagrams | Scope verification | OPTIONAL |

### For GENERAL CONDITIONS (Additional/Optional):
| Document | Purpose | Priority |
|----------|---------|----------|
| Survey sub invoices (line-item detail) | Monthly rates breakdown | OPTIONAL |
| QC testing invoices (line-item detail) | Cost by discipline/test type | OPTIONAL |
| Equipment rental summary | Rates validation | OPTIONAL |

**Note:** Most subcontractor and material costs will be captured in the Job History Detail report. Additional invoices are only needed if you require line-item detail (e.g., individual valve prices, specific test costs) that isn't broken out in the Job History.

**Standard request to user (only if gaps identified):**
> "The 6 core documents provide most of what I need. However, to get more detailed unit costs for [DISCIPLINE], it would help to have:
> - [List specific documents]
> 
> Are any of these available? If not, I can proceed with the core documents and note where we need more detail."

---

# PHASE 4: SYSTEMATIC JCD ANALYSIS

## Step 4.1: Standard Analysis Process (Per JCD)

**For each JCD, follow this sequence:**

### A. Cost Summary
```
1. Pull all relevant cost codes
2. Calculate: Budget vs Actual (cost and MH)
3. Calculate: Variance % 
4. Flag any codes >20% over budget for investigation
```

### B. Unit Cost Extraction
```
1. Identify quantity from cost code (QTY column) or calculate from description
2. Calculate: Budget $/Unit = Budget Cost ÷ Budget QTY
3. Calculate: Actual $/Unit = Actual Cost ÷ Actual QTY
4. For labor codes: Calculate MH/Unit
5. Determine: Recommended Rate (typically between budget and actual, leaning toward actual)
```

### C. Material Cost Breakdown
```
1. Filter Foundation data by material cost codes (31xx-35xx)
2. Group by vendor (Comment field)
3. Calculate vendor totals
4. Extract $/Unit where possible (requires invoice detail)
```

### D. Subcontractor Analysis
```
1. Filter by sub cost codes (40xx-47xx)
2. Identify vendors from Foundation data
3. Calculate: Sub cost as % of discipline total
4. Calculate: $/Unit metrics (e.g., rebar $/LB, elec $/SF)
```

### E. Crew & Equipment (if daily reports available)
```
1. Identify typical crew composition
2. Document equipment IDs and types
3. Note rental vs owned equipment
4. Calculate production rates achieved
```

### F. Lessons Learned
```
1. What drove major variances?
2. What worked well?
3. What should be done differently?
4. Any scope changes or VE items?
```

## Step 4.2: Standard JCD Document Structure

**Every JCD should follow this format:**

```markdown
# JCD [JOB#] - [DISCIPLINE] SECTION
## [Project Name]

---

## EXECUTIVE SUMMARY

### Grand Total - [Discipline]

| Category | Budget | Actual | Variance |
|----------|--------|--------|----------|
| Self-Performed Labor | $X | $X | X% |
| Materials | $X | $X | X% |
| Subcontractors | $X | $X | X% |
| **TOTAL** | **$X** | **$X** | **X%** |

### Key Metrics
[3-5 most important unit costs for this discipline]

---

## 1. SELF-PERFORMED LABOR

### 1.1 Cost Code Detail
[Table with all codes, budget, actual, MH, $/Unit]

### 1.2 Unit Cost Analysis
[Detailed breakdown of key activities]

### 1.3 Crew & Equipment
[If available from daily reports]

---

## 2. MATERIALS

### 2.1 Material Summary
[Table by material type]

### 2.2 Vendor Breakdown
[Who supplied what, at what cost]

---

## 3. SUBCONTRACTORS

### 3.1 Subcontractor Summary
[Table with sub name, scope, cost, $/Unit]

---

## 4. RECOMMENDED ESTIMATING RATES

### Labor Rates
| Activity | Budget | Achieved | **Recommended** |
|----------|--------|----------|-----------------|
| [Activity] | X MH/Unit | X MH/Unit | **X MH/Unit** |

### Material Costs
| Material | Budget | Achieved | **Recommended** |
|----------|--------|----------|-----------------|
| [Material] | $X/Unit | $X/Unit | **$X/Unit** |

---

## 5. LESSONS LEARNED

[Key takeaways for future estimating]

---

## Document Control
| Version | Date | Changes |
|---------|------|---------|
| 1.0 | [Date] | Initial JCD |
```

---

# PHASE 5: MASTER SUMMARY

## Step 5.1: After All JCDs Complete

**Create Master Summary with:**

1. **Project Overview** - Basic info, duration, contract type
2. **Financial Summary** - Total cost, MH, $/SF, CPI
3. **Cost by JCD** - Table showing all disciplines
4. **MH by Discipline** - Where did the labor hours go?
5. **Key Quantities** - Concrete CY, Steel TON, etc.
6. **Unit Cost Reference** - Consolidated rates from all JCDs
7. **Subcontractor Summary** - All subs with rates
8. **Material Cost Summary** - Key materials with $/Unit
9. **Lessons Learned** - Project-wide takeaways
10. **Quick Reference** - Top 20 unit costs

## Step 5.2: Coverage Verification

**Before finalizing, verify all cost codes are accounted for:**

```python
# Run coverage check
total_job = df['Actual Cost to Date'].sum()
covered = sum([jcd_totals])
uncovered = total_job - covered
coverage_pct = covered / total_job * 100

print(f"Coverage: {coverage_pct:.1f}%")
if coverage_pct < 95:
    print("WARNING: Missing cost codes - investigate")
```

---

# PHASE 6: QUALITY CHECKS

## Step 6.1: Validation Questions

**Before finalizing each JCD, verify:**

- [ ] Do Budget + Actual totals match source documents?
- [ ] Are unit costs reasonable? (Flag if >2x industry norms)
- [ ] Are MH rates reasonable? (Flag if <0.1 or >10 MH/Unit for most activities)
- [ ] Are all major cost codes accounted for?
- [ ] Are recommended rates between budget and actual (with justification if not)?

## Step 6.2: User Validation

**Present key findings to user for validation:**

> "Here are the key unit costs I've extracted for [DISCIPLINE]:
> 
> | Activity | Achieved Rate | Notes |
> |----------|---------------|-------|
> | [Key items] | X | [Any concerns] |
> 
> Do these align with your experience on this job? Any rates that seem off?"

---

# APPENDIX A: STANDARD QUESTIONS BY PHASE

## Intake Questions
1. What documents do you have available?
2. What was the project scope?
3. Were there major scope changes or VE items?
4. Any known issues or problem areas?

## During Analysis Questions
1. This cost code shows X variance - what drove this?
2. I see [vendor] charged $X - does this include [scope item]?
3. What was the typical crew size for [activity]?
4. Were there any productivity issues?

## Validation Questions
1. Does this rate align with your experience?
2. Should I adjust for any unusual conditions?
3. Any context I'm missing?

---

# APPENDIX B: COMMON ISSUES & SOLUTIONS

| Issue | Solution |
|-------|----------|
| Missing quantities in cost codes | Calculate from Foundation detail or ask user |
| Costs split across multiple codes | Combine for unit cost calculation |
| Lump sum items with no quantity | Use MH as proxy or mark as LS |
| Vendor costs not broken down | Note as "requires invoice detail" |
| Extreme variance (>50%) | Investigate - likely scope change or coding error |
| Zero budget with actual costs | Extra work / change order - track separately |

---

# APPENDIX C: OUTPUT FILE NAMING

**Standard naming convention:**

```
JCD_[JOBNUMBER]_[DISCIPLINE]_SECTION.md
JCD_[JOBNUMBER]_MASTER_SUMMARY.md
```

**Examples:**
- JCD_8553_EARTHWORK_SECTION.md
- JCD_8553_CONCRETE_SECTION.md
- JCD_8553_MASTER_SUMMARY.md

---

# APPENDIX D: TIME ESTIMATES

| Phase | Target Time |
|-------|-------------|
| Phase 1: Intake & 6 Required Documents | 15-30 min |
| Phase 2: Cost Code Analysis | 15 min |
| Phase 3: Additional Document Requests (if needed) | 5-10 min |
| Phase 4: JCD Analysis (per discipline) | 20-30 min each |
| Phase 5: Master Summary | 30 min |
| Phase 6: Quality Checks | 15 min |
| **TOTAL (8 JCDs)** | **3-4 hours** |

**Keys to Speed:**
1. **Get all 6 required documents BEFORE starting** - do not begin analysis without them
2. Use standardized scripts for data extraction
3. Follow consistent JCD format - don't reinvent structure each time
4. Don't over-analyze - capture key rates, note gaps, move on
5. Batch questions for user - don't ask one question at a time
6. **HJ Time Card Daily Report** replaces need for individual daily reports
7. **Job History Detail** has most vendor/material info - only request line-item invoices if needed

---

# REVISION HISTORY

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-11 | Claude/Travis | Initial guide based on Job 8553 cataloging |
| 1.1 | 2026-02-11 | Claude/Travis | Added specific 6 required documents (HJ Time Card Daily, HJ Cost Analysis, FND Weekly Job Detail, FND Job History Detail, HB Estimate Cost Report, HB Estimate Price Report) with exact export settings |

---

*This guide defines the standard process for the Cataloger Agent to analyze completed construction projects and extract estimating data.*
