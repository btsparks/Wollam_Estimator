"""Interview Service — Business logic for PM Context Interview.

Loads job data, cost code details, and manages PM context persistence.
All database queries live here; the API layer is a thin wrapper.
"""

from __future__ import annotations

import json
from datetime import datetime

from app.database import get_connection


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

        # Build trade-based crew breakdown from timecards (batch query)
        trade_rows = conn.execute("""
            SELECT cost_code,
                   pay_class_code,
                   COUNT(DISTINCT employee_name) as workers,
                   COUNT(DISTINCT date) as days,
                   ROUND(SUM(hours), 1) as total_hrs
            FROM hj_timecard
            WHERE job_id = ? AND pay_class_code IS NOT NULL AND pay_class_code != ''
            GROUP BY cost_code, pay_class_code
            ORDER BY cost_code, total_hrs DESC
        """, (job_id,)).fetchall()

        # Build lookup: {cost_code: {trade: {workers, days, hours}}}
        trade_breakdown = {}
        for tr in trade_rows:
            cc_code = tr["cost_code"]
            if cc_code not in trade_breakdown:
                trade_breakdown[cc_code] = {}
            trade_breakdown[cc_code][tr["pay_class_code"]] = {
                "workers": tr["workers"],
                "days": tr["days"],
                "hours": tr["total_hrs"],
            }

        # Build equipment breakdown from rate_item crew_breakdown (equipment key)
        equip_lookup = {}
        for cc_row in cost_codes:
            if cc_row["crew_breakdown"]:
                try:
                    cb = json.loads(cc_row["crew_breakdown"])
                    if cb.get("equipment"):
                        equip_lookup[cc_row["code"]] = cb["equipment"]
                except (json.JSONDecodeError, TypeError):
                    pass

        formatted_codes = []
        for cc in cost_codes:
            cc = dict(cc)
            # Crew breakdown: trades from timecards, equipment from rate_item
            crew = {
                "trades": trade_breakdown.get(cc["code"], {}),
                "equipment": equip_lookup.get(cc["code"], []),
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
                                    general_notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                pm_name = COALESCE(excluded.pm_name, pm_context.pm_name),
                project_summary = COALESCE(excluded.project_summary, pm_context.project_summary),
                site_conditions = COALESCE(excluded.site_conditions, pm_context.site_conditions),
                key_challenges = COALESCE(excluded.key_challenges, pm_context.key_challenges),
                key_successes = COALESCE(excluded.key_successes, pm_context.key_successes),
                lessons_learned = COALESCE(excluded.lessons_learned, pm_context.lessons_learned),
                general_notes = COALESCE(excluded.general_notes, pm_context.general_notes),
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
