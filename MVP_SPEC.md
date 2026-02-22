# WEIS — MVP Specification
## Phase 1: Data Layer + Conversation Interface

---

## MVP Scope Statement

**Build the minimum system that proves the core value proposition: Wollam's historical project data, stored in a structured database, queryable by any team member in plain English.**

Nothing more. Nothing less.

The MVP does not include: a dashboard UI, workflow management, agent orchestration, RFP intake, or proposal generation. Those come later. The MVP is the foundation everything else is built on.

---

## MVP Success Criteria

The MVP is complete when the following is true:

1. All existing JCD documents from Job 8553 are stored in a structured database
2. A user can ask a plain English question and receive a sourced answer from that data
3. Answers cite the source job, cost code, and discipline
4. The interface is simple enough that a non-technical user can operate it
5. New JCD data can be added without breaking existing queries

---

## What Gets Built

### Component 1: Database

A structured SQLite database that stores all JCD data in queryable tables. SQLite is chosen for Phase 1 because:
- No server setup required
- Single file, easy to back up and version
- More than sufficient for the data volume
- Easy to migrate to Postgres later if needed

The database must store:
- Project metadata (job number, name, owner, type, location, dates)
- Cost codes with budget and actual costs and manhours
- Unit cost records (activity, unit, budget rate, actual rate, recommended rate)
- Production rates (activity, unit, MH/unit or units/hour, crew size)
- Crew configurations (activity, crew composition, equipment)
- Material costs (material type, vendor, unit, cost)
- Subcontractor costs (scope, sub name, cost, unit cost)
- Lessons learned (discipline, category, description, impact)

Full schema in DATA_SCHEMA.md.

### Component 2: JCD Ingestion Scripts

Python scripts that parse existing JCD markdown files and populate the database. These scripts must:
- Parse the structured markdown format from the Cataloger Agent output
- Extract all tables and data points
- Validate data before insertion (no orphaned records, no missing required fields)
- Log what was ingested and flag what couldn't be parsed
- Be idempotent (running twice doesn't create duplicate records)

### Component 3: Conversation Interface

A simple terminal-based or minimal web chat interface where a user types a question and receives an answer sourced from the database.

**Interface requirements:**
- Plain English input
- Response includes the answer, the source job(s), the cost code(s), and a confidence indicator
- If data is insufficient, the system says so clearly rather than guessing
- Response time under 10 seconds
- Runs locally — no internet dependency for queries (AI call excepted)

**Example interactions the MVP must handle:**

```
User: What did we pay for 20-inch flanged joints?
WEIS: On Job 8553 (RTK SPD Pump Station), 20-28" flanged joints were 
      estimated at 7 MH/joint. [Cost Code 27xx, Piping JCD] 
      Confidence: HIGH — single source, validated actual data.

User: What was the concrete material cost per CY?
WEIS: On Job 8553, concrete material cost $205/CY (budget) with 
      an all-in cost of $867/CY including forming, rebar, and placement. 
      [Cost Code 33xx, Concrete JCD]
      Confidence: HIGH — validated against Foundation actuals.

User: What crew did we use for mat pours?
WEIS: On Job 8553, mat pours used a 3-pump setup. Production rate was 
      0.15 MH/CY. [Cost Code 23xx, Concrete JCD — Crew & Equipment section]
      Confidence: MEDIUM — crew detail available but limited to one project.

User: What was the electrical cost per square foot?
WEIS: On Job 8553, electrical subcontractor cost $136/SF for heavy industrial work. 
      [Cost Code 41xx, Electrical JCD]
      Confidence: MEDIUM — single project, heavy industrial classification only.
```

### Component 4: Basic Data Validation Report

A script that runs against the database and produces a simple report:
- How many projects are in the database
- How many unit cost records by discipline
- What disciplines have coverage
- What disciplines have gaps
- Any data quality flags (missing units, outlier rates, etc.)

---

## What the MVP Explicitly Does NOT Include

- Web UI dashboard
- Workflow management or task tracking
- Agent orchestration
- RFP document intake or processing
- Subcontractor RFQ generation
- Proposal writing
- Multi-user authentication
- Cloud deployment
- Integration with Heavy Job, Foundation, or Heavy Bid

These are Phase 2+ features. Do not build them in Phase 1.

---

## Technology Stack — Phase 1

| Component | Choice | Reason |
|-----------|--------|--------|
| Database | SQLite | Simple, local, no server |
| Language | Python 3.11+ | Broad library support, easy iteration |
| AI Layer | Anthropic Claude API | Handles natural language → SQL or semantic query |
| Interface | Terminal CLI or simple Streamlit | Fast to build, no frontend complexity |
| Data Format | Markdown (JCD source), SQLite (stored) | Existing JCD format preserved |

**On the interface choice:** Start with a terminal CLI. If it proves too unfriendly after initial testing, upgrade to a minimal Streamlit web interface. Do not build a custom web frontend in Phase 1.

---

## Data Available for Phase 1

### Job 8553 — RTK SPD Pump Station (COMPLETE)
All eight JCD sections are available:
- Earthwork
- Concrete
- Structural Steel
- Piping
- Mechanical Equipment
- Electrical
- Building Erection
- General Conditions
- Master Summary

### Job 8576 — RTKC 5600 Pump Station (IN PROGRESS)
Cataloging in progress. Ingest when complete.

---

## Build Sequence

### Step 1: Database Setup
1. Create SQLite database with full schema (see DATA_SCHEMA.md)
2. Write and test all table creation scripts
3. Verify schema handles all data types present in JCD documents

### Step 2: Ingestion Scripts
1. Write parser for JCD markdown format
2. Test against Job 8553 Concrete JCD first (well-structured, good reference)
3. Validate output against source document manually
4. Extend to remaining Job 8553 disciplines
5. Run full validation report

### Step 3: Query Layer
1. Define query functions for each data type (unit costs, production rates, crew, materials, subs)
2. Write natural language → query translation using Claude API
3. Format responses with source citations
4. Test against known questions with known answers

### Step 4: Interface
1. Build CLI interface
2. Test with 20 representative questions covering all disciplines
3. Evaluate if Streamlit upgrade is needed
4. Document interface for non-technical users

### Step 5: Validation
1. Run full validation report
2. Confirm all MVP success criteria are met
3. Document gaps for Phase 2

---

## Definition of Done

- [ ] Database created and populated with all Job 8553 data
- [ ] Ingestion script runs cleanly with no unhandled errors
- [ ] Validation report shows >95% of JCD data successfully ingested
- [ ] 20 test questions answered correctly with source citations
- [ ] Interface documented with example usage
- [ ] README updated with Phase 1 setup instructions
- [ ] Data gaps documented for Phase 2 prioritization

---

*WEIS MVP Specification v1.0*
*Phase 1 — Data Layer + Conversation Interface*
