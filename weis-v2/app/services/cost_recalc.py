"""Recast cost calculation from actual hours × current rates."""

import sqlite3


def get_recast_costs_by_job(conn: sqlite3.Connection, job_id: int) -> dict:
    """Calculate recast costs for all cost codes in a job.

    Returns dict with:
        job_totals: {labor_cost, equip_cost, total_cost, labor_hours, equip_hours}
        cost_codes: {code: {labor_cost, equip_cost, total_cost, labor_hours, equip_hours, unmapped_labor_hrs, unmapped_equip_hrs}}
        unmapped_labor: [{pay_class_code, hours}]
        unmapped_equipment: [{equipment_code, hours}]
    """
    # Labor costs: timecard hours × loaded rate
    labor_rows = conn.execute("""
        SELECT t.cost_code,
               COALESCE(lr.loaded_rate, 0) as rate,
               lr.pay_class_code as matched_code,
               t.pay_class_code,
               SUM(t.hours) as hours
        FROM hj_timecard t
        LEFT JOIN labor_rate lr ON t.pay_class_code = lr.pay_class_code
        WHERE t.job_id = ? AND t.pay_class_code IS NOT NULL AND t.pay_class_code != ''
        GROUP BY t.cost_code, t.pay_class_code
    """, (job_id,)).fetchall()

    # Equipment costs: equipment hours × base rate (direct match or group avg fallback)
    equip_rows = conn.execute("""
        SELECT e.cost_code,
               e.equipment_code,
               COALESCE(er.base_rate, gr.avg_rate, 0) as rate,
               er.equipment_code as matched_code,
               gr.group_name as matched_group,
               SUM(e.hours) as hours
        FROM hj_equipment_entry e
        LEFT JOIN equipment_rate er ON e.equipment_code = er.equipment_code
        LEFT JOIN (
            SELECT group_name, AVG(base_rate) as avg_rate
            FROM equipment_rate
            WHERE group_name != '' AND base_rate > 0
            GROUP BY group_name
        ) gr ON er.group_name = gr.group_name
        WHERE e.job_id = ?
        GROUP BY e.cost_code, e.equipment_code
    """, (job_id,)).fetchall()

    cc_data = {}
    unmapped_labor = {}
    unmapped_equip = {}

    # Process labor
    for row in labor_rows:
        cc = row["cost_code"]
        if cc not in cc_data:
            cc_data[cc] = {"labor_cost": 0, "equip_cost": 0, "labor_hours": 0,
                           "equip_hours": 0, "unmapped_labor_hrs": 0, "unmapped_equip_hrs": 0}
        hrs = row["hours"] or 0
        rate = row["rate"] or 0
        cc_data[cc]["labor_cost"] += hrs * rate
        cc_data[cc]["labor_hours"] += hrs
        if not row["matched_code"]:
            cc_data[cc]["unmapped_labor_hrs"] += hrs
            pcc = row["pay_class_code"]
            unmapped_labor[pcc] = unmapped_labor.get(pcc, 0) + hrs

    # Process equipment
    for row in equip_rows:
        cc = row["cost_code"]
        if cc not in cc_data:
            cc_data[cc] = {"labor_cost": 0, "equip_cost": 0, "labor_hours": 0,
                           "equip_hours": 0, "unmapped_labor_hrs": 0, "unmapped_equip_hrs": 0}
        hrs = row["hours"] or 0
        rate = row["rate"] or 0
        cc_data[cc]["equip_cost"] += hrs * rate
        cc_data[cc]["equip_hours"] += hrs
        if not row["matched_code"] and not row["matched_group"]:
            cc_data[cc]["unmapped_equip_hrs"] += hrs
            eqc = row["equipment_code"]
            unmapped_equip[eqc] = unmapped_equip.get(eqc, 0) + hrs

    # Round and compute totals
    job_totals = {"labor_cost": 0, "equip_cost": 0, "total_cost": 0,
                  "labor_hours": 0, "equip_hours": 0}
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
    """Get recast cost totals for every job. Lightweight summary query."""
    rows = conn.execute("""
        SELECT j.job_id, j.job_number, j.name,
            COALESCE(labor.labor_cost, 0) as labor_cost,
            COALESCE(labor.labor_hours, 0) as labor_hours,
            COALESCE(equip.equip_cost, 0) as equip_cost,
            COALESCE(equip.equip_hours, 0) as equip_hours
        FROM job j
        LEFT JOIN (
            SELECT t.job_id,
                   ROUND(SUM(t.hours * COALESCE(lr.loaded_rate, 0)), 2) as labor_cost,
                   ROUND(SUM(t.hours), 1) as labor_hours
            FROM hj_timecard t
            LEFT JOIN labor_rate lr ON t.pay_class_code = lr.pay_class_code
            WHERE t.pay_class_code IS NOT NULL
            GROUP BY t.job_id
        ) labor ON j.job_id = labor.job_id
        LEFT JOIN (
            SELECT e.job_id,
                   ROUND(SUM(e.hours * COALESCE(er.base_rate, gr.avg_rate, 0)), 2) as equip_cost,
                   ROUND(SUM(e.hours), 1) as equip_hours
            FROM hj_equipment_entry e
            LEFT JOIN equipment_rate er ON e.equipment_code = er.equipment_code
            LEFT JOIN (
                SELECT group_name, AVG(base_rate) as avg_rate
                FROM equipment_rate
                WHERE group_name != '' AND base_rate > 0
                GROUP BY group_name
            ) gr ON er.group_name = gr.group_name
            GROUP BY e.job_id
        ) equip ON j.job_id = equip.job_id
        ORDER BY j.job_number
    """).fetchall()

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
