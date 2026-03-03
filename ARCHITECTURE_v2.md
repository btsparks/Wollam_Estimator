# WEIS — Technical Architecture
## Wollam Estimating Intelligence System

---

## Architectural Philosophy

The system is designed around one principle: **the data is the asset, everything else is interface.**

The historical job cost data — production rates, unit costs, crew configurations, lessons learned — is what makes this system distinctly Wollam. The HCSS APIs, the database, the AI layer, and the UI are all just ways of accessing, transforming, and presenting that asset. Architectural decisions protect the data layer's integrity and make it as easy as possible to enrich over time.

---

## System Architecture (v2.0)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         HCSS SYSTEMS                                │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   Identity   │    │   HeavyJob   │    │   HeavyBid   │          │
│  │   (OAuth)    │    │   (Actuals)  │    │  (Estimates)  │          │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘          │
│         │                   │                   │                   │
└─────────┼───────────────────┼───────────────────┼───────────────────┘
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      HCSS CLIENT MODULE                             │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐               │
│  │  Auth     │   │  HeavyJob    │   │  HeavyBid    │               │
│  │  Manager  │   │  API Wrapper │   │  API Wrapper  │               │
│  └──────────┘   └──────────────┘   └──────────────┘               │
│                                                                     │
│  Handles: Authentication, pagination, rate limiting, error retry    │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       DATABASE (SQLite v2.0)                        │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    RAW DATA LAYER                            │   │
│  │                                                              │   │
│  │  BUSINESS_UNIT │ JOB │ HJ_COSTCODE │ HJ_TIMECARD            │   │
│  │  HB_ESTIMATE │ HB_BIDITEM │ HB_ACTIVITY │ HB_RESOURCE       │   │
│  │  SYNC_METADATA                                               │   │
│  │                                                              │   │
│  │  Mirror of HCSS data. No interpretation. Source of truth.    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                             │                                       │
│                    Transformation Layer                              │
│                             │                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                  TRANSFORMED DATA LAYER                      │   │
│  │                                                              │   │
│  │  RATE_CARD │ RATE_ITEM │ CREW_CONFIG │ LESSON_LEARNED        │   │
│  │                                                              │   │
│  │  Calculated rates, flagged variances, PM-reviewed data.      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                             │                                       │
│                     Aggregation Layer                                │
│                             │                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                 ESTIMATOR KNOWLEDGE BASE                     │   │
│  │                                                              │   │
│  │  RATE_LIBRARY │ BENCHMARK                                    │   │
│  │                                                              │   │
│  │  Multi-job aggregated rates, statistical benchmarks.         │   │
│  │  This is what agents query.                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     INTELLIGENCE LAYER                               │
│                                                                     │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐           │
│  │  Claude API  │   │  Agent       │   │  Query       │           │
│  │  (NL→SQL)    │   │  Orchestrator│   │  Engine      │           │
│  └──────────────┘   └──────────────┘   └──────────────┘           │
│                                                                     │
│  Natural language translation, agent coordination, data retrieval   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     PRESENTATION LAYER                               │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐               │
│  │   CLI    │   │  Streamlit   │   │  PM Interview │               │
│  │          │   │  Dashboard   │   │  Interface    │               │
│  └──────────┘   └──────────────┘   └──────────────┘               │
│                                                                     │
│  Multiple interfaces, same data layer. Build bottom-up.             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow — Ingestion (API-Driven)

```
1. Sync triggered (manual or scheduled)
2. HCSS Auth module obtains bearer token (client_credentials grant)
3. HeavyJob wrapper pulls all closed jobs for business unit
4. For each job: cost codes, hours, timecards, change orders, materials, subs
5. HeavyBid wrapper pulls matching estimate (by job number)
6. For each estimate: bid items, activities, resources, materials
7. Raw data stored in database (raw layer)
8. Transformation layer generates rate card (budget/actual/recommended rates)
9. Rate card flagged for PM review (pending_review status)
10. PM completes interview → rate card marked approved
11. Approved rates aggregated into knowledge base (rate library + benchmarks)
```

## Data Flow — Ingestion (Legacy JCD)

The manual JCD process remains as a fallback and as the validation standard:

```
1. PM catalogs completed job using Cataloger Agent
2. Cataloger produces JCD markdown files by discipline
3. JCD files parsed by ingest_jcd.py → database (transformed layer)
4. Manually cataloged data is marked with source="jcd_manual"
5. When API data becomes available for same job, API data takes precedence
```

## Data Flow — Query

```
1. User types plain English question in any interface (CLI, Streamlit, chat)
2. Query engine sends question + database schema context to Claude API
3. Claude determines query type and generates appropriate database query
4. Query runs against knowledge base (aggregated) or rate cards (per-job)
5. Claude formats response with source citations (job#, cost code, confidence)
6. Response displayed with rate, unit, source job(s), and confidence indicator
```

---

## Key Architectural Decisions

### 1. Three-Tier Database Over Flat Tables

**Decision:** Separate raw HCSS data, transformed rate cards, and aggregated knowledge base into distinct tiers within a single SQLite database.

**Why:** Raw data must be preserved exactly as received from HCSS for auditability. Transformation logic can be re-run if calculation methods improve. The knowledge base is the query layer — it contains the pre-computed answers that agents need.

**Tradeoff:** More complex schema, but each tier has a clear purpose and can be updated independently.

### 2. HCSS API Over Manual Exports

**Decision:** Connect directly to HCSS HeavyJob and HeavyBid APIs for data extraction.

**Why:** Manual export of 6 reports per job takes 3-4 hours and depends on one person knowing the exact export settings. API extraction is programmatic, repeatable, and can process all closed jobs in bulk.

**Tradeoff:** Requires API credentials (pending), adds external dependency. Mitigated by retaining the manual JCD process as fallback.

### 3. SQLite Over PostgreSQL (For Now)

**Decision:** Continue with SQLite for v2.0. Plan migration path to PostgreSQL.

**When to migrate:**
- More than 50 jobs cataloged
- Multi-user concurrent access required
- Cloud deployment needed
- Performance issues observed

Migration is straightforward — the schema is identical, only the connection layer changes.

### 4. Pydantic Models for API Responses

**Decision:** Use Pydantic data models to validate and type all HCSS API responses.

**Why:** HCSS API response schemas are not guaranteed to be stable. Pydantic catches schema changes at the deserialization boundary rather than deep in business logic. Also provides IDE autocompletion and documentation.

### 5. PM Interview as Required Step

**Decision:** Auto-generated rate cards are flagged `pending_review`. They require PM input before rates enter the knowledge base.

**Why:** Numbers without context are dangerous. A cost code that ran 40% over budget might be a scope change (not a problem), an estimating error (adjust the rate), or a one-time condition (note it, don't change the rate). Only the PM knows which.

### 6. Cost Code Mapping via Configuration

**Decision:** Cost code → discipline mapping is defined in `discipline_map.yaml`, not hard-coded.

**Why:** Wollam's cost code structure is not perfectly consistent across all jobs. The mapping configuration can be adjusted as new patterns are encountered without code changes. AI-assisted interpretation handles edge cases.

---

## Authentication & Security

### HCSS API Authentication
- OAuth 2.0 client credentials flow
- Bearer token with ~1 hour expiry
- Token refresh handled automatically (5-minute buffer before expiry)
- Client ID and secret stored as environment variables, never in source code

### API Rate Limiting
- Pagination handled by client (100 records/page default)
- Retry logic with exponential backoff for transient failures
- Sync operations are idempotent — safe to re-run

---

## Technology Stack

| Component | Technology | Notes |
|-----------|------------|-------|
| Language | Python 3.11+ | Async support for API calls |
| Database | SQLite (→ PostgreSQL) | Single file, local, no server |
| API Client | httpx (async) | Modern async HTTP client |
| Data Models | Pydantic v2 | API response validation |
| AI Layer | Claude API (Anthropic) | Natural language processing |
| Web UI | Streamlit | Rapid prototyping, no frontend build |
| CLI | Click or argparse | Developer/power-user interface |
| Configuration | YAML | Human-readable config files |
| Testing | pytest + mock data | Validate against known JCD outputs |

---

## Module Responsibilities

### HCSS Client Module (`app/hcss/`)
- OAuth token lifecycle management
- Authenticated GET/POST requests with pagination
- HeavyJob endpoint wrappers (jobs, cost codes, hours, timecards, COs, materials, subs)
- HeavyBid endpoint wrappers (estimates, bid items, activities, resources, materials)
- Pydantic response models

### Transformation Module (`app/transform/`)
- Cost code → discipline mapping (configurable)
- Unit cost calculation (budget and actual $/unit, MH/unit)
- Production rate extraction from timecard data
- Recommended rate calculation (weighted between budget and actual)
- Confidence assessment (strong/moderate/limited/none)
- Variance flagging (>20% threshold)
- Rate card assembly

### Catalog Module (`app/catalog/`)
- PM interview workflow (auto-generated questions from rate card variances)
- Lessons learned capture and indexing
- Rate card review/approval flow
- Export to markdown, Excel, or other formats

### Sync Orchestrator (`app/hcss/sync.py`)
- Full sync: all closed jobs
- Incremental sync: jobs modified since last sync
- Job-to-estimate matching (by job number)
- Error handling and sync status reporting

### Agent Module (`app/agents/`)
- 10 functional agents (see AGENTS.md)
- Chief Estimator orchestration
- Query interface to knowledge base
- Built incrementally after data layer is proven

---

## Migration Strategy (v1.3 → v2.0)

### What Stays
- Existing SQLite database (v1.3) remains operational
- All 6 existing agents continue to function
- CLI and Streamlit interfaces unchanged
- JCD files preserved as reference documents

### What Changes
- Database schema extended with raw data tables and knowledge base tables
- New HCSS module added alongside existing code
- Transformation module replaces manual JCD parsing for new jobs
- PM interview module added to catalog workflow

### Migration Steps
1. Create v2.0 schema tables alongside v1.3 tables (non-destructive)
2. Run `migrate_v2.py` to populate raw layer from existing JCD data where possible
3. Generate rate cards from migrated data
4. Validate rate cards match existing JCD outputs (Jobs 8553, 8576)
5. Once validated, new jobs enter through API pipeline
6. Legacy JCD pipeline remains as fallback

---

*WEIS Architecture v2.0*
*Last Updated: March 2026*
