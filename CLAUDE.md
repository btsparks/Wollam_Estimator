# WEIS - Wollam Estimating Intelligence System

## What This Is
AI-powered estimating intelligence system for Wollam Construction (Utah-based industrial heavy civil contractor). Transforms historical job cost data into an active intelligence layer for estimating.

## Tech Stack
- **Language**: Python 3.13+
- **Database**: SQLite (single file at `data/db/weis.db`)
- **AI**: Anthropic Claude API (natural language queries)
- **CLI**: Rich library for terminal output
- **Testing**: pytest

## Project Structure
```
app/               # Application code
  config.py        # Environment config (paths, API keys)
  database.py      # SQLite schema + connection management
data/
  jcd/             # Job Cost Data markdown files (source of truth)
  db/              # SQLite database (gitignored, generated)
scripts/           # CLI scripts (seed_db.py, etc.)
tests/             # pytest tests
  fixtures/        # Test data
JCDs/              # DEPRECATED - use data/jcd/ instead
```

## Key Architecture Decisions
- **Build bottom-up**: Data layer → Intelligence layer → Presentation layer
- **SQLite, not Postgres**: Local, single file, no server. Easy to backup/version
- **JCD markdown is source of truth**: Database is derived from markdown files
- **Every rate must cite its source**: Job number, cost code, discipline
- **No hallucination**: System says "I don't know" if data doesn't support an answer
- **Confidence indicators**: HIGH / MEDIUM / LOW / ASSUMPTION on every rate

## Development Commands
```bash
# Activate virtual environment
source .venv/Scripts/activate    # Windows Git Bash
# .venv\Scripts\activate         # Windows CMD

# Run tests
pytest tests/

# Initialize/reset database
python scripts/seed_db.py

# Install dependencies
pip install -r requirements.txt
```

## Non-Negotiable Rules
1. Every data record traces back to a specific project, discipline, and cost code
2. No project data leaves Wollam's control (Anthropic API calls only)
3. Schema changes require migration scripts
4. Ingestion scripts must be idempotent
5. All query responses include source citations

## Current Phase
**Phase 1: Data Layer** — Build database, JCD parser, ingestion pipeline, basic queries.

## JCD Data Available
- Job 8553 (RTK SPD Pump Station): 9 discipline sections + master summary in `data/jcd/`
- Disciplines: Concrete, Structural Steel, Piping, Electrical, Mechanical Equipment, Earthwork, Building Erection, General Conditions

## Environment Setup
- Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`
- Database path configurable via `WEIS_DB_PATH` env var (default: `data/db/weis.db`)


# Claude Code Behavior Rules

## Autonomy — Do Not Stop for Approval
- Make changes directly without asking for confirmation first
- Do not pause mid-task to ask "should I continue?" — always continue
- If you encounter an ambiguous situation, make the most reasonable decision, implement it, and note your reasoning at the end
- Never ask "would you like me to..." — just do it
- Complete all steps of a task in a single run before reporting back

## Self-Verification — Check Your Own Work
- After making code changes, always run the relevant test suite automatically
- If no test command is obvious, attempt: `npm test`, `pytest`, `cargo test`, or `make test` in that order
- After running tests, fix any failures before considering the task done
- Run the linter if one is configured (e.g., `npm run lint`, `ruff check .`, `eslint .`)
- If a build step exists, run it to confirm nothing is broken

## Git Workflow
- Use `git status` and `git diff` to understand the current state before starting
- Make small, focused commits with clear messages as you complete logical chunks
- Do not ask before committing — commit when a logical unit of work is done
- Use `git stash` if you need a clean slate temporarily

## Task Approach
- Break large tasks into steps and work through them sequentially without pausing
- If a file is too large to read at once, use search tools (grep, glob) to find the relevant sections
- Prefer editing existing files over creating new ones unless a new file is clearly needed
- When something doesn't work, try at least 2–3 different approaches before reporting a blocker

## Communication
- When you finish a task, give a concise summary: what you did, what you tested, and any decisions you made
- Flag anything genuinely risky or irreversible (e.g., deleting data, modifying production config) before acting — these are the exceptions where pausing is appropriate
- Keep status updates short — no need to narrate every step
