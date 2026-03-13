# Feature Spec: PM Context Interview

## Purpose
The PM Context Interview is a guided workflow where project managers provide context about how cost codes were used on their completed jobs. This context transforms raw HeavyJob numbers into usable estimating intelligence.

**Without PM context**, the AI can only say: "Cost code 2215 on Job 8553 had 0.28 MH/SF actual."

**With PM context**, the AI can say: "Wall forming on the RTK pump station achieved 0.28 MH/SF. The PM noted this included 20-30' walls with one-sided pours against excavation, using EFCO forms. Rate would be higher for two-sided freestanding walls."

## The Core Problem
HeavyJob records WHAT happened (hours, quantities, costs) but not WHY or HOW:
- Cost code "2215 — C_F/S Walls" doesn't tell you it was one-sided forming
- Cost code "5100" might combine fusing AND excavation in one code, or they might be split
- A low MH/unit might mean great productivity, OR it might mean the quantity was front-loaded and hours followed later
- Equipment codes alone don't tell you the access was restricted or the haul was uphill

The PM Context Interview captures this institutional knowledge before it's lost.

## User Flow

### Step 1: Job Selection
The PM sees a list of all jobs from HeavyJob, showing:
- Job number and name
- Status (active/completed)
- Number of cost codes
- Data richness indicator (how much timecard data exists)
- Interview completion status: Not Started / In Progress / Complete

PM selects a job to provide context for.

### Step 2: Job Overview
After selecting a job, the PM sees a summary dashboard:
- Job name, number, duration
- Total actual hours, total actual cost
- Number of cost codes with data
- Top 5 cost codes by labor hours (gives the PM a quick sense of where the hours went)

Below this, the PM fills in **job-level context**:
- **Project Summary**: What was this job? (free text, 2-3 sentences)
- **Site Conditions**: Access, terrain, weather, restrictions (free text)
- **Key Challenges**: What made this job hard? (free text)
- **Key Successes**: What went well? (free text)
- **Lessons Learned**: What would you do differently next time? (free text)
- **General Notes**: Anything else relevant (free text)

### Step 3: Cost Code Walkthrough
The core of the interview. The PM walks through each cost code that has actual data, presented one at a time (or in a scrollable list).

For each cost code, the PM sees the **raw data** from HeavyJob:
```
Cost Code: 2215 — C_F/S Walls
Unit: SF
Budget: 15,200 SF / 4,256 MH → 0.28 MH/SF
Actual: 14,800 SF / 4,144 MH → 0.28 MH/SF
Confidence: HIGH (47 timecards across 23 days)
Avg Daily Crew: 8.2 workers
Crew Breakdown: 1 FORE, 3 CARP, 3 LAB, 1 OPR
```

And is asked to provide **context** (all fields optional — PM can skip any):

- **What does this code actually cover?** (scope_included)
  - Placeholder: "e.g., Forming and stripping walls 20-30' height, one-sided pours against excavation, EFCO forms"

- **What is NOT included in this code?** (scope_excluded)
  - Placeholder: "e.g., Rebar is separate (code 2220), concrete placement is separate (code 2230)"

- **Related cost codes** (related_codes)
  - Multi-select or free text: "Works with code 2220 (rebar) and 2230 (placement)"

- **What conditions affected production?** (conditions)
  - Placeholder: "e.g., Mine site access restrictions added 30 min/day for badging. Winter months required heat blankets."

- **Anything else an estimator should know?** (notes)
  - Placeholder: "e.g., This rate is conservative — crew was still learning the form system for the first 2 weeks."

### Step 4: Review & Submit
After walking through cost codes, the PM sees a summary:
- Total cost codes reviewed: X of Y
- Cost codes with context: X
- Cost codes skipped: X

PM can go back and edit any entry, then mark the job as "Interview Complete."

## Data Model

### pm_context table (one row per job)
```
job_id          → FK to job table
pm_name         → Who provided this context
project_summary → Free text overview
site_conditions → Free text
key_challenges  → Free text
key_successes   → Free text
lessons_learned → Free text
general_notes   → Free text
completed_at    → Timestamp when PM finished
```

### cc_context table (one row per cost code per job)
```
job_id              → FK to job table
cost_code           → The 4-digit code string
description_override → PM's clarified description (may differ from HeavyJob's)
scope_included      → What work this code covers
scope_excluded      → What is NOT in this code
related_codes       → JSON array of related code strings
conditions          → Conditions that affected production
notes               → General notes
```

## API Endpoints

### GET /api/interview/jobs
Returns all jobs with interview status.
```json
[
  {
    "job_id": 1,
    "job_number": "8553",
    "name": "RTK SPD Pump Station",
    "status": "completed",
    "cost_code_count": 87,
    "cost_codes_with_data": 62,
    "cost_codes_with_context": 15,
    "data_richness": 85,
    "interview_status": "in_progress"
  }
]
```

### GET /api/interview/job/{job_id}
Returns full job detail for the interview.
```json
{
  "job": { "job_id": 1, "job_number": "8553", "name": "RTK SPD Pump Station", ... },
  "pm_context": { "project_summary": "...", "site_conditions": "...", ... },
  "cost_codes": [
    {
      "code": "2215",
      "description": "C_F/S Walls",
      "unit": "SF",
      "bgt_qty": 15200, "act_qty": 14800,
      "bgt_labor_hrs": 4256, "act_labor_hrs": 4144,
      "act_mh_per_unit": 0.28,
      "confidence": "high",
      "timecard_count": 47,
      "crew_size_avg": 8.2,
      "crew_breakdown": {"FORE": 1, "CARP": 3, "LAB": 3, "OPR": 1},
      "context": {
        "scope_included": "Forming and stripping walls...",
        "scope_excluded": "Rebar separate (2220)...",
        "conditions": "Mine site access restrictions...",
        "notes": null
      }
    }
  ]
}
```

### POST /api/interview/context
Save PM context (auto-saves on blur/change, not just on submit).
```json
{
  "job_id": 1,
  "type": "job",
  "data": {
    "pm_name": "Mike Johnson",
    "project_summary": "..."
  }
}
// OR
{
  "job_id": 1,
  "type": "cost_code",
  "cost_code": "2215",
  "data": {
    "scope_included": "...",
    "scope_excluded": "...",
    "conditions": "..."
  }
}
```

### GET /api/interview/progress
Overall progress dashboard data.
```json
{
  "total_jobs": 63,
  "jobs_with_context": 5,
  "jobs_complete": 2,
  "total_cost_codes_with_data": 1847,
  "cost_codes_with_context": 128,
  "top_priority_jobs": [
    {"job_id": 1, "job_number": "8553", "name": "RTK SPD Pump Station", "data_richness": 85, "context_coverage": 24}
  ]
}
```

## UI Design Notes

### Job List Page
- Card-style layout, one card per job
- Each card shows: job number, name, data richness bar, interview status badge
- Sort by: data richness (default), job number, name, status
- Filter by: interview status (All / Not Started / In Progress / Complete)
- Priority jobs highlighted — those with most timecard data but no context

### Interview Page
- Left panel: scrollable list of cost codes (showing code, description, completion dot)
- Right panel: the selected cost code's data + context form
- Top bar: job summary (name, number, progress)
- Auto-save on field blur (no "Save" button — it just saves)
- Green checkmark appears next to cost codes that have context
- "Mark Complete" button at the bottom when PM is done

### Design System
- Follow the Wollam design system in `docs/DESIGN_SYSTEM.md`
- Navy sidebar, gold accents, Inter font
- Cards with subtle shadows, hover states
- Confidence badges: HIGH (green), MODERATE (amber), LOW (red)
- Data richness shown as a horizontal bar (navy gradient fill)

## Priority of Cost Codes
Not all cost codes are equally important. The interview should prioritize:

1. **High-activity codes** — 20+ timecards, 10+ work days (these are the production activities)
2. **High-variance codes** — where budget MH/unit differs significantly from actual (something happened worth explaining)
3. **High-dollar codes** — largest actual cost (these matter most for future estimates)
4. **Low-data codes** — 1-4 timecards (PM can explain if this was a minor activity or a data quality issue)

Present high-priority codes first in the walkthrough. Let PM skip low-priority codes easily.

## What This Is NOT
- This is NOT an approval workflow — PM context is informational, not authoritative
- This is NOT a data entry form — PM is adding context to existing data, not entering new data
- This is NOT required for the AI chat to work — chat works with raw data alone, PM context makes it better
