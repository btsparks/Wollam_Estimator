"""WEIS AI Query Engine — Estimating Intelligence Assistant.

Uses Claude API with tool use to translate natural language questions
into database queries and format responses with source citations.

Architecture:
  1. Intent classification (6 types: lookup, benchmark, similarity, variance, recommendation, artifact)
  2. Tool-based data retrieval (HeavyJob SQL, JCD records, bid docs)
  3. Structured response enforcement (Answer -> Evidence -> Assumptions -> Risk -> Next Actions)
  4. Progressive disclosure (table first, detail on request)
"""

import json
import logging
from datetime import datetime
from anthropic import Anthropic
from app.config import ANTHROPIC_API_KEY
from app import query
from app.database import get_connection

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool Definitions — organized by data source
# ---------------------------------------------------------------------------

# === HCSS HeavyJob Tools (primary data — 15K cost codes, 221K timecards) ===

HEAVYJOB_TOOLS = [
    {
        "name": "search_heavyjob_costcodes",
        "description": (
            "Search HCSS HeavyJob cost codes across all jobs. Primary data source "
            "with 15,000+ cost codes containing actual labor hours and quantities from field timecards. "
            "Use for questions about labor hours, production rates, MH/unit, quantities, or "
            "cost code activity across projects."
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
            "Search field intelligence rate items from the rate card system. "
            "Each item has actual MH/unit, $/unit (labor+equipment), timecard count, crew data, "
            "and confidence level based on data richness. Use when the user asks 'what rate should I use', "
            "'what's typical MH/unit for X', or wants production rates with confidence assessment. "
            "Confidence: high (20+ timecards), moderate (5-19), low (1-4)."
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
                    "description": "Minimum confidence level: 'moderate' (includes moderate+high) or 'high' (high only — 20+ timecards). Default returns all."
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
    {
        "name": "get_related_costcodes",
        "description": (
            "Get ALL active cost codes in the same discipline on a specific job. "
            "Use AFTER finding matching cost codes to discover related work. "
            "For example, 'pipe install' on a job might also have fuse, dig/lay/backfill, "
            "bedding, testing codes in the same discipline. This finds the full scope picture. "
            "Always use this when answering scope-of-work questions to show ALL relevant codes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_number": {
                    "type": "string",
                    "description": "Job number to search. Example: '8553'"
                },
                "discipline": {
                    "type": "string",
                    "description": "Discipline to filter by (from initial search results). Example: 'mechanical_piping', 'earthwork'"
                },
            },
            "required": ["job_number", "discipline"],
        },
    },
    {
        "name": "get_trade_breakdown",
        "description": (
            "Analyze the labor trade breakdown for a job or specific cost code. "
            "Shows which trades (Foreman, Operator, Laborer, Welder, Ironworker, Carpenter, etc.) "
            "worked on the activity, total hours per trade, and average crew composition. "
            "Use for crew planning questions like 'what crew do I need for X' or "
            "'what's the trade mix for excavation'. Data comes from 278K timecard rows with trade codes."
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
                    "description": "Cost code filter (partial match). Example: '2340'"
                },
                "description": {
                    "type": "string",
                    "description": "Cost code description search. Example: 'excavation', 'formwork'"
                },
            },
            "required": ["job_number"],
        },
    },
    {
        "name": "get_equipment_analysis",
        "description": (
            "Analyze equipment usage for a job or specific cost code. "
            "Shows which equipment types were used, total hours, days active, and utilization patterns. "
            "Use for equipment planning questions like 'what equipment did we use for earthwork' or "
            "'how many crane hours on 8553'. Data from 196K equipment entries across all jobs."
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
                    "description": "Cost code filter (partial match). Example: '2340'"
                },
                "description": {
                    "type": "string",
                    "description": "Cost code description search. Example: 'excavation', 'crane'"
                },
                "equipment_type": {
                    "type": "string",
                    "description": "Equipment type search. Example: 'crane', 'excavator', 'haul'"
                },
            },
            "required": ["job_number"],
        },
    },
    {
        "name": "get_production_timeline",
        "description": (
            "Get daily/weekly production data for a cost code on a specific job. "
            "Shows how production progressed over time — daily hours, quantities, crew size, "
            "and production rate trends. Use to understand ramp-up, peak production, "
            "seasonal effects, or to validate whether a production rate is sustainable. "
            "Great for answering 'how long did it take' or 'what was peak daily production'."
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
                    "description": "Cost code (exact or partial). Example: '2340'"
                },
                "description": {
                    "type": "string",
                    "description": "Cost code description search. Example: 'excavation'"
                },
                "granularity": {
                    "type": "string",
                    "description": "Time grouping: 'daily' or 'weekly'. Default: 'weekly'"
                },
            },
            "required": ["job_number"],
        },
    },
    {
        "name": "compare_jobs",
        "description": (
            "Compare two or more jobs side by side for a specific scope of work. "
            "Shows matched cost codes across jobs with MH/unit, quantities, crew size, and confidence. "
            "Use when the estimator wants to compare performance across projects for the same activity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_numbers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of job numbers to compare. Example: ['8553', '8465']"
                },
                "description": {
                    "type": "string",
                    "description": "Activity description to match across jobs. Example: 'excavation'"
                },
                "discipline": {
                    "type": "string",
                    "description": "Discipline filter. Example: 'earthwork'"
                },
            },
            "required": ["job_numbers", "description"],
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
    """Search rate_item table for field intelligence rates."""
    conn = get_connection()
    try:
        sql = """
            SELECT ri.activity, ri.description, ri.discipline, ri.unit,
                   ri.act_mh_per_unit, ri.act_cost_per_unit,
                   ri.timecard_count, ri.work_days, ri.crew_size_avg,
                   ri.daily_qty_avg, ri.daily_qty_peak,
                   ri.total_hours, ri.total_qty,
                   ri.total_labor_cost, ri.total_equip_cost,
                   ri.confidence, ri.confidence_reason, ri.crew_breakdown,
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
        if min_confidence == "high":
            sql += " AND ri.confidence = 'high'"
        elif min_confidence == "moderate":
            sql += " AND ri.confidence IN ('high', 'moderate')"
        if has_actual_rate:
            sql += " AND ri.act_mh_per_unit > 0"
        if unit:
            sql += " AND ri.unit LIKE ?"
            params.append(f"%{unit}%")

        sql += f" ORDER BY ri.timecard_count DESC, ri.act_mh_per_unit DESC NULLS LAST LIMIT {limit}"

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


def _get_related_costcodes(job_number, discipline, limit=30):
    """Get all active cost codes in the same discipline on a job."""
    conn = get_connection()
    try:
        job = conn.execute(
            "SELECT job_id FROM job WHERE job_number = ?", (job_number,)
        ).fetchone()
        if not job:
            return {"error": f"Job {job_number} not found"}

        rows = conn.execute("""
            SELECT cc.code, cc.description, cc.unit, cc.discipline,
                   cc.act_labor_hrs, cc.act_qty,
                   CASE WHEN cc.act_qty > 0 AND cc.act_labor_hrs > 0
                        THEN ROUND(cc.act_labor_hrs / cc.act_qty, 4) END as act_mh_per_unit,
                   (SELECT COUNT(*) FROM hj_timecard
                    WHERE job_id = cc.job_id AND cost_code = cc.code) as timecard_count
            FROM hj_costcode cc
            WHERE cc.job_id = ? AND cc.discipline LIKE ? AND cc.act_labor_hrs > 0
            ORDER BY cc.act_labor_hrs DESC
            LIMIT ?
        """, (job["job_id"], f"%{discipline}%", limit)).fetchall()

        return {
            "job_number": job_number,
            "discipline": discipline,
            "cost_codes": [dict(r) for r in rows],
        }
    finally:
        conn.close()


def _get_trade_breakdown(job_number, cost_code=None, description=None):
    """Analyze labor trade breakdown from timecard pay_class_code data."""
    conn = get_connection()
    try:
        job = conn.execute(
            "SELECT job_id, name FROM job WHERE job_number = ?", (job_number,)
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
            # Trade breakdown from pay_class_code
            trades = conn.execute("""
                SELECT pay_class_code as trade_code,
                       pay_class_desc as trade_name,
                       COUNT(DISTINCT employee_id) as workers,
                       ROUND(SUM(hours), 1) as total_hours,
                       COUNT(DISTINCT date) as days_worked
                FROM hj_timecard
                WHERE job_id = ? AND cost_code = ? AND pay_class_code IS NOT NULL
                GROUP BY pay_class_code, pay_class_desc
                ORDER BY total_hours DESC
            """, (job_id, cc["code"])).fetchall()

            # Daily crew size average
            daily_crew = conn.execute("""
                SELECT date, COUNT(DISTINCT employee_id) as crew_size,
                       ROUND(SUM(hours), 1) as daily_hours
                FROM hj_timecard
                WHERE job_id = ? AND cost_code = ?
                GROUP BY date
            """, (job_id, cc["code"])).fetchall()

            avg_crew = round(sum(r["crew_size"] for r in daily_crew) / len(daily_crew), 1) if daily_crew else 0
            total_days = len(daily_crew)

            results.append({
                "cost_code": cc["code"],
                "description": cc["description"],
                "total_work_days": total_days,
                "avg_daily_crew_size": avg_crew,
                "trades": [dict(r) for r in trades],
            })

        return {"job_number": job_number, "job_name": job["name"], "cost_codes": results}
    finally:
        conn.close()


def _get_equipment_analysis(job_number, cost_code=None, description=None, equipment_type=None):
    """Analyze equipment usage from hj_equipment_entry table."""
    conn = get_connection()
    try:
        job = conn.execute(
            "SELECT job_id, name FROM job WHERE job_number = ?", (job_number,)
        ).fetchone()
        if not job:
            return {"error": f"Job {job_number} not found"}

        job_id = job["job_id"]

        # Build query based on filters
        sql = """
            SELECT e.equipment_code, e.equipment_desc,
                   ROUND(SUM(e.hours), 1) as total_hours,
                   COUNT(DISTINCT e.date) as days_used,
                   MIN(e.date) as first_used, MAX(e.date) as last_used
            FROM hj_equipment_entry e
            WHERE e.job_id = ?
        """
        params = [job_id]

        if cost_code:
            sql += " AND e.cost_code LIKE ?"
            params.append(f"%{cost_code}%")
        if description:
            # Join to hj_costcode for description search
            sql = """
                SELECT e.equipment_code, e.equipment_desc,
                       ROUND(SUM(e.hours), 1) as total_hours,
                       COUNT(DISTINCT e.date) as days_used,
                       MIN(e.date) as first_used, MAX(e.date) as last_used
                FROM hj_equipment_entry e
                JOIN hj_costcode cc ON e.job_id = cc.job_id AND e.cost_code = cc.code
                WHERE e.job_id = ? AND cc.description LIKE ?
            """
            params = [job_id, f"%{description}%"]
        if equipment_type:
            sql += " AND (e.equipment_desc LIKE ? OR e.equipment_code LIKE ?)"
            params.extend([f"%{equipment_type}%", f"%{equipment_type}%"])

        sql += " GROUP BY e.equipment_code, e.equipment_desc ORDER BY total_hours DESC LIMIT 30"

        rows = conn.execute(sql, params).fetchall()

        # Total equipment hours for context
        total_equip = conn.execute(
            "SELECT ROUND(SUM(hours), 1) FROM hj_equipment_entry WHERE job_id = ?", (job_id,)
        ).fetchone()[0] or 0

        return {
            "job_number": job_number,
            "job_name": job["name"],
            "total_equipment_hours_on_job": total_equip,
            "equipment": [dict(r) for r in rows],
        }
    finally:
        conn.close()


def _get_production_timeline(job_number, cost_code=None, description=None, granularity="weekly"):
    """Get production timeline — daily or weekly aggregation."""
    conn = get_connection()
    try:
        job = conn.execute(
            "SELECT job_id, name FROM job WHERE job_number = ?", (job_number,)
        ).fetchone()
        if not job:
            return {"error": f"Job {job_number} not found"}

        job_id = job["job_id"]

        # Find the cost code
        cc_sql = "SELECT code, description, unit, act_qty, act_labor_hrs FROM hj_costcode WHERE job_id = ? AND act_labor_hrs > 0"
        cc_params = [job_id]
        if cost_code:
            cc_sql += " AND code LIKE ?"
            cc_params.append(f"%{cost_code}%")
        if description:
            cc_sql += " AND description LIKE ?"
            cc_params.append(f"%{description}%")
        cc_sql += " ORDER BY act_labor_hrs DESC LIMIT 1"

        cc = conn.execute(cc_sql, cc_params).fetchone()
        if not cc:
            return {"error": "No matching cost code with timecard data"}

        # Get daily production data
        if granularity == "daily":
            group_expr = "date"
            label = "date"
        else:
            # Weekly: group by year-week
            group_expr = "strftime('%Y-W%W', date)"
            label = "week"

        timeline = conn.execute(f"""
            SELECT {group_expr} as period,
                   COUNT(DISTINCT employee_id) as crew_size,
                   ROUND(SUM(hours), 1) as total_hours,
                   COUNT(DISTINCT date) as work_days
            FROM hj_timecard
            WHERE job_id = ? AND cost_code = ?
            GROUP BY {group_expr}
            ORDER BY period
        """, (job_id, cc["code"])).fetchall()

        return {
            "job_number": job_number,
            "job_name": job["name"],
            "cost_code": cc["code"],
            "description": cc["description"],
            "unit": cc["unit"],
            "total_actual_qty": cc["act_qty"],
            "total_actual_hours": cc["act_labor_hrs"],
            "granularity": granularity,
            "periods": [dict(r) for r in timeline],
        }
    finally:
        conn.close()


def _compare_jobs(job_numbers, description, discipline=None):
    """Compare multiple jobs side by side for a specific scope."""
    conn = get_connection()
    try:
        results = []
        for jn in job_numbers:
            job = conn.execute(
                "SELECT job_id, name FROM job WHERE job_number = ?", (jn,)
            ).fetchone()
            if not job:
                results.append({"job_number": jn, "error": "Not found"})
                continue

            sql = """
                SELECT cc.code, cc.description, cc.unit, cc.discipline,
                       cc.act_labor_hrs, cc.act_qty,
                       CASE WHEN cc.act_qty > 0 AND cc.act_labor_hrs > 0
                            THEN ROUND(cc.act_labor_hrs / cc.act_qty, 4) END as act_mh_per_unit,
                       (SELECT COUNT(*) FROM hj_timecard WHERE job_id = cc.job_id AND cost_code = cc.code) as timecard_count
                FROM hj_costcode cc
                WHERE cc.job_id = ? AND cc.description LIKE ? AND cc.act_labor_hrs > 0
            """
            params = [job["job_id"], f"%{description}%"]
            if discipline:
                sql += " AND cc.discipline LIKE ?"
                params.append(f"%{discipline}%")
            sql += " ORDER BY cc.act_labor_hrs DESC LIMIT 10"

            rows = conn.execute(sql, params).fetchall()
            results.append({
                "job_number": jn,
                "job_name": job["name"],
                "matching_codes": [dict(r) for r in rows],
            })

        return {"comparison": results}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tool Function Map
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS = {
    # HeavyJob tools (primary — 278K timecards, 196K equipment entries, 15K cost codes)
    "search_heavyjob_costcodes": _search_heavyjob_costcodes,
    "search_rate_items": _search_rate_items,
    "get_job_summary": _get_job_summary,
    "list_jobs": _list_jobs,
    "aggregate_rates_across_jobs": _aggregate_rates_across_jobs,
    "get_crew_data": _get_crew_data,
    "get_related_costcodes": _get_related_costcodes,
    # New field intelligence tools (v1.9 data)
    "get_trade_breakdown": _get_trade_breakdown,
    "get_equipment_analysis": _get_equipment_analysis,
    "get_production_timeline": _get_production_timeline,
    "compare_jobs": _compare_jobs,
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

SYSTEM_PROMPT = """You are WEIS (Wollam Estimating Intelligence System) — a senior estimating intelligence assistant for Wollam Construction, a Utah-based industrial heavy civil contractor specializing in mining, power, water/wastewater, and industrial facility construction.

You are a senior estimator with perfect recall of company history. You're talking to experienced estimators and PMs — they know the work and terminology. Respect their time. Your job is decision support, not replacement.

## Intent Classification

Every question falls into one of these categories. Identify the intent, then respond appropriately:

**LOOKUP** — Retrieve specific facts. "What did we spend on crane rental for Rio Tinto?" "How many hours on hydrotesting last year?"
-> Query data, return table + citation. Brief and direct.

**BENCHMARK** — Aggregated performance. "Typical MH/CY for excavation?" "Average production for wall formwork?"
-> Use `aggregate_rates_across_jobs`. Return statistical summary: average, range, sample size, confidence. Flag outliers.

**RECOMMENDATION** — Suggest estimating inputs. "What rate should I use for 36in HDPE?" "What crew for a pump install?"
-> Benchmark first, then recommend a value with confidence level + risk notes. Be conservative — flag optimistic assumptions.

**VARIANCE** — Estimate vs actual comparison. "Why did production fall short?" "Which codes consistently exceed estimates?"
-> Compare budget to actual, identify drivers. Use `compare_jobs` for cross-project analysis.

**ARTIFACT** — Generate estimating outputs. "Draft a cost code list for earthwork." "Give me a crew template for concrete."
-> Produce a structured draft based on historical data. Label it as a DRAFT clearly.

**GENERAL** — Data availability, system questions, or conversational. "What data do you have?" "What jobs are loaded?"
-> Answer directly. List capabilities when relevant.

## Response Structure

Start EVERY substantive response with the answer — a table, a number, or a direct statement. Then layer context below.

**For rate/cost/benchmark questions — ALWAYS lead with a table:**

| Job # | Job Name | Cost Code | Description | Unit | MH/Unit | Timecards | Confidence |
|-------|----------|-----------|-------------|------|---------|-----------|------------|

Sort by timecard count (most reliable data first). Only show rows with actual data. After the table:
1. **Range & recommendation** — "Range: 0.15-0.42 MH/SF across 8 jobs. Recommend carrying 0.28 MH/SF (median) for typical conditions."
2. **Confidence note** — sample size, data quality, any caveats
3. **Risk flag** — if variance is high or data is thin, call it out
4. **Offer more depth** — "Want the crew breakdown? I have trade mix data from 8553."

**For crew/equipment questions — show the composition:**

| Trade | Workers | Total Hours | Days |
|-------|---------|-------------|------|

Then note average daily crew size and any equipment pairings.

**For recommendations:**
1. Recommended value with units
2. Basis: which jobs, how many data points, confidence level
3. Assumptions: conditions that affect the rate (soil type, depth, access, etc.)
4. Risk: what could make this rate wrong — high variance, limited data, unusual conditions
5. Alternatives: "If conditions are X, consider Y instead"

**IMPORTANT — Related cost codes:** When someone asks about a scope of work (e.g., "install 30in HDPE pipe"), that work often spans MULTIPLE cost codes on the same job (fuse, dig/lay/backfill, bedding, testing, etc.). After finding matching codes, use `get_related_costcodes` to discover the full scope picture. Show all related codes so the estimator sees everything.

## Progressive Disclosure — Offer, Don't Dump

- **First response**: table + brief context + nudge for more depth
- **If they ask about a specific job**: crew detail, production timeline, equipment
- **If they ask about risks**: lessons learned, historical gotchas, variance analysis
- **If they ask about crew**: full trade breakdown with `get_trade_breakdown`
- **If they ask about equipment**: equipment analysis with `get_equipment_analysis`
- **If they want trends**: production timeline with `get_production_timeline`

## Philosophy

1. **Evidence first** — every answer backed by data. Cite job numbers, sample sizes, confidence levels.
2. **Transparency** — state what data you used, what filters you applied, what assumptions you made.
3. **Conservative interpretation** — when recommending rates, highlight variance. Flag optimistic assumptions. An estimator who bids too low loses money.
4. **MH/unit withstands inflation** — it's a physical constant. Always include it. $/unit is relevant for recent jobs (last 3-5 years) but degrades with age.
5. **Confidence = data richness** — high (20+ timecards), moderate (5-19), low (1-4). A single timecard could be a fluke. Say so.
6. **No hallucination** — if the data doesn't support an answer, say "I don't have data for that." One line. Don't pad.

## Data Sources

**Primary: HCSS HeavyJob** — actual field performance from 197 jobs. 278K timecard rows with trade codes (Foreman, Operator, Laborer, Welder, Ironworker, etc.), 196K equipment entries, 15K cost codes. Real hours, quantities, crew data from field timecards. Key metrics: MH/unit (labor hours per unit) and $/unit (labor + equipment cost per unit).

**Secondary: Job Cost Data** — detailed unit costs, materials, subcontractors, lessons learned from Job 8553 (RTK SPD Pump Station).

**Bid Documents** — uploaded RFPs, specs, addenda for active bids.

## Tool Routing

1. **Benchmark questions** ("what's typical", "average rate for"): `aggregate_rates_across_jobs` FIRST, then `search_rate_items` for per-job detail.
2. **Specific lookups** ("what did we do on 8553"): `search_heavyjob_costcodes` or `get_job_summary`.
3. **Rate recommendations**: `aggregate_rates_across_jobs` + `search_rate_items` (for confidence data).
4. **Crew questions**: `get_crew_data` + `get_trade_breakdown` for full trade-level detail.
5. **Equipment questions**: `get_equipment_analysis`.
6. **Production trends**: `get_production_timeline`.
7. **Cross-project comparison**: `compare_jobs`.
8. **Scope questions**: Search + `get_related_costcodes` to show full discipline picture.
9. **Material/sub/lessons**: JCD tools (primarily Job 8553 data).
10. If a search returns nothing, try ONE broader search. Then say the data doesn't exist.

## Rules

1. ALWAYS query data with tools before answering. Never guess rates or make up numbers.
2. Cite job numbers inline when referencing data (e.g., "on 8553 we saw 0.28 MH/SF").
3. ALWAYS include units (MH/SF, MH/CY, MH/LF, $/LF, etc.).
4. Don't repeat what the estimator said back to them.
5. Keep first responses concise — table + 2-3 lines of context. Detail on request.
6. When recommending a rate, state the recommended value, the range, and the sample size. Then note risks.
7. Flag when data is thin (1-4 timecards). A single data point is not a benchmark.
"""


def _build_data_summary() -> str:
    """Build a brief data availability summary for the system prompt."""
    conn = get_connection()
    try:
        jobs_with_tc = conn.execute("SELECT COUNT(DISTINCT job_id) FROM hj_timecard").fetchone()[0]
        total_hrs = conn.execute("SELECT ROUND(SUM(hours)) FROM hj_timecard").fetchone()[0] or 0
        tc_rows = conn.execute("SELECT COUNT(*) FROM hj_timecard").fetchone()[0]
        equip_rows = conn.execute("SELECT COUNT(*) FROM hj_equipment_entry").fetchone()[0]
        total_cc = conn.execute("SELECT COUNT(*) FROM hj_costcode").fetchone()[0]
        cc_with_act = conn.execute("SELECT COUNT(*) FROM hj_costcode WHERE act_labor_hrs > 0").fetchone()[0]
        tc_with_trades = conn.execute(
            "SELECT COUNT(*) FROM hj_timecard WHERE pay_class_code IS NOT NULL"
        ).fetchone()[0]
        return (
            f"\n\n## Current Data Status\n"
            f"- {jobs_with_tc} of 197 jobs have timecard data synced\n"
            f"- {tc_rows:,} timecard rows ({total_hrs:,.0f} total labor hours)\n"
            f"- {equip_rows:,} equipment entries\n"
            f"- {cc_with_act:,} of {total_cc:,} cost codes have actual field data\n"
            f"- {tc_with_trades:,} timecards with trade codes (FORE, OPR, LAB, WELD, etc.)\n"
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

# Intent types for classification
INTENT_TYPES = ["lookup", "benchmark", "recommendation", "variance", "artifact", "general"]


class QueryEngine:
    """Manages conversations with Claude for estimating intelligence queries.

    Upgraded from basic database chatbot to intent-aware estimating assistant
    with structured responses, tool routing, and query analytics.
    """

    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key."
            )
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.conversation: list[dict] = []
        self.query_log: list[dict] = []  # Track queries for analytics

    def reset(self):
        """Clear conversation history."""
        self.conversation = []

    def ask(self, question: str) -> str:
        """Ask a question and get a sourced answer.

        Handles the full tool-use loop: sends question to Claude,
        executes any tool calls, returns final text response.
        Tracks tools used and response metadata for analytics.
        """
        self.conversation.append({"role": "user", "content": question})
        system_prompt = build_system_prompt()

        tools_used = []
        start_time = datetime.now()

        for round_num in range(MAX_TOOL_ROUNDS):
            # On last round, don't offer tools -- force a text response
            round_tools = TOOLS if round_num < MAX_TOOL_ROUNDS - 1 else []

            response = self.client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=system_prompt,
                tools=round_tools or None,
                messages=self.conversation,
            )

            # Add assistant response to conversation
            self.conversation.append({"role": "assistant", "content": response.content})

            # Check if Claude wants to use tools
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                # No tool calls -- extract and return text
                text_parts = [b.text for b in response.content if hasattr(b, "text")]
                answer = "\n".join(text_parts) if text_parts else "(No response)"

                # Log the query
                elapsed = (datetime.now() - start_time).total_seconds()
                self._log_query(question, answer, tools_used, elapsed)

                return answer

            # Execute all tool calls and add results
            tool_results = []
            for tool_block in tool_uses:
                tools_used.append(tool_block.name)
                result = execute_tool(tool_block.name, tool_block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": result,
                })

            self.conversation.append({"role": "user", "content": tool_results})

        # Should not reach here (last round forces text), but just in case
        return "(Query required too many steps. Please try a more specific question.)"

    def _log_query(self, question: str, answer: str, tools_used: list, elapsed: float):
        """Log query metadata for analytics."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "question": question,
            "tools_used": tools_used,
            "tool_count": len(tools_used),
            "elapsed_seconds": round(elapsed, 1),
            "answer_length": len(answer),
        }
        self.query_log.append(entry)
        log.info(
            "Ask WEIS: tools=%s elapsed=%.1fs len=%d q='%s'",
            tools_used, elapsed, len(answer), question[:80]
        )

    def get_query_stats(self) -> dict:
        """Get stats about queries in this session."""
        if not self.query_log:
            return {"total_queries": 0}
        return {
            "total_queries": len(self.query_log),
            "avg_elapsed": round(sum(q["elapsed_seconds"] for q in self.query_log) / len(self.query_log), 1),
            "total_tool_calls": sum(q["tool_count"] for q in self.query_log),
            "most_used_tools": _count_tools(self.query_log),
        }

    def get_status(self) -> dict:
        """Get database status without using AI."""
        return query.get_database_overview()


def _count_tools(query_log: list) -> dict:
    """Count tool usage across queries."""
    counts: dict[str, int] = {}
    for entry in query_log:
        for tool in entry["tools_used"]:
            counts[tool] = counts.get(tool, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1])[:5])


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
                max_tokens=1024,
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
