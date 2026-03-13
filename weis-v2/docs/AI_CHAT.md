# Feature Spec: AI Estimating Chat

## Purpose
The AI Chat is the primary interface for estimators to query Wollam's historical field data. An estimator describes what they're pricing, and the system returns data-backed rates, crew configurations, production benchmarks, and confidence levels — all citing specific jobs and cost codes.

## How It Works

### The Estimator's Experience
The estimator opens the chat and types something like:

> "What's a good MH/SF rate for wall forming? We're looking at 25' walls, industrial site."

The system:
1. Identifies the discipline (concrete), activity (wall forming), and rate type (MH/SF)
2. Queries the database for all wall forming cost codes across all jobs
3. Pulls PM context where available (scope, conditions, notes)
4. Sends the assembled context + question to Claude
5. Returns a response like:

> **Wall Forming — Historical Rates**
>
> From Job 8553 (RTK SPD Pump Station), cost code 2215 "C_F/S Walls":
> - **Actual: 0.28 MH/SF** (Confidence: HIGH — 47 timecards, 23 work days)
> - Crew: 1 foreman, 3 carpenters, 3 laborers, 1 operator (avg 8.2/day)
> - Production: ~640 SF/day average
>
> **PM Context**: Walls were 20-30' height, one-sided pours against excavation using EFCO forms. Mine site with access restrictions (badging added ~30 min/day). Rate is conservative — crew was learning the form system for the first 2 weeks.
>
> **For your 25' walls on an industrial site**: The 0.28 MH/SF rate is directly applicable. If your walls are freestanding (two-sided), expect 0.32-0.35 MH/SF. If access is less restricted than a mine site, you could see 0.25-0.28 MH/SF.
>
> ⚠️ This is based on one job. Get PM context from other jobs with forming data to strengthen the benchmark.
>
> *Sources: Job 8553, CC 2215, rate_item confidence: high*

### What Makes This Different from ChatGPT
- **Real data, not training data** — every number comes from Wollam's actual field records
- **Source citations** — every rate tied to a specific job, cost code, and confidence level
- **PM context included** — not just numbers, but the story behind the numbers
- **Honest about gaps** — clearly states when data is limited or doesn't exist
- **Wollam-specific** — rates reflect Wollam's crews, equipment, and market conditions

## Context Assembly — The Core Engine

This is the most important part of the system. The quality of the AI response depends entirely on the quality of the context provided to Claude.

### Step 1: Intent Parsing
Extract search signals from the user's message:

```python
# Keywords to detect
DISCIPLINE_SIGNALS = {
    "concrete": ["concrete", "forming", "rebar", "pour", "slab", "wall", "foundation", "formwork"],
    "earthwork": ["excavation", "fill", "grading", "backfill", "earthwork", "dig", "haul"],
    "structural_steel": ["steel", "erection", "iron", "bolting", "welding", "structural"],
    "piping": ["pipe", "piping", "fuse", "hdpe", "flanged", "weld", "hydrotest"],
    "electrical": ["electrical", "conduit", "wire", "panel", "duct bank", "grounding"],
    "mechanical": ["pump", "mechanical", "equipment", "alignment", "grout"],
    "building": ["pemb", "metal building", "erection", "siding", "roofing"],
    "general_conditions": ["gc", "general conditions", "supervision", "management"],
}

RATE_SIGNALS = {
    "mh_per_unit": ["mh/", "man-hours per", "labor rate", "manhours"],
    "cost_per_unit": ["$/", "cost per", "dollars per", "price per", "all-in"],
    "production": ["production", "output", "per day", "per hour", "per shift"],
    "crew": ["crew", "crew size", "how many", "team", "workers"],
}
```

### Step 2: Database Queries
Based on detected signals, query for relevant data:

```sql
-- Find matching rate items across all jobs
SELECT ri.*, rc.job_id, j.job_number, j.name as job_name
FROM rate_item ri
JOIN rate_card rc ON ri.card_id = rc.card_id
JOIN job j ON rc.job_id = j.job_id
WHERE ri.discipline = ?
  AND ri.act_mh_per_unit IS NOT NULL
ORDER BY ri.confidence DESC, ri.timecard_count DESC;

-- Get PM context for those cost codes
SELECT cc.*, pc.project_summary, pc.site_conditions
FROM cc_context cc
LEFT JOIN pm_context pc ON pc.job_id = cc.job_id
WHERE cc.job_id = ? AND cc.cost_code = ?;

-- Get budget vs actual for variance context
SELECT code, description, unit,
       bgt_qty, act_qty,
       bgt_labor_hrs, act_labor_hrs,
       ROUND(act_labor_hrs / NULLIF(act_qty, 0), 4) as act_mh_per_unit
FROM hj_costcode
WHERE job_id = ? AND code = ?;
```

### Step 3: Context Block Assembly
Build a structured context block for Claude:

```
AVAILABLE HISTORICAL DATA:

JOB 8553 — RTK SPD Pump Station (Industrial pump station, Bingham Canyon Mine, UT)
PM Context: {project_summary from pm_context}
Site Conditions: {site_conditions from pm_context}

  Cost Code 2215 — C_F/S Walls
  Unit: SF
  Actual: 14,800 SF completed, 4,144 labor hours → 0.28 MH/SF
  Budget: 15,200 SF planned, 4,256 MH budgeted → 0.28 MH/SF (on budget)
  Confidence: HIGH (47 timecards across 23 work days)
  Daily Crew: Avg 8.2 workers (1 FORE, 3 CARP, 3 LAB, 1 OPR)
  Daily Production: Avg 643 SF/day, Peak 820 SF/day
  PM Context — Scope: {scope_included}
  PM Context — Excluded: {scope_excluded}
  PM Context — Conditions: {conditions}
  PM Context — Notes: {notes}

JOB 8576 — [another job with relevant data]
  ...

---
DATA GAPS:
- No forming data available from jobs other than 8553
- No PM context for Job 8576 cost codes
```

### Step 4: Claude API Call
Send to Claude with the Estimator Agent system prompt:

```python
messages = [
    {
        "role": "system",
        "content": ESTIMATOR_SYSTEM_PROMPT  # From the attached project description
    },
    {
        "role": "user",
        "content": f"""
{context_block}

---
ESTIMATOR'S QUESTION:
{user_message}

Provide a response with:
1. Direct answer to the question with specific rates
2. Source citations (job number, cost code, confidence level)
3. PM context where available
4. Scaling guidance if the estimator's scope differs from historical
5. Gaps or limitations in the data
6. Recommendation for what to validate with quotes
"""
    }
]
```

### Step 5: Response Formatting
Parse Claude's response and attach structured source metadata:

```json
{
    "response": "...(Claude's formatted response)...",
    "sources": [
        {
            "job_number": "8553",
            "job_name": "RTK SPD Pump Station",
            "cost_code": "2215",
            "description": "C_F/S Walls",
            "rate": 0.28,
            "rate_type": "MH/SF",
            "confidence": "high",
            "has_pm_context": true
        }
    ],
    "conversation_id": "abc-123"
}
```

## System Prompt for Claude

The system prompt is critical. It defines how Claude should behave as an estimating assistant. Use the Estimator Agent prompt from the attached project description (`AI Estimator - Estimator` project), with one modification: instead of referencing hardcoded Job 8553 data, reference the dynamically assembled context block.

Key behaviors:
- Always cite sources (job number, cost code, confidence)
- Always show confidence level
- Never invent rates — only use data provided in the context
- Clearly state when data is limited
- Recommend getting quotes when confidence is low
- Think like a contractor, not an academic
- Provide scaling guidance when the new scope differs from historical

## Conversation Persistence

Each chat session creates a conversation that's saved to the database. This allows:
- Estimators to come back to a conversation later
- Building on previous context (e.g., "What about the piping on that same job?")
- Review of AI recommendations during bid review

### Conversation History in Context
When a conversation has history, include the last 5 messages in the Claude API call for continuity. Don't send the full history — it wastes tokens and dilutes the data context.

## UI Design

### Chat Page Layout
```
┌──────────────────────────────────────────────────────────┐
│  HEADER: AI Estimating Assistant                          │
│  Subtitle: Ask questions about historical rates & costs   │
├──────────┬───────────────────────────────────────────────┤
│          │                                               │
│ CONVER-  │  CHAT AREA (scrollable)                       │
│ SATION   │                                               │
│ LIST     │  ┌─────────────────────────────────────────┐  │
│          │  │ User: What's a good rate for wall       │  │
│ • Current│  │ forming on 25' industrial walls?        │  │
│ • Mar 10 │  ├─────────────────────────────────────────┤  │
│ • Mar 8  │  │ AI: Based on Job 8553...               │  │
│ • Mar 5  │  │ [formatted response with sources]       │  │
│          │  └─────────────────────────────────────────┘  │
│          │                                               │
│          │  ┌─────────────────────────────────────────┐  │
│          │  │ 💬 Type your question...          [Send] │  │
│          │  └─────────────────────────────────────────┘  │
└──────────┴───────────────────────────────────────────────┘
```

### Message Formatting
- **User messages**: Right-aligned, navy background, white text
- **AI responses**: Left-aligned, white card with subtle border
- **Source citations**: Collapsible section at the bottom of each AI message, showing job/code/confidence as badges
- **Confidence badges**: Color-coded pills (green HIGH, amber MODERATE, red LOW)
- **Loading state**: Skeleton shimmer animation while waiting for Claude response

### Conversation List
- Left sidebar (narrower than the navy nav sidebar)
- Shows conversation title (auto-generated from first message) and date
- "New Conversation" button at top
- Click to switch between conversations

### Suggested Prompts
For new conversations, show 3-4 suggested prompts:
- "What are our historical rates for concrete wall forming?"
- "How many hours should I plan for HDPE pipe fusing?"
- "What crew size works best for structural steel erection?"
- "Compare earthwork production across our completed jobs"

## Error Handling
- **No relevant data found**: "I don't have historical data for [topic]. Consider getting vendor quotes for this scope."
- **Low confidence data**: "I found data, but confidence is LOW (only 2 timecards). Use these as rough guidance only and validate with quotes."
- **API error**: "I'm having trouble connecting to the AI service. Please try again in a moment."
- **No ANTHROPIC_API_KEY**: "AI chat requires an Anthropic API key. Please configure it in .env."

## What This Is NOT
- **Not a bid generator** — it provides intelligence, not a complete bid
- **Not a replacement for takeoff** — estimator still measures quantities
- **Not a guarantee** — historical data is guidance, not gospel
- **Not limited to one job** — queries should pull data from ALL relevant jobs in the database
