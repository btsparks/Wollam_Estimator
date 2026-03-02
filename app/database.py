"""WEIS database connection and schema management."""

import sqlite3
from pathlib import Path
from app.config import DB_PATH

SCHEMA_VERSION = "1.2"

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
