# WEIS — Database Schema
## Historical Job Cost Data — SQLite

---

## Schema Overview

The database is organized around three core concepts:

1. **Projects** — The completed jobs that form the knowledge base
2. **Cost Data** — Unit costs, production rates, crew configs, and materials from each project
3. **Intelligence** — Lessons learned, benchmarks, and recommended rates derived from the data

All cost data is traceable back to a specific project, discipline, and cost code. No orphaned records.

---

## Table Definitions

### Table: projects

Master record for each cataloged project.

```sql
CREATE TABLE projects (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_number          TEXT NOT NULL UNIQUE,       -- e.g. "8553"
    job_name            TEXT NOT NULL,              -- e.g. "RTK SPD Pump Station"
    owner               TEXT,                       -- e.g. "Rio Tinto Kennecott"
    project_type        TEXT,                       -- pump_station | mining | industrial | refinery | other
    contract_type       TEXT,                       -- prime | sub_kiewit | sub_other
    location            TEXT,                       -- City, State or site name
    start_date          DATE,
    end_date            DATE,
    duration_months     REAL,
    contract_value      REAL,                       -- Final contract value $
    total_actual_cost   REAL,                       -- Total actual cost $
    total_budget_cost   REAL,                       -- Total budget cost $
    total_actual_mh     REAL,                       -- Total actual manhours
    total_budget_mh     REAL,                       -- Total budget manhours
    building_sf         REAL,                       -- Building square footage if applicable
    cpi                 REAL,                       -- Cost performance index (budget/actual)
    projected_margin    REAL,                       -- Projected margin % at closeout
    notes               TEXT,                       -- General project notes
    cataloged_date      DATE,                       -- When this was cataloged
    cataloged_by        TEXT,                       -- Who cataloged it
    data_quality        TEXT DEFAULT 'complete',    -- complete | partial | estimated
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### Table: disciplines

Defines the work breakdown structure for each project.

```sql
CREATE TABLE disciplines (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_code     TEXT NOT NULL,              -- EARTHWORK | CONCRETE | STEEL | PIPING | MECHANICAL | ELECTRICAL | BUILDING | GCONDITIONS
    discipline_name     TEXT NOT NULL,              -- Human readable
    budget_cost         REAL,
    actual_cost         REAL,
    variance_cost       REAL,                       -- actual - budget
    variance_pct        REAL,                       -- (actual - budget) / budget * 100
    budget_mh           REAL,
    actual_mh           REAL,
    variance_mh         REAL,
    self_perform_cost   REAL,
    subcontract_cost    REAL,
    material_cost       REAL,
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### Table: cost_codes

Individual cost code records from Heavy Job Cost Analysis.

```sql
CREATE TABLE cost_codes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER NOT NULL REFERENCES disciplines(id),
    cost_code           TEXT NOT NULL,              -- e.g. "2310"
    description         TEXT NOT NULL,              -- e.g. "Wall Forms - Set"
    unit                TEXT,                       -- SF, CY, LF, EA, TON, MH, LS, etc.
    budget_qty          REAL,
    actual_qty          REAL,
    budget_cost         REAL,
    actual_cost         REAL,
    budget_mh           REAL,
    actual_mh           REAL,
    budget_unit_cost    REAL,                       -- budget_cost / budget_qty
    actual_unit_cost    REAL,                       -- actual_cost / actual_qty
    budget_mh_per_unit  REAL,                       -- budget_mh / budget_qty
    actual_mh_per_unit  REAL,                       -- actual_mh / actual_qty
    over_budget_flag    BOOLEAN DEFAULT FALSE,      -- TRUE if actual > budget * 1.2
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### Table: unit_costs

Extracted and validated unit cost rates, one record per activity per project.

```sql
CREATE TABLE unit_costs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER NOT NULL REFERENCES disciplines(id),
    cost_code_id        INTEGER REFERENCES cost_codes(id),
    activity            TEXT NOT NULL,              -- e.g. "Wall Form/Strip"
    unit                TEXT NOT NULL,              -- SF, CY, LF, EA, TON, etc.
    budget_rate         REAL,                       -- $/unit budget
    actual_rate         REAL,                       -- $/unit actual
    recommended_rate    REAL,                       -- Cataloger's recommended rate
    rate_basis          TEXT,                       -- "budget" | "actual" | "average" | "adjusted"
    rate_notes          TEXT,                       -- Why this rate was recommended
    mh_per_unit_budget  REAL,
    mh_per_unit_actual  REAL,
    mh_per_unit_rec     REAL,                       -- Recommended MH/unit
    project_conditions  TEXT,                       -- Relevant conditions that affect rate
    confidence          TEXT DEFAULT 'MEDIUM',      -- HIGH | MEDIUM | LOW
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### Table: production_rates

Production rates extracted from cost codes and time card data.

```sql
CREATE TABLE production_rates (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER NOT NULL REFERENCES disciplines(id),
    activity            TEXT NOT NULL,              -- e.g. "Structural Excavation"
    unit                TEXT NOT NULL,              -- CY, TON, LF, SF, EA
    production_unit     TEXT NOT NULL,              -- "CY/hr" or "MH/CY" etc.
    budget_rate         REAL,
    actual_rate         REAL,
    recommended_rate    REAL,
    crew_size           INTEGER,                    -- Number of workers
    equipment_primary   TEXT,                       -- Primary equipment type
    equipment_secondary TEXT,                       -- Supporting equipment
    conditions          TEXT,                       -- Material type, depth, access, etc.
    notes               TEXT,
    confidence          TEXT DEFAULT 'MEDIUM',
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### Table: crew_configurations

Crew compositions for specific activities.

```sql
CREATE TABLE crew_configurations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER NOT NULL REFERENCES disciplines(id),
    activity            TEXT NOT NULL,
    crew_description    TEXT NOT NULL,              -- Full crew composition narrative
    foreman             INTEGER DEFAULT 0,          -- Count
    journeyman          INTEGER DEFAULT 0,
    apprentice          INTEGER DEFAULT 0,
    laborer             INTEGER DEFAULT 0,
    operator            INTEGER DEFAULT 0,
    ironworker          INTEGER DEFAULT 0,
    pipefitter          INTEGER DEFAULT 0,
    electrician         INTEGER DEFAULT 0,
    other_trades        TEXT,                       -- Any trades not listed above
    total_crew_size     INTEGER,
    equipment_list      TEXT,                       -- Comma-separated equipment list
    shift_hours         REAL DEFAULT 10,
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### Table: material_costs

Material cost records from Foundation Job History.

```sql
CREATE TABLE material_costs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER NOT NULL REFERENCES disciplines(id),
    cost_code           TEXT,
    material_type       TEXT NOT NULL,              -- e.g. "Ready Mix Concrete", "Reinforcing Steel"
    material_description TEXT,                     -- More specific description
    vendor              TEXT,                       -- Supplier name
    unit                TEXT,                       -- CY, TON, LF, EA, LB, etc.
    quantity            REAL,
    unit_cost           REAL,                       -- $/unit
    total_cost          REAL,
    po_number           TEXT,
    delivery_date       DATE,
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### Table: subcontractors

Subcontractor scope and cost records.

```sql
CREATE TABLE subcontractors (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER NOT NULL REFERENCES disciplines(id),
    cost_code           TEXT,
    sub_name            TEXT,                       -- Subcontractor company name
    scope_description   TEXT NOT NULL,              -- What they did
    scope_category      TEXT,                       -- rebar | concrete_pump | electrical | building_erection | survey | testing | other
    contract_amount     REAL,
    actual_amount       REAL,
    unit                TEXT,                       -- SF, TON, LB, LS, etc.
    quantity            REAL,
    unit_cost           REAL,                       -- $/unit
    sub_pct_of_discipline REAL,                    -- Sub cost as % of discipline total
    performance_rating  TEXT,                       -- good | acceptable | poor
    would_use_again     BOOLEAN,
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### Table: lessons_learned

Lessons learned by discipline and category.

```sql
CREATE TABLE lessons_learned (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER REFERENCES disciplines(id),
    category            TEXT NOT NULL,              -- scope_gap | production_variance | material | subcontractor | schedule | safety | design | estimating
    severity            TEXT DEFAULT 'MEDIUM',      -- HIGH | MEDIUM | LOW
    title               TEXT NOT NULL,              -- Short description
    description         TEXT NOT NULL,              -- Full narrative
    impact              TEXT,                       -- Cost/schedule impact described
    recommendation      TEXT,                       -- What to do differently
    applies_to          TEXT,                       -- Project types this applies to
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### Table: benchmark_rates

System-level benchmark rates compiled across all projects. Used for confidence comparisons.

```sql
CREATE TABLE benchmark_rates (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    discipline_code     TEXT NOT NULL,
    activity            TEXT NOT NULL,
    unit                TEXT NOT NULL,
    low_rate            REAL,                       -- Low end of observed range
    high_rate           REAL,                       -- High end of observed range
    typical_rate        REAL,                       -- Most common / recommended
    rate_type           TEXT NOT NULL,              -- unit_cost | mh_per_unit | production_rate
    source_jobs         TEXT,                       -- Comma-separated job numbers
    project_type        TEXT,                       -- pump_station | mining | industrial | all
    notes               TEXT,
    last_updated        DATE,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### Table: general_conditions_breakdown

Detailed GC cost breakdown for benchmarking overhead rates.

```sql
CREATE TABLE general_conditions_breakdown (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    category            TEXT NOT NULL,              -- management | supervision | safety | survey | testing | insurance | equipment | temp_facilities | other
    description         TEXT,
    cost_code           TEXT,
    budget_cost         REAL,
    actual_cost         REAL,
    unit                TEXT,                       -- $/day | $/month | % of job | LS
    rate                REAL,                       -- Extracted rate
    duration            REAL,                       -- Months or days as applicable
    pct_of_total_job    REAL,                       -- This GC item as % of total job cost
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## Key Indexes

```sql
-- Performance indexes for common query patterns
CREATE INDEX idx_unit_costs_activity ON unit_costs(activity);
CREATE INDEX idx_unit_costs_discipline ON unit_costs(discipline_id);
CREATE INDEX idx_production_rates_activity ON production_rates(activity);
CREATE INDEX idx_cost_codes_code ON cost_codes(cost_code);
CREATE INDEX idx_lessons_category ON lessons_learned(category);
CREATE INDEX idx_subcontractors_category ON subcontractors(scope_category);
CREATE INDEX idx_material_costs_type ON material_costs(material_type);
```

---

## Confidence Level Definitions

| Level | Definition |
|-------|------------|
| HIGH | Rate validated against actual costs on 2+ projects under similar conditions |
| MEDIUM | Rate from single project with good data quality, conditions reasonably similar |
| LOW | Rate from single project with limited data or significantly different conditions |
| ASSUMPTION | No historical data — using industry benchmark or professional judgment |

---

## Data Quality Rules

Before any record is inserted, validate:

1. `project_id` references a valid project
2. `discipline_id` references a valid discipline for that project
3. Numeric fields are non-negative (no negative costs, MH, or quantities)
4. `unit` field is a recognized unit code
5. `actual_rate` is within 10x of `budget_rate` (flag if not, don't reject)
6. Required text fields are not empty strings

---

## Sample Queries

### Find all unit costs for a given activity
```sql
SELECT 
    p.job_number,
    p.job_name,
    uc.activity,
    uc.unit,
    uc.actual_rate,
    uc.recommended_rate,
    uc.confidence,
    uc.rate_notes
FROM unit_costs uc
JOIN projects p ON uc.project_id = p.id
WHERE uc.activity LIKE '%flanged joint%'
ORDER BY p.end_date DESC;
```

### Get production rates for a discipline
```sql
SELECT 
    p.job_number,
    pr.activity,
    pr.production_unit,
    pr.actual_rate,
    pr.recommended_rate,
    pr.crew_size,
    pr.equipment_primary,
    pr.conditions
FROM production_rates pr
JOIN projects p ON pr.project_id = p.id
JOIN disciplines d ON pr.discipline_id = d.id
WHERE d.discipline_code = 'CONCRETE'
ORDER BY pr.activity;
```

### Get benchmark summary for estimating
```sql
SELECT 
    br.discipline_code,
    br.activity,
    br.unit,
    br.typical_rate,
    br.low_rate,
    br.high_rate,
    br.rate_type,
    br.source_jobs
FROM benchmark_rates br
WHERE br.discipline_code = 'PIPING'
ORDER BY br.activity;
```

### General conditions as % of job
```sql
SELECT 
    p.job_number,
    p.job_name,
    d.actual_cost as gc_cost,
    p.total_actual_cost,
    ROUND(d.actual_cost / p.total_actual_cost * 100, 1) as gc_pct
FROM disciplines d
JOIN projects p ON d.project_id = p.id
WHERE d.discipline_code = 'GCONDITIONS';
```

---

*WEIS Data Schema v1.0*
