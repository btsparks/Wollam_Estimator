"""AI Estimating Chat Service — SQL tool + Claude API.

The core engine for WEIS estimating chat. Claude queries the database
directly via a run_sql tool, then assembles data-backed answers with
source citations.

All database queries live here; the API layer is a thin wrapper.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

import anthropic

from app.config import ANTHROPIC_API_KEY
from app.database import get_connection
from app.services.cost_report_import import get_data_quality
from app.services.sql_tool import (
    SCHEMA_DESCRIPTION,
    TOOL_DEFINITION,
    execute_sql,
)

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOOL_CALLS = 5  # Cap tool-use iterations per message

# ─────────────────────────────────────────────────────────────
# Signal Dictionaries — keyword detection for intent parsing
# ─────────────────────────────────────────────────────────────

DISCIPLINE_SIGNALS = {
    "concrete": [
        "concrete", "forming", "rebar", "pour", "slab", "wall",
        "foundation", "formwork", "footing", "stem", "cure",
    ],
    "earthwork": [
        "excavation", "fill", "grading", "backfill", "earthwork",
        "dig", "haul", "compaction", "topsoil", "trench", "embankment",
    ],
    "structural_steel": [
        "steel", "erection", "iron", "bolting", "welding",
        "structural", "beam", "column", "joist",
    ],
    "piping": [
        "pipe", "piping", "fuse", "hdpe", "flanged", "weld",
        "hydrotest", "valve", "fitting",
    ],
    "electrical": [
        "electrical", "conduit", "wire", "panel", "duct bank",
        "grounding", "cable",
    ],
    "mechanical": [
        "pump", "mechanical", "equipment", "alignment", "grout", "skid",
    ],
    "building": [
        "pemb", "metal building", "erection", "siding", "roofing",
    ],
    "general_conditions": [
        "gc", "general conditions", "supervision", "management",
        "mob", "demob",
    ],
}

RATE_SIGNALS = {
    "mh_per_unit": ["mh/", "man-hours per", "labor rate", "manhours", "man hours"],
    "cost_per_unit": ["$/", "cost per", "dollars per", "price per", "all-in"],
    "production": ["production", "output", "per day", "per hour", "per shift"],
    "crew": ["crew", "crew size", "how many", "team", "workers"],
}

ESTIMATE_SIGNALS = [
    "estimate", "bid", "budgeted", "proposed", "what was bid",
    "heavybid", "bid price", "bid item", "bid total", "estimated",
    "bid vs actual", "bid versus actual", "estimate vs actual",
]


# ─────────────────────────────────────────────────────────────
# Intent Parsing
# ─────────────────────────────────────────────────────────────

def detect_signals(message: str) -> dict:
    """Parse user message to detect discipline, rate type, keyword, and job signals.

    Returns {"disciplines": [...], "rate_types": [...], "keywords": [...],
             "job_numbers": [...], "job_name_keywords": [...]}.
    """
    msg_lower = message.lower()

    # Detect explicit job numbers (4-digit patterns like 8540, 8553)
    job_numbers = re.findall(r"\b(8\d{3})\b", message)

    # Detect disciplines
    disciplines = []
    for disc, keywords in DISCIPLINE_SIGNALS.items():
        for kw in keywords:
            if kw in msg_lower:
                if disc not in disciplines:
                    disciplines.append(disc)
                break

    # Detect rate types
    rate_types = []
    for rtype, keywords in RATE_SIGNALS.items():
        for kw in keywords:
            if kw in msg_lower:
                if rtype not in rate_types:
                    rate_types.append(rtype)
                break

    # Extract content keywords — words 4+ chars, excluding common stop words
    stop_words = {
        "what", "that", "this", "with", "from", "have", "been", "were",
        "they", "their", "about", "would", "could", "should", "which",
        "there", "where", "when", "your", "much", "many", "some", "good",
        "best", "does", "will", "also", "just", "than", "then", "more",
        "most", "like", "into", "over", "such", "only", "each", "well",
        "very", "historical", "looking", "need", "want", "know", "find",
        "show", "give", "tell",
    }
    words = re.findall(r"[a-z]{4,}", msg_lower)
    keywords = [w for w in words if w not in stop_words]
    # Deduplicate while preserving order
    seen = set()
    unique_keywords = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique_keywords.append(w)

    # Job name keywords — words that might match job names (not stop words, not disciplines)
    # These are used to search job.name for project matching
    discipline_words = set()
    for kws in DISCIPLINE_SIGNALS.values():
        discipline_words.update(kws)
    job_name_keywords = [
        w for w in unique_keywords
        if w not in discipline_words and len(w) >= 4
    ]

    # Detect estimate intent
    estimate_intent = any(kw in msg_lower for kw in ESTIMATE_SIGNALS)

    return {
        "disciplines": disciplines,
        "rate_types": rate_types,
        "keywords": unique_keywords,
        "job_numbers": job_numbers,
        "job_name_keywords": job_name_keywords,
        "estimate_intent": estimate_intent,
    }


# ─────────────────────────────────────────────────────────────
# Database Search
# ─────────────────────────────────────────────────────────────

def search_rate_items(signals: dict) -> list[dict]:
    """Query rate_item + rate_card + job tables to find matching data.

    Search strategy:
    1. Job number match (explicit 8xxx references)
    2. Job name match (keywords matching project names)
    3. Discipline match on rate_item.discipline
    4. Keyword match on rate_item.description
    5. Filter to items with actual data
    6. Order by confidence DESC, timecard_count DESC
    7. Limit to top 30 results
    """
    conn = get_connection()
    try:
        disciplines = signals.get("disciplines", [])
        keywords = signals.get("keywords", [])
        job_numbers = signals.get("job_numbers", [])
        job_name_keywords = signals.get("job_name_keywords", [])

        # --- Strategy 1: If explicit job numbers given, search those jobs ---
        if job_numbers:
            return _search_by_jobs(conn, job_numbers, disciplines, keywords)

        # --- Strategy 2: If job name keywords, find matching jobs first ---
        if job_name_keywords:
            matched_jobs = _find_jobs_by_name(conn, job_name_keywords)
            if matched_jobs:
                # Only use discipline signals to filter, not keywords
                # (keywords were used to find the jobs, not to filter cost codes)
                return _search_by_job_ids(conn, matched_jobs, disciplines, [])

        # --- Strategy 3: Discipline + keyword search (original approach) ---
        return _search_by_signals(conn, disciplines, keywords)

    finally:
        conn.close()


def _find_jobs_by_name(conn, name_keywords: list[str]) -> list[int]:
    """Find job_ids whose name matches any of the keywords."""
    clauses = []
    params = []
    for kw in name_keywords[:5]:
        clauses.append("j.name LIKE ?")
        params.append(f"%{kw}%")

    if not clauses:
        return []

    rows = conn.execute(f"""
        SELECT j.job_id FROM job j
        WHERE {' OR '.join(clauses)}
        LIMIT 10
    """, params).fetchall()
    return [r["job_id"] for r in rows]


def _search_by_jobs(conn, job_numbers: list[str], disciplines: list[str],
                    keywords: list[str]) -> list[dict]:
    """Search rate items for specific job numbers."""
    placeholders = ", ".join("?" for _ in job_numbers)
    params = list(job_numbers)

    # Additional filters
    extra = ""
    if disciplines:
        disc_ph = ", ".join("?" for _ in disciplines)
        extra += f" AND ri.discipline IN ({disc_ph})"
        params.extend(disciplines)

    # Keyword filter on description (optional narrowing)
    if keywords and disciplines:
        # If we have both, use keywords as additional OR filter
        kw_clauses = []
        for kw in keywords[:10]:
            kw_clauses.append("ri.description LIKE ?")
            params.append(f"%{kw}%")
        extra += f" AND (ri.discipline IN ({', '.join('?' for _ in disciplines)}) OR ({' OR '.join(kw_clauses)}))"
        params.extend(disciplines)

    query = f"""
        SELECT
            ri.item_id, ri.card_id, ri.discipline,
            ri.activity as cost_code, ri.description, ri.unit,
            ri.act_mh_per_unit, ri.act_cost_per_unit,
            ri.confidence, ri.confidence_reason,
            ri.timecard_count, ri.work_days,
            ri.crew_size_avg, ri.daily_qty_avg, ri.daily_qty_peak,
            ri.total_hours, ri.total_qty,
            ri.total_labor_cost, ri.total_equip_cost,
            ri.crew_breakdown,
            rc.job_id, j.job_number, j.name as job_name
        FROM rate_item ri
        JOIN rate_card rc ON ri.card_id = rc.card_id
        JOIN job j ON rc.job_id = j.job_id
        WHERE j.job_number IN ({placeholders})
          AND (ri.act_mh_per_unit IS NOT NULL OR ri.timecard_count > 0)
          {extra}
        ORDER BY
            j.job_number,
            CASE ri.confidence
                WHEN 'high' THEN 1 WHEN 'strong' THEN 1
                WHEN 'moderate' THEN 2 WHEN 'medium' THEN 2
                WHEN 'limited' THEN 3 WHEN 'low' THEN 3
                ELSE 4
            END ASC,
            ri.timecard_count DESC
        LIMIT 30
    """
    return _execute_rate_query(conn, query, params)


def _search_by_job_ids(conn, job_ids: list[int], disciplines: list[str],
                       keywords: list[str]) -> list[dict]:
    """Search rate items for specific job IDs (from name matching)."""
    placeholders = ", ".join("?" for _ in job_ids)
    params = list(job_ids)

    extra_filters = []
    if disciplines:
        disc_ph = ", ".join("?" for _ in disciplines)
        extra_filters.append(f"ri.discipline IN ({disc_ph})")
        params.extend(disciplines)

    kw_clauses = []
    for kw in keywords[:10]:
        kw_clauses.append("ri.description LIKE ?")
        params.append(f"%{kw}%")

    filter_sql = ""
    if extra_filters and kw_clauses:
        filter_sql = f"AND ({' AND '.join(extra_filters)} OR ({' OR '.join(kw_clauses)}))"
    elif extra_filters:
        filter_sql = f"AND {' AND '.join(extra_filters)}"
    elif kw_clauses:
        filter_sql = f"AND ({' OR '.join(kw_clauses)})"

    query = f"""
        SELECT
            ri.item_id, ri.card_id, ri.discipline,
            ri.activity as cost_code, ri.description, ri.unit,
            ri.act_mh_per_unit, ri.act_cost_per_unit,
            ri.confidence, ri.confidence_reason,
            ri.timecard_count, ri.work_days,
            ri.crew_size_avg, ri.daily_qty_avg, ri.daily_qty_peak,
            ri.total_hours, ri.total_qty,
            ri.total_labor_cost, ri.total_equip_cost,
            ri.crew_breakdown,
            rc.job_id, j.job_number, j.name as job_name
        FROM rate_item ri
        JOIN rate_card rc ON ri.card_id = rc.card_id
        JOIN job j ON rc.job_id = j.job_id
        WHERE rc.job_id IN ({placeholders})
          AND (ri.act_mh_per_unit IS NOT NULL OR ri.timecard_count > 0)
          {filter_sql}
        ORDER BY
            CASE ri.confidence
                WHEN 'high' THEN 1 WHEN 'strong' THEN 1
                WHEN 'moderate' THEN 2 WHEN 'medium' THEN 2
                WHEN 'limited' THEN 3 WHEN 'low' THEN 3
                ELSE 4
            END ASC,
            ri.timecard_count DESC
        LIMIT 30
    """
    return _execute_rate_query(conn, query, params)


def _search_by_signals(conn, disciplines: list[str], keywords: list[str]) -> list[dict]:
    """Original signal-based search — discipline + keyword matching."""
    where_parts = []
    params = []

    where_parts.append("(ri.act_mh_per_unit IS NOT NULL OR ri.timecard_count > 0)")

    if disciplines:
        disc_placeholders = ", ".join("?" for _ in disciplines)
        where_parts.append(f"(ri.discipline IN ({disc_placeholders}))")
        params.extend(disciplines)

    keyword_clauses = []
    for kw in keywords[:10]:
        keyword_clauses.append("ri.description LIKE ?")
        params.append(f"%{kw}%")

    if disciplines and keyword_clauses:
        disc_clause = where_parts.pop()
        actual_clause = where_parts.pop()
        combined = f"{actual_clause} AND ({disc_clause} OR ({' OR '.join(keyword_clauses)}))"
        where_parts.append(combined)
    elif keyword_clauses:
        where_parts.append(f"({' OR '.join(keyword_clauses)})")

    where_sql = " AND ".join(where_parts) if where_parts else "1=1"

    if not disciplines and not keywords:
        where_sql = "(ri.act_mh_per_unit IS NOT NULL OR ri.timecard_count > 0)"
        params = []

    query = f"""
        SELECT
            ri.item_id, ri.card_id, ri.discipline,
            ri.activity as cost_code, ri.description, ri.unit,
            ri.act_mh_per_unit, ri.act_cost_per_unit,
            ri.confidence, ri.confidence_reason,
            ri.timecard_count, ri.work_days,
            ri.crew_size_avg, ri.daily_qty_avg, ri.daily_qty_peak,
            ri.total_hours, ri.total_qty,
            ri.total_labor_cost, ri.total_equip_cost,
            ri.crew_breakdown,
            rc.job_id, j.job_number, j.name as job_name
        FROM rate_item ri
        JOIN rate_card rc ON ri.card_id = rc.card_id
        JOIN job j ON rc.job_id = j.job_id
        WHERE {where_sql}
        ORDER BY
            CASE ri.confidence
                WHEN 'high' THEN 1 WHEN 'strong' THEN 1
                WHEN 'moderate' THEN 2 WHEN 'medium' THEN 2
                WHEN 'limited' THEN 3 WHEN 'low' THEN 3
                ELSE 4
            END ASC,
            ri.timecard_count DESC
        LIMIT 30
    """
    return _execute_rate_query(conn, query, params)


def _execute_rate_query(conn, query: str, params: list) -> list[dict]:
    """Execute a rate item query and parse results."""
    rows = conn.execute(query, params).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        if item.get("crew_breakdown"):
            try:
                item["crew_breakdown"] = json.loads(item["crew_breakdown"])
            except (json.JSONDecodeError, TypeError):
                item["crew_breakdown"] = None
        results.append(item)
    return results


def search_costcodes_direct(signals: dict, exclude_pairs: set[tuple] = None) -> list[dict]:
    """Fallback search: query hj_costcode directly for cost codes not in rate_item.

    Used when rate_item search returns sparse results. Finds cost codes with
    actual hours/quantities that may not have rate cards calculated.

    Args:
        signals: Parsed signal dict from detect_signals().
        exclude_pairs: Set of (job_id, cost_code) tuples already found via rate_item.

    Returns list of dicts with source='hj_costcode' flag.
    """
    if exclude_pairs is None:
        exclude_pairs = set()

    conn = get_connection()
    try:
        job_numbers = signals.get("job_numbers", [])
        job_name_keywords = signals.get("job_name_keywords", [])
        keywords = signals.get("keywords", [])

        where_parts = ["(cc.act_labor_hrs > 0 OR cc.act_qty > 0)"]
        params = []

        # Job number filter
        if job_numbers:
            ph = ", ".join("?" for _ in job_numbers)
            where_parts.append(f"j.job_number IN ({ph})")
            params.extend(job_numbers)
        elif job_name_keywords:
            # Find matching jobs by name
            name_clauses = []
            for kw in job_name_keywords[:5]:
                name_clauses.append("j.name LIKE ?")
                params.append(f"%{kw}%")
            where_parts.append(f"({' OR '.join(name_clauses)})")

        # Keyword filter on description
        if keywords:
            kw_clauses = []
            for kw in keywords[:10]:
                kw_clauses.append("cc.description LIKE ?")
                params.append(f"%{kw}%")
            where_parts.append(f"({' OR '.join(kw_clauses)})")

        # Need at least one filter beyond the actuals check
        if len(where_parts) < 2:
            return []

        where_sql = " AND ".join(where_parts)

        rows = conn.execute(f"""
            SELECT
                cc.cc_id, cc.job_id, cc.code, cc.description, cc.unit,
                cc.act_labor_hrs, cc.act_qty, cc.act_labor_cost,
                cc.act_equip_hrs, cc.act_equip_cost,
                cc.bgt_labor_hrs, cc.bgt_qty,
                j.job_number, j.name as job_name
            FROM hj_costcode cc
            JOIN job j ON cc.job_id = j.job_id
            WHERE {where_sql}
            ORDER BY cc.act_labor_hrs DESC
            LIMIT 20
        """, params).fetchall()

        results = []
        for row in rows:
            item = dict(row)
            # Skip if already found via rate_item
            if (item["job_id"], item["code"]) in exclude_pairs:
                continue
            # Calculate MH/unit if possible
            mh_per_unit = None
            if item["act_labor_hrs"] and item["act_qty"] and item["act_qty"] > 0:
                mh_per_unit = item["act_labor_hrs"] / item["act_qty"]
            item["act_mh_per_unit"] = mh_per_unit
            item["cost_code"] = item["code"]
            item["source"] = "hj_costcode"
            results.append(item)
            if len(results) >= 15:
                break

        return results
    finally:
        conn.close()


def search_estimates(signals: dict) -> list[dict]:
    """Search HeavyBid estimates when estimate intent is detected.

    Returns estimate-level summary + relevant bid items and activities.
    """
    conn = get_connection()
    try:
        job_numbers = signals.get("job_numbers", [])
        job_name_keywords = signals.get("job_name_keywords", [])
        keywords = signals.get("keywords", [])

        # Find matching estimates
        where_parts = []
        params = []

        if job_numbers:
            # Match by linked_job_number or by code prefix
            jn_clauses = []
            for jn in job_numbers:
                jn_clauses.append("e.linked_job_number = ?")
                params.append(jn)
                jn_clauses.append("e.code LIKE ?")
                params.append(f"{jn}%")
            where_parts.append(f"({' OR '.join(jn_clauses)})")
        elif job_name_keywords:
            name_clauses = []
            for kw in job_name_keywords[:5]:
                name_clauses.append("(e.name LIKE ? OR e.project_name LIKE ?)")
                params.extend([f"%{kw}%", f"%{kw}%"])
            where_parts.append(f"({' OR '.join(name_clauses)})")

        where_sql = " AND ".join(where_parts) if where_parts else "1=1"

        est_rows = conn.execute(f"""
            SELECT
                e.estimate_id, e.code, e.name, e.description,
                e.bid_total, e.total_manhours,
                e.total_labor, e.total_equip, e.total_subcontract,
                e.total_perm_material, e.total_const_material,
                e.estimator, e.bid_date, e.job_duration,
                e.linked_job_number, e.linked_job_id
            FROM hb_estimate e
            WHERE {where_sql}
            ORDER BY e.bid_total DESC
            LIMIT 5
        """, params).fetchall()

        results = []
        for est in est_rows:
            est_data = dict(est)
            est_id = est_data["estimate_id"]

            # Fetch bid items for this estimate
            bi_params = [est_id]
            bi_extra = ""
            if keywords:
                kw_clauses = []
                for kw in keywords[:10]:
                    kw_clauses.append("bi.description LIKE ?")
                    bi_params.append(f"%{kw}%")
                # If keywords given, filter bid items — but also include all if few match
                bi_extra = f"AND ({' OR '.join(kw_clauses)})"

            bid_items = conn.execute(f"""
                SELECT
                    bi.biditem_id, bi.biditem_code, bi.description,
                    bi.quantity, bi.bid_quantity, bi.units,
                    bi.bid_price, bi.labor, bi.manhours,
                    bi.total_cost, bi.direct_total,
                    bi.cost_notes, bi.bid_notes
                FROM hb_biditem bi
                WHERE bi.estimate_id = ? {bi_extra}
                ORDER BY bi.manhours DESC NULLS LAST
                LIMIT 15
            """, bi_params).fetchall()

            # If keyword filter returned nothing, get all bid items
            if not bid_items and keywords:
                bid_items = conn.execute("""
                    SELECT
                        bi.biditem_id, bi.biditem_code, bi.description,
                        bi.quantity, bi.bid_quantity, bi.units,
                        bi.bid_price, bi.labor, bi.manhours,
                        bi.total_cost, bi.direct_total,
                        bi.cost_notes, bi.bid_notes
                    FROM hb_biditem bi
                    WHERE bi.estimate_id = ?
                    ORDER BY bi.manhours DESC NULLS LAST
                    LIMIT 15
                """, [est_id]).fetchall()

            est_data["bid_items"] = [dict(bi) for bi in bid_items]

            # Fetch activities for this estimate
            activities = conn.execute("""
                SELECT
                    a.activity_id, a.activity_code, a.description,
                    a.quantity, a.units, a.production_rate, a.production_type,
                    a.crew, a.man_hours, a.crew_hours,
                    a.labor, a.direct_total,
                    a.notes, a.biditem_code,
                    a.heavyjob_code, a.heavyjob_description
                FROM hb_activity a
                WHERE a.estimate_id = ?
                ORDER BY a.man_hours DESC NULLS LAST
                LIMIT 25
            """, [est_id]).fetchall()

            est_data["activities"] = [dict(a) for a in activities]
            est_data["source_type"] = "estimate"
            results.append(est_data)

        return results
    finally:
        conn.close()


def build_estimate_context(estimate_data: list[dict]) -> str:
    """Build the ESTIMATE DATA section for the context block."""
    if not estimate_data:
        return ""

    lines = ["---", "ESTIMATE DATA (what was bid):\n"]

    for est in estimate_data:
        code = est.get("code", "?")
        name = est.get("name", "Unknown")
        bid_total = est.get("bid_total") or 0
        total_mh = est.get("total_manhours") or 0
        labor = est.get("total_labor") or 0
        equip = est.get("total_equip") or 0
        sub = est.get("total_subcontract") or 0
        estimator = est.get("estimator") or "Unknown"
        bid_date = est.get("bid_date") or "Unknown"
        linked = est.get("linked_job_number") or "None"
        duration = est.get("job_duration")

        lines.append(f"ESTIMATE {code} — {name}")
        lines.append(f"Bid Total: ${bid_total:,.0f} | Total MH: {total_mh:,.0f}")
        lines.append(f"Labor: ${labor:,.0f} | Equip: ${equip:,.0f} | Sub: ${sub:,.0f}")
        lines.append(f"Estimator: {estimator} | Bid Date: {bid_date}")
        lines.append(f"Linked Job: {linked}")
        if duration:
            lines.append(f"Job Duration: {duration:.0f} days")
        lines.append("")

        # Bid items
        for bi in est.get("bid_items", []):
            bi_code = bi.get("biditem_code") or "?"
            bi_desc = bi.get("description") or "No description"
            bi_qty = bi.get("quantity") or bi.get("bid_quantity")
            bi_units = bi.get("units") or ""
            bi_price = bi.get("bid_price")
            bi_labor = bi.get("labor") or 0
            bi_mh = bi.get("manhours") or 0
            bi_cost_notes = bi.get("cost_notes")
            bi_bid_notes = bi.get("bid_notes")

            lines.append(f"  Bid Item {bi_code} — {bi_desc}")
            parts = []
            if bi_qty:
                parts.append(f"Qty: {bi_qty:,.1f} {bi_units}")
            if bi_price:
                parts.append(f"Bid Price: ${bi_price:,.2f}/{bi_units}")
            if bi_mh:
                parts.append(f"MH: {bi_mh:,.0f}")
            if bi_labor:
                parts.append(f"Labor: ${bi_labor:,.0f}")
            if parts:
                lines.append(f"  {' | '.join(parts)}")
            if bi_cost_notes:
                lines.append(f"  Cost Notes: {bi_cost_notes}")
            if bi_bid_notes:
                lines.append(f"  Bid Notes: {bi_bid_notes}")
            lines.append("")

        # Activities (grouped summary)
        activities = est.get("activities", [])
        if activities:
            lines.append("  Activities:")
            for act in activities:
                act_code = act.get("activity_code") or "?"
                act_desc = act.get("description") or ""
                act_qty = act.get("quantity")
                act_units = act.get("units") or ""
                act_prod = act.get("production_rate")
                act_crew = act.get("crew") or ""
                act_mh = act.get("man_hours") or 0
                act_notes = act.get("notes")
                hj_code = act.get("heavyjob_code")

                act_line = f"    {act_code} — {act_desc}"
                act_parts = []
                if act_qty:
                    act_parts.append(f"Qty: {act_qty:,.1f} {act_units}")
                if act_prod:
                    act_parts.append(f"Prod: {act_prod:,.1f} {act_units}/day")
                if act_crew:
                    act_parts.append(f"Crew: {act_crew}")
                if act_mh:
                    act_parts.append(f"MH: {act_mh:,.0f}")
                if hj_code:
                    act_parts.append(f"HJ Code: {hj_code}")
                lines.append(act_line)
                if act_parts:
                    lines.append(f"    {' | '.join(act_parts)}")
                if act_notes:
                    lines.append(f"    Notes: {act_notes}")

            lines.append("")
        lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# PM Context Retrieval
# ─────────────────────────────────────────────────────────────

def get_pm_context(job_id: int, cost_code: str = None) -> dict:
    """Get PM context at job level and optionally cost code level.

    Returns {
        "job": {project_summary, site_conditions, key_challenges, ...} or None,
        "cost_code": {scope_included, scope_excluded, conditions, notes} or None,
    }
    """
    conn = get_connection()
    try:
        # Job-level PM context
        pm_row = conn.execute(
            "SELECT * FROM pm_context WHERE job_id = ?", (job_id,)
        ).fetchone()
        pm = dict(pm_row) if pm_row else None

        # Cost-code-level context
        cc = None
        if cost_code:
            cc_row = conn.execute(
                "SELECT * FROM cc_context WHERE job_id = ? AND cost_code = ?",
                (job_id, cost_code),
            ).fetchone()
            cc = dict(cc_row) if cc_row else None

        return {"job": pm, "cost_code": cc}
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Foreman Notes Retrieval
# ─────────────────────────────────────────────────────────────

def get_foreman_notes(job_id: int, cost_code: str, limit: int = 5) -> list[str]:
    """Get the most informative foreman notes for a cost code on a job.

    Returns up to `limit` unique notes, filtered for substance (10+ chars),
    ordered by most recent first. These are field-level observations written
    by foremen on their daily timecards in HeavyJob.
    """
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT DISTINCT notes
            FROM hj_timecard
            WHERE job_id = ? AND cost_code = ?
              AND notes IS NOT NULL AND LENGTH(notes) >= 10
            ORDER BY date DESC
            LIMIT ?
        """, (job_id, cost_code, limit)).fetchall()
        return [r["notes"] for r in rows]
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Context Block Assembly
# ─────────────────────────────────────────────────────────────

def build_context_block(rate_items: list[dict], signals: dict,
                        costcode_items: list[dict] = None,
                        estimate_data: list[dict] = None) -> str:
    """Assemble a structured text block for Claude from rate items and PM context.

    Groups items by job and includes all available context for each.
    costcode_items: Optional fallback results from hj_costcode (raw actuals, no rate card).
    estimate_data: Optional HeavyBid estimate data.
    """
    if not rate_items and not costcode_items and not estimate_data:
        return (
            "AVAILABLE HISTORICAL DATA:\n\n"
            "No matching rate data found in the database for this query.\n\n"
            "---\n"
            "DATA GAPS:\n"
            "- No historical data matches the requested scope\n"
            "- Recommend getting vendor/subcontractor quotes"
        )

    # Group items by job
    jobs: dict[int, list[dict]] = {}
    for item in rate_items:
        jid = item["job_id"]
        if jid not in jobs:
            jobs[jid] = []
        jobs[jid].append(item)

    lines = ["AVAILABLE HISTORICAL DATA:\n"]
    data_gaps = []
    jobs_without_pm = []

    for job_id, items in jobs.items():
        job_number = items[0]["job_number"]
        job_name = items[0]["job_name"]

        # Get PM context for this job
        pm_ctx = get_pm_context(job_id)
        pm_job = pm_ctx["job"]

        lines.append(f"JOB {job_number} — {job_name}")

        if pm_job:
            if pm_job.get("project_summary"):
                lines.append(f"PM Context: {pm_job['project_summary']}")
            if pm_job.get("site_conditions"):
                lines.append(f"Site Conditions: {pm_job['site_conditions']}")
        else:
            jobs_without_pm.append(job_number)

        # Data quality warning from cost report comparison
        dq = get_data_quality(job_id)
        if dq["quality"] == "incomplete":
            lines.append(f"DATA WARNING: {dq['note']}. Rates from this job should be treated with caution.")
        elif dq["quality"] == "partial":
            lines.append(f"DATA NOTE: {dq['note']}.")

        lines.append("")

        for item in items:
            cc = item["cost_code"]
            desc = item.get("description") or "No description"
            unit = item.get("unit") or "—"

            lines.append(f"  Cost Code {cc} — {desc}")
            lines.append(f"  Unit: {unit}")

            # Production data
            total_qty = item.get("total_qty")
            total_hours = item.get("total_hours")
            mh_per_unit = item.get("act_mh_per_unit")

            if total_qty and total_hours:
                lines.append(
                    f"  Actual: {total_qty:,.0f} {unit} completed, "
                    f"{total_hours:,.0f} labor hours"
                )
            if mh_per_unit is not None:
                lines.append(f"  MH/Unit: {mh_per_unit:.4f} MH/{unit}")

            cost_per_unit = item.get("act_cost_per_unit")
            if cost_per_unit is not None:
                lines.append(f"  Cost/Unit: ${cost_per_unit:,.2f}/{unit}")

            # Confidence
            confidence = item.get("confidence", "unknown")
            confidence_reason = item.get("confidence_reason", "")
            tc_count = item.get("timecard_count", 0) or 0
            work_days = item.get("work_days", 0) or 0
            if confidence_reason:
                lines.append(f"  Confidence: {confidence.upper()} ({confidence_reason})")
            else:
                lines.append(
                    f"  Confidence: {confidence.upper()} "
                    f"({tc_count} timecards across {work_days} work days)"
                )

            # Crew
            crew_avg = item.get("crew_size_avg")
            crew_breakdown = item.get("crew_breakdown")
            if crew_avg:
                crew_str = f"  Daily Crew: Avg {crew_avg:.1f} workers"
                if crew_breakdown and isinstance(crew_breakdown, dict):
                    trades = crew_breakdown.get("trades", {})
                    if trades:
                        # Show top trades by worker count
                        trade_parts = []
                        for trade_name, count in sorted(
                            trades.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0, reverse=True
                        )[:5]:
                            if isinstance(count, dict):
                                trade_parts.append(f"{count.get('workers', '?')} {trade_name}")
                            else:
                                trade_parts.append(f"{count} {trade_name}")
                        crew_str += f" ({', '.join(trade_parts)})"
                lines.append(crew_str)

                # Equipment
                if crew_breakdown and isinstance(crew_breakdown, dict):
                    equipment = crew_breakdown.get("equipment", [])
                    if equipment:
                        equip_parts = []
                        for eq in equipment[:4]:
                            if isinstance(eq, dict):
                                equip_parts.append(
                                    f"{eq.get('desc', eq.get('code', '?'))} "
                                    f"({eq.get('days', '?')} days)"
                                )
                        if equip_parts:
                            lines.append(f"  Equipment: {', '.join(equip_parts)}")

            # Daily production
            daily_avg = item.get("daily_qty_avg")
            daily_peak = item.get("daily_qty_peak")
            if daily_avg:
                prod_str = f"  Daily Production: Avg {daily_avg:,.1f} {unit}/day"
                if daily_peak:
                    prod_str += f", Peak {daily_peak:,.1f} {unit}/day"
                lines.append(prod_str)

            # PM cost code context
            cc_ctx = get_pm_context(job_id, cc)
            cc_detail = cc_ctx.get("cost_code")
            if cc_detail:
                if cc_detail.get("scope_included"):
                    lines.append(f"  PM Context — Scope: {cc_detail['scope_included']}")
                if cc_detail.get("scope_excluded"):
                    lines.append(f"  PM Context — Excluded: {cc_detail['scope_excluded']}")
                if cc_detail.get("conditions"):
                    lines.append(f"  PM Context — Conditions: {cc_detail['conditions']}")
                if cc_detail.get("notes"):
                    lines.append(f"  PM Context — Notes: {cc_detail['notes']}")

            # Foreman notes from timecards
            foreman_notes = get_foreman_notes(job_id, cc)
            if foreman_notes:
                lines.append(f"  Foreman Notes ({len(foreman_notes)}):")
                for note in foreman_notes:
                    lines.append(f"    - {note}")

            lines.append("")

        lines.append("")

    # Raw costcode fallback section
    if costcode_items:
        lines.append("---")
        lines.append("RAW COST CODE ACTUALS (no rate card calculated):\n")
        cc_by_job: dict[int, list[dict]] = {}
        for cc_item in costcode_items:
            jid = cc_item["job_id"]
            if jid not in cc_by_job:
                cc_by_job[jid] = []
            cc_by_job[jid].append(cc_item)

        for jid, cc_items in cc_by_job.items():
            jnum = cc_items[0]["job_number"]
            jname = cc_items[0]["job_name"]
            lines.append(f"JOB {jnum} — {jname}")
            for cc_item in cc_items:
                code = cc_item["cost_code"]
                desc = cc_item.get("description") or "No description"
                unit = cc_item.get("unit") or "—"
                hrs = cc_item.get("act_labor_hrs") or 0
                qty = cc_item.get("act_qty") or 0
                mh = cc_item.get("act_mh_per_unit")
                lines.append(f"  Cost Code {code} — {desc}")
                lines.append(f"  Unit: {unit}")
                if hrs:
                    lines.append(f"  Actual Hours: {hrs:,.0f}")
                if qty:
                    lines.append(f"  Actual Qty: {qty:,.1f} {unit}")
                if mh is not None:
                    lines.append(f"  MH/Unit: {mh:.4f} (calculated from raw actuals)")
                lines.append(f"  Note: Raw actuals only — no detailed rate card calculated.")
                lines.append("")
            lines.append("")

    # Estimate data section
    if estimate_data:
        est_block = build_estimate_context(estimate_data)
        if est_block:
            lines.append(est_block)

    # Data gaps section
    lines.append("---")
    lines.append("DATA GAPS:")

    if jobs_without_pm:
        lines.append(f"- No PM context available for jobs: {', '.join(jobs_without_pm)}")

    # Note limited data
    disciplines_found = set(
        item.get("discipline", "unmapped") for item in rate_items
    )
    requested = set(signals.get("disciplines", []))
    missing = requested - disciplines_found
    if missing:
        for disc in missing:
            lines.append(f"- No data found for discipline: {disc}")

    if len(rate_items) == 1:
        lines.append(
            "- Only one matching cost code found — limited basis for comparison"
        )

    low_confidence = [
        item for item in rate_items
        if item.get("confidence", "").lower() in ("limited", "low", "none")
    ]
    if low_confidence:
        lines.append(
            f"- {len(low_confidence)} of {len(rate_items)} items have low/limited confidence"
        )

    # Flag jobs with known incomplete timecard data
    incomplete_jobs = []
    for job_id in jobs:
        dq = get_data_quality(job_id)
        if dq["quality"] in ("incomplete", "partial"):
            jnum = jobs[job_id][0]["job_number"]
            incomplete_jobs.append(f"{jnum} ({dq['coverage_pct']}% timecard coverage)")
    if incomplete_jobs:
        lines.append(f"- Incomplete timecard data for: {', '.join(incomplete_jobs)}")

    if not data_gaps and not jobs_without_pm and not missing and len(rate_items) > 1 and not incomplete_jobs:
        lines.append("- None identified")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are WEIS — Wollam Construction's estimating intelligence tool. You have direct SQL access to a database of 197 HeavyJob projects, 15,019 cost codes, 324K timecards, HeavyBid estimates, PM context, and 62K Dropbox documents.

Use the run_sql tool to look up data BEFORE answering. Do not guess or rely on memory.

WHAT YOU CAN ANSWER:
- Specific jobs by number (e.g., "8540") or name keywords
- Production rates, crew sizes, and costs by discipline or activity
- Project context: what happened on a job, site conditions, challenges
- Comparisons across jobs, disciplines, or cost codes
- Patterns and trends in historical data
- Estimates: what was bid, bid item breakdowns, estimated production rates
- Bid vs Actual comparisons when a job has both an estimate and field actuals
- Document and diary intelligence

QUERY GUIDELINES:
- For rates: JOIN rate_item ri → rate_card rc ON ri.card_id = rc.card_id → job j ON rc.job_id = j.job_id
- For raw actuals: Query hj_costcode cc JOIN job j ON cc.job_id = j.job_id
- For PM context: pm_context (job level), cc_context (cost code level) — join via job_id
- For estimates: hb_estimate → hb_biditem → hb_activity → hb_resource (join via estimate_id)
- For bid vs actual: Link hb_estimate.linked_job_id to job.job_id
- For crew details: Query hj_timecard grouped by pay_class_code (ALWAYS filter by job_id + cost_code)
- For documents: dropbox_document JOIN dropbox_extract via doc_id
- Always include job_number and job name in results so you can cite sources
- Use LIMIT to keep results manageable
- ⚠️ hj_timecard (324K rows) and hj_equipment_entry (221K rows) are large — ALWAYS filter by job_id
- rate_item.activity column holds the cost code string (same as hj_costcode.code)

WHAT YOU CAN DO:
- Compare rates, crews, and production across jobs or disciplines
- Summarize and organize data into useful groupings
- Highlight notable differences, outliers, or patterns
- Explain what the numbers show
- Compare bid estimates to actual field performance
- Use tables, bullet points, or narrative — whatever best answers the question
- If explicitly asked "what should I use?", highlight the highest-confidence data point and explain why

HARD RULES — NEVER BREAK THESE:
- ONLY use numbers from your SQL query results. No extrapolation. No inventing numbers.
- NEVER add % adjustments, contingencies, scaling factors, or risk buffers.
- NEVER generate dollar totals or MH budgets by multiplying user quantities by rates.
- NEVER provide unsolicited recommendations, next steps, or guidance.
- NEVER include sections titled "Recommendations," "Scaling," "Next Steps," "Risk," or "Guidance."
- If data doesn't exist, say so in one sentence. Stop there.
- The estimator decides risk, assumptions, and adjustments — not you.

RESPONSE FORMAT:
- Lead with a brief answer, then show supporting data
- Use a markdown table when showing multiple items
- Always cite sources: job number, cost code, confidence level
- Include PM context when it adds useful color
- Keep it concise — the estimator will ask follow-ups if they want more

""" + SCHEMA_DESCRIPTION


# System prompt used when an active bid is selected and document context is available.
# This completely replaces SYSTEM_PROMPT — it puts bid documents first and makes SQL secondary.
BID_SYSTEM_PROMPT = """You are WEIS — Wollam Construction's estimating intelligence tool. The user is currently reviewing bid documents for an ACTIVE project they are pricing.

YOU HAVE BEEN PROVIDED BID DOCUMENT EXCERPTS BELOW. These are the primary source of truth for this conversation.

HOW TO ANSWER:
1. ANSWER FROM THE BID DOCUMENT EXCERPTS FIRST. Read them carefully. Quote specific language when relevant.
2. Cite every answer with the document filename and section heading so the user can find it in the original.
3. If the excerpts contain the answer, DO NOT run SQL queries — just answer directly from the documents.
4. ONLY use the run_sql tool when:
   - The user explicitly asks about historical data, past projects, or comparisons to other jobs
   - The user asks about production rates, crew sizes, or costs from completed work
   - The bid documents don't contain enough information and historical context would help
   - The user says "historically," "on past projects," "compare to actuals," etc.
5. If the excerpts don't fully answer the question, say what you found and what's missing. Offer to search historical data.

WHAT THE BID DOCUMENTS CONTAIN:
- Specifications (testing requirements, material standards, submittals, QA/QC)
- Contract terms (LDs, bonding, insurance, retainage, payment terms)
- Scope of work (what's included, exclusions, alternates)
- Addenda and clarifications
- Bid schedules and pay items
- RFIs and owner responses

WHEN YOU DO USE SQL (for historical comparisons):
""" + """- For rates: JOIN rate_item ri → rate_card rc ON ri.card_id = rc.card_id → job j ON rc.job_id = j.job_id
- For raw actuals: Query hj_costcode cc JOIN job j ON cc.job_id = j.job_id
- For PM context: pm_context (job level), cc_context (cost code level) — join via job_id
- For estimates: hb_estimate → hb_biditem → hb_activity → hb_resource (join via estimate_id)
- For crew details: Query hj_timecard grouped by pay_class_code (ALWAYS filter by job_id + cost_code)
- Always include job_number and job name in results so you can cite sources
- Use LIMIT to keep results manageable
- ⚠️ hj_timecard (324K rows) is large — ALWAYS filter by job_id

HARD RULES — NEVER BREAK THESE:
- ONLY use numbers from bid documents or your SQL query results. No extrapolation. No inventing numbers.
- NEVER add % adjustments, contingencies, scaling factors, or risk buffers.
- NEVER provide unsolicited recommendations, next steps, or guidance.
- If data doesn't exist in the documents or database, say so in one sentence. Stop there.
- The estimator decides risk, assumptions, and adjustments — not you.

RESPONSE FORMAT:
- Lead with a direct answer sourced from the bid documents
- Cite the document: [Filename | Section] for every claim
- Use a markdown table when showing multiple items
- Keep it concise — the estimator will ask follow-ups if they want more

""" + SCHEMA_DESCRIPTION


# ─────────────────────────────────────────────────────────────
# Main Chat Entry Point
# ─────────────────────────────────────────────────────────────

HISTORICAL_TRIGGERS = [
    "historically", "past projects", "how have we handled",
    "previous bids", "on other projects", "in the past",
]


def _sqlite_keyword_search(bid_id: int, message: str, limit: int = 10) -> list[dict]:
    """Fallback: keyword search on bid_document_chunks via SQLite LIKE.

    Extracts significant words from the message, scores chunks by keyword
    match count, and returns top results in the same format as search_bid().
    """
    import re as _re

    # Extract meaningful keywords (3+ chars, skip stopwords)
    stopwords = {"the", "and", "for", "this", "that", "with", "are", "what",
                 "how", "does", "from", "have", "has", "been", "will", "can",
                 "about", "which", "their", "there", "they", "our", "any"}
    words = _re.findall(r"[a-zA-Z]{3,}", message.lower())
    keywords = [w for w in words if w not in stopwords]

    if not keywords:
        return []

    conn = get_connection()
    try:
        # Build a query that counts keyword matches per chunk
        case_clauses = " + ".join(
            f"(CASE WHEN LOWER(c.chunk_text) LIKE '%' || ? || '%' THEN 1 ELSE 0 END)"
            for _ in keywords
        )
        sql = f"""
            SELECT c.id, c.chunk_text, c.section_heading, c.document_id,
                   d.filename, d.doc_category,
                   ({case_clauses}) as match_score
            FROM bid_document_chunks c
            JOIN bid_documents d ON c.document_id = d.id
            WHERE c.bid_id = ? AND ({case_clauses}) > 0
            ORDER BY match_score DESC
            LIMIT ?
        """
        params = list(keywords) + [bid_id] + list(keywords) + [limit]
        rows = conn.execute(sql, params).fetchall()

        return [
            {
                "chunk_id": f"sqlite_{r['id']}",
                "chunk_text": r["chunk_text"],
                "section_heading": r["section_heading"] or "",
                "filename": r["filename"] or "",
                "doc_category": r["doc_category"] or "",
                "document_id": r["document_id"],
                "distance": 1.0 - (r["match_score"] / len(keywords)),  # rough relevance
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("SQLite keyword fallback failed for bid %d: %s", bid_id, e)
        return []
    finally:
        conn.close()


def _build_vector_context(bid_id: int, message: str) -> tuple[str, list[dict]]:
    """Build vector search context block for the system prompt.

    Searches the bid's document collection, and optionally institutional
    memory if the message contains historical triggers.

    Returns (context_string, vector_sources) where vector_sources is a list
    of source dicts for the frontend citation badges.
    """
    context_parts = []
    vector_sources = []

    try:
        from app.services.vector_store import search_bid, search_institutional

        # Bid document search (vector)
        results = search_bid(bid_id, message, n_results=10)

        # SQLite keyword fallback if vector search returned nothing
        if not results:
            results = _sqlite_keyword_search(bid_id, message)

        if results:
            lines = ["\n\n--- Relevant Bid Document Excerpts ---"]
            seen_files = set()
            for r in results:
                header = f"\n[{r.get('filename', '?')}"
                if r.get("section_heading"):
                    header += f" | {r['section_heading']}"
                header += "]"
                lines.append(header)
                lines.append(r.get("chunk_text", ""))

                # Build source citation (dedupe by filename + section)
                source_key = (r.get("filename", ""), r.get("section_heading", ""))
                if source_key not in seen_files:
                    seen_files.add(source_key)
                    vector_sources.append({
                        "source_type": "document",
                        "filename": r.get("filename", "Unknown"),
                        "section": r.get("section_heading", ""),
                        "doc_category": r.get("doc_category", ""),
                        "distance": r.get("distance"),
                    })
            context_parts.append("\n".join(lines))

        # Historical search (opt-in via trigger words)
        msg_lower = message.lower()
        if any(trigger in msg_lower for trigger in HISTORICAL_TRIGGERS):
            hist_results = search_institutional(message, n_results=5)
            if hist_results:
                lines = ["\n\n--- Historical Project Context ---"]
                for r in hist_results:
                    meta = r.get("metadata", {})
                    source = f"Job {meta.get('job_id', '?')} | {meta.get('source_type', '')}"
                    lines.append(f"\n[{source}]")
                    lines.append(r.get("chunk_text", ""))
                context_parts.append("\n".join(lines))

    except Exception as e:
        logger.warning("Vector context build failed for bid %d: %s", bid_id, e)

    if context_parts:
        context_str = "\n".join(context_parts)
        return context_str, vector_sources
    return "", vector_sources


def send_message(conversation_id: int | None, message: str, bid_id: int | None = None) -> dict:
    """Main chat entry point — process a user message and return AI response.

    Uses Claude tool-use loop: Claude calls run_sql to query the database
    directly, then assembles a response from the results.

    If bid_id is provided, vector search augments the system prompt with
    relevant bid document excerpts.

    Returns dict with response, sources, conversation_id.
    """
    if not ANTHROPIC_API_KEY:
        return {
            "error": "AI chat requires an Anthropic API key. Please configure it in .env.",
            "conversation_id": conversation_id,
        }

    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        is_new = conversation_id is None

        # 1. Create or validate conversation
        if is_new:
            cursor = conn.execute(
                "INSERT INTO chat_conversations (title, bid_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (None, bid_id, now, now),
            )
            conversation_id = cursor.lastrowid
        else:
            existing = conn.execute(
                "SELECT id FROM chat_conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if not existing:
                return {"error": f"Conversation {conversation_id} not found"}
            conn.execute(
                "UPDATE chat_conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )

        # 2. Save user message
        conn.execute(
            "INSERT INTO chat_messages (conversation_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
            (conversation_id, message, now),
        )
        conn.commit()

        # 3. Load conversation history for continuity
        history_rows = conn.execute(
            """SELECT role, content FROM chat_messages
               WHERE conversation_id = ?
               ORDER BY created_at DESC LIMIT 10""",
            (conversation_id,),
        ).fetchall()
        history = [{"role": r["role"], "content": r["content"]} for r in reversed(history_rows)]
        # Prior messages (excluding the one we just saved)
        prior_messages = history[:-1] if len(history) > 1 else []
        prior_messages = prior_messages[-10:]

        # 3b. Vector search context — bid documents + optional historical
        effective_system = SYSTEM_PROMPT
        vector_sources = []
        if bid_id:
            from app.config import VECTOR_SEARCH_ENABLED
            if VECTOR_SEARCH_ENABLED:
                bid_context, vector_sources = _build_vector_context(bid_id, message)
                if bid_context:
                    # Use the bid-focused system prompt instead of appending to the
                    # historical-data-first prompt. This tells Claude to answer from
                    # bid documents first and only use SQL for historical comparisons.
                    effective_system = BID_SYSTEM_PROMPT + bid_context

        # 4. Build Claude API messages
        api_messages = []
        for msg in prior_messages:
            api_messages.append({"role": msg["role"], "content": msg["content"]})
        api_messages.append({"role": "user", "content": message})

        # 5. Call Claude with tool-use loop
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        executed_queries = []
        ai_content = ""

        for iteration in range(MAX_TOOL_CALLS + 1):
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=effective_system,
                tools=[TOOL_DEFINITION],
                messages=api_messages,
            )

            # Check if Claude wants to use a tool
            if response.stop_reason == "tool_use":
                # Process all tool use blocks in this response
                tool_results = []
                assistant_content = []

                for block in response.content:
                    if block.type == "text":
                        assistant_content.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })
                        # Execute the SQL query
                        query = block.input.get("query", "")
                        logger.info("Chat SQL [iter %d]: %s", iteration, query[:200])
                        result = execute_sql(query)
                        executed_queries.append({"query": query, "result": result})

                        # Format result for Claude
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": _format_sql_result(result),
                        })

                # Append assistant message with tool use
                api_messages.append({"role": "assistant", "content": assistant_content})
                # Append tool results
                api_messages.append({"role": "user", "content": tool_results})

            else:
                # Claude is done — extract text response
                ai_content = "\n".join(
                    block.text for block in response.content if block.type == "text"
                )
                break
        else:
            # Hit max iterations — force a final text response.
            # Add a user nudge so Claude knows to synthesize what it has.
            api_messages.append({
                "role": "user",
                "content": [{"type": "text", "text": "Please provide your answer now based on the data you've already gathered. No more queries needed."}],
            })
            try:
                final_response = client.messages.create(
                    model=MODEL,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=[TOOL_DEFINITION],
                    tool_choice={"type": "none"},
                    messages=api_messages,
                )
                ai_content = "\n".join(
                    block.text for block in final_response.content if block.type == "text"
                ) or "I gathered data but couldn't complete the analysis. Please try a more specific question."
            except Exception:
                ai_content = "\n".join(
                    block.text for block in response.content if block.type == "text"
                ) or "I ran out of query attempts. Please try a more specific question."

        # 6. Build source metadata from executed queries + vector search
        sources = vector_sources + _extract_sources_from_queries(executed_queries)
        sources_json = json.dumps(sources) if sources else None

        # 7. Save AI response
        conn.execute(
            "INSERT INTO chat_messages (conversation_id, role, content, sources_json, created_at) "
            "VALUES (?, 'assistant', ?, ?, ?)",
            (conversation_id, ai_content, sources_json, datetime.now().isoformat()),
        )

        # 8. Auto-title new conversations
        if is_new:
            title = message[:50].strip()
            if len(message) > 50:
                title = title.rsplit(" ", 1)[0] if " " in title else title
                title += "..."
            conn.execute(
                "UPDATE chat_conversations SET title = ? WHERE id = ?",
                (title, conversation_id),
            )

        conn.commit()

        title_row = conn.execute(
            "SELECT title FROM chat_conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        title = title_row["title"] if title_row else "New Conversation"

        return {
            "conversation_id": conversation_id,
            "response": ai_content,
            "sources": sources,
            "title": title or "New Conversation",
        }

    except anthropic.APIError as e:
        logger.error("Claude API error: %s", e)
        return {
            "error": f"AI service error: {str(e)}",
            "conversation_id": conversation_id,
        }
    except Exception as e:
        logger.error("Chat error: %s", e, exc_info=True)
        return {
            "error": f"An unexpected error occurred: {str(e)}",
            "conversation_id": conversation_id,
        }
    finally:
        conn.close()


def _format_sql_result(result: dict) -> str:
    """Format SQL execution result as a concise string for Claude."""
    if result.get("error"):
        return f"ERROR: {result['error']}"

    columns = result.get("columns", [])
    rows = result.get("rows", [])

    if not rows:
        return "Query returned 0 rows."

    # Tab-separated format — compact and easy for Claude to parse
    lines = ["\t".join(str(c) for c in columns)]
    for row in rows:
        lines.append("\t".join(
            str(v) if v is not None else "NULL" for v in row
        ))

    summary = f"{result['row_count']} rows"
    if result.get("truncated"):
        summary += " (truncated — more rows available, refine your query)"

    lines.append(f"\n[{summary}]")
    return "\n".join(lines)


def _extract_sources_from_queries(executed_queries: list[dict]) -> list[dict]:
    """Extract source metadata from SQL query results.

    Scans query results for job_number and cost_code columns to build
    the sources list for the frontend citation badges.
    """
    sources = []
    seen = set()

    for qinfo in executed_queries:
        result = qinfo.get("result", {})
        columns = result.get("columns", [])
        rows = result.get("rows", [])

        if not columns or not rows:
            continue

        # Find column indices for source-relevant fields
        col_map = {c.lower(): i for i, c in enumerate(columns)}
        jn_idx = col_map.get("job_number")
        cc_idx = col_map.get("cost_code") or col_map.get("code") or col_map.get("activity")
        desc_idx = col_map.get("description") or col_map.get("job_name") or col_map.get("name")
        conf_idx = col_map.get("confidence")

        if jn_idx is None:
            continue

        for row in rows:
            job_number = str(row[jn_idx]) if row[jn_idx] else None
            if not job_number:
                continue

            cost_code = str(row[cc_idx]) if cc_idx is not None and row[cc_idx] else None
            source_key = (job_number, cost_code or "")
            if source_key in seen:
                continue
            seen.add(source_key)

            desc = str(row[desc_idx]) if desc_idx is not None and row[desc_idx] else None
            conf = str(row[conf_idx]) if conf_idx is not None and row[conf_idx] else None

            sources.append({
                "job_number": job_number,
                "cost_code": cost_code,
                "description": desc,
                "confidence": conf,
                "source_type": "sql_query",
            })

            # Cap sources to avoid huge metadata
            if len(sources) >= 50:
                return sources

    return sources


def _has_pm_context(job_id: int, cost_code: str) -> bool:
    """Check if PM context exists for a job/cost code combination."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM cc_context WHERE job_id = ? AND cost_code = ?",
            (job_id, cost_code),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _has_foreman_notes(job_id: int, cost_code: str) -> bool:
    """Check if foreman notes exist for a job/cost code combination."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM hj_timecard WHERE job_id = ? AND cost_code = ? AND notes IS NOT NULL AND LENGTH(notes) >= 10 LIMIT 1",
            (job_id, cost_code),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Conversation CRUD
# ─────────────────────────────────────────────────────────────

def list_conversations() -> list[dict]:
    """List all conversations, most recent first, with message count."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT
                c.id,
                c.title,
                c.bid_id,
                c.created_at,
                c.updated_at,
                COUNT(m.id) as message_count
            FROM chat_conversations c
            LEFT JOIN chat_messages m ON m.conversation_id = c.id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_conversation(conversation_id: int) -> dict | None:
    """Get a conversation with all its messages."""
    conn = get_connection()
    try:
        conv = conn.execute(
            "SELECT * FROM chat_conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if not conv:
            return None

        messages = conn.execute(
            """SELECT id, role, content, sources_json, created_at
               FROM chat_messages
               WHERE conversation_id = ?
               ORDER BY created_at ASC""",
            (conversation_id,),
        ).fetchall()

        formatted_messages = []
        for msg in messages:
            m = dict(msg)
            if m.get("sources_json"):
                try:
                    m["sources"] = json.loads(m["sources_json"])
                except (json.JSONDecodeError, TypeError):
                    m["sources"] = None
            else:
                m["sources"] = None
            del m["sources_json"]
            formatted_messages.append(m)

        return {
            "id": conv["id"],
            "title": conv["title"],
            "bid_id": conv["bid_id"],
            "created_at": conv["created_at"],
            "updated_at": conv["updated_at"],
            "messages": formatted_messages,
        }
    finally:
        conn.close()


def delete_conversation(conversation_id: int) -> bool:
    """Delete a conversation and all its messages. Returns True if deleted."""
    conn = get_connection()
    try:
        # Check it exists
        existing = conn.execute(
            "SELECT id FROM chat_conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if not existing:
            return False

        conn.execute(
            "DELETE FROM chat_messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        conn.execute(
            "DELETE FROM chat_conversations WHERE id = ?",
            (conversation_id,),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_data_summary() -> dict:
    """Return a summary of available data for the chat UI."""
    conn = get_connection()
    try:
        total_jobs = conn.execute("SELECT COUNT(*) as c FROM job").fetchone()["c"]
        total_rate_items = conn.execute(
            "SELECT COUNT(*) as c FROM rate_item WHERE act_mh_per_unit IS NOT NULL OR timecard_count > 0"
        ).fetchone()["c"]
        total_timecards = conn.execute("SELECT COUNT(*) as c FROM hj_timecard").fetchone()["c"]
        jobs_with_pm = conn.execute("SELECT COUNT(*) as c FROM pm_context").fetchone()["c"]
        timecards_with_notes = conn.execute(
            "SELECT COUNT(*) as c FROM hj_timecard WHERE notes IS NOT NULL AND LENGTH(notes) >= 10"
        ).fetchone()["c"]
        jobs_with_notes = conn.execute(
            "SELECT COUNT(DISTINCT job_id) as c FROM hj_timecard WHERE notes IS NOT NULL AND LENGTH(notes) >= 10"
        ).fetchone()["c"]

        disc_rows = conn.execute(
            "SELECT DISTINCT discipline FROM rate_item WHERE discipline IS NOT NULL AND discipline != 'unmapped' ORDER BY discipline"
        ).fetchall()
        disciplines = [r["discipline"] for r in disc_rows]

        total_estimates = conn.execute("SELECT COUNT(*) as c FROM hb_estimate").fetchone()["c"]

        return {
            "total_jobs": total_jobs,
            "total_rate_items": total_rate_items,
            "total_timecards": total_timecards,
            "timecards_with_notes": timecards_with_notes,
            "jobs_with_foreman_notes": jobs_with_notes,
            "disciplines": disciplines,
            "jobs_with_pm_context": jobs_with_pm,
            "total_estimates": total_estimates,
        }
    finally:
        conn.close()