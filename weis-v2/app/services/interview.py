"""Interview Service — Business logic for PM Context Interview.

Loads job data, cost code details, and manages PM context persistence.
All database queries live here; the API layer is a thin wrapper.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime

from app.database import get_connection


# ── Trade simplification ──
# Order matters: OEF (Union Foreman) must match before OE* (Operator)
TRADE_GROUPS: list[tuple[str, list[str]]] = [
    ("Crane Operator", ["CRANE"]),
    ("Foreman", ["FORE", "GFORE", "OEF"]),
    ("Operator", ["OE", "OPER"]),
    ("Laborer", ["LAB", "TEMPL"]),
    ("Carpenter", ["CARP", "TEMPC"]),
    ("Iron Worker", ["IRON"]),
    ("Pipe Fitter", ["PIPE"]),
    ("Welder", ["WELD"]),
    ("Superintendent", ["SUP"]),
]

# Overhead trades excluded from crew display (not production crew)
OVERHEAD_TRADES = {"Safety", "Engineer", "Project Manager", "Field Clerk", "Maintenance"}

# Minimum presence to include in typical crew (30% of work days)
CREW_PRESENCE_THRESHOLD = 0.30


def simplify_trade(pay_class_code: str) -> str:
    """Map a pay_class_code to a simplified trade group name."""
    if not pay_class_code:
        return "Other"
    code = pay_class_code.upper().strip()
    for group_name, prefixes in TRADE_GROUPS:
        for prefix in prefixes:
            if code == prefix or code.startswith(prefix):
                return group_name
    # Fallback for unmatched codes
    overhead_map = {
        "SAFE": "Safety", "SAFETY": "Safety", "ENG": "Engineer",
        "PM": "Project Manager", "CLERK": "Field Clerk",
        "MAIN": "Maintenance", "TEMP": "Other",
    }
    return overhead_map.get(code, code)


# ── Equipment simplification ──
EQUIPMENT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Mini Excavator", ["mini excavator", "mini exc"]),
    ("Excavator", ["excavator"]),
    ("Crane", ["crane"]),
    ("Forklift", ["forklift", "fork lift", "telehandler"]),
    ("Dozer", ["dozer", "bulldozer", "smart grade doz"]),
    ("Loader", ["loader"]),
    ("Scraper", ["scraper"]),
    ("Grader", ["grader"]),
    ("Haul Truck", ["haul truck", "haul", "articulated", "artic truck", "dump"]),
    ("Water Truck", ["water truck"]),
    ("Skid Steer", ["skid steer", "skidsteer"]),
    ("Welder", ["welder", "welding"]),
    ("Light Tower", ["light tower"]),
    ("Compactor", ["compactor", "roller"]),
    ("Generator", ["generator"]),
    ("Pump", ["pump"]),
    ("Paver", ["paver"]),
    ("Trencher", ["trencher"]),
    ("Concrete", ["concrete", "mixer"]),
]

# Equipment categories filtered out of crew display (support/transport, not production)
EXCLUDED_EQUIPMENT = {"Pickup", "Van", "Trailer", "Flatbed", "Lube Truck", "Enclosed", "Vehicle"}

_PICKUP_RE = re.compile(
    r"\bf-?(?:150|250|350|450|550)\b|\bsierra\b|\b(?:2500|3500)\s*(?:hd|gmc)?\b|\bchevrolet\b",
    re.IGNORECASE,
)


def simplify_equipment_name(desc: str) -> str:
    """Simplify an equipment description to a general category."""
    if not desc:
        return "Equipment"
    # Bare year string (e.g., "2019") — can't categorize
    if re.match(r"^\d{4}$", desc.strip()):
        return "Vehicle"
    lower = desc.lower()

    # Check for parenthesized category (HCSS common pattern: "PC 360 - Komatsu (Excavator)")
    paren = re.search(r"\(([^)]+)\)", desc)
    if paren:
        cat = paren.group(1).strip().lower()
        if "mini" in cat and "excavator" in cat:
            return "Mini Excavator"
        if "excavator" in cat:
            return "Excavator"
        if "loader" in cat:
            return "Loader"
        if "dozer" in cat:
            return "Dozer"
        if "skid" in cat:
            return "Skid Steer"
        if "truck" in cat or "artic" in cat:
            return "Haul Truck"
        if "crane" in cat:
            return "Crane"
        if "grader" in cat:
            return "Grader"
        if "scraper" in cat:
            return "Scraper"
        # "HD 785 (100 Ton)" = Haul Truck, generic "(X Ton)" = Crane
        if "ton" in cat:
            if re.search(r"\bhd\b|\bdump\b|\bhaul\b|\bartic", lower):
                return "Haul Truck"
            return "Crane"
        return paren.group(1).strip()

    # Pickups / utility trucks
    if _PICKUP_RE.search(desc):
        if "flatbed" in lower:
            return "Flatbed"
        return "Pickup"

    # Vans
    if re.search(r"\bvan\b", lower) or re.search(r"\be-?350\b.*econoline", lower):
        return "Van"

    # Trailers / enclosed
    if re.search(r"\btrailer\b|\benclosed\b|\blowboy\b", lower):
        return "Trailer"

    # Lube trucks
    if "lube" in lower:
        return "Lube Truck"

    # Keyword-based matching
    for category, keywords in EQUIPMENT_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return category

    # Tonnage pattern → likely crane ("130 Ton - Linkbelt", "80 Ton - Grove")
    if re.search(r"\d+\s*ton\b", lower):
        return "Crane"

    # Bobcat without other context → Skid Steer
    if "bobcat" in lower:
        return "Skid Steer"

    return desc


def _build_crew_breakdown(
    conn, job_id: int, work_days_by_cc: dict[str, int]
) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """Build simplified crew breakdowns for all cost codes in a job.

    Returns (trade_breakdown, equip_breakdown) dictionaries keyed by cost code.
    Each value is a list of {name, avg_count, days_present} dicts, filtered to
    trades/equipment present on >= CREW_PRESENCE_THRESHOLD of work days.
    """

    # ── Trades: daily worker counts per trade per cost code ──
    trade_rows = conn.execute("""
        SELECT cost_code, pay_class_code, date,
               COUNT(DISTINCT employee_name) as workers
        FROM hj_timecard
        WHERE job_id = ? AND pay_class_code IS NOT NULL AND pay_class_code != ''
        GROUP BY cost_code, pay_class_code, date
    """, (job_id,)).fetchall()

    # {cost_code: {trade_group: {date: worker_count}}}
    trade_daily: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    for row in trade_rows:
        group = simplify_trade(row["pay_class_code"])
        if group in OVERHEAD_TRADES or group == "Other":
            continue
        trade_daily[row["cost_code"]][group][row["date"]] += row["workers"]

    trade_breakdown: dict[str, list[dict]] = {}
    for cc_code, groups in trade_daily.items():
        wd = work_days_by_cc.get(cc_code, 1)
        items = []
        for name, daily_counts in groups.items():
            days_present = len(daily_counts)
            presence = days_present / wd if wd > 0 else 0
            if presence < CREW_PRESENCE_THRESHOLD:
                continue
            avg_count = sum(daily_counts.values()) / days_present
            items.append({
                "name": name,
                "avg_count": round(avg_count),
                "days_present": days_present,
            })
        items.sort(key=lambda x: x["days_present"], reverse=True)
        trade_breakdown[cc_code] = items

    # ── Equipment: daily unit counts per simplified name per cost code ──
    equip_rows = conn.execute("""
        SELECT cost_code, equipment_desc, date,
               COUNT(DISTINCT equipment_code) as unit_count
        FROM hj_equipment_entry
        WHERE job_id = ?
        GROUP BY cost_code, equipment_desc, date
    """, (job_id,)).fetchall()

    # {cost_code: {simplified_name: {date: unit_count}}}
    equip_daily: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    for row in equip_rows:
        name = simplify_equipment_name(row["equipment_desc"])
        if name in EXCLUDED_EQUIPMENT:
            continue
        equip_daily[row["cost_code"]][name][row["date"]] += row["unit_count"]

    equip_breakdown: dict[str, list[dict]] = {}
    for cc_code, categories in equip_daily.items():
        wd = work_days_by_cc.get(cc_code, 1)
        items = []
        for name, daily_counts in categories.items():
            days_present = len(daily_counts)
            presence = days_present / wd if wd > 0 else 0
            if presence < CREW_PRESENCE_THRESHOLD:
                continue
            avg_count = sum(daily_counts.values()) / days_present
            items.append({
                "name": name,
                "avg_count": round(avg_count),
                "days_present": days_present,
            })
        items.sort(key=lambda x: x["days_present"], reverse=True)
        equip_breakdown[cc_code] = items

    return trade_breakdown, equip_breakdown


def get_jobs_with_interview_status() -> list[dict]:
    """Return all jobs with interview completion metadata.

    For each job, computes:
    - cost_code_count: total cost codes
    - cost_codes_with_data: cost codes that have actual labor hours
    - cost_codes_with_context: cost codes that have PM context
    - data_richness: 0-100 score based on timecard/budget coverage
    - interview_status: not_started / in_progress / complete
    """
    conn = get_connection()
    try:
        # Pre-aggregate timecard counts to avoid correlated subquery on 278K rows
        rows = conn.execute("""
            SELECT
                j.job_id,
                j.job_number,
                j.name,
                j.status,
                COALESCE(cc_agg.cc_total, 0) as cost_code_count,
                COALESCE(cc_agg.cc_with_data, 0) as cost_codes_with_data,
                COALESCE(cx_agg.cx_count, 0) as cost_codes_with_context,
                COALESCE(tc_agg.tc_count, 0) as timecard_count,
                COALESCE(di_agg.diary_count, 0) as diary_entry_count,
                pc.id as pm_context_id,
                pc.completed_at,
                pc.source as pm_source,
                est.estimate_id as linked_estimate_id,
                est.code as linked_estimate_code
            FROM job j
            LEFT JOIN pm_context pc ON pc.job_id = j.job_id
            LEFT JOIN hb_estimate est ON est.linked_job_id = j.job_id
            LEFT JOIN (
                SELECT job_id,
                       COUNT(*) as cc_total,
                       SUM(CASE WHEN act_labor_hrs > 0 THEN 1 ELSE 0 END) as cc_with_data
                FROM hj_costcode GROUP BY job_id
            ) cc_agg ON cc_agg.job_id = j.job_id
            LEFT JOIN (
                SELECT job_id, COUNT(*) as cx_count
                FROM cc_context GROUP BY job_id
            ) cx_agg ON cx_agg.job_id = j.job_id
            LEFT JOIN (
                SELECT job_id, COUNT(*) as tc_count
                FROM hj_timecard GROUP BY job_id
            ) tc_agg ON tc_agg.job_id = j.job_id
            LEFT JOIN (
                SELECT job_id, COUNT(*) as diary_count
                FROM diary_entry GROUP BY job_id
            ) di_agg ON di_agg.job_id = j.job_id
            ORDER BY j.job_number
        """).fetchall()

        jobs = []
        for r in rows:
            r = dict(r)
            tc_count = r.pop("timecard_count", 0) or 0
            cc_data = r.get("cost_codes_with_data", 0) or 0
            cc_total = r.get("cost_code_count", 0) or 0
            cc_context = r.get("cost_codes_with_context", 0) or 0

            # Data richness: blend of timecard count and cost code coverage
            richness = 0
            if tc_count > 0:
                richness += 25
            if tc_count > 100:
                richness += 15
            if tc_count > 500:
                richness += 10
            if cc_data > 0:
                richness += 25
            if cc_total > 0 and cc_data > 0:
                richness += int((cc_data / cc_total) * 25)
            richness = min(richness, 100)

            # Interview status
            if r.get("completed_at"):
                status = "complete"
            elif r.get("pm_context_id") or cc_context > 0:
                status = "in_progress"
            else:
                status = "not_started"

            jobs.append({
                "job_id": r["job_id"],
                "job_number": r["job_number"],
                "name": r["name"],
                "status": r["status"],
                "cost_code_count": cc_total,
                "cost_codes_with_data": cc_data,
                "cost_codes_with_context": cc_context,
                "data_richness": richness,
                "interview_status": status,
                "diary_entry_count": r.get("diary_entry_count", 0) or 0,
                "pm_source": r.get("pm_source"),
                "linked_estimate_id": r.get("linked_estimate_id"),
                "linked_estimate_code": r.get("linked_estimate_code"),
            })

        return jobs
    finally:
        conn.close()


def get_job_interview_detail(job_id: int) -> dict | None:
    """Return full job detail for the interview page.

    Includes job info, PM context (if any), and all cost codes with
    their actual data and any existing PM context.
    """
    conn = get_connection()
    try:
        # Job info
        job = conn.execute(
            "SELECT * FROM job WHERE job_id = ?", (job_id,)
        ).fetchone()
        if not job:
            return None
        job = dict(job)

        # Job-level summary stats
        stats = conn.execute("""
            SELECT
                ROUND(SUM(act_labor_hrs), 0) as total_actual_hrs,
                ROUND(SUM(bgt_labor_hrs), 0) as total_budget_hrs,
                ROUND(SUM(bgt_labor_cost), 0) as total_budget_labor_cost,
                ROUND(SUM(bgt_equip_cost), 0) as total_budget_equip_cost,
                ROUND(SUM(bgt_matl_cost), 0) as total_budget_matl_cost,
                ROUND(SUM(bgt_sub_cost), 0) as total_budget_sub_cost,
                ROUND(SUM(bgt_total), 0) as total_budget_cost,
                ROUND(SUM(act_labor_cost), 0) as total_actual_labor_cost,
                ROUND(SUM(act_equip_cost), 0) as total_actual_equip_cost,
                ROUND(SUM(act_matl_cost), 0) as total_actual_matl_cost,
                ROUND(SUM(act_sub_cost), 0) as total_actual_sub_cost,
                ROUND(SUM(act_total), 0) as total_actual_cost,
                COUNT(*) as total_cost_codes,
                COUNT(CASE WHEN act_labor_hrs > 0 THEN 1 END) as cost_codes_with_data
            FROM hj_costcode WHERE job_id = ?
        """, (job_id,)).fetchone()
        stats = dict(stats) if stats else {}

        # PM context (job-level)
        pm_ctx = conn.execute(
            "SELECT * FROM pm_context WHERE job_id = ?", (job_id,)
        ).fetchone()
        pm_context = dict(pm_ctx) if pm_ctx else None

        # Diary summary
        diary_row = conn.execute("""
            SELECT
                COUNT(*) as entry_count,
                COUNT(DISTINCT cost_code) as cost_code_count,
                COUNT(DISTINCT foreman) as foreman_count,
                MIN(date) as date_start,
                MAX(date) as date_end,
                GROUP_CONCAT(DISTINCT foreman) as foremen
            FROM diary_entry
            WHERE job_id = ? AND cost_code IS NOT NULL
        """, (job_id,)).fetchone()
        diary_summary = None
        if diary_row and diary_row["entry_count"] > 0:
            ds = dict(diary_row)
            ds["foremen"] = ds["foremen"].split(",") if ds["foremen"] else []
            diary_summary = ds

        # All cost codes with actual data, enriched with rate_item and cc_context
        cost_codes = conn.execute("""
            SELECT
                cc.code,
                cc.description,
                cc.unit,
                cc.bgt_qty,
                cc.act_qty,
                cc.bgt_labor_hrs,
                cc.bgt_labor_cost,
                cc.bgt_equip_cost,
                cc.bgt_matl_cost,
                cc.bgt_sub_cost,
                cc.bgt_total,
                cc.act_labor_hrs,
                cc.act_labor_cost,
                cc.act_equip_hrs,
                cc.act_equip_cost,
                cc.act_matl_cost,
                cc.act_sub_cost,
                cc.act_total,
                cc.discipline,
                ri.act_mh_per_unit,
                ri.confidence,
                ri.timecard_count,
                ri.work_days,
                ri.crew_size_avg,
                ri.crew_breakdown,
                ri.daily_qty_avg,
                ri.daily_qty_peak,
                cx.scope_included,
                cx.scope_excluded,
                cx.description_override,
                cx.related_codes,
                cx.conditions as cx_conditions,
                cx.notes as cx_notes,
                cx.source as cx_source
            FROM hj_costcode cc
            LEFT JOIN rate_card rc ON rc.job_id = cc.job_id
            LEFT JOIN rate_item ri ON ri.card_id = rc.card_id AND ri.activity = cc.code
            LEFT JOIN cc_context cx ON cx.job_id = cc.job_id AND cx.cost_code = cc.code
            WHERE cc.job_id = ? AND cc.act_labor_hrs > 0
            ORDER BY cc.act_labor_hrs DESC
        """, (job_id,)).fetchall()

        # Build simplified crew breakdowns (trades + equipment)
        work_days_by_cc = {
            cc["code"]: cc["work_days"] or 1 for cc in cost_codes
        }
        trade_breakdown, equip_breakdown = _build_crew_breakdown(
            conn, job_id, work_days_by_cc
        )

        formatted_codes = []
        for cc in cost_codes:
            cc = dict(cc)
            trades_list = trade_breakdown.get(cc["code"], [])
            equip_list = equip_breakdown.get(cc["code"], [])
            # Compute typical daily crew from consistent trades
            typical_crew_size = sum(t["avg_count"] for t in trades_list)
            crew = {
                "trades": trades_list,
                "equipment": equip_list,
                "typical_crew_size": typical_crew_size,
            }

            # Build context sub-object (None if no context exists)
            has_context = any([
                cc.get("scope_included"),
                cc.get("scope_excluded"),
                cc.get("cx_conditions"),
                cc.get("cx_notes"),
                cc.get("description_override"),
            ])
            context = {
                "scope_included": cc.get("scope_included"),
                "scope_excluded": cc.get("scope_excluded"),
                "description_override": cc.get("description_override"),
                "related_codes": cc.get("related_codes"),
                "conditions": cc.get("cx_conditions"),
                "notes": cc.get("cx_notes"),
                "source": cc.get("cx_source"),
            } if has_context else None

            formatted_codes.append({
                "code": cc["code"],
                "description": cc["description"],
                "unit": cc["unit"],
                "bgt_qty": cc["bgt_qty"],
                "act_qty": cc["act_qty"],
                "bgt_labor_hrs": cc["bgt_labor_hrs"],
                "bgt_labor_cost": cc["bgt_labor_cost"],
                "bgt_equip_cost": cc["bgt_equip_cost"],
                "bgt_matl_cost": cc["bgt_matl_cost"],
                "bgt_sub_cost": cc["bgt_sub_cost"],
                "bgt_total": cc["bgt_total"],
                "act_labor_hrs": cc["act_labor_hrs"],
                "act_labor_cost": cc["act_labor_cost"],
                "act_equip_hrs": cc["act_equip_hrs"],
                "act_equip_cost": cc["act_equip_cost"],
                "act_matl_cost": cc["act_matl_cost"],
                "act_sub_cost": cc["act_sub_cost"],
                "act_total": cc["act_total"],
                "act_mh_per_unit": cc["act_mh_per_unit"],
                "confidence": cc["confidence"],
                "timecard_count": cc["timecard_count"],
                "work_days": cc["work_days"],
                "crew_size_avg": cc["crew_size_avg"],
                "crew_breakdown": crew,
                "daily_qty_avg": cc["daily_qty_avg"],
                "daily_qty_peak": cc["daily_qty_peak"],
                "discipline": cc["discipline"],
                "has_context": has_context,
                "context": context,
            })

        # Top 5 cost codes by hours for the overview section
        top_5 = formatted_codes[:5]

        # Document summary
        doc_row = conn.execute("""
            SELECT COUNT(*) as doc_count,
                   SUM(CASE WHEN analyzed = 1 THEN 1 ELSE 0 END) as analyzed_count
            FROM job_document WHERE job_id = ?
        """, (job_id,)).fetchone()
        doc_summary = None
        if doc_row and doc_row["doc_count"] > 0:
            doc_types = conn.execute(
                "SELECT doc_type, COUNT(*) as count FROM job_document WHERE job_id = ? GROUP BY doc_type",
                (job_id,),
            ).fetchall()
            doc_summary = {
                "doc_count": doc_row["doc_count"],
                "analyzed_count": doc_row["analyzed_count"],
                "by_type": {t["doc_type"]: t["count"] for t in doc_types},
            }

        return {
            "job": {
                "job_id": job["job_id"],
                "job_number": job["job_number"],
                "name": job["name"],
                "status": job["status"],
                "total_actual_hrs": stats.get("total_actual_hrs"),
                "total_budget_hrs": stats.get("total_budget_hrs"),
                "total_budget_cost": stats.get("total_budget_cost"),
                "total_budget_labor_cost": stats.get("total_budget_labor_cost"),
                "total_budget_equip_cost": stats.get("total_budget_equip_cost"),
                "total_budget_matl_cost": stats.get("total_budget_matl_cost"),
                "total_budget_sub_cost": stats.get("total_budget_sub_cost"),
                "total_actual_cost": stats.get("total_actual_cost"),
                "total_actual_labor_cost": stats.get("total_actual_labor_cost"),
                "total_actual_equip_cost": stats.get("total_actual_equip_cost"),
                "total_actual_matl_cost": stats.get("total_actual_matl_cost"),
                "total_actual_sub_cost": stats.get("total_actual_sub_cost"),
                "total_cost_codes": stats.get("total_cost_codes"),
                "cost_codes_with_data": stats.get("cost_codes_with_data"),
            },
            "pm_context": pm_context,
            "cost_codes": formatted_codes,
            "top_5": top_5,
            "diary_summary": diary_summary,
            "doc_summary": doc_summary,
        }
    finally:
        conn.close()


def save_job_context(job_id: int, data: dict) -> dict:
    """Save or update PM context at the job level (pm_context table).

    Uses INSERT OR REPLACE (UPSERT on job_id unique constraint).
    """
    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        conn.execute("""
            INSERT INTO pm_context (job_id, pm_name, project_summary, site_conditions,
                                    key_challenges, key_successes, lessons_learned,
                                    general_notes, has_per_diem, per_diem_rate, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                pm_name = COALESCE(excluded.pm_name, pm_context.pm_name),
                project_summary = COALESCE(excluded.project_summary, pm_context.project_summary),
                site_conditions = COALESCE(excluded.site_conditions, pm_context.site_conditions),
                key_challenges = COALESCE(excluded.key_challenges, pm_context.key_challenges),
                key_successes = COALESCE(excluded.key_successes, pm_context.key_successes),
                lessons_learned = COALESCE(excluded.lessons_learned, pm_context.lessons_learned),
                general_notes = COALESCE(excluded.general_notes, pm_context.general_notes),
                has_per_diem = excluded.has_per_diem,
                per_diem_rate = excluded.per_diem_rate,
                updated_at = excluded.updated_at
        """, (
            job_id,
            data.get("pm_name"),
            data.get("project_summary"),
            data.get("site_conditions"),
            data.get("key_challenges"),
            data.get("key_successes"),
            data.get("lessons_learned"),
            data.get("general_notes"),
            1 if data.get("has_per_diem") else 0,
            data.get("per_diem_rate"),
            now,
        ))
        conn.commit()
        return {"status": "saved", "job_id": job_id, "type": "job"}
    finally:
        conn.close()


def save_cost_code_context(job_id: int, cost_code: str, data: dict) -> dict:
    """Save or update PM context for a specific cost code (cc_context table)."""
    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        related = data.get("related_codes")
        if isinstance(related, list):
            related = json.dumps(related)

        conn.execute("""
            INSERT INTO cc_context (job_id, cost_code, description_override,
                                    scope_included, scope_excluded, related_codes,
                                    conditions, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, cost_code) DO UPDATE SET
                description_override = COALESCE(excluded.description_override, cc_context.description_override),
                scope_included = COALESCE(excluded.scope_included, cc_context.scope_included),
                scope_excluded = COALESCE(excluded.scope_excluded, cc_context.scope_excluded),
                related_codes = COALESCE(excluded.related_codes, cc_context.related_codes),
                conditions = COALESCE(excluded.conditions, cc_context.conditions),
                notes = COALESCE(excluded.notes, cc_context.notes),
                updated_at = excluded.updated_at
        """, (
            job_id, cost_code,
            data.get("description_override"),
            data.get("scope_included"),
            data.get("scope_excluded"),
            related,
            data.get("conditions"),
            data.get("notes"),
            now,
        ))
        conn.commit()
        return {"status": "saved", "job_id": job_id, "cost_code": cost_code, "type": "cost_code"}
    finally:
        conn.close()


def mark_interview_complete(job_id: int) -> dict:
    """Mark a job's interview as complete by setting completed_at."""
    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        # Ensure pm_context row exists
        conn.execute("""
            INSERT INTO pm_context (job_id, completed_at, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                completed_at = excluded.completed_at,
                updated_at = excluded.updated_at
        """, (job_id, now, now))
        conn.commit()
        return {"status": "completed", "job_id": job_id, "completed_at": now}
    finally:
        conn.close()


def get_interview_progress() -> dict:
    """Return overall interview progress stats."""
    conn = get_connection()
    try:
        total_jobs = conn.execute("SELECT COUNT(*) FROM job").fetchone()[0]
        jobs_with_context = conn.execute(
            "SELECT COUNT(*) FROM pm_context"
        ).fetchone()[0]
        jobs_complete = conn.execute(
            "SELECT COUNT(*) FROM pm_context WHERE completed_at IS NOT NULL"
        ).fetchone()[0]
        total_cc_with_data = conn.execute(
            "SELECT COUNT(*) FROM hj_costcode WHERE act_labor_hrs > 0"
        ).fetchone()[0]
        cc_with_context = conn.execute(
            "SELECT COUNT(*) FROM cc_context"
        ).fetchone()[0]

        # Top priority jobs: most timecard data, least context
        priority = conn.execute("""
            SELECT
                j.job_id,
                j.job_number,
                j.name,
                COUNT(DISTINCT tc.date) as work_days,
                COUNT(tc.tc_id) as tc_count,
                (SELECT COUNT(*) FROM cc_context cx WHERE cx.job_id = j.job_id) as context_count,
                (SELECT COUNT(*) FROM hj_costcode cc WHERE cc.job_id = j.job_id AND cc.act_labor_hrs > 0) as cc_with_data
            FROM job j
            JOIN hj_timecard tc ON tc.job_id = j.job_id
            LEFT JOIN pm_context pc ON pc.job_id = j.job_id
            WHERE pc.completed_at IS NULL
            GROUP BY j.job_id
            HAVING tc_count > 50
            ORDER BY tc_count DESC
            LIMIT 10
        """).fetchall()

        priority_jobs = []
        for p in priority:
            p = dict(p)
            cc_data = p.get("cc_with_data", 0) or 0
            ctx = p.get("context_count", 0) or 0
            coverage = round((ctx / cc_data * 100), 1) if cc_data > 0 else 0
            richness = min(int(p.get("tc_count", 0) / 100), 100)
            priority_jobs.append({
                "job_id": p["job_id"],
                "job_number": p["job_number"],
                "name": p["name"],
                "data_richness": richness,
                "context_coverage": coverage,
            })

        return {
            "total_jobs": total_jobs,
            "jobs_with_context": jobs_with_context,
            "jobs_complete": jobs_complete,
            "total_cost_codes_with_data": total_cc_with_data,
            "cost_codes_with_context": cc_with_context,
            "top_priority_jobs": priority_jobs,
        }
    finally:
        conn.close()
