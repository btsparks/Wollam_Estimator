# WEIS v2 — Wollam Estimating Intelligence System

## What This Is
A stripped-down, focused rebuild of the Wollam Construction estimating tool. Two features, done right:

1. **PM Context Interview** — Project managers provide context about how cost codes were used on their jobs
2. **Diary Intelligence** — Import HeavyJob diary exports, AI-synthesize draft PM context from foreman notes
3. **Document Intelligence** — Upload project documents (change orders, KPIs, RFI logs, material tracking), AI enriches context
4. **Rate Settings & Cost Recalculation** — Import labor/equipment rates from HeavyJob, recast all historical costs at current rates
5. **AI Estimating Chat** — Estimators ask questions and get data-backed answers from historical HeavyJob actuals + PM context

The database contains real HCSS HeavyJob data: actual man-hours per unit, actual dollars per unit, crew compositions, equipment usage, and production rates across every project Wollam has tracked.

## Tech Stack
- **Language**: Python 3.13+
- **Database**: SQLite (single file at `data/db/weis.db`, schema v2.3) — already populated with HeavyJob data
- **Backend**: FastAPI (lightweight, async, serves both API and static files)
- **Frontend**: Single-page HTML app with vanilla JS + Tailwind CSS (CDN)
- **AI**: Anthropic Claude API (natural language queries against the database)
- **HCSS Integration**: Async httpx client for HeavyJob API sync (already built, in `app/hcss/`)
- **Data Validation**: Pydantic v2

## Project Structure
```
weis-v2/
├── app/
│   ├── __init__.py
│   ├── config.py           # Environment config (paths, API keys, DIARY_DIR)
│   ├── database.py         # SQLite schema v2.1 + connection management + migrations
│   ├── main.py             # FastAPI app entry point
│   ├── api/                # API route modules
│   │   ├── interview.py    # PM Context Interview endpoints
│   │   ├── chat.py         # AI Chat endpoints
│   │   ├── diary.py        # Diary import/synthesis endpoints
│   │   ├── documents.py    # Document upload/enrichment endpoints
│   │   └── settings.py     # Rate settings, import, and recast cost endpoints
│   ├── services/           # Business logic
│   │   ├── interview.py    # Interview flow logic (load job, present cost codes, save context)
│   │   ├── chat.py         # AI chat engine (query builder, context assembly, Claude API)
│   │   ├── diary_parser.py # HeavyJob diary .txt file parser (state machine)
│   │   ├── diary_import.py # Diary import + status/entries/summary queries
│   │   ├── diary_synthesis.py # AI synthesis of diary entries → PM/CC context (Claude Haiku)
│   │   ├── document_extract.py # Text extraction from PDF/Excel/CSV/TXT uploads
│   │   ├── document_enrichment.py # AI enrichment of context from uploaded documents
│   │   ├── rate_import.py  # Parse PayClass.txt + EquipmentSetup.txt from HeavyJob
│   │   └── cost_recalc.py  # Recast cost calculation engine (hours × current rates)
│   ├── hcss/               # HCSS API integration (CARRIED OVER — working)
│   │   ├── auth.py         # OAuth 2.0 client credentials
│   │   ├── client.py       # Base HTTP client (pagination, retry, rate limiting)
│   │   ├── heavyjob.py     # HeavyJob API wrapper + timecard flattener
│   │   ├── models.py       # Pydantic models for API responses
│   │   └── storage.py      # DB writers (upsert jobs, cost codes, timecards, rate cards)
│   └── transform/          # Data transformation (CARRIED OVER — working)
│       ├── calculator.py   # Field intelligence calculator (MH/unit, $/unit, confidence)
│       ├── rate_card.py    # Rate card generator from timecard data
│       └── mapper.py       # Cost code → discipline mapping (YAML-driven)
├── static/                 # Frontend assets
│   ├── index.html          # Single-page app shell
│   ├── styles.css          # Wollam design system tokens + components
│   └── app.js              # Frontend logic (routing, API calls, rendering)
├── Heavy Job Notes/        # HeavyJob diary export .txt files (11 files, ~181K lines)
├── config/
│   └── discipline_map.yaml # Cost code → discipline mapping rules (CARRIED OVER)
├── data/
│   ├── documents/          # Uploaded PM context documents (per job_id subfolder)
│   └── db/
│       └── weis.db         # SQLite database (schema v2.3, populated with HeavyJob + diary + rate data)
├── scripts/
│   └── sync_everything.py  # HCSS sync script (CARRIED OVER — working)
├── tests/                  # pytest tests
│   ├── test_interview.py   # Interview API tests
│   ├── test_diary.py       # Diary parser + API tests
│   ├── test_documents.py   # Document upload + extraction tests
│   └── test_settings.py    # Rate import, settings API, recast cost tests
├── docs/                   # Feature specs and architecture docs
│   ├── ARCHITECTURE.md     # Technical design
│   ├── PM_CONTEXT_INTERVIEW.md  # Feature spec
│   ├── AI_CHAT.md          # Feature spec
│   ├── DESIGN_SYSTEM.md    # Wollam visual design system (summary)
│   └── RESKIN_SKILL_REFERENCE.md  # Complete CSS/component specs (authoritative source)
├── .env                    # API keys (gitignored)
├── .env.example            # Template
├── requirements.txt        # Dependencies
└── CLAUDE.md               # This file
```

## What's Built
- **`app/hcss/`** — Complete HCSS HeavyJob API integration (OAuth, pagination, retry, rate limiting)
- **`app/transform/`** — Rate card generation, discipline mapping, field intelligence calculator
- **`app/database.py`** — Schema v2.3 with HeavyJob tables + diary_entry + job_document + pm_context/cc_context + labor_rate/equipment_rate
- **`app/config.py`** — Environment variable management
- **`app/main.py`** — FastAPI app with interview, chat, and diary routers
- **`app/api/interview.py`** — PM Context Interview endpoints
- **`app/api/diary.py`** — Diary import/synthesis endpoints
- **`app/services/interview.py`** — Interview flow logic
- **`app/services/diary_parser.py`** — HeavyJob diary .txt parser (state machine)
- **`app/services/diary_import.py`** — Diary import + status/entries/summary queries
- **`app/services/diary_synthesis.py`** — AI synthesis of diary entries → PM/CC context
- **`app/api/documents.py`** — Document upload/list/delete/enrich endpoints
- **`app/api/settings.py`** — Rate settings, import, coverage, recast cost endpoints
- **`app/services/document_extract.py`** — Text extraction from PDF/Excel/CSV/TXT
- **`app/services/document_enrichment.py`** — AI enrichment of context from uploaded documents
- **`app/services/rate_import.py`** — Parse PayClass.txt (34 labor rates) + EquipmentSetup.txt (1,318 equipment items)
- **`app/services/cost_recalc.py`** — Recast cost engine: actual hours × current loaded rates per cost code
- **`static/`** — Single-page frontend with interview + diary UI
- **`config/discipline_map.yaml`** — Cost code to discipline mapping rules
- **`scripts/sync_everything.py`** — Full HCSS data sync with adaptive concurrency

## What Needs To Be Built
1. **AI Estimating Chat** — see `docs/AI_CHAT.md`

## Database Overview

### HeavyJob Tables (the gold — actual field data)
| Table | What It Contains | Key Fields |
|-------|-----------------|------------|
| `job` | Every project tracked in HeavyJob | job_number, name, status |
| `hj_costcode` | Cost codes with budget AND actual values | code, description, unit, bgt_labor_hrs, act_labor_hrs, act_qty |
| `hj_timecard` | One row per employee per cost code per day | cost_code, hours, employee_name, pay_class_code, quantity |
| `hj_equipment_entry` | Equipment hours per cost code per day | equipment_code, hours |
| `hj_employee` | Employee roster with trade codes | code, first_name, last_name |
| `hj_pay_item` | Contract pay items linked to cost codes | pay_item, description, unit, unit_price |
| `hj_forecast` | Job-level financial forecasts | cost_at_completion, margin_percent |

### Rate Intelligence Tables (calculated from HeavyJob data)
| Table | What It Contains |
|-------|-----------------|
| `rate_card` | One card per job — summary of all calculated rates |
| `rate_item` | One item per cost code per job — MH/unit, $/unit, crew size, daily production, confidence |

### PM Context Tables
| Table | What It Contains |
|-------|-----------------|
| `pm_context` | PM-provided context per job (project_summary, site_conditions, key_challenges, key_successes, lessons_learned, source) |
| `cc_context` | PM-provided context per cost code (scope_included, scope_excluded, conditions, notes, source) |

### Diary Tables
| Table | What It Contains |
|-------|-----------------|
| `diary_entry` | Parsed HeavyJob diary notes — date, foreman, cost_code, company_note, inspector_note, quantity, unit |

### Document Tables
| Table | What It Contains |
|-------|-----------------|
| `job_document` | Uploaded PM documents — filename, doc_type, extracted_text, analyzed flag, file stored in data/documents/{job_id}/ |

### Rate & Cost Tables
| Table | What It Contains |
|-------|-----------------|
| `labor_rate` | Pay class rates from HeavyJob — base_rate, tax_pct, fringe, loaded_rate (base + tax + fringe). 34 pay classes. |
| `equipment_rate` | Equipment rates from HeavyJob — equipment_code, base_rate, group_name. 1,318 items in 48 groups. |

## Key Data Relationships
```
job (1) ──→ (many) hj_costcode    — cost codes for a project
job (1) ──→ (many) hj_timecard    — daily timecard entries
job (1) ──→ (1)    rate_card      — calculated rate intelligence
rate_card (1) ──→ (many) rate_item — per-cost-code rates
job (1) ──→ (1)    pm_context     — PM's project-level context
hj_costcode (1) ──→ (0..1) cc_context — PM's cost-code-level context
```

## Development Commands
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate      # Mac/Linux
# .venv\Scripts\activate       # Windows

# Install dependencies
pip install -r requirements.txt

# Run the app (FastAPI with auto-reload)
uvicorn app.main:app --reload --port 8000

# Run tests
pytest tests/

# Sync HeavyJob data (requires HCSS credentials)
python scripts/sync_everything.py
```

## Non-Negotiable Rules
1. **Every rate must cite its source** — job number, cost code, confidence level
2. **No hallucination** — if data doesn't exist, say "no data available"
3. **PM context is separate from raw data** — PM notes enrich but never overwrite actuals
4. **Database is the single source of truth** — all queries go through SQLite
5. **Keep it simple** — two features, done well. No feature creep.
6. **Match the Wollam design system** — see `docs/DESIGN_SYSTEM.md` for brand standards and `docs/RESKIN_SKILL_REFERENCE.md` for the complete CSS/component specs (this is the authoritative source for Wollam's cross-product visual identity — every color, shadow, animation, and component pattern is defined there)

## Autonomy Rules for Claude Code
- Make changes directly without asking for confirmation
- Do not pause mid-task to ask "should I continue?" — always continue
- Complete all steps of a task in a single run before reporting back
- After making code changes, run `pytest tests/` automatically
- If tests fail, fix them before considering the task done
- Make small, focused commits with clear messages

## Environment Setup
- Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`
- HCSS credentials (`HCSS_CLIENT_ID`, `HCSS_CLIENT_SECRET`) needed only for data sync
- Database is pre-populated — no sync needed to start development
