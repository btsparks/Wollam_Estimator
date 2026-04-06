"""Recast cost calculation from actual hours × current rates.

Applies overtime adjustments by estimating OT fraction from weekly hours
patterns (40-hour threshold per FLSA), then using per-pay-class OT factors.
"""

import sqlite3

# Weekly OT threshold (hours). Hours beyond this are treated as overtime.
OT_WEEKLY_THRESHOLD = 40


def _compute_ot_fraction(conn: sqlite3.Connection, job_id: int) -> float:
    """Estimate overtime fraction for a job from weekly hours patterns.

    Groups timecard hours by employee + ISO week, then computes what
    fraction of total hours exceeded the 40-hour weekly threshold.
    """
    row = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN weekly_hrs > ? THEN weekly_hrs - ? ELSE 0 END), 0) as ot_hrs,
            COALESCE(SUM(weekly_hrs), 0) as total_hrs
        FROM (
            SELECT employee_name, strftime('%Y-%W', date) as week,
                   SUM(hours) as weekly_hrs
            FROM hj_timecard
            WHERE job_id = ? AND pay_class_code IS NOT NULL AND hours > 0
            GROUP BY employee_name, week
        )
    """, (OT_WEEKLY_THRESHOLD, OT_WEEKLY_THRESHOLD, job_id)).fetchone()
    total = row["total_hrs"] or 0
    ot = row["ot_hrs"] or 0
    return ot / total if total > 0 else 0


def _get_equip_group_averages(conn: sqlite3.Connection) -> dict[str, float]:
    """Get average base_rate per equipment group for fallback matching."""
    rows = conn.execute("""
        SELECT group_name, AVG(base_rate) as avg_rate
        FROM equipment_rate
        WHERE group_name != '' AND base_rate > 0
        GROUP BY group_name
    """).fetchall()
    return {r["group_name"]: r["avg_rate"] for r in rows}


# Map simplified equipment categories to equipment_rate group names
_CATEGORY_TO_GROUP = {
    "Excavator": "EXCAVATOR",
    "Mini Excavator": "EXC/BH",
    "Loader": "LOADER/SKIDS",
    "Dozer": "DOZER",
    "Haul Truck": "HAUL TRUCK",
    "Crane": "CRANE",
    "Forklift": "FORKLIFT",
    "Scraper": "SCRAPER",
    "Grader": "GRADER",
    "Skid Steer": "LOADER/SKIDS",
    "Compactor": "ROLLER",
    "Water Truck": "WATER TRUCK",
    "Welder": "WELDER",
    "Light Tower": "GENERATOR",
    "Generator": "GENERATOR",
    "Pickup": "PICKUP",
    "Van": "VAN",
    "Trailer": "TRAILER",
    "Pump": "SMALL TOOLS",
    "Boom Lift": "LIFT",
    "Scissor Lift": "LIFT",
    "Concrete": "CONCRETE EQ",
    "Paver": "CONCRETE EQ",
}


def _equip_fallback_rate(
    desc: str, group_avgs: dict[str, float]
) -> float:
    """Estimate a rate for unmatched equipment using description keywords."""
    from app.services.interview import simplify_equipment_name

    category = simplify_equipment_name(desc)
    group = _CATEGORY_TO_GROUP.get(category)
    if group and group in group_avgs:
        return group_avgs[group]
    return 0.0


def get_recast_costs_by_job(conn: sqlite3.Connection, job_id: int) -> dict:
    """Calculate recast costs for all cost codes in a job.

    Labor costs use OT-adjusted rates:
        cost = hours × loaded_rate × (1 + ot_fraction × (ot_factor - 1))

    Equipment costs use direct code match with group-average fallback
    for unmatched codes.

    Returns dict with:
        job_totals: {labor_cost, equip_cost, total_cost, labor_hours, equip_hours, ot_fraction}
        cost_codes: {code: {labor_cost, equip_cost, total_cost, labor_hours, equip_hours, ...}}
        unmapped_labor: [{pay_class_code, hours}]
        unmapped_equipment: [{equipment_code, hours}]
    """
    ot_fraction = _compute_ot_fraction(conn, job_id)

    # Per diem: look up from pm_context
    pd_row = conn.execute(
        "SELECT has_per_diem, per_diem_rate FROM pm_context WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    per_diem_rate = 0.0
    if pd_row and pd_row["has_per_diem"] and pd_row["per_diem_rate"]:
        per_diem_rate = pd_row["per_diem_rate"]

    # Labor costs: timecard hours × loaded rate × OT adjustment
    labor_rows = conn.execute("""
        SELECT t.cost_code,
               COALESCE(lr.loaded_rate, 0) as rate,
               COALESCE(lr.ot_factor, 1.5) as ot_factor,
               lr.pay_class_code as matched_code,
               t.pay_class_code,
               SUM(t.hours) as hours
        FROM hj_timecard t
        LEFT JOIN labor_rate lr ON t.pay_class_code = lr.pay_class_code
        WHERE t.job_id = ? AND t.pay_class_code IS NOT NULL AND t.pay_class_code != ''
        GROUP BY t.cost_code, t.pay_class_code
    """, (job_id,)).fetchall()

    # Equipment costs: direct match + group fallback
    equip_rows = conn.execute("""
        SELECT e.cost_code,
               e.equipment_code,
               e.equipment_desc,
               COALESCE(er.base_rate, 0) as rate,
               er.equipment_code as matched_code,
               er.group_name as matched_group,
               SUM(e.hours) as hours
        FROM hj_equipment_entry e
        LEFT JOIN equipment_rate er ON e.equipment_code = er.equipment_code
        WHERE e.job_id = ?
        GROUP BY e.cost_code, e.equipment_code
    """, (job_id,)).fetchall()

    # Pre-load group averages for equipment fallback
    group_avgs = _get_equip_group_averages(conn)

    cc_data = {}
    unmapped_labor = {}
    unmapped_equip = {}

    # Process labor with OT adjustment
    for row in labor_rows:
        cc = row["cost_code"]
        if cc not in cc_data:
            cc_data[cc] = {"labor_cost": 0, "equip_cost": 0, "labor_hours": 0,
                           "equip_hours": 0, "unmapped_labor_hrs": 0, "unmapped_equip_hrs": 0}
        hrs = row["hours"] or 0
        rate = row["rate"] or 0
        ot_factor = row["ot_factor"] or 1.5
        # OT-adjusted rate: straight portion + OT portion at premium
        adjusted_rate = rate * (1 + ot_fraction * (ot_factor - 1))
        cc_data[cc]["labor_cost"] += hrs * adjusted_rate
        cc_data[cc]["labor_hours"] += hrs
        if not row["matched_code"]:
            cc_data[cc]["unmapped_labor_hrs"] += hrs
            pcc = row["pay_class_code"]
            unmapped_labor[pcc] = unmapped_labor.get(pcc, 0) + hrs

    # Process equipment with fallback for unmatched codes
    for row in equip_rows:
        cc = row["cost_code"]
        if cc not in cc_data:
            cc_data[cc] = {"labor_cost": 0, "equip_cost": 0, "labor_hours": 0,
                           "equip_hours": 0, "unmapped_labor_hrs": 0, "unmapped_equip_hrs": 0}
        hrs = row["hours"] or 0
        rate = row["rate"] or 0

        # Fallback: if no direct match, try description-based category lookup
        if rate == 0 and not row["matched_code"]:
            rate = _equip_fallback_rate(row["equipment_desc"] or "", group_avgs)

        cc_data[cc]["equip_cost"] += hrs * rate
        cc_data[cc]["equip_hours"] += hrs
        if not row["matched_code"] and rate == 0:
            cc_data[cc]["unmapped_equip_hrs"] += hrs
            eqc = row["equipment_code"]
            unmapped_equip[eqc] = unmapped_equip.get(eqc, 0) + hrs

    # Per diem: compute worker-days per cost code and add to labor cost
    per_diem_total = 0.0
    if per_diem_rate > 0:
        wd_rows = conn.execute("""
            SELECT cost_code, COUNT(DISTINCT employee_name || '|' || date) as worker_days
            FROM hj_timecard
            WHERE job_id = ? AND pay_class_code IS NOT NULL AND hours > 0
            GROUP BY cost_code
        """, (job_id,)).fetchall()
        for wd in wd_rows:
            cc = wd["cost_code"]
            pd_cost = wd["worker_days"] * per_diem_rate
            per_diem_total += pd_cost
            if cc in cc_data:
                cc_data[cc]["labor_cost"] += pd_cost

    # Round and compute totals
    job_totals = {"labor_cost": 0, "equip_cost": 0, "total_cost": 0,
                  "labor_hours": 0, "equip_hours": 0,
                  "ot_fraction": round(ot_fraction, 4),
                  "per_diem_rate": per_diem_rate,
                  "per_diem_total": round(per_diem_total, 2)}
    for cc, data in cc_data.items():
        data["labor_cost"] = round(data["labor_cost"], 2)
        data["equip_cost"] = round(data["equip_cost"], 2)
        data["total_cost"] = round(data["labor_cost"] + data["equip_cost"], 2)
        job_totals["labor_cost"] += data["labor_cost"]
        job_totals["equip_cost"] += data["equip_cost"]
        job_totals["labor_hours"] += data["labor_hours"]
        job_totals["equip_hours"] += data["equip_hours"]

    job_totals["labor_cost"] = round(job_totals["labor_cost"], 2)
    job_totals["equip_cost"] = round(job_totals["equip_cost"], 2)
    job_totals["total_cost"] = round(job_totals["labor_cost"] + job_totals["equip_cost"], 2)

    return {
        "job_totals": job_totals,
        "cost_codes": cc_data,
        "unmapped_labor": [{"pay_class_code": k, "hours": round(v, 1)}
                           for k, v in sorted(unmapped_labor.items())],
        "unmapped_equipment": [{"equipment_code": k, "hours": round(v, 1)}
                               for k, v in sorted(unmapped_equip.items(), key=lambda x: -x[1])[:20]],
    }


def get_recast_summary_all_jobs(conn: sqlite3.Connection) -> list[dict]:
    """Get recast cost totals for every job with OT adjustment.

    Uses a CTE to compute per-job OT fraction from weekly hours.
    """
    rows = conn.execute("""
        WITH job_ot AS (
            SELECT job_id,
                   CASE WHEN SUM(weekly_hrs) > 0
                        THEN SUM(CASE WHEN weekly_hrs > ?
                                      THEN weekly_hrs - ? ELSE 0 END) * 1.0
                             / SUM(weekly_hrs)
                        ELSE 0 END as ot_fraction
            FROM (
                SELECT job_id, employee_name,
                       strftime('%Y-%W', date) as week,
                       SUM(hours) as weekly_hrs
                FROM hj_timecard
                WHERE pay_class_code IS NOT NULL AND hours > 0
                GROUP BY job_id, employee_name, week
            )
            GROUP BY job_id
        )
        SELECT j.job_id, j.job_number, j.name,
            COALESCE(labor.labor_cost, 0) as labor_cost,
            COALESCE(labor.labor_hours, 0) as labor_hours,
            COALESCE(equip.equip_cost, 0) as equip_cost,
            COALESCE(equip.equip_hours, 0) as equip_hours,
            COALESCE(jot.ot_fraction, 0) as ot_fraction
        FROM job j
        LEFT JOIN job_ot jot ON jot.job_id = j.job_id
        LEFT JOIN (
            SELECT t.job_id,
                   ROUND(SUM(t.hours * COALESCE(lr.loaded_rate, 0)
                         * (1 + COALESCE(jot.ot_fraction, 0)
                            * (COALESCE(lr.ot_factor, 1.5) - 1))), 2) as labor_cost,
                   ROUND(SUM(t.hours), 1) as labor_hours
            FROM hj_timecard t
            LEFT JOIN labor_rate lr ON t.pay_class_code = lr.pay_class_code
            LEFT JOIN job_ot jot ON jot.job_id = t.job_id
            WHERE t.pay_class_code IS NOT NULL
            GROUP BY t.job_id
        ) labor ON j.job_id = labor.job_id
        LEFT JOIN (
            SELECT e.job_id,
                   ROUND(SUM(e.hours * COALESCE(er.base_rate, 0)), 2) as equip_cost,
                   ROUND(SUM(e.hours), 1) as equip_hours
            FROM hj_equipment_entry e
            LEFT JOIN equipment_rate er ON e.equipment_code = er.equipment_code
            GROUP BY e.job_id
        ) equip ON j.job_id = equip.job_id
        ORDER BY j.job_number
    """, (OT_WEEKLY_THRESHOLD, OT_WEEKLY_THRESHOLD)).fetchall()

    return [
        {
            "job_id": r["job_id"],
            "job_number": r["job_number"],
            "name": r["name"],
            "labor_cost": r["labor_cost"],
            "labor_hours": r["labor_hours"],
            "equip_cost": r["equip_cost"],
            "equip_hours": r["equip_hours"],
            "total_cost": round(r["labor_cost"] + r["equip_cost"], 2),
            "ot_fraction": round(r["ot_fraction"], 4),
        }
        for r in rows
    ]


def get_rate_coverage(conn: sqlite3.Connection) -> dict:
    """Check how well actual timecard/equipment data maps to imported rates."""
    # Labor coverage
    labor_stats = conn.execute("""
        SELECT
            COUNT(DISTINCT t.pay_class_code) as total_codes,
            COUNT(DISTINCT CASE WHEN lr.pay_class_code IS NOT NULL THEN t.pay_class_code END) as mapped_codes,
            SUM(t.hours) as total_hours,
            SUM(CASE WHEN lr.pay_class_code IS NOT NULL THEN t.hours ELSE 0 END) as mapped_hours
        FROM hj_timecard t
        LEFT JOIN labor_rate lr ON t.pay_class_code = lr.pay_class_code
        WHERE t.pay_class_code IS NOT NULL AND t.pay_class_code != ''
    """).fetchone()

    # Equipment coverage
    equip_stats = conn.execute("""
        SELECT
            COUNT(DISTINCT e.equipment_code) as total_codes,
            COUNT(DISTINCT CASE WHEN er.equipment_code IS NOT NULL THEN e.equipment_code END) as mapped_codes,
            SUM(e.hours) as total_hours,
            SUM(CASE WHEN er.equipment_code IS NOT NULL THEN e.hours ELSE 0 END) as mapped_hours
        FROM hj_equipment_entry e
        LEFT JOIN equipment_rate er ON e.equipment_code = er.equipment_code
        WHERE e.equipment_code IS NOT NULL
    """).fetchone()

    return {
        "labor": {
            "total_codes": labor_stats["total_codes"],
            "mapped_codes": labor_stats["mapped_codes"],
            "total_hours": round(labor_stats["total_hours"] or 0, 0),
            "mapped_hours": round(labor_stats["mapped_hours"] or 0, 0),
            "coverage_pct": round(
                (labor_stats["mapped_hours"] or 0) / (labor_stats["total_hours"] or 1) * 100, 1
            ),
        },
        "equipment": {
            "total_codes": equip_stats["total_codes"],
            "mapped_codes": equip_stats["mapped_codes"],
            "total_hours": round(equip_stats["total_hours"] or 0, 0),
            "mapped_hours": round(equip_stats["mapped_hours"] or 0, 0),
            "coverage_pct": round(
                (equip_stats["mapped_hours"] or 0) / (equip_stats["total_hours"] or 1) * 100, 1
            ),
        },
    }
