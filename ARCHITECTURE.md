# WEIS — Technical Architecture
## Wollam Estimating Intelligence System

---

## Architectural Philosophy

The system is designed around one principle: **the data is the asset, everything else is interface.**

The historical job cost data — production rates, unit costs, crew configurations, lessons learned — is what makes this system distinctly Wollam. The database, the AI layer, and the UI are all just ways of accessing and presenting that asset. Architectural decisions should protect the data layer's integrity and make it as easy as possible to enrich over time.

**Three layers, built in sequence:**

```
┌─────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                │
│         Dashboard UI / Chat Interface / Reports      │
├─────────────────────────────────────────────────────┤
│                  INTELLIGENCE LAYER                  │
│      Claude API / Agent Orchestration / Queries      │
├─────────────────────────────────────────────────────┤
│                     DATA LAYER                       │
│          SQLite DB / JCD Files / Document Store      │
└─────────────────────────────────────────────────────┘
```

Build bottom-up. Do not build the presentation layer until the data layer is solid.

---

## Phase 1 Architecture (MVP)

### Overview

```
JCD Markdown Files
       │
       ▼
┌─────────────┐
│  Ingestion  │  Python scripts parse JCD markdown
│   Scripts   │  and populate the SQLite database
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   SQLite    │  Structured storage for all historical
│  Database   │  job cost data, rates, and lessons learned
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────┐
│   Query     │────▶│  Claude API  │  Natural language
│   Engine    │◀────│              │  translation layer
└──────┬──────┘     └──────────────┘
       │
       ▼
┌─────────────┐
│     CLI     │  Terminal interface for Phase 1
│  Interface  │  Streamlit upgrade path for Phase 2
└─────────────┘
```

### Data Flow — Ingestion

```
1. PM catalogs completed job using Cataloger Agent (separate process)
2. Cataloger produces JCD markdown files by discipline
3. JCD files placed in /data/jcd/ directory
4. ingest_jcd.py script parses markdown and extracts structured data
5. Data validated before insertion
6. Records written to SQLite tables
7. Validation report generated confirming coverage
```

### Data Flow — Query

```
1. User types plain English question in chat interface
2. Query engine sends question + database schema context to Claude API
3. Claude determines query type and generates appropriate database query
4. Database returns relevant records
5. Claude formats response with source citations
6. Response displayed to user with job#, cost code, discipline, confidence
```

---

## Phase 2 Architecture (Conversation Layer + Basic UI)

When Phase 1 is proven, Phase 2 adds:

```
┌────────────────────────────────────────────────────────┐
│                   STREAMLIT WEB APP                    │
│    ┌──────────────┐        ┌───────────────────────┐   │
│    │   Chat Panel │        │   Project Status Panel │   │
│    │              │        │   (simple, Phase 2)   │   │
│    └──────────────┘        └───────────────────────┘   │
└────────────────────────────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
     ┌──────────────┐       ┌──────────────────┐
     │  Historical  │       │  Active Project  │
     │  Data Query  │       │  Document Store  │
     │  (SQLite)    │       │  (RFP files,     │
     └──────────────┘       │   addenda, RFIs) │
                            └──────────────────┘
```

The Phase 2 document store holds the *current bid's* living document set — RFP package, addenda, RFI log — separate from the historical database.

---

## Phase 3 Architecture (Command Center + Agents)

Full architecture with agent orchestration:

```
┌─────────────────────────────────────────────────────────────┐
│                    WEIS APPLICATION                         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              COMMAND CENTER DASHBOARD                │   │
│  │   Estimate Status │ Agent Lanes │ Decision Queue     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │               CONVERSATION LAYER                    │   │
│  │         Chat Interface │ Context-Aware Queries      │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  INTELLIGENCE LAYER                         │
│                                                             │
│  Chief Estimator Agent (Orchestrator)                       │
│       │                                                     │
│       ├── Legal/Contract Agent                              │
│       ├── Quality Manager Agent                             │
│       ├── Safety Manager Agent                              │
│       ├── Takeoff Engineer Agent                            │
│       ├── Estimator Agent(s)                                │
│       ├── Subcontract/Procurement Agent                     │
│       ├── Scheduler Agent                                   │
│       ├── Shadow PM Agent                                   │
│       └── Document Control Agent                           │
│                                                             │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                     DATA LAYER                              │
│                                                             │
│  ┌─────────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Historical DB  │  │  Active Bid  │  │  Document    │  │
│  │  (SQLite/PG)    │  │  Database    │  │  Store       │  │
│  │  Job cost data  │  │  Current     │  │  RFP files   │  │
│  │  Rates, crews   │  │  estimate    │  │  Addenda     │  │
│  │  Lessons        │  │  state       │  │  RFI log     │  │
│  └─────────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Strategy

### Phase 1: SQLite
- Single file database
- Runs locally, no server
- Sufficient for current data volume (handful of jobs)
- Easy to inspect, back up, and version control

### Phase 2+: Consider migration to PostgreSQL when:
- More than 20 jobs cataloged
- Multi-user access required
- Cloud deployment needed
- Performance issues with SQLite

Migration path is straightforward — the schema is identical, only the connection string changes.

---

## AI Integration Strategy

### Claude API Usage

The Claude API is used for two purposes:

**1. Natural Language → Query Translation**
User asks a plain English question. Claude translates it to either:
- A SQL query against the historical database
- A semantic search over document content
- A combination of both

Claude is given the database schema as context so it generates valid queries.

**2. Response Formatting**
Raw database results are passed back to Claude for formatting into a clear, cited, human-readable response.

### Context Management

Each query includes:
- The user's question
- The database schema (always)
- Relevant schema sections (based on query type)
- Active project context if in bid mode (Phase 2+)

### API Key Management
- Store API key in `.env` file, never in code
- `.env` is in `.gitignore`
- Use `python-dotenv` for loading

---

## File Structure — Full

```
weis/
├── README.md
├── VISION.md
├── MVP_SPEC.md
├── ARCHITECTURE.md
├── DATA_SCHEMA.md
├── AGENTS.md
├── ROADMAP.md
├── requirements.txt
├── .env.example              # Template for API key setup
├── .gitignore
│
├── data/
│   ├── jcd/                  # Source JCD markdown files
│   │   ├── JCD_8553_EARTHWORK_SECTION.md
│   │   ├── JCD_8553_CONCRETE_SECTION.md
│   │   ├── JCD_8553_STEEL_SECTION.md
│   │   ├── JCD_8553_PIPING_SECTION.md
│   │   ├── JCD_8553_MECHANICAL_SECTION.md
│   │   ├── JCD_8553_ELECTRICAL_SECTION.md
│   │   ├── JCD_8553_BUILDING_SECTION.md
│   │   ├── JCD_8553_GCONDITIONS_SECTION.md
│   │   └── JCD_8553_MASTER_SUMMARY.md
│   └── db/
│       └── weis.db           # SQLite database (generated)
│
├── scripts/
│   ├── ingest_jcd.py         # Parse JCD markdown → database
│   ├── seed_db.py            # Initialize and seed database
│   ├── validate_db.py        # Run data quality report
│   └── test_queries.py       # Test suite for query layer
│
├── app/
│   ├── main.py               # Entry point
│   ├── database.py           # Database connection and helpers
│   ├── query_engine.py       # Natural language → query translation
│   ├── response_formatter.py # Format results with citations
│   ├── chat.py               # CLI/Streamlit interface
│   └── config.py             # Configuration management
│
└── tests/
    ├── test_ingestion.py
    ├── test_queries.py
    └── fixtures/             # Sample JCD snippets for testing
```

---

## Non-Negotiable Constraints

1. **Every rate recommendation must cite its source** — job number, cost code, discipline, and whether it's budget or actual.

2. **Confidence indicators are required** — HIGH (multiple sources), MEDIUM (single source, validated), LOW (single source, limited conditions), ASSUMPTION (no data, using benchmark).

3. **The system must say "I don't know"** — If data doesn't support an answer, the system must say so clearly rather than hallucinate a number.

4. **No data leaves the system** — All processing happens locally or via the Anthropic API. No project data goes to third-party services.

5. **Schema changes are versioned** — Any change to the database schema must include a migration script.

---

*WEIS Architecture Document v1.0*
