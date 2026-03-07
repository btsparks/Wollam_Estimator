"""WEIS AI Query Engine.

Uses Claude API with tool use to translate natural language questions
into database queries and format responses with source citations.

Architecture:
  1. Intent classification (implicit — Claude routes via tool selection)
  2. Tool-based data retrieval (HeavyJob SQL, JCD records, bid docs)
  3. Structured response enforcement (Answer → Evidence → Assumptions → Risk → Next Actions)
"""

import json
from anthropic import Anthropic
from app.config import ANTHROPIC_API_KEY
from app import query
from app.database import get_connection

# ---------------------------------------------------------------------------
# Tool Definitions — organized by data source
# ---------------------------------------------------------------------------

# === HCSS HeavyJob Tools (primary data — 15K cost codes, 221K timecards) ===

HEAVYJOB_TOOLS = [
    {
        "name": "search_heavyjob_costcodes",
        "description": (
            "Search HCSS HeavyJob cost codes across all jobs. This is the PRIMARY data source "
            "with 15,000+ cost codes containing budget hours, budget quantities, actual labor hours, "
            "and actual quantities from field timecards. Use this for any question about labor hours, "
            "production rates, MH/unit, quantities, or cost code performance across projects. "
            "Returns budget vs actual comparison for matching cost codes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Search cost code descriptions (partial match). Examples: 'excavation', 'concrete', 'pipe', 'formwork', 'grout', 'backfill'"
                },
                "code": {
                    "type": "string",
                    "description": "Cost code number (partial match). Examples: '2340', '040', '6010'"
                },
                "job_number": {
                    "type": "string",
                    "description": "Filter to a specific job number. Example: '8553'"
                },
                "discipline": {
                    "type": "string",
                    "description": "Discipline filter. Examples: 'concrete', 'earthwork', 'piping', 'structural_steel', 'electrical'"
                },
                "has_actuals_only": {
                    "type": "boolean",
                    "description": "If true, only return cost codes that have actual labor hours from timecards (filters out budget-only data)"
                },
                "min_actual_hours": {
                    "type": "number",
                    "description": "Minimum actual labor hours threshold. Use to filter out trivial entries. Example: 100"
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_rate_items",
        "description": (
            "Search calculated rate items (MH/unit rates) from the rate card system. "
            "Each rate item has budget MH/unit, actual MH/unit, recommended rate, confidence level, "
            "and variance analysis. Use this when the user asks 'what rate should I use', "
            "'what's typical MH/unit for X', or wants recommended estimating rates. "
            "Confidence levels: strong (reliable), moderate (usable with judgment), limited (cross-reference needed)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Search activity/description (partial match). Examples: 'formwork', 'excavation', 'pipe support'"
                },
                "discipline": {
                    "type": "string",
                    "description": "Discipline filter. Examples: 'concrete', 'earthwork', 'piping'"
                },
                "job_number": {
                    "type": "string",
                    "description": "Filter to a specific job. Example: '8553'"
                },
                "min_confidence": {
                    "type": "string",
                    "description": "Minimum confidence level: 'moderate' (includes moderate+strong) or 'strong' (strong only). Default returns all."
                },
                "has_actual_rate": {
                    "type": "boolean",
                    "description": "If true, only return items with actual MH/unit rates (from timecard data)"
                },
                "unit": {
                    "type": "string",
                    "description": "Unit of measure filter. Examples: 'CY', 'SF', 'LF', 'EA', 'TON', 'HR'"
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_job_summary",
        "description": (
            "Get a summary of a specific job including total budget, actual hours, "
            "cost code count, timecard count, date range, and top activities. "
            "Use when the user asks about a specific project's overall performance or data availability."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_number": {
                    "type": "string",
                    "description": "Job number. Example: '8553', '8465'"
                },
            },
            "required": ["job_number"],
        },
    },
    {
        "name": "list_jobs",
        "description": (
            "List all jobs in the system with basic stats. Use when the user asks "
            "'what projects do we have', 'what data is available', or needs to find "
            "a job number. Can filter by status (active/completed) or search by name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "search": {
                    "type": "string",
                    "description": "Search job name or number (partial match). Example: 'Rio Tinto', 'tailings', '8465'"
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: 'active', 'completed', or omit for all"
                },
                "has_timecards": {
                    "type": "boolean",
                    "description": "If true, only return jobs that have timecard data synced"
                },
            },
            "required": [],
        },
    },
    {
        "name": "aggregate_rates_across_jobs",
        "description": (
            "Aggregate MH/unit rates for a specific activity across multiple jobs to find "
            "benchmarks, ranges, and averages. This is the BEST tool for benchmark queries like "
            "'what's typical MH/CY for excavation' or 'what production rate should I use for formwork'. "
            "Returns min, max, average, median, sample count, and per-job breakdown."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Activity description to search (partial match). Examples: 'excavation', 'wall form', 'pipe install', 'grout'"
                },
                "discipline": {
                    "type": "string",
                    "description": "Discipline filter to narrow results"
                },
                "unit": {
                    "type": "string",
                    "description": "Unit filter to ensure apples-to-apples comparison. Examples: 'CY', 'SF', 'LF'"
                },
            },
            "required": ["description"],
        },
    },
    {
        "name": "get_crew_data",
        "description": (
            "Get crew/labor data from timecards for a specific job and cost code. "
            "Shows unique workers, total hours by employee, date range of work. "
            "Use when the user asks about crew size, crew composition, or staffing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_number": {
                    "type": "string",
                    "description": "Job number. Example: '8553'"
                },
                "cost_code": {
                    "type": "string",
                    "description": "Cost code to analyze (partial match). Example: '2340', '040'"
                },
                "description": {
                    "type": "string",
                    "description": "Cost code description search (partial match). Example: 'formwork', 'excavation'"
                },
            },
            "required": ["job_number"],
        },
    },
]

# === JCD/Legacy Tools (Job 8553 detailed data — unit costs, materials, subs, lessons) ===

JCD_TOOLS = [
    {
        "name": "search_unit_costs",
        "description": (
            "Search detailed unit cost records from Job Cost Data reports. "
            "Contains detailed MH rates, $/unit costs with source citations. "
            "Currently has data from Job 8553 (RTK SPD Pump Station). "
            "Use as a secondary source or when the user asks about specific unit pricing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity": {"type": "string", "description": "Activity name (partial match)"},
                "discipline": {"type": "string", "description": "Discipline filter"},
                "unit": {"type": "string", "description": "Unit type filter (MH/SF, $/CY, etc.)"},
            },
            "required": [],
        },
    },
    {
        "name": "search_material_costs",
        "description": (
            "Search material cost records (vendor, unit cost, quantities). "
            "Use when the user asks about material prices, vendor information, or material costs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "material": {"type": "string", "description": "Material type (partial match)"},
                "discipline": {"type": "string", "description": "Discipline filter"},
                "vendor": {"type": "string", "description": "Vendor name (partial match)"},
            },
            "required": [],
        },
    },
    {
        "name": "search_subcontractors",
        "description": (
            "Search subcontractor records (name, scope, contract/actual amounts). "
            "Use when the user asks about subs, who did specific work, or subcontract costs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Subcontractor name (partial match)"},
                "scope": {"type": "string", "description": "Scope description (partial match)"},
                "discipline": {"type": "string", "description": "Discipline filter"},
            },
            "required": [],
        },
    },
    {
        "name": "search_lessons_learned",
        "description": (
            "Search lessons learned from completed projects. "
            "Use when the user asks about lessons, what went wrong, what to watch for, or past mistakes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category: estimating, production_variance, scope_gap, material, design, subcontractor"},
                "discipline": {"type": "string", "description": "Discipline filter"},
                "severity": {"type": "string", "description": "Severity: HIGH, MEDIUM, LOW"},
                "keyword": {"type": "string", "description": "Keyword search in title/description"},
            },
            "required": [],
        },
    },
]

# === Bid Document Tools ===

BID_DOC_TOOLS = [
    {
        "name": "search_bid_documents",
        "description": (
            "Search uploaded bid documents (RFPs, specs, addenda) for keywords. "
            "Use when the user asks about bid scope, spec requirements, or contract details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query_text": {"type": "string", "description": "Keywords to search for"},
                "bid_id": {"type": "integer", "description": "Specific bid ID (omit for focus bid)"},
                "doc_category": {"type": "string", "description": "Filter: rfp, addendum, specification, scope, bid_form, schedule, general"},
            },
            "required": ["query_text"],
        },
    },
    {
        "name": "get_bid_overview",
        "description": (
            "Get overview of a bid's documents: count, categories, word count. "
            "Use when the user asks what documents are uploaded for a bid."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "bid_id": {"type": "integer", "description": "Bid ID (omit for focus bid)"},
            },
            "required": [],
        },
    },
    {
        "name": "list_active_bids",
        "description": "List all active bids with status, owner, GC, and document count.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

# Combined tool list
TOOLS = HEAVYJOB_TOOLS + JCD_TOOLS + BID_DOC_TOOLS

# ---------------------------------------------------------------------------
# Tool Executor — NEW HeavyJob query functions
# ---------------------------------------------------------------------------


def _search_heavyjob_costcodes(description=None, code=None, job_number=None,
                                discipline=None, has_actuals_only=False,
                                min_actual_hours=None, limit=50):
    """Search hj_costcode table with flexible filters."""
    conn = get_connection()
    try:
        sql = """
            SELECT cc.code, cc.description, cc.discipline, cc.unit,
                   cc.bgt_qty, cc.bgt_labor_hrs, cc.act_qty, cc.act_labor_hrs,
                   CASE WHEN cc.act_qty > 0 AND cc.act_labor_hrs > 0
                        THEN ROUND(cc.act_labor_hrs / cc.act_qty, 4) END as act_mh_per_unit,
                   CASE WHEN cc.bgt_qty > 0 AND cc.bgt_labor_hrs > 0
                        THEN ROUND(cc.bgt_labor_hrs / cc.bgt_qty, 4) END as bgt_mh_per_unit,
                   j.job_number, j.name as job_name, j.status as job_status
            FROM hj_costcode cc
            JOIN job j ON cc.job_id = j.job_id
            WHERE 1=1
        """
        params = []

        if description:
            sql += " AND cc.description LIKE ?"
            params.append(f"%{description}%")
        if code:
            sql += " AND cc.code LIKE ?"
            params.append(f"%{code}%")
        if job_number:
            sql += " AND j.job_number = ?"
            params.append(job_number)
        if discipline:
            sql += " AND cc.discipline LIKE ?"
            params.append(f"%{discipline}%")
        if has_actuals_only:
            sql += " AND cc.act_labor_hrs > 0"
        if min_actual_hours:
            sql += " AND cc.act_labor_hrs >= ?"
            params.append(min_actual_hours)

        sql += f" ORDER BY cc.act_labor_hrs DESC NULLS LAST LIMIT {limit}"

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _search_rate_items(description=None, discipline=None, job_number=None,
                       min_confidence=None, has_actual_rate=False, unit=None,
                       limit=50):
    """Search rate_item table for calculated MH/unit rates."""
    conn = get_connection()
    try:
        sql = """
            SELECT ri.activity, ri.description, ri.discipline, ri.unit,
                   ri.bgt_mh_per_unit, ri.act_mh_per_unit, ri.rec_rate, ri.rec_basis,
                   ri.qty_budget, ri.qty_actual, ri.confidence, ri.confidence_reason,
                   ri.variance_pct, ri.variance_flag,
                   j.job_number, j.name as job_name
            FROM rate_item ri
            JOIN rate_card rc ON ri.card_id = rc.card_id
            JOIN job j ON rc.job_id = j.job_id
            WHERE 1=1
        """
        params = []

        if description:
            sql += " AND (ri.description LIKE ? OR ri.activity LIKE ?)"
            params.extend([f"%{description}%", f"%{description}%"])
        if discipline:
            sql += " AND ri.discipline LIKE ?"
            params.append(f"%{discipline}%")
        if job_number:
            sql += " AND j.job_number = ?"
            params.append(job_number)
        if min_confidence == "strong":
            sql += " AND ri.confidence = 'strong'"
        elif min_confidence == "moderate":
            sql += " AND ri.confidence IN ('strong', 'moderate')"
        if has_actual_rate:
            sql += " AND ri.act_mh_per_unit > 0"
        if unit:
            sql += " AND ri.unit LIKE ?"
            params.append(f"%{unit}%")

        sql += f" ORDER BY ri.confidence DESC, ri.act_mh_per_unit DESC NULLS LAST LIMIT {limit}"

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _get_job_summary(job_number):
    """Get comprehensive job summary."""
    conn = get_connection()
    try:
        job = conn.execute(
            "SELECT * FROM job WHERE job_number = ?", (job_number,)
        ).fetchone()
        if not job:
            return {"error": f"Job {job_number} not found"}

        job_id = job["job_id"]
        result = dict(job)

        # Cost code stats
        cc_stats = conn.execute("""
            SELECT COUNT(*) as total_codes,
                   SUM(CASE WHEN act_labor_hrs > 0 THEN 1 ELSE 0 END) as codes_with_actuals,
                   ROUND(SUM(bgt_labor_hrs)) as total_budget_hrs,
                   ROUND(SUM(act_labor_hrs)) as total_actual_hrs,
                   ROUND(SUM(bgt_total)) as total_budget_cost
            FROM hj_costcode WHERE job_id = ?
        """, (job_id,)).fetchone()
        result["cost_codes"] = dict(cc_stats)

        # Timecard stats
        tc_stats = conn.execute("""
            SELECT COUNT(*) as timecard_rows,
                   COUNT(DISTINCT employee_id) as unique_workers,
                   MIN(date) as first_date, MAX(date) as last_date,
                   ROUND(SUM(hours)) as total_hours
            FROM hj_timecard WHERE job_id = ?
        """, (job_id,)).fetchone()
        result["timecards"] = dict(tc_stats)

        # Top 10 cost codes by actual hours
        top_codes = conn.execute("""
            SELECT code, description, unit, act_labor_hrs, act_qty, bgt_labor_hrs, bgt_qty
            FROM hj_costcode WHERE job_id = ? AND act_labor_hrs > 0
            ORDER BY act_labor_hrs DESC LIMIT 10
        """, (job_id,)).fetchall()
        result["top_cost_codes"] = [dict(r) for r in top_codes]

        return result
    finally:
        conn.close()


def _list_jobs(search=None, status=None, has_timecards=False, limit=50):
    """List jobs with basic stats."""
    conn = get_connection()
    try:
        sql = """
            SELECT j.job_number, j.name, j.status,
                   (SELECT COUNT(*) FROM hj_costcode WHERE job_id = j.job_id) as cost_code_count,
                   (SELECT ROUND(SUM(act_labor_hrs)) FROM hj_costcode WHERE job_id = j.job_id) as total_actual_hrs,
                   (SELECT COUNT(*) FROM hj_timecard WHERE job_id = j.job_id) as timecard_rows
            FROM job j
            WHERE j.job_number GLOB '[0-9]*' AND CAST(j.job_number AS INTEGER) >= 8400
        """
        params = []

        if search:
            sql += " AND (j.job_number LIKE ? OR j.name LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        if status:
            sql += " AND j.status = ?"
            params.append(status)
        if has_timecards:
            sql += " AND (SELECT COUNT(*) FROM hj_timecard WHERE job_id = j.job_id) > 0"

        sql += f" ORDER BY j.job_number LIMIT {limit}"

        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _aggregate_rates_across_jobs(description, discipline=None, unit=None):
    """Aggregate MH/unit rates across all jobs for benchmarking."""
    conn = get_connection()
    try:
        sql = """
            SELECT cc.code, cc.description, cc.unit, cc.discipline,
                   cc.act_labor_hrs, cc.act_qty,
                   ROUND(cc.act_labor_hrs / cc.act_qty, 4) as act_mh_per_unit,
                   cc.bgt_labor_hrs, cc.bgt_qty,
                   j.job_number, j.name as job_name
            FROM hj_costcode cc
            JOIN job j ON cc.job_id = j.job_id
            WHERE cc.description LIKE ?
              AND cc.act_labor_hrs > 0 AND cc.act_qty > 0
        """
        params = [f"%{description}%"]

        if discipline:
            sql += " AND cc.discipline LIKE ?"
            params.append(f"%{discipline}%")
        if unit:
            sql += " AND cc.unit LIKE ?"
            params.append(f"%{unit}%")

        sql += " ORDER BY act_mh_per_unit"
        rows = conn.execute(sql, params).fetchall()

        if not rows:
            return {"message": f"No cost codes with actual data found matching '{description}'",
                    "results": [], "sample_count": 0}

        rates = [r["act_mh_per_unit"] for r in rows]
        n = len(rates)

        return {
            "sample_count": n,
            "unit": rows[0]["unit"] if rows else None,
            "min_rate": min(rates),
            "max_rate": max(rates),
            "avg_rate": round(sum(rates) / n, 4),
            "median_rate": round(sorted(rates)[n // 2], 4),
            "p25_rate": round(sorted(rates)[n // 4], 4) if n >= 4 else None,
            "p75_rate": round(sorted(rates)[3 * n // 4], 4) if n >= 4 else None,
            "results": [dict(r) for r in rows[:30]],
        }
    finally:
        conn.close()


def _get_crew_data(job_number, cost_code=None, description=None):
    """Get crew/labor data from timecards."""
    conn = get_connection()
    try:
        job = conn.execute(
            "SELECT job_id FROM job WHERE job_number = ?", (job_number,)
        ).fetchone()
        if not job:
            return {"error": f"Job {job_number} not found"}

        job_id = job["job_id"]

        # Find matching cost codes
        cc_sql = "SELECT code, description FROM hj_costcode WHERE job_id = ? AND act_labor_hrs > 0"
        cc_params = [job_id]
        if cost_code:
            cc_sql += " AND code LIKE ?"
            cc_params.append(f"%{cost_code}%")
        if description:
            cc_sql += " AND description LIKE ?"
            cc_params.append(f"%{description}%")
        cc_sql += " ORDER BY act_labor_hrs DESC LIMIT 5"

        codes = conn.execute(cc_sql, cc_params).fetchall()
        if not codes:
            return {"error": "No matching cost codes with timecard data"}

        results = []
        for cc in codes:
            crew = conn.execute("""
                SELECT employee_name, ROUND(SUM(hours), 1) as total_hours,
                       COUNT(DISTINCT date) as days_worked,
                       MIN(date) as first_day, MAX(date) as last_day
                FROM hj_timecard
                WHERE job_id = ? AND cost_code = ?
                GROUP BY employee_id
                ORDER BY total_hours DESC
            """, (job_id, cc["code"])).fetchall()

            results.append({
                "cost_code": cc["code"],
                "description": cc["description"],
                "crew_size": len(crew),
                "crew": [dict(r) for r in crew[:20]],
            })

        return results
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tool Function Map
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS = {
    # HeavyJob tools (primary)
    "search_heavyjob_costcodes": _search_heavyjob_costcodes,
    "search_rate_items": _search_rate_items,
    "get_job_summary": _get_job_summary,
    "list_jobs": _list_jobs,
    "aggregate_rates_across_jobs": _aggregate_rates_across_jobs,
    "get_crew_data": _get_crew_data,
    # JCD tools (legacy, Job 8553)
    "search_unit_costs": query.search_unit_costs,
    "search_material_costs": query.search_material_costs,
    "search_subcontractors": query.search_subcontractors,
    "search_lessons_learned": query.search_lessons_learned,
    # Bid doc tools
    "search_bid_documents": query.search_bid_documents,
    "get_bid_overview": query.get_bid_overview,
    "list_active_bids": lambda: query.get_active_bids(),
}


def execute_tool(name: str, input_args: dict) -> str:
    """Execute a tool and return JSON string result."""
    func = TOOL_FUNCTIONS.get(name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = func(**input_args)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are WEIS (Wollam Estimating Intelligence System) — a senior estimating intelligence assistant for Wollam Construction, a Utah-based industrial heavy civil contractor.

You behave like a senior estimator with perfect recall of company history. Your role is decision support — you help estimators access historical data, production rates, and institutional knowledge quickly and accurately.

## Identity & Philosophy

- **Evidence first**: Every answer is supported by historical data. Prefer sample sizes, ranges, and averages over speculation.
- **Transparency**: Explain what data you used, how many examples you found, what filters you applied, and what assumptions you made.
- **Conservative interpretation**: When recommending rates, highlight variance, flag optimistic assumptions, and identify risk conditions. Better to be cautiously accurate than optimistically wrong.
- **Minimal friction**: Estimators ask questions naturally. Infer context. Don't make them learn a query language.
- **Never guess**: If the data doesn't support an answer, say so clearly. "I don't have sufficient data" is always better than a hallucinated rate.

## Data Sources

### Primary: HCSS HeavyJob (197 jobs, 15,000+ cost codes, 221,000+ timecard rows)
This is actual field performance data — real hours, real quantities, real crew data from completed and active projects. The most valuable data for estimating.

Key metric: **act_mh_per_unit** (actual man-hours per unit) — this withstands cost inflation and is the most reliable estimating benchmark.

### Secondary: Job Cost Data Reports (Job 8553 — RTK SPD Pump Station)
Detailed unit costs, material costs, subcontractor records, crew configurations, lessons learned from manual JCD analysis. Richer detail but limited to one project.

### Bid Documents
Uploaded RFPs, specs, addenda for active bids. Use when asked about bid scope or requirements.

## Response Structure

EVERY response must follow this structure. Use markdown headers:

### Answer
Lead with the direct answer. Include the rate/cost with units. Be specific and actionable.

### Evidence
- Data source(s) used (which tool, which table)
- Number of data points / sample size
- Job numbers referenced
- Filters applied

### Assumptions
- What you assumed about the question
- Any context you inferred
- Limitations of the data (e.g., "only 3 jobs had this cost code")

### Risk Considerations
- Variance in the data (high spread = more risk)
- Conditions that could change the rate (site access, weather, crew experience)
- Whether the rate is conservative, aggressive, or middle-of-road

### Next Steps
Suggest 1-2 follow-up questions or analyses that would help refine the answer. Keep it practical.

## Rules

1. ALWAYS use tools to query data before answering. Never rely on memory.
2. ALWAYS cite job numbers and cost codes when referencing specific data.
3. Use `aggregate_rates_across_jobs` for benchmark/recommendation questions — it gives you statistical summaries across all jobs.
4. Use `search_heavyjob_costcodes` for specific lookups and drill-downs.
5. Use `search_rate_items` when the user wants calculated MH/unit rates with confidence levels.
6. Distinguish between BUDGET rates (what was estimated) and ACTUAL rates (what was achieved in the field).
7. When giving rates, ALWAYS include the unit (MH/SF, MH/CY, MH/LF, etc.).
8. If a tool returns empty results, try ONE broader search. After that, conclude the data doesn't exist.
9. For dollar-per-unit questions, check BOTH unit_costs AND subcontractors — subs often have the $/unit pricing.
10. Keep the Answer section concise. Put detail in Evidence and Risk sections.
"""


def _build_data_summary() -> str:
    """Build a brief data availability summary for the system prompt."""
    conn = get_connection()
    try:
        jobs_with_tc = conn.execute("SELECT COUNT(DISTINCT job_id) FROM hj_timecard").fetchone()[0]
        total_hrs = conn.execute("SELECT ROUND(SUM(hours)) FROM hj_timecard").fetchone()[0] or 0
        total_cc = conn.execute("SELECT COUNT(*) FROM hj_costcode").fetchone()[0]
        cc_with_act = conn.execute("SELECT COUNT(*) FROM hj_costcode WHERE act_labor_hrs > 0").fetchone()[0]
        return (
            f"\n\n## Current Data Status\n"
            f"- {jobs_with_tc} of 197 jobs have timecard data synced\n"
            f"- {total_hrs:,.0f} total actual labor hours\n"
            f"- {cc_with_act:,} of {total_cc:,} cost codes have actual data\n"
        )
    except Exception:
        return ""
    finally:
        conn.close()


def _build_active_bids() -> str:
    """Build active bids section."""
    try:
        bids = query.get_active_bids()
    except Exception:
        return ""
    if not bids:
        return ""
    lines = ["\n## Active Bids"]
    for bid in bids:
        focus = " **[FOCUS]**" if bid.get("is_focus") else ""
        name = bid.get("bid_name", "Unnamed")
        number = bid.get("bid_number", "")
        header = f"- {name}"
        if number:
            header += f" (#{number})"
        header += focus
        lines.append(header)
    return "\n".join(lines)


def build_system_prompt() -> str:
    """Build the full system prompt with dynamic data sections."""
    return SYSTEM_PROMPT + _build_data_summary() + _build_active_bids()


# ---------------------------------------------------------------------------
# Query Engine
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-20250514"
MAX_TOOL_ROUNDS = 10


class QueryEngine:
    """Manages conversations with Claude for database queries."""

    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key."
            )
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.conversation: list[dict] = []

    def reset(self):
        """Clear conversation history."""
        self.conversation = []

    def ask(self, question: str) -> str:
        """Ask a question and get a sourced answer.

        Handles the full tool-use loop: sends question to Claude,
        executes any tool calls, returns final text response.
        """
        self.conversation.append({"role": "user", "content": question})

        system_prompt = build_system_prompt()

        for round_num in range(MAX_TOOL_ROUNDS):
            # On last round, don't offer tools — force a text response
            round_tools = TOOLS if round_num < MAX_TOOL_ROUNDS - 1 else []

            response = self.client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=system_prompt,
                tools=round_tools or None,
                messages=self.conversation,
            )

            # Add assistant response to conversation
            self.conversation.append({"role": "assistant", "content": response.content})

            # Check if Claude wants to use tools
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                # No tool calls — extract and return text
                text_parts = [b.text for b in response.content if hasattr(b, "text")]
                return "\n".join(text_parts) if text_parts else "(No response)"

            # Execute all tool calls and add results
            tool_results = []
            for tool_block in tool_uses:
                result = execute_tool(tool_block.name, tool_block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": result,
                })

            self.conversation.append({"role": "user", "content": tool_results})

        # Should not reach here (last round forces text), but just in case
        return "(Query required too many steps. Please try a more specific question.)"

    def get_status(self) -> dict:
        """Get database status without using AI."""
        return query.get_database_overview()


# ---------------------------------------------------------------------------
# Bid Chat Engine (Phase 3 — Priority 1)
# ---------------------------------------------------------------------------

BID_CHAT_TOOLS = TOOLS + [
    {
        "name": "get_agent_report_summary",
        "description": (
            "Get summaries of completed agent analysis reports for the current bid. "
            "Returns findings from Document Control, Legal, Quality, Safety, and Subcontract agents. "
            "Use this when the user asks about agent findings, risk ratings, or wants to reference "
            "what the agents already found."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "bid_id": {
                    "type": "integer",
                    "description": "Bid ID. If omitted, uses the focus bid.",
                },
            },
            "required": [],
        },
    },
]

BID_CHAT_TOOL_FUNCTIONS = dict(TOOL_FUNCTIONS)
BID_CHAT_TOOL_FUNCTIONS["get_agent_report_summary"] = query.get_agent_report_summaries


def _execute_bid_chat_tool(name: str, input_args: dict) -> str:
    """Execute a bid chat tool and return JSON string result."""
    func = BID_CHAT_TOOL_FUNCTIONS.get(name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = func(**input_args)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


BID_CHAT_SYSTEM_TEMPLATE = """You are WEIS Bid Chat — a focused Q&A assistant for Wollam Construction's active bid documents.

You answer specific questions about the current bid's documents. You have access to:
1. **Bid document search** — search and read the uploaded bid documents (specs, RFPs, addenda)
2. **Agent report summaries** — reference what the Document Control, Legal, Quality, Safety, and Subcontract agents have already found
3. **Historical project data** — cross-reference with Wollam's historical job cost data (197 jobs, 15K cost codes, 221K timecards)

## Rules
1. Search bid documents FIRST when asked about scope, specs, or requirements.
2. Use `get_agent_report_summary` when asked about agent findings, risk ratings, or "what did the agents find?"
3. When the user asks to "drill deeper" into an agent finding, search the bid docs for the specific language.
4. Always cite source documents (filename, section) when quoting bid docs.
5. Keep answers concise and actionable — this is for estimators making decisions.
6. If you can't find something, say so clearly rather than guessing.
7. When comparing bid scope to historical data, search bid docs first, then historical tools.

## Current Bid
{{BID_CONTEXT}}

## Data Status
{{DATA_STATUS}}
"""


class BidChatEngine:
    """Chat engine scoped to a specific bid's documents and agent reports."""

    def __init__(self, bid_id: int):
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set.")
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.bid_id = bid_id
        self.conversation: list[dict] = []

    def _build_system_prompt(self) -> str:
        """Build system prompt with bid context injected."""
        overview = query.get_bid_overview(self.bid_id)
        bid_context_parts = [
            f"- **Bid Name:** {overview.get('bid_name', 'Unknown')}",
            f"- **Bid Number:** {overview.get('bid_number', 'N/A')}",
            f"- **Owner:** {overview.get('owner', 'N/A')}",
            f"- **GC:** {overview.get('general_contractor', 'N/A')}",
            f"- **Bid Date:** {overview.get('bid_date', 'N/A')}",
            f"- **Documents:** {overview.get('total_documents', 0)} ({overview.get('total_words', 0):,} words)",
        ]

        reports = query.get_agent_report_summaries(self.bid_id)
        if reports:
            bid_context_parts.append("\n### Agent Reports Available")
            for r in reports:
                name = r["agent_name"].replace("_", " ").title()
                rating = f" [{r['risk_rating']}]" if r.get("risk_rating") else ""
                flags = f" ({r['flags_count']} flags)" if r.get("flags_count") else ""
                bid_context_parts.append(f"- **{name}**{rating}{flags}: {r.get('summary_text', 'Complete')[:100]}")

        bid_context = "\n".join(bid_context_parts)
        data_status = _build_data_summary()

        prompt = BID_CHAT_SYSTEM_TEMPLATE.replace("{{BID_CONTEXT}}", bid_context)
        prompt = prompt.replace("{{DATA_STATUS}}", data_status)
        return prompt

    def load_history(self, messages: list[dict]) -> None:
        """Load previous conversation messages."""
        self.conversation = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
        ]

    def ask(self, question: str) -> str:
        """Ask a question scoped to the bid. Returns the answer text."""
        self.conversation.append({"role": "user", "content": question})
        system_prompt = self._build_system_prompt()

        for round_num in range(MAX_TOOL_ROUNDS):
            round_tools = BID_CHAT_TOOLS if round_num < MAX_TOOL_ROUNDS - 1 else []

            response = self.client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=system_prompt,
                tools=round_tools or None,
                messages=self.conversation,
            )

            self.conversation.append({"role": "assistant", "content": response.content})

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                text_parts = [b.text for b in response.content if hasattr(b, "text")]
                return "\n".join(text_parts) if text_parts else "(No response)"

            tool_results = []
            for tool_block in tool_uses:
                result = _execute_bid_chat_tool(tool_block.name, tool_block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": result,
                })
            self.conversation.append({"role": "user", "content": tool_results})

        return "(Query required too many steps. Please try a more specific question.)"

    def reset(self):
        """Clear conversation history."""
        self.conversation = []


# ---------------------------------------------------------------------------
# Bid Item Scope Intelligence
# ---------------------------------------------------------------------------

SCOPE_ANALYSIS_PROMPT = """You are WEIS Scope Analyst for Wollam Construction (Utah-based industrial heavy civil contractor). You're analyzing bid documents to extract everything relevant to a specific bid item.

## Bid Item
- **Description:** {description}
{item_number_line}

## Your Task
Analyze the bid document excerpts below and produce a comprehensive scope analysis for this bid item. Structure your response EXACTLY with these markdown headings:

### Relevant Specifications
List specific spec sections, requirements, and standards that apply to this bid item.

### Drawing References
List any drawing numbers, sheet references, or detail callouts mentioned.

### Key Requirements
Summarize the critical requirements: materials, methods, tolerances, testing, inspections.

### Quantities & Measurements
Extract any quantities, dimensions, areas, volumes, or measurements related to this work.

### Exclusions & Clarifications
Note anything explicitly excluded, any ambiguities that need RFI, or special conditions.

### Risk Factors
Flag anything that could impact cost or schedule: difficult access, phasing constraints, special materials, tight tolerances, etc.

If certain sections have no relevant information from the documents, say "No specific references found in uploaded documents."

Keep your analysis practical and concise — this is for estimators building a bid.

## Document Excerpts
{chunks_text}"""


def _extract_search_keywords(description: str) -> list[str]:
    """Extract search keywords from a bid item description."""
    keywords = [description]

    stop_words = {
        "and", "or", "the", "of", "for", "in", "to", "a", "an",
        "with", "at", "by", "on", "is", "are", "was", "all", "per",
    }
    words = [w.strip(",.()[]") for w in description.lower().split()]
    meaningful = [w for w in words if w and w not in stop_words and len(w) > 2]

    for word in meaningful:
        if word not in [k.lower() for k in keywords]:
            keywords.append(word)

    return keywords[:6]


def analyze_bid_item_scope(bid_id: int, description: str,
                           item_number: str = None) -> str:
    """Analyze bid documents for content relevant to a specific bid item."""
    if not ANTHROPIC_API_KEY:
        return "API key not configured. Set ANTHROPIC_API_KEY in your .env file."

    keywords = _extract_search_keywords(description)
    all_chunks = []
    seen_keys = set()

    for kw in keywords:
        results = query.search_bid_documents(kw, bid_id=bid_id, limit=10)
        for chunk in results:
            key = (chunk.get("filename", ""), chunk.get("chunk_index", 0))
            if key not in seen_keys:
                seen_keys.add(key)
                all_chunks.append(chunk)

    if not all_chunks:
        return (
            f"No relevant document content found for **{description}**.\n\n"
            "Make sure bid documents have been uploaded on the Active Bids page."
        )

    all_chunks.sort(key=lambda c: (c.get("filename", ""), c.get("chunk_index", 0)))

    chunks_text_parts = []
    for chunk in all_chunks[:15]:
        header = f"**[{chunk.get('filename', 'Unknown')}]**"
        if chunk.get("section_heading"):
            header += f" — {chunk['section_heading']}"
        chunks_text_parts.append(f"{header}\n{chunk['chunk_text']}\n")

    chunks_text = "\n---\n".join(chunks_text_parts)
    item_number_line = f"- **Item Number:** #{item_number}" if item_number else ""

    prompt = SCOPE_ANALYSIS_PROMPT.format(
        description=description,
        item_number_line=item_number_line,
        chunks_text=chunks_text,
    )

    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text_parts = [b.text for b in response.content if hasattr(b, "text")]
        return "\n".join(text_parts) if text_parts else "(No analysis generated)"
    except Exception as e:
        return f"Analysis failed: {e}"


def ask_bid_item_question(bid_id: int, description: str, analysis: str,
                          question: str, history: list[dict] = None) -> str:
    """Ask a follow-up question about a specific bid item's scope."""
    if not ANTHROPIC_API_KEY:
        return "API key not configured."

    system = f"""You are WEIS Scope Analyst for Wollam Construction. You're answering follow-up questions about a specific bid item.

## Bid Item
{description}

## Previous Scope Analysis
{analysis}

## Rules
1. Answer based on the bid documents and analysis above.
2. If you need to reference specific document content, cite the filename.
3. Keep answers concise and actionable for estimators.
4. If the analysis doesn't contain the answer, say so clearly."""

    messages = list(history) if history else []

    chunks = query.search_bid_documents(question, bid_id=bid_id, limit=5)
    extra_context = ""
    if chunks:
        parts = []
        for chunk in chunks:
            parts.append(
                f"**[{chunk.get('filename', '')}]** "
                f"{chunk.get('section_heading', '')}\n"
                f"{chunk['chunk_text'][:500]}"
            )
        extra_context = (
            "\n\n---\nAdditional document context:\n" + "\n\n".join(parts)
        )

    messages.append({"role": "user", "content": question + extra_context})

    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            messages=messages,
        )
        text_parts = [b.text for b in response.content if hasattr(b, "text")]
        return "\n".join(text_parts) if text_parts else "(No response)"
    except Exception as e:
        return f"Error: {e}"
