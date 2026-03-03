# WEIS — Database Schema
## Version 2.0 — API-Native with Three-Tier Structure

---

## Schema Philosophy

The database has three tiers, each with a distinct purpose:

1. **Raw Data Layer** — Mirror of HCSS API data. No interpretation. Stored exactly as received. Enables re-processing if transformation logic improves.
2. **Transformed Data Layer** — Calculated rates, flagged variances, PM-reviewed data. One rate card per job per discipline.
3. **Estimator Knowledge Base** — Multi-job aggregated rates and statistical benchmarks. This is what agents query.

Data flows downward: Raw → Transformed → Knowledge Base. Each tier can be rebuilt from the tier above it.

---

## Tier 1: Raw Data Layer

### SYNC_METADATA
Tracks API sync operations for auditability and incremental sync support.

```sql
CREATE TABLE sync_metadata (
    sync_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,          -- 'heavyjob', 'heavybid', 'jcd_manual'
    sync_type       TEXT NOT NULL,          -- 'full', 'incremental', 'manual'
    started_at      DATETIME NOT NULL,
    completed_at    DATETIME,
    status          TEXT DEFAULT 'running', -- 'running', 'completed', 'failed'
    jobs_processed  INTEGER DEFAULT 0,
    jobs_failed     INTEGER DEFAULT 0,
    error_log       TEXT,
    notes           TEXT
);
```

### BUSINESS_UNIT
HCSS business unit — required for all API calls.

```sql
CREATE TABLE business_unit (
    bu_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    hcss_bu_id      TEXT UNIQUE NOT NULL,   -- HCSS business unit UUID
    name            TEXT NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### JOB
Core project record. One row per HeavyJob job.

```sql
CREATE TABLE job (
    job_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hcss_job_id     TEXT UNIQUE,            -- HeavyJob UUID (null for manual entries)
    job_number      TEXT NOT NULL,           -- e.g., '8553', '8576'
    name            TEXT NOT NULL,
    status          TEXT,                    -- 'Active', 'Closed', 'Pending'
    start_date      DATE,
    end_date        DATE,
    bu_id           INTEGER REFERENCES business_unit(bu_id),
    estimate_id     INTEGER REFERENCES hb_estimate(estimate_id),
    
    -- Project metadata (from API or manual entry)
    owner_client    TEXT,                    -- e.g., 'RTKC'
    contract_type   TEXT,                    -- e.g., 'Sub to Kiewit - FF'
    project_type    TEXT,                    -- e.g., 'Pump Station - Mining'
    location        TEXT,
    duration_months REAL,
    base_contract   REAL,
    revised_contract REAL,
    
    -- Data source tracking
    data_source     TEXT DEFAULT 'hcss_api', -- 'hcss_api', 'jcd_manual'
    last_synced     DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### HJ_COSTCODE
HeavyJob cost code with budget and actual values. One row per cost code per job.

```sql
CREATE TABLE hj_costcode (
    cc_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    hcss_cc_id      TEXT,                   -- HeavyJob cost code UUID
    job_id          INTEGER NOT NULL REFERENCES job(job_id),
    code            TEXT NOT NULL,           -- e.g., '2215'
    description     TEXT,                    -- e.g., 'C_F/S Walls'
    discipline      TEXT,                    -- Mapped from discipline_map.yaml
    unit            TEXT,                    -- 'SF', 'CY', 'LF', 'EA', 'LS', etc.
    
    -- Budget values
    bgt_qty         REAL,
    bgt_labor_hrs   REAL,
    bgt_labor_cost  REAL,
    bgt_equip_hrs   REAL,
    bgt_equip_cost  REAL,
    bgt_matl_cost   REAL,
    bgt_sub_cost    REAL,
    bgt_total       REAL,
    
    -- Actual values
    act_qty         REAL,
    act_labor_hrs   REAL,
    act_labor_cost  REAL,
    act_equip_hrs   REAL,
    act_equip_cost  REAL,
    act_matl_cost   REAL,
    act_sub_cost    REAL,
    act_total       REAL,
    
    -- Progress
    pct_complete    REAL,                   -- 0-100
    
    UNIQUE(job_id, code)
);
```

### HJ_TIMECARD
Time card data for crew analysis and production rate calculation.

```sql
CREATE TABLE hj_timecard (
    tc_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    hcss_tc_id      TEXT,
    job_id          INTEGER NOT NULL REFERENCES job(job_id),
    cc_id           INTEGER REFERENCES hj_costcode(cc_id),
    cost_code       TEXT,                   -- Denormalized for convenience
    date            DATE NOT NULL,
    employee_id     TEXT,
    employee_name   TEXT,
    hours           REAL,
    equip_id        TEXT,
    equip_hours     REAL,
    foreman_id      TEXT,
    status          TEXT,                   -- 'Approved', 'Pending'
    quantity         REAL                   -- Production quantity recorded
);
```

### HJ_CHANGE_ORDER
Change orders from HeavyJob.

```sql
CREATE TABLE hj_change_order (
    co_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    hcss_co_id      TEXT,
    job_id          INTEGER NOT NULL REFERENCES job(job_id),
    co_number       TEXT,
    description     TEXT,
    amount          REAL,
    status          TEXT,                   -- 'Approved', 'Pending', 'Rejected'
    approved_date   DATE,
    category        TEXT,                   -- 'SC' (Scope Change), 'DD' (Design Dev)
    schedule_impact TEXT
);
```

### HJ_MATERIAL
Materials received/installed.

```sql
CREATE TABLE hj_material (
    material_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    hcss_mat_id     TEXT,
    job_id          INTEGER NOT NULL REFERENCES job(job_id),
    description     TEXT,
    quantity        REAL,
    unit            TEXT,
    unit_cost       REAL,
    total_cost      REAL,
    vendor          TEXT,
    po_number       TEXT,
    date_received   DATE
);
```

### HJ_SUBCONTRACT
Subcontract data.

```sql
CREATE TABLE hj_subcontract (
    sub_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hcss_sub_id     TEXT,
    job_id          INTEGER NOT NULL REFERENCES job(job_id),
    vendor          TEXT NOT NULL,
    scope           TEXT,
    contract_amount REAL,
    actual_amount   REAL,
    status          TEXT,
    notes           TEXT
);
```

### HB_ESTIMATE
HeavyBid estimate record.

```sql
CREATE TABLE hb_estimate (
    estimate_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    hcss_est_id     TEXT UNIQUE,
    name            TEXT NOT NULL,
    description     TEXT,
    bid_date        DATE,
    status          TEXT,                   -- 'Won', 'Lost', 'Pending'
    total_cost      REAL,
    total_price     REAL,
    bu_id           INTEGER REFERENCES business_unit(bu_id)
);
```

### HB_BIDITEM
Bid items from HeavyBid estimate.

```sql
CREATE TABLE hb_biditem (
    biditem_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    hcss_bi_id      TEXT,
    estimate_id     INTEGER NOT NULL REFERENCES hb_estimate(estimate_id),
    code            TEXT,
    description     TEXT,
    quantity        REAL,
    unit            TEXT,
    total_cost      REAL,
    total_price     REAL
);
```

### HB_ACTIVITY
Activities (cost buildup) from HeavyBid.

```sql
CREATE TABLE hb_activity (
    activity_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    hcss_act_id     TEXT,
    estimate_id     INTEGER NOT NULL REFERENCES hb_estimate(estimate_id),
    biditem_id      INTEGER REFERENCES hb_biditem(biditem_id),
    code            TEXT,
    description     TEXT,
    quantity        REAL,
    unit            TEXT,
    labor_hours     REAL,
    labor_cost      REAL,
    equip_hours     REAL,
    equip_cost      REAL,
    matl_cost       REAL,
    sub_cost        REAL,
    total_cost      REAL,
    production_rate REAL
);
```

### HB_RESOURCE
Labor and equipment resources from HeavyBid.

```sql
CREATE TABLE hb_resource (
    resource_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    hcss_res_id     TEXT,
    estimate_id     INTEGER NOT NULL REFERENCES hb_estimate(estimate_id),
    type            TEXT NOT NULL,           -- 'Labor', 'Equipment'
    code            TEXT,
    description     TEXT,
    rate            REAL,
    hours           REAL,
    cost            REAL
);
```

---

## Tier 2: Transformed Data Layer

### RATE_CARD
One rate card per job. Contains summary metrics and PM review status.

```sql
CREATE TABLE rate_card (
    card_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL REFERENCES job(job_id),
    
    -- Summary
    total_budget    REAL,
    total_actual    REAL,
    cpi             REAL,                   -- Cost Performance Index
    
    -- Status
    status          TEXT DEFAULT 'draft',   -- 'draft', 'pending_review', 'approved'
    pm_reviewed     BOOLEAN DEFAULT FALSE,
    pm_name         TEXT,
    pm_notes        TEXT,
    review_date     DATETIME,
    
    -- Metadata
    data_source     TEXT DEFAULT 'hcss_api',
    generated_date  DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(job_id)
);
```

### RATE_ITEM
Individual rate items within a rate card. One row per cost code per job.

```sql
CREATE TABLE rate_item (
    item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id         INTEGER NOT NULL REFERENCES rate_card(card_id),
    discipline      TEXT NOT NULL,
    activity        TEXT NOT NULL,           -- Cost code (e.g., '2215')
    description     TEXT,                    -- Activity description
    unit            TEXT,                    -- 'SF', 'CY', 'MH/SF', '$/CY', etc.
    
    -- Budget rates
    bgt_mh_per_unit REAL,
    bgt_cost_per_unit REAL,
    
    -- Actual rates
    act_mh_per_unit REAL,
    act_cost_per_unit REAL,
    
    -- Recommended rate
    rec_rate        REAL,
    rec_basis       TEXT,                   -- 'budget', 'actual', 'calculated', 'pm_override'
    
    -- Quantities
    qty_budget      REAL,
    qty_actual      REAL,
    
    -- Confidence
    confidence      TEXT DEFAULT 'moderate', -- 'strong', 'moderate', 'limited', 'none'
    confidence_reason TEXT,
    
    -- Variance
    variance_pct    REAL,
    variance_flag   BOOLEAN DEFAULT FALSE,  -- True if >20%
    variance_explanation TEXT,               -- From PM interview
    
    -- Source tracking
    source_codes    TEXT,                    -- Comma-separated cost codes
    
    UNIQUE(card_id, activity)
);
```

### CREW_CONFIG
Crew configurations extracted from timecard data.

```sql
CREATE TABLE crew_config (
    config_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL REFERENCES job(job_id),
    discipline      TEXT NOT NULL,
    activity        TEXT,
    crew_size       INTEGER,
    composition     TEXT,                   -- JSON: {"foreman": 1, "carpenter": 3, "laborer": 2}
    production_rate REAL,                   -- Units per crew-hour
    production_unit TEXT,                   -- e.g., 'SF/day', 'CY/hr'
    days_worked     INTEGER,
    source_tcs      TEXT,                   -- Timecard IDs used
    notes           TEXT
);
```

### LESSON_LEARNED
Lessons learned from PM interviews and cataloging.

```sql
CREATE TABLE lesson_learned (
    lesson_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL REFERENCES job(job_id),
    discipline      TEXT,
    category        TEXT,                   -- 'variance', 'success', 'risk', 'process'
    description     TEXT NOT NULL,
    impact          TEXT,                   -- 'high', 'medium', 'low'
    recommendation  TEXT,
    pm_name         TEXT,
    captured_date   DATETIME DEFAULT CURRENT_TIMESTAMP,
    source          TEXT DEFAULT 'pm_interview' -- 'pm_interview', 'jcd_manual', 'auto'
);
```

---

## Tier 3: Estimator Knowledge Base

### RATE_LIBRARY
Aggregated recommended rates across all cataloged jobs. One row per activity.

```sql
CREATE TABLE rate_library (
    rate_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    discipline      TEXT NOT NULL,
    activity        TEXT NOT NULL,
    description     TEXT,
    
    -- Rate
    rate            REAL NOT NULL,
    unit            TEXT NOT NULL,           -- 'MH/SF', '$/CY', '$/LF', etc.
    rate_type       TEXT,                    -- 'labor', 'equipment', 'all_in', 'material'
    
    -- Confidence
    confidence      TEXT DEFAULT 'moderate',
    jobs_count      INTEGER DEFAULT 0,      -- Number of jobs this rate is based on
    source_jobs     TEXT,                    -- Comma-separated job numbers
    
    -- Statistical range
    rate_low        REAL,
    rate_high       REAL,
    std_dev         REAL,
    
    -- Metadata
    last_updated    DATETIME,
    notes           TEXT,
    
    UNIQUE(discipline, activity, rate_type)
);
```

### BENCHMARK
Roll-up benchmarks for high-level estimating and sanity checking.

```sql
CREATE TABLE benchmark (
    bench_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    metric          TEXT NOT NULL,           -- e.g., 'all_in_concrete', 'gc_percent'
    description     TEXT,
    value           REAL NOT NULL,
    unit            TEXT,                    -- '$/CY', '%', '$/SF', etc.
    
    -- Context
    project_type    TEXT,                    -- e.g., 'pump_station_mine', 'industrial'
    applicable_when TEXT,                    -- Conditions where benchmark applies
    
    -- Statistical
    jobs_count      INTEGER DEFAULT 0,
    std_dev         REAL,
    range_low       REAL,
    range_high      REAL,
    
    -- Metadata
    source_jobs     TEXT,
    last_updated    DATETIME,
    
    UNIQUE(metric, project_type)
);
```

---

## Cost Code → Discipline Mapping

Mapping is defined in `config/discipline_map.yaml` and applied during transformation. The mapping logic:

1. Check for exact code match in overrides
2. Check for specific code match in discipline subcategories
3. Match by 2-digit prefix to discipline
4. If no match, flag for manual assignment

```
Code Prefix → Discipline
10xx, 20xx  → General Conditions
21xx, 31xx  → Earthwork
22xx, 23xx, 33xx, 40xx → Concrete
24xx, 34xx, 42xx → Structural Steel
26xx, 27xx, 32xx → Mechanical / Piping
28xx, 41xx  → Electrical
2405-2415   → SS Pipe Conveyance (specific codes)
50xx-54xx   → Change Orders (tracked separately by discipline)
```

---

## Unit Cost Calculation Rules

### Labor Rate
```
budget_mh_per_unit = budget_labor_hours / budget_quantity
actual_mh_per_unit = actual_labor_hours / actual_quantity
budget_cost_per_unit = budget_labor_cost / budget_quantity
actual_cost_per_unit = actual_labor_cost / budget_quantity
```

### Recommended Rate
```
If actual <= budget:
    recommended = actual + (budget - actual) * 0.2    # 80% toward actual
If actual > budget:
    recommended = budget + (actual - budget) * 0.5    # 50% between
```

PM can override recommended rate during interview.

### Confidence Assessment
| Level | Criteria |
|-------|----------|
| Strong | ≥90% complete, has budget AND actual, reasonable quantities |
| Moderate | 50-89% complete, or has actual but no budget comparison |
| Limited | Has budget only, no actual data |
| None | Insufficient data for rate calculation |

### Variance Flag
Any rate item with >20% budget-to-actual variance is flagged. PM interview must provide an explanation before the rate card can be approved.

---

## Data Validation Rules

1. `job_id` and `code` combinations must be unique per job
2. Numeric fields (costs, hours, quantities) must be non-negative
3. `unit` must be a recognized unit code from the master unit list
4. Actual rate should be within 10x of budget rate (flag if not, don't reject)
5. Required text fields (job name, code description) must not be empty
6. Confidence level must be one of: strong, moderate, limited, none
7. Rate card status must follow the lifecycle: draft → pending_review → approved

---

## Sample Queries

### Find rates for a specific activity across all jobs
```sql
SELECT 
    j.job_number,
    j.name AS job_name,
    ri.activity,
    ri.description,
    ri.act_mh_per_unit,
    ri.act_cost_per_unit,
    ri.rec_rate,
    ri.confidence,
    ri.unit
FROM rate_item ri
JOIN rate_card rc ON ri.card_id = rc.card_id
JOIN job j ON rc.job_id = j.job_id
WHERE ri.description LIKE '%wall form%'
  AND rc.status = 'approved'
ORDER BY j.end_date DESC;
```

### Get aggregated rate from knowledge base
```sql
SELECT 
    discipline,
    activity,
    description,
    rate,
    unit,
    confidence,
    jobs_count,
    source_jobs,
    rate_low,
    rate_high
FROM rate_library
WHERE discipline = 'concrete'
  AND activity LIKE '%form%wall%'
ORDER BY confidence DESC;
```

### GC as percentage of job
```sql
SELECT 
    j.job_number,
    j.name,
    b.value AS gc_percent,
    b.range_low,
    b.range_high,
    b.jobs_count
FROM benchmark b
JOIN job j ON j.job_number IN (
    SELECT value FROM json_each(b.source_jobs)
)
WHERE b.metric = 'gc_percent'
  AND b.project_type = 'pump_station_mine';
```

### Lessons learned for a discipline
```sql
SELECT 
    j.job_number,
    ll.category,
    ll.description,
    ll.recommendation,
    ll.impact,
    ll.pm_name
FROM lesson_learned ll
JOIN job j ON ll.job_id = j.job_id
WHERE ll.discipline = 'earthwork'
ORDER BY ll.impact DESC, j.end_date DESC;
```

---

*WEIS Data Schema v2.0*
*Last Updated: March 2026*
