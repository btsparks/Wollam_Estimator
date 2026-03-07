"""
WEIS Database Migration — v1.3 → v2.0

Creates all v2.0 tables alongside existing v1.3 tables.
Does NOT drop, rename, or modify any existing tables.
Safe to run multiple times (idempotent — uses CREATE TABLE IF NOT EXISTS).

Three-tier schema:
    Tier 1 (Raw):        sync_metadata, business_unit, job, hj_costcode,
                         hj_timecard, hj_change_order, hj_material,
                         hj_subcontract, hb_estimate, hb_biditem,
                         hb_activity, hb_resource
    Tier 2 (Transformed): rate_card, rate_item, crew_config, lesson_learned
    Tier 3 (Knowledge):  rate_library, benchmark

Usage:
    python scripts/migrate_v2.py
"""

import sqlite3
import os
import sys

# Default database path — same as the existing v1.3 database
DB_PATH = os.environ.get("WEIS_DB_PATH", os.path.join("data", "db", "weis.db"))


# ─────────────────────────────────────────────────────────────
# Tier 1: Raw Data Layer
# Mirror of HCSS API data. No interpretation. Source of truth.
# ─────────────────────────────────────────────────────────────

TIER_1_TABLES = [
    # Tracks every sync operation for auditability and incremental sync
    """
    CREATE TABLE IF NOT EXISTS sync_metadata (
        sync_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        source          TEXT NOT NULL,           -- 'heavyjob', 'heavybid', 'jcd_manual'
        sync_type       TEXT NOT NULL,           -- 'full', 'incremental', 'manual'
        started_at      DATETIME NOT NULL,
        completed_at    DATETIME,
        status          TEXT DEFAULT 'running',  -- 'running', 'completed', 'failed'
        jobs_processed  INTEGER DEFAULT 0,
        jobs_failed     INTEGER DEFAULT 0,
        error_log       TEXT,
        notes           TEXT
    )
    """,

    # HCSS business unit — required context for all API calls
    """
    CREATE TABLE IF NOT EXISTS business_unit (
        bu_id           INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_bu_id      TEXT UNIQUE NOT NULL,    -- HCSS business unit UUID
        name            TEXT NOT NULL,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # Core project record. One row per HeavyJob job.
    # Links to business_unit (which HCSS org) and optionally to hb_estimate (the bid)
    """
    CREATE TABLE IF NOT EXISTS job (
        job_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_job_id     TEXT UNIQUE,             -- HeavyJob UUID (null for manual entries)
        job_number      TEXT NOT NULL,            -- e.g., '8553', '8576'
        name            TEXT NOT NULL,
        status          TEXT,                     -- 'Active', 'Closed', 'Pending'
        start_date      DATE,
        end_date        DATE,
        bu_id           INTEGER REFERENCES business_unit(bu_id),
        estimate_id     INTEGER REFERENCES hb_estimate(estimate_id),

        -- Project metadata (from API or manual entry)
        owner_client    TEXT,                     -- e.g., 'RTKC' (Rio Tinto Kennecott Copper)
        contract_type   TEXT,                     -- e.g., 'Sub to Kiewit - FF'
        project_type    TEXT,                     -- e.g., 'Pump Station - Mining'
        location        TEXT,
        duration_months REAL,
        base_contract   REAL,
        revised_contract REAL,

        -- Data source tracking
        data_source     TEXT DEFAULT 'hcss_api',  -- 'hcss_api', 'jcd_manual'
        last_synced     DATETIME,
        created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # HeavyJob cost code with budget and actual values.
    # One row per cost code per job. This is the core data for rate calculation.
    #
    # Budget = what was estimated. Actual = what happened in the field.
    # The delta between these two is where all the intelligence lives.
    """
    CREATE TABLE IF NOT EXISTS hj_costcode (
        cc_id           INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_cc_id      TEXT,                    -- HeavyJob cost code UUID
        job_id          INTEGER NOT NULL REFERENCES job(job_id),
        code            TEXT NOT NULL,            -- e.g., '2215' (C_F/S Walls)
        description     TEXT,                     -- e.g., 'C_F/S Walls'
        discipline      TEXT,                     -- Mapped from discipline_map.yaml
        unit            TEXT,                     -- 'SF', 'CY', 'LF', 'EA', 'LS', etc.

        -- Budget values (what was estimated)
        bgt_qty         REAL,
        bgt_labor_hrs   REAL,
        bgt_labor_cost  REAL,
        bgt_equip_hrs   REAL,
        bgt_equip_cost  REAL,
        bgt_matl_cost   REAL,
        bgt_sub_cost    REAL,
        bgt_total       REAL,

        -- Actual values (what happened in the field)
        act_qty         REAL,
        act_labor_hrs   REAL,
        act_labor_cost  REAL,
        act_equip_hrs   REAL,
        act_equip_cost  REAL,
        act_matl_cost   REAL,
        act_sub_cost    REAL,
        act_total       REAL,

        -- Progress (0-100, from HeavyJob foreman reporting)
        pct_complete    REAL,

        UNIQUE(job_id, code)
    )
    """,

    # Time card data from HeavyJob — records daily crew labor by cost code.
    # Used for crew analysis and production rate calculation.
    """
    CREATE TABLE IF NOT EXISTS hj_timecard (
        tc_id           INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_tc_id      TEXT,
        job_id          INTEGER NOT NULL REFERENCES job(job_id),
        cc_id           INTEGER REFERENCES hj_costcode(cc_id),
        cost_code       TEXT,                    -- Denormalized for convenience
        date            DATE NOT NULL,
        employee_id     TEXT,
        employee_name   TEXT,
        employee_code   TEXT,                    -- Trade code (e.g., OE4 = operator)
        hours           REAL,
        equip_id        TEXT,
        equip_hours     REAL,
        foreman_id      TEXT,
        status          TEXT,                    -- 'Approved', 'Pending'
        quantity        REAL                     -- Production quantity recorded that day
    )
    """,

    # Equipment entries from timecards — tracks equipment usage per cost code.
    """
    CREATE TABLE IF NOT EXISTS hj_equipment_entry (
        entry_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_tc_id      TEXT,
        job_id          INTEGER NOT NULL REFERENCES job(job_id),
        cost_code       TEXT,
        date            DATE,
        equipment_id    TEXT,
        equipment_code  TEXT,
        equipment_desc  TEXT,
        hours           REAL,
        cost_code_id    TEXT
    )
    """,

    # Change orders from HeavyJob.
    # Categories: SC (Scope Change), DD (Design Development).
    # CO patterns reveal project risk — DD-driven COs averaged 61% of CO value on 8576.
    """
    CREATE TABLE IF NOT EXISTS hj_change_order (
        co_id           INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_co_id      TEXT,
        job_id          INTEGER NOT NULL REFERENCES job(job_id),
        co_number       TEXT,
        description     TEXT,
        amount          REAL,
        status          TEXT,                    -- 'Approved', 'Pending', 'Rejected'
        approved_date   DATE,
        category        TEXT,                    -- 'SC' (Scope Change), 'DD' (Design Dev)
        schedule_impact TEXT
    )
    """,

    # Materials received/installed.
    """
    CREATE TABLE IF NOT EXISTS hj_material (
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
    )
    """,

    # Subcontract data — who we hired, for what scope, at what cost.
    """
    CREATE TABLE IF NOT EXISTS hj_subcontract (
        sub_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_sub_id     TEXT,
        job_id          INTEGER NOT NULL REFERENCES job(job_id),
        vendor          TEXT NOT NULL,
        scope           TEXT,
        contract_amount REAL,
        actual_amount   REAL,
        status          TEXT,
        notes           TEXT
    )
    """,

    # HeavyBid estimate record — the bid that was submitted.
    """
    CREATE TABLE IF NOT EXISTS hb_estimate (
        estimate_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_est_id     TEXT UNIQUE,
        name            TEXT NOT NULL,
        description     TEXT,
        bid_date        DATE,
        status          TEXT,                    -- 'Won', 'Lost', 'Pending'
        total_cost      REAL,
        total_price     REAL,
        bu_id           INTEGER REFERENCES business_unit(bu_id)
    )
    """,

    # Bid items from HeavyBid — the scheduled values / pay items.
    """
    CREATE TABLE IF NOT EXISTS hb_biditem (
        biditem_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_bi_id      TEXT,
        estimate_id     INTEGER NOT NULL REFERENCES hb_estimate(estimate_id),
        code            TEXT,
        description     TEXT,
        quantity        REAL,
        unit            TEXT,
        total_cost      REAL,
        total_price     REAL
    )
    """,

    # Activities (cost buildup) from HeavyBid — how each bid item is priced.
    # This is the estimator's "detail" — labor, equipment, material breakdown.
    """
    CREATE TABLE IF NOT EXISTS hb_activity (
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
    )
    """,

    # Labor and equipment resources from HeavyBid — the rate book.
    """
    CREATE TABLE IF NOT EXISTS hb_resource (
        resource_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_res_id     TEXT,
        estimate_id     INTEGER NOT NULL REFERENCES hb_estimate(estimate_id),
        type            TEXT NOT NULL,            -- 'Labor', 'Equipment'
        code            TEXT,
        description     TEXT,
        rate            REAL,
        hours           REAL,
        cost            REAL
    )
    """,
]


# ─────────────────────────────────────────────────────────────
# Tier 2: Transformed Data Layer
# Calculated rates, flagged variances, PM-reviewed data.
# ─────────────────────────────────────────────────────────────

TIER_2_TABLES = [
    # One rate card per job. Contains summary metrics and PM review status.
    # Lifecycle: draft → pending_review → approved
    """
    CREATE TABLE IF NOT EXISTS rate_card (
        card_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id          INTEGER NOT NULL REFERENCES job(job_id),

        -- Summary
        total_budget    REAL,
        total_actual    REAL,
        cpi             REAL,                    -- Cost Performance Index (budget / actual)

        -- Status
        status          TEXT DEFAULT 'draft',    -- 'draft', 'pending_review', 'approved'
        pm_reviewed     BOOLEAN DEFAULT FALSE,
        pm_name         TEXT,
        pm_notes        TEXT,
        review_date     DATETIME,

        -- Metadata
        data_source     TEXT DEFAULT 'hcss_api',
        generated_date  DATETIME DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(job_id)
    )
    """,

    # Individual rate items within a rate card.
    # One row per cost code per job — this is where the magic happens.
    # Budget rate vs actual rate → recommended rate with confidence.
    """
    CREATE TABLE IF NOT EXISTS rate_item (
        item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id         INTEGER NOT NULL REFERENCES rate_card(card_id),
        discipline      TEXT NOT NULL,
        activity        TEXT NOT NULL,            -- Cost code (e.g., '2215')
        description     TEXT,                     -- Activity description (e.g., 'C_F/S Walls')
        unit            TEXT,                     -- 'SF', 'CY', 'MH/SF', '$/CY', etc.

        -- Budget rates (what was estimated per unit)
        bgt_mh_per_unit REAL,
        bgt_cost_per_unit REAL,

        -- Actual rates (what happened per unit)
        act_mh_per_unit REAL,
        act_cost_per_unit REAL,

        -- Recommended rate (calculated or PM-overridden)
        rec_rate        REAL,
        rec_basis       TEXT,                    -- 'budget', 'actual', 'calculated', 'pm_override'

        -- Quantities
        qty_budget      REAL,
        qty_actual      REAL,

        -- Confidence (strong/moderate/limited/none)
        confidence      TEXT DEFAULT 'moderate',
        confidence_reason TEXT,

        -- Variance (budget vs actual)
        variance_pct    REAL,
        variance_flag   BOOLEAN DEFAULT FALSE,   -- True if >20%
        variance_explanation TEXT,                -- From PM interview

        -- Field intelligence (from timecard analysis)
        timecard_count  INTEGER DEFAULT 0,
        work_days       INTEGER DEFAULT 0,
        crew_size_avg   REAL,
        daily_qty_avg   REAL,
        daily_qty_peak  REAL,
        total_hours     REAL,
        total_qty       REAL,
        total_labor_cost REAL,
        total_equip_cost REAL,
        crew_breakdown  TEXT,                    -- JSON crew/equipment breakdown

        -- Source tracking
        source_codes    TEXT,                    -- Comma-separated cost codes if aggregated

        UNIQUE(card_id, activity)
    )
    """,

    # Crew configurations extracted from timecard data.
    # Tells future estimators: "On this job, for this activity, the crew was..."
    """
    CREATE TABLE IF NOT EXISTS crew_config (
        config_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id          INTEGER NOT NULL REFERENCES job(job_id),
        discipline      TEXT NOT NULL,
        activity        TEXT,
        crew_size       INTEGER,
        composition     TEXT,                    -- JSON: {"foreman": 1, "carpenter": 3, "laborer": 2}
        production_rate REAL,                    -- Units per crew-hour
        production_unit TEXT,                    -- e.g., 'SF/day', 'CY/hr'
        days_worked     INTEGER,
        source_tcs      TEXT,                    -- Timecard IDs used to derive this
        notes           TEXT
    )
    """,

    # Lessons learned from PM interviews and cataloging.
    # Categories: variance (cost overrun/underrun), success, risk, process
    """
    CREATE TABLE IF NOT EXISTS lesson_learned (
        lesson_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id          INTEGER NOT NULL REFERENCES job(job_id),
        discipline      TEXT,
        category        TEXT,                    -- 'variance', 'success', 'risk', 'process'
        description     TEXT NOT NULL,
        impact          TEXT,                    -- 'high', 'medium', 'low'
        recommendation  TEXT,
        pm_name         TEXT,
        captured_date   DATETIME DEFAULT CURRENT_TIMESTAMP,
        source          TEXT DEFAULT 'pm_interview'  -- 'pm_interview', 'jcd_manual', 'auto'
    )
    """,
]


# ─────────────────────────────────────────────────────────────
# Tier 3: Estimator Knowledge Base
# Aggregated rates across all approved rate cards.
# This is what the Estimator Agent queries.
# ─────────────────────────────────────────────────────────────

TIER_3_TABLES = [
    # Aggregated recommended rates across all cataloged jobs.
    # One row per activity per rate type.
    # Example: discipline='concrete', activity='2215', rate=0.25, unit='MH/SF'
    """
    CREATE TABLE IF NOT EXISTS rate_library (
        rate_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        discipline      TEXT NOT NULL,
        activity        TEXT NOT NULL,
        description     TEXT,

        -- Rate
        rate            REAL NOT NULL,
        unit            TEXT NOT NULL,            -- 'MH/SF', '$/CY', '$/LF', etc.
        rate_type       TEXT,                     -- 'labor', 'equipment', 'all_in', 'material'

        -- Confidence (based on number of jobs backing this rate)
        confidence      TEXT DEFAULT 'moderate',
        jobs_count      INTEGER DEFAULT 0,        -- More jobs = higher confidence
        source_jobs     TEXT,                     -- Comma-separated job numbers

        -- Statistical range
        rate_low        REAL,
        rate_high       REAL,
        std_dev         REAL,

        -- Metadata
        last_updated    DATETIME,
        notes           TEXT,

        UNIQUE(discipline, activity, rate_type)
    )
    """,

    # Roll-up benchmarks for high-level estimating and sanity checking.
    # Example: metric='all_in_concrete', value=867, unit='$/CY', project_type='pump_station_mine'
    """
    CREATE TABLE IF NOT EXISTS benchmark (
        bench_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        metric          TEXT NOT NULL,            -- e.g., 'all_in_concrete', 'gc_percent'
        description     TEXT,
        value           REAL NOT NULL,
        unit            TEXT,                     -- '$/CY', '%', '$/SF', etc.

        -- Context (benchmarks apply to specific project types)
        project_type    TEXT,                     -- e.g., 'pump_station_mine', 'industrial'
        applicable_when TEXT,                     -- Human-readable conditions

        -- Statistical
        jobs_count      INTEGER DEFAULT 0,
        std_dev         REAL,
        range_low       REAL,
        range_high      REAL,

        -- Metadata
        source_jobs     TEXT,
        last_updated    DATETIME,

        UNIQUE(metric, project_type)
    )
    """,
]


# ─────────────────────────────────────────────────────────────
# Indexes for performance on frequent queries
# ─────────────────────────────────────────────────────────────

INDEXES = [
    # Job lookups by number (most common query pattern)
    "CREATE INDEX IF NOT EXISTS idx_job_number ON job(job_number)",

    # Cost code lookups by job + code (unique constraint handles this, but explicit for clarity)
    "CREATE INDEX IF NOT EXISTS idx_hj_cc_job_code ON hj_costcode(job_id, code)",

    # Filter cost codes by discipline (e.g., "show me all concrete cost codes")
    "CREATE INDEX IF NOT EXISTS idx_hj_cc_discipline ON hj_costcode(discipline)",

    # Rate item lookups by card + activity (unique constraint)
    "CREATE INDEX IF NOT EXISTS idx_equip_entry_job ON hj_equipment_entry(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_equip_entry_cc ON hj_equipment_entry(job_id, cost_code)",
    "CREATE INDEX IF NOT EXISTS idx_ri_card_activity ON rate_item(card_id, activity)",

    # Filter rate items by discipline
    "CREATE INDEX IF NOT EXISTS idx_ri_discipline ON rate_item(discipline)",

    # Knowledge base lookups by discipline + activity
    "CREATE INDEX IF NOT EXISTS idx_rl_disc_activity ON rate_library(discipline, activity)",

    # Lessons learned by job + discipline
    "CREATE INDEX IF NOT EXISTS idx_ll_job_disc ON lesson_learned(job_id, discipline)",
]


def migrate(db_path: str = DB_PATH) -> dict:
    """
    Run the v2.0 migration on the specified database.

    Creates all v2.0 tables and indexes alongside existing v1.3 tables.
    Idempotent — safe to run multiple times.

    Returns:
        dict with 'tables_created', 'indexes_created', 'existing_tables'
    """
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        print("Run 'python scripts/seed_db.py' first to create the v1.3 database.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check existing tables before migration
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    existing_tables = {row[0] for row in cursor.fetchall()}

    print(f"Database: {db_path}")
    print(f"Existing tables: {len(existing_tables)}")
    print()

    tables_created = []
    tables_skipped = []

    # Create all tables across all three tiers
    all_tables = (
        [("Tier 1 — Raw Data", TIER_1_TABLES)]
        + [("Tier 2 — Transformed", TIER_2_TABLES)]
        + [("Tier 3 — Knowledge Base", TIER_3_TABLES)]
    )

    for tier_name, table_list in all_tables:
        print(f"--- {tier_name} ---")
        for sql in table_list:
            # Extract table name from CREATE TABLE statement
            table_name = sql.split("IF NOT EXISTS")[1].split("(")[0].strip()

            if table_name in existing_tables:
                tables_skipped.append(table_name)
                print(f"  SKIP  {table_name} (already exists)")
            else:
                cursor.execute(sql)
                tables_created.append(table_name)
                print(f"  CREATE {table_name}")
        print()

    # Create indexes
    print("--- Indexes ---")
    indexes_created = 0
    for sql in INDEXES:
        index_name = sql.split("IF NOT EXISTS")[1].split("ON")[0].strip()
        cursor.execute(sql)
        indexes_created += 1
        print(f"  INDEX  {index_name}")

    conn.commit()

    # Final summary
    print()
    print("=" * 50)
    print("Migration Summary")
    print("=" * 50)
    print(f"  Tables created:  {len(tables_created)}")
    print(f"  Tables skipped:  {len(tables_skipped)} (already existed)")
    print(f"  Indexes created: {indexes_created}")

    if tables_created:
        print(f"\n  New tables: {', '.join(tables_created)}")

    # Verify all expected tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    final_tables = {row[0] for row in cursor.fetchall()}

    expected_v2 = {
        "sync_metadata", "business_unit", "job", "hj_costcode", "hj_timecard",
        "hj_equipment_entry",
        "hj_change_order", "hj_material", "hj_subcontract", "hb_estimate",
        "hb_biditem", "hb_activity", "hb_resource", "rate_card", "rate_item",
        "crew_config", "lesson_learned", "rate_library", "benchmark",
    }
    missing = expected_v2 - final_tables
    if missing:
        print(f"\n  WARNING: Missing tables: {', '.join(missing)}")
    else:
        print(f"\n  All {len(expected_v2)} v2.0 tables verified.")

    # Confirm v1.3 tables are untouched
    v13_tables = existing_tables - expected_v2
    v13_still_present = v13_tables & final_tables
    if v13_tables == v13_still_present:
        print(f"  All {len(v13_tables)} v1.3 tables untouched.")
    else:
        lost = v13_tables - v13_still_present
        print(f"  WARNING: v1.3 tables missing after migration: {', '.join(lost)}")

    conn.close()

    return {
        "tables_created": tables_created,
        "tables_skipped": tables_skipped,
        "indexes_created": indexes_created,
        "existing_tables": list(existing_tables),
    }


if __name__ == "__main__":
    migrate()
