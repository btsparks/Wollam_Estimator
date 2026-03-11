"""WEIS database connection and schema management."""

import sqlite3
from pathlib import Path
from app.config import DB_PATH

SCHEMA_VERSION = "1.9"

SCHEMA_SQL = """
-- ============================================================
-- WEIS Database Schema v1.0
-- Wollam Estimating Intelligence System
-- ============================================================

-- Schema versioning
CREATE TABLE IF NOT EXISTS schema_version (
    version     TEXT NOT NULL,
    applied_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Master record for each cataloged project
CREATE TABLE IF NOT EXISTS projects (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_number          TEXT NOT NULL UNIQUE,
    job_name            TEXT NOT NULL,
    owner               TEXT,
    project_type        TEXT,
    contract_type       TEXT,
    location            TEXT,
    start_date          DATE,
    end_date            DATE,
    duration_months     REAL,
    contract_value      REAL,
    total_actual_cost   REAL,
    total_budget_cost   REAL,
    total_actual_mh     REAL,
    total_budget_mh     REAL,
    building_sf         REAL,
    cpi                 REAL,
    projected_margin    REAL,
    notes               TEXT,
    cataloged_date      DATE,
    cataloged_by        TEXT,
    data_quality        TEXT DEFAULT 'complete',
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Work breakdown by discipline for each project
CREATE TABLE IF NOT EXISTS disciplines (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_code     TEXT NOT NULL,
    discipline_name     TEXT NOT NULL,
    budget_cost         REAL,
    actual_cost         REAL,
    variance_cost       REAL,
    variance_pct        REAL,
    budget_mh           REAL,
    actual_mh           REAL,
    variance_mh         REAL,
    self_perform_cost   REAL,
    subcontract_cost    REAL,
    material_cost       REAL,
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Individual cost code records
CREATE TABLE IF NOT EXISTS cost_codes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER NOT NULL REFERENCES disciplines(id),
    cost_code           TEXT NOT NULL,
    description         TEXT NOT NULL,
    unit                TEXT,
    budget_qty          REAL,
    actual_qty          REAL,
    budget_cost         REAL,
    actual_cost         REAL,
    budget_mh           REAL,
    actual_mh           REAL,
    budget_unit_cost    REAL,
    actual_unit_cost    REAL,
    budget_mh_per_unit  REAL,
    actual_mh_per_unit  REAL,
    over_budget_flag    BOOLEAN DEFAULT FALSE,
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Extracted unit cost rates
CREATE TABLE IF NOT EXISTS unit_costs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER NOT NULL REFERENCES disciplines(id),
    cost_code_id        INTEGER REFERENCES cost_codes(id),
    activity            TEXT NOT NULL,
    unit                TEXT NOT NULL,
    budget_rate         REAL,
    actual_rate         REAL,
    recommended_rate    REAL,
    rate_basis          TEXT,
    rate_notes          TEXT,
    mh_per_unit_budget  REAL,
    mh_per_unit_actual  REAL,
    mh_per_unit_rec     REAL,
    project_conditions  TEXT,
    confidence          TEXT DEFAULT 'MEDIUM',
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Production rates
CREATE TABLE IF NOT EXISTS production_rates (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER NOT NULL REFERENCES disciplines(id),
    activity            TEXT NOT NULL,
    unit                TEXT NOT NULL,
    production_unit     TEXT NOT NULL,
    budget_rate         REAL,
    actual_rate         REAL,
    recommended_rate    REAL,
    crew_size           INTEGER,
    equipment_primary   TEXT,
    equipment_secondary TEXT,
    conditions          TEXT,
    notes               TEXT,
    confidence          TEXT DEFAULT 'MEDIUM',
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Crew compositions
CREATE TABLE IF NOT EXISTS crew_configurations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER NOT NULL REFERENCES disciplines(id),
    activity            TEXT NOT NULL,
    crew_description    TEXT NOT NULL,
    foreman             INTEGER DEFAULT 0,
    journeyman          INTEGER DEFAULT 0,
    apprentice          INTEGER DEFAULT 0,
    laborer             INTEGER DEFAULT 0,
    operator            INTEGER DEFAULT 0,
    ironworker          INTEGER DEFAULT 0,
    pipefitter          INTEGER DEFAULT 0,
    electrician         INTEGER DEFAULT 0,
    other_trades        TEXT,
    total_crew_size     INTEGER,
    equipment_list      TEXT,
    shift_hours         REAL DEFAULT 10,
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Material cost records
CREATE TABLE IF NOT EXISTS material_costs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER NOT NULL REFERENCES disciplines(id),
    cost_code           TEXT,
    material_type       TEXT NOT NULL,
    material_description TEXT,
    vendor              TEXT,
    unit                TEXT,
    quantity            REAL,
    unit_cost           REAL,
    total_cost          REAL,
    po_number           TEXT,
    delivery_date       DATE,
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Subcontractor records
CREATE TABLE IF NOT EXISTS subcontractors (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER NOT NULL REFERENCES disciplines(id),
    cost_code           TEXT,
    sub_name            TEXT,
    scope_description   TEXT NOT NULL,
    scope_category      TEXT,
    contract_amount     REAL,
    actual_amount       REAL,
    unit                TEXT,
    quantity            REAL,
    unit_cost           REAL,
    sub_pct_of_discipline REAL,
    performance_rating  TEXT,
    would_use_again     BOOLEAN,
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Lessons learned
CREATE TABLE IF NOT EXISTS lessons_learned (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    discipline_id       INTEGER REFERENCES disciplines(id),
    category            TEXT NOT NULL,
    severity            TEXT DEFAULT 'MEDIUM',
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    impact              TEXT,
    recommendation      TEXT,
    applies_to          TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Benchmark rates compiled across projects
CREATE TABLE IF NOT EXISTS benchmark_rates (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    discipline_code     TEXT NOT NULL,
    activity            TEXT NOT NULL,
    unit                TEXT NOT NULL,
    low_rate            REAL,
    high_rate           REAL,
    typical_rate        REAL,
    rate_type           TEXT NOT NULL,
    source_jobs         TEXT,
    project_type        TEXT,
    notes               TEXT,
    last_updated        DATE,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- General conditions breakdown
CREATE TABLE IF NOT EXISTS general_conditions_breakdown (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL REFERENCES projects(id),
    category            TEXT NOT NULL,
    description         TEXT,
    cost_code           TEXT,
    budget_cost         REAL,
    actual_cost         REAL,
    unit                TEXT,
    rate                REAL,
    duration            REAL,
    pct_of_total_job    REAL,
    notes               TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_unit_costs_activity ON unit_costs(activity);
CREATE INDEX IF NOT EXISTS idx_unit_costs_discipline ON unit_costs(discipline_id);
CREATE INDEX IF NOT EXISTS idx_production_rates_activity ON production_rates(activity);
CREATE INDEX IF NOT EXISTS idx_cost_codes_code ON cost_codes(cost_code);
CREATE INDEX IF NOT EXISTS idx_lessons_category ON lessons_learned(category);
CREATE INDEX IF NOT EXISTS idx_subcontractors_category ON subcontractors(scope_category);
CREATE INDEX IF NOT EXISTS idx_material_costs_type ON material_costs(material_type);

-- ============================================================
-- Active Bid Documents (Phase 2.4)
-- ============================================================

CREATE TABLE IF NOT EXISTS active_bids (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bid_name            TEXT NOT NULL,
    bid_number          TEXT,
    owner               TEXT,
    general_contractor  TEXT,
    bid_date            DATE,
    project_type        TEXT,
    location            TEXT,
    estimated_value     REAL,
    status              TEXT DEFAULT 'active',
    notes               TEXT,
    is_focus            BOOLEAN DEFAULT FALSE,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bid_documents (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bid_id              INTEGER NOT NULL REFERENCES active_bids(id),
    filename            TEXT NOT NULL,
    file_type           TEXT NOT NULL,
    file_size_bytes     INTEGER,
    doc_category        TEXT DEFAULT 'general',
    doc_label           TEXT,
    extraction_status   TEXT DEFAULT 'pending',
    extraction_warning  TEXT,
    page_count          INTEGER,
    word_count          INTEGER,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bid_document_chunks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id         INTEGER NOT NULL REFERENCES bid_documents(id),
    bid_id              INTEGER NOT NULL REFERENCES active_bids(id),
    chunk_index         INTEGER NOT NULL,
    chunk_text          TEXT NOT NULL,
    section_heading     TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bid_documents_bid ON bid_documents(bid_id);
CREATE INDEX IF NOT EXISTS idx_bid_chunks_bid ON bid_document_chunks(bid_id);
CREATE INDEX IF NOT EXISTS idx_bid_chunks_document ON bid_document_chunks(document_id);

-- ============================================================
-- Agent Reports (Phase 3)
-- ============================================================

CREATE TABLE IF NOT EXISTS agent_reports (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bid_id              INTEGER NOT NULL REFERENCES active_bids(id),
    agent_name          TEXT NOT NULL,
    agent_version       TEXT NOT NULL DEFAULT '1.0',
    status              TEXT NOT NULL DEFAULT 'pending',
    report_json         TEXT,
    summary_text        TEXT,
    risk_rating         TEXT,
    flags_count         INTEGER DEFAULT 0,
    input_doc_count     INTEGER DEFAULT 0,
    input_chunk_count   INTEGER DEFAULT 0,
    tokens_used         INTEGER DEFAULT 0,
    duration_seconds    REAL,
    error_message       TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_reports_bid_agent
    ON agent_reports(bid_id, agent_name);

-- ============================================================
-- Bid Chat Messages (Phase 3 — Priority 1)
-- ============================================================

CREATE TABLE IF NOT EXISTS bid_chat_messages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bid_id              INTEGER NOT NULL REFERENCES active_bids(id),
    role                TEXT NOT NULL,
    content             TEXT NOT NULL,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bid_chat_bid ON bid_chat_messages(bid_id);

-- ============================================================
-- Bid Schedule of Values (Phase 4 — SOV Module)
-- ============================================================

CREATE TABLE IF NOT EXISTS bid_sov_item (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bid_id              INTEGER NOT NULL REFERENCES active_bids(id) ON DELETE CASCADE,
    item_number         TEXT,
    description         TEXT NOT NULL,
    quantity            REAL,
    unit                TEXT,
    owner_amount        REAL,
    cost_code           TEXT,
    discipline          TEXT,
    mapped_by           TEXT DEFAULT 'manual',
    unit_price          REAL,
    total_price         REAL,
    rate_source         TEXT,
    rate_confidence     TEXT,
    notes               TEXT,
    sort_order          INTEGER DEFAULT 0,
    pm_quantity         REAL,
    pm_unit             TEXT,
    quantity_status     TEXT DEFAULT 'pending',
    quantity_notes      TEXT,
    quantity_verified_at DATETIME,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bid_sov_bid ON bid_sov_item(bid_id);
CREATE INDEX IF NOT EXISTS idx_bid_sov_cost_code ON bid_sov_item(cost_code);

-- ============================================================
-- Bid Activities (Phase 4b — Activity-level estimating)
-- ============================================================

CREATE TABLE IF NOT EXISTS bid_activity (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bid_sov_item_id     INTEGER NOT NULL REFERENCES bid_sov_item(id) ON DELETE CASCADE,
    activity_number     TEXT,
    description         TEXT NOT NULL,
    quantity            REAL,
    unit                TEXT,
    unit_rate_mh        REAL,
    labor_rate          REAL,
    unit_price          REAL,
    total_price         REAL,
    cost_code           TEXT,
    discipline          TEXT,
    source              TEXT DEFAULT 'manual',
    confidence          TEXT,
    notes               TEXT,
    sort_order          INTEGER DEFAULT 0,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bid_activity_sov_item ON bid_activity(bid_sov_item_id);
CREATE INDEX IF NOT EXISTS idx_bid_activity_cost_code ON bid_activity(cost_code);
"""


def get_connection(db_path: Path = None) -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_1_0_to_1_1(conn: sqlite3.Connection) -> None:
    """Migrate schema from 1.0 to 1.1: add active bid document tables."""
    bid_tables_sql = """
    CREATE TABLE IF NOT EXISTS active_bids (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        bid_name            TEXT NOT NULL,
        bid_number          TEXT,
        owner               TEXT,
        general_contractor  TEXT,
        bid_date            DATE,
        project_type        TEXT,
        location            TEXT,
        estimated_value     REAL,
        status              TEXT DEFAULT 'active',
        notes               TEXT,
        is_focus            BOOLEAN DEFAULT FALSE,
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS bid_documents (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        bid_id              INTEGER NOT NULL REFERENCES active_bids(id),
        filename            TEXT NOT NULL,
        file_type           TEXT NOT NULL,
        file_size_bytes     INTEGER,
        doc_category        TEXT DEFAULT 'general',
        doc_label           TEXT,
        extraction_status   TEXT DEFAULT 'pending',
        extraction_warning  TEXT,
        page_count          INTEGER,
        word_count          INTEGER,
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS bid_document_chunks (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id         INTEGER NOT NULL REFERENCES bid_documents(id),
        bid_id              INTEGER NOT NULL REFERENCES active_bids(id),
        chunk_index         INTEGER NOT NULL,
        chunk_text          TEXT NOT NULL,
        section_heading     TEXT,
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_bid_documents_bid ON bid_documents(bid_id);
    CREATE INDEX IF NOT EXISTS idx_bid_chunks_bid ON bid_document_chunks(bid_id);
    CREATE INDEX IF NOT EXISTS idx_bid_chunks_document ON bid_document_chunks(document_id);
    """
    conn.executescript(bid_tables_sql)
    conn.execute("UPDATE schema_version SET version = '1.1'")


def _migrate_1_1_to_1_2(conn: sqlite3.Connection) -> None:
    """Migrate schema from 1.1 to 1.2: add agent_reports table."""
    agent_reports_sql = """
    CREATE TABLE IF NOT EXISTS agent_reports (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        bid_id              INTEGER NOT NULL REFERENCES active_bids(id),
        agent_name          TEXT NOT NULL,
        agent_version       TEXT NOT NULL DEFAULT '1.0',
        status              TEXT NOT NULL DEFAULT 'pending',
        report_json         TEXT,
        summary_text        TEXT,
        risk_rating         TEXT,
        flags_count         INTEGER DEFAULT 0,
        input_doc_count     INTEGER DEFAULT 0,
        input_chunk_count   INTEGER DEFAULT 0,
        tokens_used         INTEGER DEFAULT 0,
        duration_seconds    REAL,
        error_message       TEXT,
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_reports_bid_agent
        ON agent_reports(bid_id, agent_name);
    """
    conn.executescript(agent_reports_sql)
    conn.execute("UPDATE schema_version SET version = '1.2'")


def _migrate_1_2_to_1_3(conn: sqlite3.Connection) -> None:
    """Migrate schema from 1.2 to 1.3: add bid chat, document hashing, report diffing."""
    migration_sql = """
    CREATE TABLE IF NOT EXISTS bid_chat_messages (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        bid_id              INTEGER NOT NULL REFERENCES active_bids(id),
        role                TEXT NOT NULL,
        content             TEXT NOT NULL,
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_bid_chat_bid ON bid_chat_messages(bid_id);
    """
    conn.executescript(migration_sql)

    # Add new columns to existing tables (SQLite ADD COLUMN is safe if already exists)
    for col_sql in [
        "ALTER TABLE bid_documents ADD COLUMN file_hash TEXT",
        "ALTER TABLE bid_documents ADD COLUMN version INTEGER DEFAULT 1",
        "ALTER TABLE bid_documents ADD COLUMN supersedes_id INTEGER",
        "ALTER TABLE agent_reports ADD COLUMN documents_analyzed TEXT",
    ]:
        try:
            conn.execute(col_sql)
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.execute("UPDATE schema_version SET version = '1.3'")


def _migrate_1_3_to_1_4(conn: sqlite3.Connection) -> None:
    """Migrate schema from 1.3 to 1.4: add bid_sov_item table."""
    sov_sql = """
    CREATE TABLE IF NOT EXISTS bid_sov_item (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        bid_id              INTEGER NOT NULL REFERENCES active_bids(id) ON DELETE CASCADE,
        item_number         TEXT,
        description         TEXT NOT NULL,
        quantity            REAL,
        unit                TEXT,
        owner_amount        REAL,
        cost_code           TEXT,
        discipline          TEXT,
        mapped_by           TEXT DEFAULT 'manual',
        unit_price          REAL,
        total_price         REAL,
        rate_source         TEXT,
        rate_confidence     TEXT,
        notes               TEXT,
        sort_order          INTEGER DEFAULT 0,
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_bid_sov_bid ON bid_sov_item(bid_id);
    CREATE INDEX IF NOT EXISTS idx_bid_sov_cost_code ON bid_sov_item(cost_code);
    """
    conn.executescript(sov_sql)
    conn.execute("UPDATE schema_version SET version = '1.4'")


def _migrate_1_4_to_1_5(conn: sqlite3.Connection) -> None:
    """Migrate schema from 1.4 to 1.5: add PM quantity columns to bid_sov_item."""
    for col_sql in [
        "ALTER TABLE bid_sov_item ADD COLUMN pm_quantity REAL",
        "ALTER TABLE bid_sov_item ADD COLUMN pm_unit TEXT",
        "ALTER TABLE bid_sov_item ADD COLUMN quantity_status TEXT DEFAULT 'pending'",
        "ALTER TABLE bid_sov_item ADD COLUMN quantity_notes TEXT",
        "ALTER TABLE bid_sov_item ADD COLUMN quantity_verified_at DATETIME",
    ]:
        try:
            conn.execute(col_sql)
        except sqlite3.OperationalError:
            pass  # Column already exists
    conn.execute("UPDATE schema_version SET version = '1.5'")


def _migrate_1_5_to_1_6(conn: sqlite3.Connection) -> None:
    """Migrate schema from 1.5 to 1.6: add bid_activity table."""
    activity_sql = """
    CREATE TABLE IF NOT EXISTS bid_activity (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        bid_sov_item_id     INTEGER NOT NULL REFERENCES bid_sov_item(id) ON DELETE CASCADE,
        activity_number     TEXT,
        description         TEXT NOT NULL,
        quantity            REAL,
        unit                TEXT,
        unit_rate_mh        REAL,
        labor_rate          REAL,
        unit_price          REAL,
        total_price         REAL,
        cost_code           TEXT,
        discipline          TEXT,
        source              TEXT DEFAULT 'manual',
        confidence          TEXT,
        notes               TEXT,
        sort_order          INTEGER DEFAULT 0,
        created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_bid_activity_sov_item ON bid_activity(bid_sov_item_id);
    CREATE INDEX IF NOT EXISTS idx_bid_activity_cost_code ON bid_activity(cost_code);
    """
    conn.executescript(activity_sql)
    conn.execute("UPDATE schema_version SET version = '1.6'")


def _migrate_1_6_to_1_7(conn: sqlite3.Connection) -> None:
    """Migrate schema from 1.6 to 1.7: field intelligence rate cards.

    Changes:
    1. Add employee_code to hj_timecard (trade code like OE4)
    2. Create hj_equipment_entry table (equipment per cost code per day)
    3. Rework rate_item: drop budget-centric fields, add activity-level fields
    """
    # 1. Add employee_code to timecards
    for col_sql in [
        "ALTER TABLE hj_timecard ADD COLUMN employee_code TEXT",
    ]:
        try:
            conn.execute(col_sql)
        except sqlite3.OperationalError:
            pass

    # 2. Equipment entry table — one row per equipment per cost code per day
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS hj_equipment_entry (
        entry_id            INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_tc_id          TEXT,
        job_id              INTEGER NOT NULL REFERENCES job(job_id),
        cost_code           TEXT,
        date                DATE,
        equipment_id        TEXT,
        equipment_code      TEXT,
        equipment_desc      TEXT,
        hours               REAL,
        cost_code_id        TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_equip_entry_job ON hj_equipment_entry(job_id);
    CREATE INDEX IF NOT EXISTS idx_equip_entry_cc ON hj_equipment_entry(job_id, cost_code);
    """)

    # 3. Rework rate_item — add field intelligence columns
    for col_sql in [
        "ALTER TABLE rate_item ADD COLUMN timecard_count INTEGER DEFAULT 0",
        "ALTER TABLE rate_item ADD COLUMN work_days INTEGER DEFAULT 0",
        "ALTER TABLE rate_item ADD COLUMN crew_size_avg REAL",
        "ALTER TABLE rate_item ADD COLUMN daily_qty_avg REAL",
        "ALTER TABLE rate_item ADD COLUMN daily_qty_peak REAL",
        "ALTER TABLE rate_item ADD COLUMN total_hours REAL",
        "ALTER TABLE rate_item ADD COLUMN total_qty REAL",
        "ALTER TABLE rate_item ADD COLUMN total_labor_cost REAL",
        "ALTER TABLE rate_item ADD COLUMN total_equip_cost REAL",
        "ALTER TABLE rate_item ADD COLUMN crew_breakdown TEXT",
    ]:
        try:
            conn.execute(col_sql)
        except sqlite3.OperationalError:
            pass

    conn.execute("UPDATE schema_version SET version = '1.7'")


def _migrate_1_7_to_1_8(conn: sqlite3.Connection) -> None:
    """Migrate schema from 1.7 to 1.8: employees, pay items, forecasts, E360 timecards.

    New tables for data discovered via HCSS API endpoint probing (2026-03-09):
    1. hj_employee — full employee roster with trade codes
    2. hj_pay_item — contract pay items with quantities, prices, linked cost codes
    3. hj_forecast — job-level financial forecasts
    4. e360_timecard — equipment mechanic timecards (maintenance hours)
    """
    conn.executescript("""
    -- Employee roster from HeavyJob /api/v1/employees
    CREATE TABLE IF NOT EXISTS hj_employee (
        employee_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_id         TEXT UNIQUE,
        code            TEXT,
        first_name      TEXT,
        last_name       TEXT,
        middle_initial  TEXT,
        suffix          TEXT,
        nick_name       TEXT,
        email           TEXT,
        phone           TEXT,
        is_salaried     BOOLEAN DEFAULT FALSE,
        is_active       BOOLEAN DEFAULT TRUE,
        is_deleted      BOOLEAN DEFAULT FALSE,
        synced_at       DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_hj_employee_code ON hj_employee(code);
    CREATE INDEX IF NOT EXISTS idx_hj_employee_active ON hj_employee(is_active);

    -- Pay items from HeavyJob /api/v1/payItems
    CREATE TABLE IF NOT EXISTS hj_pay_item (
        pay_item_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_id         TEXT,
        job_id          INTEGER REFERENCES job(job_id),
        hcss_job_id     TEXT,
        pay_item        TEXT,
        description     TEXT,
        status          TEXT,
        owner_code      TEXT,
        contract_qty    REAL,
        unit            TEXT,
        unit_price      REAL,
        stop_overruns   BOOLEAN DEFAULT FALSE,
        linked_cost_codes TEXT,
        is_deleted      BOOLEAN DEFAULT FALSE,
        synced_at       DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_hj_pay_item_job ON hj_pay_item(job_id);
    CREATE INDEX IF NOT EXISTS idx_hj_pay_item_hcss_job ON hj_pay_item(hcss_job_id);

    -- Job forecasts from HeavyJob /api/v1/forecasts
    CREATE TABLE IF NOT EXISTS hj_forecast (
        forecast_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_id         TEXT,
        hcss_forecast_id TEXT,
        job_id          INTEGER REFERENCES job(job_id),
        job_code        TEXT,
        job_description TEXT,
        job_status      TEXT,
        forecast_date   DATE,
        forecast_status TEXT,
        to_date_total_cost   REAL,
        cost_to_completion   REAL,
        cost_at_completion   REAL,
        budget_total         REAL,
        variance             REAL,
        contract_revenue     REAL,
        to_date_revenue      REAL,
        revenue_to_completion REAL,
        forecast_revenue     REAL,
        margin_percent       REAL,
        markup_percent       REAL,
        create_date          DATETIME,
        synced_at            DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_hj_forecast_job ON hj_forecast(job_id);
    CREATE INDEX IF NOT EXISTS idx_hj_forecast_job_code ON hj_forecast(job_code);

    -- E360 equipment mechanic timecards from /api/v2/timecards
    CREATE TABLE IF NOT EXISTS e360_timecard (
        entry_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        hcss_id         TEXT,
        timecard_id     INTEGER,
        timecard_date   DATE,
        mechanic_id     INTEGER,
        mechanic_code   TEXT,
        payclass        TEXT,
        status          TEXT,
        approval_level1 TEXT,
        equipment_name  TEXT,
        equipment_code  TEXT,
        work_type       TEXT,
        work_code       TEXT,
        item_code       TEXT,
        regular_hours   REAL,
        overtime_hours  REAL,
        double_time_hours REAL,
        damage_related  BOOLEAN DEFAULT FALSE,
        on_site         BOOLEAN DEFAULT FALSE,
        synced_at       DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_e360_tc_date ON e360_timecard(timecard_date);
    CREATE INDEX IF NOT EXISTS idx_e360_tc_equip ON e360_timecard(equipment_name);
    CREATE INDEX IF NOT EXISTS idx_e360_tc_mechanic ON e360_timecard(mechanic_code);
    """)

    conn.execute("UPDATE schema_version SET version = '1.8'")


def _migrate_1_8_to_1_9(conn: sqlite3.Connection) -> None:
    """Migrate schema from 1.8 to 1.9: add trade code + foreman name to timecards.

    New columns on hj_timecard:
    1. pay_class_code — trade code (FORE, OPR1, LAB1) from payClassCode
    2. pay_class_desc — trade description (Foreman, Operator) from payClassDescription
    3. foreman_name — foreman description from foremanDescription
    """
    for col_sql in [
        "ALTER TABLE hj_timecard ADD COLUMN pay_class_code TEXT",
        "ALTER TABLE hj_timecard ADD COLUMN pay_class_desc TEXT",
        "ALTER TABLE hj_timecard ADD COLUMN foreman_name TEXT",
    ]:
        try:
            conn.execute(col_sql)
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.execute("UPDATE schema_version SET version = '1.9'")


def init_db(db_path: Path = None) -> None:
    """Create all tables and indexes from the schema.

    If the database already exists at an older schema version, runs
    the appropriate migration(s) to bring it up to date.
    """
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        # Record schema version
        existing = conn.execute("SELECT version FROM schema_version").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
        else:
            current = existing["version"]
            if current == "1.0":
                _migrate_1_0_to_1_1(conn)
                current = "1.1"
            if current == "1.1":
                _migrate_1_1_to_1_2(conn)
                current = "1.2"
            if current == "1.2":
                _migrate_1_2_to_1_3(conn)
                current = "1.3"
            if current == "1.3":
                _migrate_1_3_to_1_4(conn)
                current = "1.4"
            if current == "1.4":
                _migrate_1_4_to_1_5(conn)
                current = "1.5"
            if current == "1.5":
                _migrate_1_5_to_1_6(conn)
                current = "1.6"
            if current == "1.6":
                _migrate_1_6_to_1_7(conn)
                current = "1.7"
            if current == "1.7":
                _migrate_1_7_to_1_8(conn)
                current = "1.8"
            if current == "1.8":
                _migrate_1_8_to_1_9(conn)
        conn.commit()
        print(f"Database initialized at {db_path or DB_PATH} (schema v{SCHEMA_VERSION})")
    finally:
        conn.close()


def delete_project_cascade(project_id: int, db_path: Path = None) -> dict:
    """Delete a project and all its child records.

    Deletes in correct order to respect foreign key constraints.
    Returns dict with counts of deleted records per table.
    """
    conn = get_connection(db_path)
    try:
        deleted = {}
        # Child tables first (order matters for FK constraints)
        child_tables = [
            "general_conditions_breakdown",
            "lessons_learned",
            "subcontractors",
            "material_costs",
            "crew_configurations",
            "production_rates",
            "unit_costs",
            "cost_codes",
            "disciplines",
        ]
        for table in child_tables:
            cursor = conn.execute(
                f"DELETE FROM {table} WHERE project_id = ?", (project_id,)
            )
            deleted[table] = cursor.rowcount

        # Finally delete the project itself
        cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        deleted["projects"] = cursor.rowcount

        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_table_counts(db_path: Path = None) -> dict:
    """Return row counts for all tables."""
    conn = get_connection(db_path)
    try:
        tables = [
            "projects", "disciplines", "cost_codes", "unit_costs",
            "production_rates", "crew_configurations", "material_costs",
            "subcontractors", "lessons_learned", "benchmark_rates",
            "general_conditions_breakdown",
        ]
        counts = {}
        for table in tables:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            counts[table] = row["cnt"]
        return counts
    finally:
        conn.close()
