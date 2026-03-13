# WEIS v2 — Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    BROWSER (Single-Page App)                 │
│  ┌──────────────┐  ┌──────────────────────────────────────┐ │
│  │  Navy Sidebar │  │  Content Area                        │ │
│  │              │  │  ┌─────────────────────────────────┐ │ │
│  │  • Interview │  │  │  PM Context Interview            │ │ │
│  │  • AI Chat   │  │  │  — or —                          │ │ │
│  │              │  │  │  AI Estimating Chat               │ │ │
│  │              │  │  └─────────────────────────────────┘ │ │
│  └──────────────┘  └──────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                    HTTP/JSON API calls
                              │
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (:8000)                    │
│                                                              │
│  ┌──────────────────────┐  ┌─────────────────────────────┐  │
│  │  /api/interview/*    │  │  /api/chat/*                │  │
│  │  - GET  /jobs        │  │  - POST /message            │  │
│  │  - GET  /job/{id}    │  │  - GET  /history            │  │
│  │  - POST /context     │  │  - GET  /conversations      │  │
│  │  - GET  /progress    │  │                             │  │
│  └──────────┬───────────┘  └──────────────┬──────────────┘  │
│             │                              │                 │
│  ┌──────────▼───────────┐  ┌──────────────▼──────────────┐  │
│  │  Interview Service   │  │  Chat Service               │  │
│  │  - Load job data     │  │  - Build context from DB    │  │
│  │  - Present cost codes│  │  - Call Claude API          │  │
│  │  - Save PM context   │  │  - Format response          │  │
│  │  - Track completion  │  │  - Cite sources             │  │
│  └──────────┬───────────┘  └──────────────┬──────────────┘  │
│             │                              │                 │
│  ┌──────────▼──────────────────────────────▼──────────────┐  │
│  │                   SQLite Database                       │  │
│  │  data/db/weis.db (schema v1.9 + new PM context tables) │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  HCSS Sync (scripts/sync_everything.py)                │  │
│  │  Runs on-demand to pull fresh data from HeavyJob API   │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## Tech Choices

### Why FastAPI (not Streamlit, not NiceGUI)
- **Separation of concerns** — backend logic separate from UI rendering
- **Standard REST API** — easy to test, easy to extend
- **Static file serving** — serves the HTML/CSS/JS frontend directly
- **Async support** — matches the existing async HCSS client
- **No framework lock-in** — frontend is plain HTML, replaceable without touching backend

### Why Vanilla HTML/JS + Tailwind (not React, not Vue)
- **Zero build step** — no webpack, no npm, no node_modules
- **Tailwind via CDN** — one `<script>` tag, instant styling
- **Simple state** — two pages, no complex routing needed
- **Fast iteration** — edit HTML, refresh browser
- **Design system control** — CSS custom properties for Wollam brand tokens, Tailwind for layout

### Why SQLite (kept from v1)
- **Already populated** — 60+ jobs, thousands of cost codes, hundreds of thousands of timecards
- **Single file** — easy to backup, version, copy
- **No server** — works offline, no Docker, no config
- **Fast enough** — all queries are simple aggregations, sub-second response

## API Design

### Interview Endpoints

```
GET  /api/interview/jobs
  → List all jobs with completion status (has PM context or not)

GET  /api/interview/job/{job_id}
  → Job detail + all cost codes + existing PM context (if any)

POST /api/interview/context
  → Save PM context for a cost code or job-level note
  Body: {job_id, cost_code?, context_type, text}

GET  /api/interview/progress
  → Overall stats: jobs with context, cost codes with context, % coverage
```

### Chat Endpoints

```
POST /api/chat/message
  → Send a message, get AI response
  Body: {message, conversation_id?}
  Response: {response, sources: [{job, cost_code, rate, confidence}], conversation_id}

GET  /api/chat/conversations
  → List all saved conversations

GET  /api/chat/history/{conversation_id}
  → Get messages for a conversation
```

### Static Files

```
GET /                → Serves static/index.html
GET /static/*        → Serves CSS, JS, assets
```

## Database Changes (v2.0 migration)

Add two new tables to the existing v1.9 schema:

```sql
-- PM-provided context at the job level
CREATE TABLE IF NOT EXISTS pm_context (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL REFERENCES job(job_id),
    pm_name         TEXT,
    project_summary TEXT,          -- PM's overview: what was this job about?
    site_conditions TEXT,          -- Access, terrain, weather, restrictions
    key_challenges  TEXT,          -- What made this job hard?
    key_successes   TEXT,          -- What went well?
    lessons_learned TEXT,          -- What would you do differently?
    general_notes   TEXT,          -- Anything else
    completed_at    DATETIME,      -- When the PM finished the interview
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id)
);

-- PM-provided context at the cost code level
CREATE TABLE IF NOT EXISTS cc_context (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL REFERENCES job(job_id),
    cost_code       TEXT NOT NULL,  -- The 4-digit code (e.g., '2215')
    description_override TEXT,      -- PM can clarify what this code really tracked
    scope_included  TEXT,           -- What work is included in this code
    scope_excluded  TEXT,           -- What is NOT included (common confusion)
    related_codes   TEXT,           -- Other codes that work together (JSON array)
    conditions      TEXT,           -- Conditions that affected this code's production
    notes           TEXT,           -- General PM notes
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id, cost_code)
);

-- Chat conversation persistence
CREATE TABLE IF NOT EXISTS chat_conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT,           -- Auto-generated from first message
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id),
    role            TEXT NOT NULL,  -- 'user' or 'assistant'
    content         TEXT NOT NULL,
    sources_json    TEXT,           -- JSON array of cited sources
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## AI Chat — Context Assembly Strategy

When an estimator asks a question, the Chat Service builds a context package from the database before calling Claude:

```
1. Parse the question for intent signals:
   - Discipline keywords (concrete, steel, piping, earthwork, electrical)
   - Activity keywords (forming, rebar, excavation, erection)
   - Rate type (MH/unit, $/unit, crew size, production rate)
   - Specific job references (job 8553, "the pump station")

2. Query the database for relevant data:
   - rate_item table: actual MH/unit, $/unit, confidence, crew breakdown
   - hj_costcode table: budget vs actual quantities, hours, costs
   - cc_context table: PM's explanation of what the cost code covers
   - pm_context table: job-level conditions, challenges, lessons

3. Assemble into a structured context block:
   - "Here are the relevant historical rates from Wollam's field data..."
   - Include confidence levels and data richness indicators
   - Include PM context where available
   - Flag where data is thin or missing

4. Send to Claude with the estimator agent system prompt:
   - System prompt defines the Estimator Agent persona
   - Context block provides the data
   - User message is the estimator's question

5. Return response with source citations:
   - Every rate cited with job number, cost code, confidence
   - Clearly marked where PM context influenced the answer
   - Flagged where data is limited
```

## File Organization Principles

- **One module = one responsibility** — no god files
- **Services contain business logic** — API routes are thin wrappers
- **Frontend is static** — no server-side rendering, no template complexity
- **Tests mirror source structure** — `tests/test_api_interview.py` tests `app/api/interview.py`
- **Docs are specs** — each feature has one comprehensive spec document
