"""
HCSS Storage Layer — Pydantic Models <-> v2.0 SQLite Tables

Bridges the gap between in-memory Pydantic models and the v2.0 database
schema. Every other Phase C component depends on this module.

Tier 1 Writers: Raw API data -> DB (job, hj_costcode, hj_timecard, etc.)
Tier 2 Writers: Transformed data -> DB (rate_card, rate_item)
Readers:        DB -> dicts (for Streamlit pages and review workflows)
Sync Metadata:  Audit trail for sync operations

Pattern: uses get_connection() with try/finally/close.
         Uses INSERT OR REPLACE for idempotency.
         Parameterized queries only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.database import get_connection
import logging

from app.hcss.models import (
    HBActivity,
    HBBidItem,
    HBEstimate,
    HBEstimateFilters,
    HBEstimateTotals,
    HBResource,
    HJChangeOrder,
    HJCostCode,
    HJJob,
    HJMaterial,
    HJSubcontract,
    HJTimeCard,
)

logger = logging.getLogger(__name__)
from app.transform.rate_card import RateCardResult, RateItemResult


# ─────────────────────────────────────────────────────────────
# Tier 1 Writers — Raw API Data -> DB
# ─────────────────────────────────────────────────────────────

def upsert_business_unit(hcss_bu_id: str, name: str) -> int:
    """Insert or update a business unit. Returns bu_id."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO business_unit (hcss_bu_id, name)
               VALUES (?, ?)
               ON CONFLICT(hcss_bu_id) DO UPDATE SET name = excluded.name""",
            (hcss_bu_id, name),
        )
        conn.commit()
        row = conn.execute(
            "SELECT bu_id FROM business_unit WHERE hcss_bu_id = ?",
            (hcss_bu_id,),
        ).fetchone()
        return row["bu_id"]
    finally:
        conn.close()


def upsert_job(job: HJJob, bu_id: int, data_source: str = "hcss_api") -> int:
    """Insert or update a job record. Returns job_id."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO job (hcss_job_id, job_number, name, status,
                   start_date, end_date, bu_id, owner_client, contract_type,
                   project_type, location, data_source, last_synced)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(hcss_job_id) DO UPDATE SET
                   job_number = excluded.job_number,
                   name = excluded.name,
                   status = excluded.status,
                   start_date = excluded.start_date,
                   end_date = excluded.end_date,
                   bu_id = excluded.bu_id,
                   owner_client = excluded.owner_client,
                   contract_type = excluded.contract_type,
                   project_type = excluded.project_type,
                   location = excluded.location,
                   data_source = excluded.data_source,
                   last_synced = excluded.last_synced""",
            (
                job.id, job.jobNumber, job.description or "", job.status,
                None,  # start_date — not in costCodes API, enrich later
                None,  # end_date — not in costCodes API, enrich later
                bu_id, None, None,
                None, None,
                data_source, datetime.now().isoformat(),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT job_id FROM job WHERE hcss_job_id = ?", (job.id,),
        ).fetchone()
        return row["job_id"]
    finally:
        conn.close()


def upsert_cost_codes(
    cost_codes: list[HJCostCode],
    job_id: int,
    mapper: Any = None,
) -> int:
    """Insert or update cost codes for a job. Returns count inserted."""
    conn = get_connection()
    try:
        count = 0
        for cc in cost_codes:
            discipline = None
            if mapper and cc.code:
                discipline = mapper.map_code(cc.code, cc.description)

            conn.execute(
                """INSERT INTO hj_costcode (
                       hcss_cc_id, job_id, code, description, discipline, unit,
                       bgt_qty, bgt_labor_hrs, bgt_labor_cost,
                       bgt_equip_hrs, bgt_equip_cost,
                       bgt_matl_cost, bgt_sub_cost, bgt_total,
                       act_qty, act_labor_hrs, act_labor_cost,
                       act_equip_hrs, act_equip_cost,
                       act_matl_cost, act_sub_cost, act_total,
                       pct_complete)
                   VALUES (?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(job_id, code) DO UPDATE SET
                       hcss_cc_id = excluded.hcss_cc_id,
                       description = excluded.description,
                       discipline = excluded.discipline,
                       unit = excluded.unit,
                       bgt_qty = excluded.bgt_qty,
                       bgt_labor_hrs = excluded.bgt_labor_hrs,
                       bgt_labor_cost = excluded.bgt_labor_cost,
                       bgt_equip_hrs = excluded.bgt_equip_hrs,
                       bgt_equip_cost = excluded.bgt_equip_cost,
                       bgt_matl_cost = excluded.bgt_matl_cost,
                       bgt_sub_cost = excluded.bgt_sub_cost,
                       bgt_total = excluded.bgt_total,
                       act_qty = excluded.act_qty,
                       act_labor_hrs = excluded.act_labor_hrs,
                       act_labor_cost = excluded.act_labor_cost,
                       act_equip_hrs = excluded.act_equip_hrs,
                       act_equip_cost = excluded.act_equip_cost,
                       act_matl_cost = excluded.act_matl_cost,
                       act_sub_cost = excluded.act_sub_cost,
                       act_total = excluded.act_total,
                       pct_complete = excluded.pct_complete""",
                (
                    cc.id, job_id, cc.code, cc.description, discipline, cc.unit,
                    cc.budgetQuantity, cc.budgetLaborHours, cc.budgetLaborCost,
                    cc.budgetEquipmentHours, cc.budgetEquipmentCost,
                    cc.budgetMaterialCost, cc.budgetSubcontractCost, cc.budgetTotalCost,
                    cc.actualQuantity, cc.actualLaborHours, cc.actualLaborCost,
                    cc.actualEquipmentHours, cc.actualEquipmentCost,
                    cc.actualMaterialCost, cc.actualSubcontractCost, cc.actualTotalCost,
                    cc.percentComplete,
                ),
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def upsert_timecards(timecards: list[HJTimeCard], job_id: int) -> int:
    """Insert time cards for a job. Returns count inserted."""
    conn = get_connection()
    try:
        count = 0
        for tc in timecards:
            conn.execute(
                """INSERT INTO hj_timecard (
                       hcss_tc_id, job_id, cost_code, date,
                       employee_id, employee_name, employee_code, hours,
                       equip_id, equip_hours, foreman_id,
                       status, quantity,
                       pay_class_code, pay_class_desc, foreman_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tc.id, job_id, tc.costCode,
                    tc.tc_date,
                    tc.employeeId, tc.employeeName, tc.employeeCode, tc.hours,
                    tc.equipmentId, tc.equipmentHours, tc.foremanId,
                    tc.status, tc.quantity,
                    tc.payClassCode, tc.payClassDesc, tc.foremanName,
                ),
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def upsert_change_orders(cos: list[HJChangeOrder], job_id: int) -> int:
    """Insert change orders for a job. Returns count inserted."""
    conn = get_connection()
    try:
        count = 0
        for co in cos:
            conn.execute(
                """INSERT INTO hj_change_order (
                       hcss_co_id, job_id, co_number, description,
                       amount, status, approved_date, category,
                       schedule_impact)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    co.id, job_id, co.changeOrderNumber, co.description,
                    co.amount, co.status,
                    str(co.approvedDate) if co.approvedDate else None,
                    co.category, co.scheduleImpact,
                ),
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def upsert_materials(materials: list[HJMaterial], job_id: int) -> int:
    """Insert materials for a job. Returns count inserted."""
    conn = get_connection()
    try:
        count = 0
        for mat in materials:
            conn.execute(
                """INSERT INTO hj_material (
                       hcss_mat_id, job_id, description, quantity,
                       unit, unit_cost, total_cost, vendor,
                       po_number, date_received)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    mat.id, job_id, mat.description, mat.quantity,
                    mat.unit, mat.unitCost, mat.totalCost, mat.vendor,
                    mat.poNumber,
                    str(mat.dateReceived) if mat.dateReceived else None,
                ),
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def upsert_subcontracts(subs: list[HJSubcontract], job_id: int) -> int:
    """Insert subcontracts for a job. Returns count inserted."""
    conn = get_connection()
    try:
        count = 0
        for sub in subs:
            conn.execute(
                """INSERT INTO hj_subcontract (
                       hcss_sub_id, job_id, vendor, scope,
                       contract_amount, actual_amount, status, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sub.id, job_id, sub.vendor, sub.scope,
                    sub.contractAmount, sub.actualAmount,
                    sub.status, sub.notes,
                ),
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def upsert_hb_estimate(estimate: HBEstimate, bu_id: str) -> int:
    """Insert or update a HeavyBid estimate. Auto-links to HeavyJob by job number.
    Returns the local estimate_id."""
    import re
    conn = get_connection()
    try:
        # Parse job number from estimate code (e.g. "8553-CO-WEIR" -> "8553")
        linked_job_number = None
        linked_job_id = None
        if estimate.code:
            m = re.match(r'^(\d+)', estimate.code)
            if m:
                linked_job_number = m.group(1)
                row = conn.execute(
                    "SELECT job_id FROM job WHERE job_number = ?",
                    (linked_job_number,),
                ).fetchone()
                if row:
                    linked_job_id = row["job_id"]
                else:
                    logger.warning(
                        "Estimate %s: job number %s not found in HeavyJob",
                        estimate.code, linked_job_number,
                    )

        # Extract flattened values from nested objects
        f = estimate.filters or HBEstimateFilters()
        t = estimate.totals or HBEstimateTotals()

        conn.execute(
            """INSERT INTO hb_estimate (
                   hcss_est_id, bu_id, code, name, description,
                   estimate_version, processed_status,
                   project_name, project_number, bid_date, start_date,
                   created_date, modified_date, state, estimator, owner, type_of_work,
                   total_labor, total_burden, total_perm_material, total_const_material,
                   total_subcontract, total_equip_oe, total_company_equip, total_rented_equip,
                   total_equip, total_entry_cost, bid_total, total_manhours,
                   bal_markup, actual_markup, total_cost_takeoff, addon_bond_total, job_duration,
                   linked_job_number, linked_job_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(hcss_est_id) DO UPDATE SET
                   bu_id=excluded.bu_id, code=excluded.code, name=excluded.name,
                   description=excluded.description, estimate_version=excluded.estimate_version,
                   processed_status=excluded.processed_status,
                   project_name=excluded.project_name, project_number=excluded.project_number,
                   bid_date=excluded.bid_date, start_date=excluded.start_date,
                   created_date=excluded.created_date, modified_date=excluded.modified_date,
                   state=excluded.state, estimator=excluded.estimator, owner=excluded.owner,
                   type_of_work=excluded.type_of_work,
                   total_labor=excluded.total_labor, total_burden=excluded.total_burden,
                   total_perm_material=excluded.total_perm_material,
                   total_const_material=excluded.total_const_material,
                   total_subcontract=excluded.total_subcontract,
                   total_equip_oe=excluded.total_equip_oe,
                   total_company_equip=excluded.total_company_equip,
                   total_rented_equip=excluded.total_rented_equip,
                   total_equip=excluded.total_equip, total_entry_cost=excluded.total_entry_cost,
                   bid_total=excluded.bid_total, total_manhours=excluded.total_manhours,
                   bal_markup=excluded.bal_markup, actual_markup=excluded.actual_markup,
                   total_cost_takeoff=excluded.total_cost_takeoff,
                   addon_bond_total=excluded.addon_bond_total, job_duration=excluded.job_duration,
                   linked_job_number=excluded.linked_job_number,
                   linked_job_id=excluded.linked_job_id,
                   synced_at=CURRENT_TIMESTAMP""",
            (
                estimate.id, bu_id, estimate.code, estimate.name, estimate.description,
                estimate.estimateVersion, estimate.processedStatus,
                f.projectName, f.projectNumber, f.bidDate, f.startDate,
                f.createdDate, f.modifiedDate, f.state, f.estimator, f.owner, f.typeOfWork,
                t.totalLabor_Total, t.burden_Total, t.permanentMaterial_Total,
                t.constructionMaterial_Total, t.subcontract_Total,
                t.equipmentOperatingExpense_Total, t.companyEquipment_Total,
                t.rentedEquipment_Total, t.totalEqp_Total,
                t.totalEntryCost_Bid_Total, t.bidTotal_Bid, t.manhours_Total,
                t.balMarkup_Bid, t.actualMarkup_Bid, t.totalCost_Takeoff,
                t.addonBondTotal, t.job_Duration,
                linked_job_number, linked_job_id,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT estimate_id FROM hb_estimate WHERE hcss_est_id = ?",
            (estimate.id,),
        ).fetchone()
        return row["estimate_id"]
    finally:
        conn.close()


def upsert_hb_biditems(items: list[HBBidItem], estimate_id: int) -> int:
    """Insert or replace bid items for an estimate. Returns count."""
    conn = get_connection()
    try:
        # Clear existing bid items for re-sync
        conn.execute("DELETE FROM hb_biditem WHERE estimate_id = ?", (estimate_id,))
        count = 0
        for item in items:
            conn.execute(
                """INSERT INTO hb_biditem (
                       hcss_bi_id, estimate_id, biditem_code, description, type,
                       quantity, bid_quantity, units, bid_price,
                       labor, burden, perm_material, const_material,
                       subcontract, equip_oe, company_equip, rented_equip,
                       misc1, misc2, misc3, direct_total, indirect_total,
                       total_cost, manhours, markup, total_takeoff, total_balanced,
                       addon_bond, pricing_status, cost_notes, bid_notes,
                       folder, review_flag, sort_code)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item.id, estimate_id, item.biditemCode, item.description, item.type,
                    item.quantity, item.bidQuantity, item.units, item.bidPrice,
                    item.labor, item.burden, item.permanentMaterial, item.constructionMaterial,
                    item.subcontract, item.equipmentOperatingExpense, item.companyEquipment,
                    item.rentedEquipment,
                    item.misc1, item.misc2, item.misc3, item.directTotal, item.indirectTotal,
                    item.totalCost, item.manhours, item.markup, item.totalTakeoff,
                    item.totalBalanced, item.addonBond,
                    item.pricingStatus, item.costNotes, item.bidNotes,
                    item.folder, item.reviewFlag, item.sortCode,
                ),
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def upsert_hb_activities(activities: list[HBActivity], estimate_id: int) -> int:
    """Insert or replace activities for an estimate. Returns count."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM hb_activity WHERE estimate_id = ?", (estimate_id,))
        count = 0
        for act in activities:
            conn.execute(
                """INSERT INTO hb_activity (
                       hcss_act_id, estimate_id, hcss_biditem_id, biditem_code,
                       activity_code, description, quantity, units,
                       production_type, production_rate, hours_per_day,
                       crew, crew_hours, crew_percent, man_hours,
                       calculated_duration, efficient_percent,
                       labor, burden, perm_material, const_material,
                       subcontract, equip_oe, company_equip, rented_equip,
                       misc1, misc2, misc3, direct_total, crew_cost,
                       notes, workers_comp_code, calendar, factorable, factor,
                       non_additive, heavyjob_code, heavyjob_description,
                       heavyjob_quantity, heavyjob_unit)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    act.id, estimate_id, act.biditemId, act.biditemCode,
                    act.activityCode, act.description, act.quantity, act.units,
                    act.productionType, act.productionRate, act.hoursPerDay,
                    act.crew, act.crewHours, act.crewPercent, act.manHours,
                    act.calculatedDuration, act.efficientPercent,
                    act.labor, act.burden, act.permanentMaterial, act.constructionMaterial,
                    act.subcontract, act.equipmentOperatingExpense, act.companyEquipment,
                    act.rentedEquipment,
                    act.misc1, act.misc2, act.misc3, act.directTotal, act.crewCost,
                    act.notes, act.workersCompCode, act.calendar, act.factorable, act.factor,
                    act.nonAdditive, act.heavyJobCode, act.heavyJobDescription,
                    act.heavyJobQuantity, act.heavyJobUnit,
                ),
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def upsert_hb_resources(resources: list[HBResource], estimate_id: int) -> int:
    """Insert or replace resources for an estimate. Returns count."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM hb_resource WHERE estimate_id = ?", (estimate_id,))
        count = 0
        for res in resources:
            conn.execute(
                """INSERT INTO hb_resource (
                       hcss_res_id, estimate_id, hcss_biditem_id, hcss_activity_id,
                       activity_code, biditem_code, resource_code, description,
                       type_cost, sub_type, quantity, units, percent,
                       unit_price, currency, total, pieces,
                       factorable, factor, skip_cost,
                       operating_percent, rent_percent, crew_code,
                       equip_operator_code, man_hour_unit)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    res.id, estimate_id, res.biditemId, res.activityId,
                    res.activityCode, res.biditemCode, res.resourceCode, res.description,
                    res.typeCost, res.subType, res.quantity, res.units, res.percent,
                    res.unitPrice, res.currency, res.total, res.pieces,
                    res.factorable, res.factor, res.skipCost,
                    res.operatingPercent, res.rentPercent, res.crewCode,
                    res.equipmentOperatorCode, res.manHourUnit,
                ),
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


# ── HeavyBid Readers ───────────────────────────────────────────

def get_all_hb_estimates() -> list[dict]:
    """Get all synced HeavyBid estimates with linked job info."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT e.*,
                   j.job_number AS hj_job_number,
                   j.name AS hj_job_name,
                   j.status AS hj_job_status,
                   (SELECT COUNT(*) FROM hb_biditem bi WHERE bi.estimate_id = e.estimate_id) AS biditem_count,
                   (SELECT COUNT(*) FROM hb_activity a WHERE a.estimate_id = e.estimate_id) AS activity_count,
                   (SELECT COUNT(*) FROM hb_resource r WHERE r.estimate_id = e.estimate_id) AS resource_count
            FROM hb_estimate e
            LEFT JOIN job j ON e.linked_job_id = j.job_id
            ORDER BY e.code
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_hb_estimate_detail(estimate_id: int) -> dict | None:
    """Get a single HeavyBid estimate with linked job info and counts."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT e.*,
                   j.job_number AS hj_job_number,
                   j.name AS hj_job_name,
                   j.status AS hj_job_status,
                   (SELECT COUNT(*) FROM hb_biditem bi WHERE bi.estimate_id = e.estimate_id) AS biditem_count,
                   (SELECT COUNT(*) FROM hb_activity a WHERE a.estimate_id = e.estimate_id) AS activity_count,
                   (SELECT COUNT(*) FROM hb_resource r WHERE r.estimate_id = e.estimate_id) AS resource_count
            FROM hb_estimate e
            LEFT JOIN job j ON e.linked_job_id = j.job_id
            WHERE e.estimate_id = ?
        """, (estimate_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_hb_biditems(estimate_id: int) -> list[dict]:
    """Get all bid items for an estimate, ordered by sort code."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT bi.*,
                   (SELECT COUNT(*) FROM hb_activity a WHERE a.estimate_id = bi.estimate_id
                    AND a.hcss_biditem_id = bi.hcss_bi_id) AS activity_count
            FROM hb_biditem bi
            WHERE bi.estimate_id = ?
            ORDER BY bi.sort_code, bi.biditem_code
        """, (estimate_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_hb_activities(estimate_id: int, biditem_id: str = None) -> list[dict]:
    """Get activities for an estimate, optionally filtered by bid item."""
    conn = get_connection()
    try:
        if biditem_id:
            rows = conn.execute("""
                SELECT a.*,
                       (SELECT COUNT(*) FROM hb_resource r WHERE r.estimate_id = a.estimate_id
                        AND r.hcss_activity_id = a.hcss_act_id) AS resource_count
                FROM hb_activity a
                WHERE a.estimate_id = ? AND a.hcss_biditem_id = ?
                ORDER BY a.activity_code
            """, (estimate_id, biditem_id)).fetchall()
        else:
            rows = conn.execute("""
                SELECT a.*,
                       (SELECT COUNT(*) FROM hb_resource r WHERE r.estimate_id = a.estimate_id
                        AND r.hcss_activity_id = a.hcss_act_id) AS resource_count
                FROM hb_activity a
                WHERE a.estimate_id = ?
                ORDER BY a.biditem_code, a.activity_code
            """, (estimate_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_hb_resources(estimate_id: int, activity_id: str = None) -> list[dict]:
    """Get resources for an estimate, optionally filtered by activity."""
    conn = get_connection()
    try:
        if activity_id:
            rows = conn.execute("""
                SELECT * FROM hb_resource
                WHERE estimate_id = ? AND hcss_activity_id = ?
                ORDER BY type_cost, resource_code
            """, (estimate_id, activity_id)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM hb_resource
                WHERE estimate_id = ?
                ORDER BY activity_code, type_cost, resource_code
            """, (estimate_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_hb_estimates_for_job(job_id: int) -> list[dict]:
    """Get all HeavyBid estimates linked to a HeavyJob job."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT estimate_id, hcss_est_id, code, name, bid_total, total_manhours
            FROM hb_estimate
            WHERE linked_job_id = ?
            ORDER BY code
        """, (job_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Tier 2 Writers — Transformed Data -> DB
# ─────────────────────────────────────────────────────────────

def upsert_rate_card(card: RateCardResult, job_id: int) -> int:
    """Insert or update a rate card for a job. Returns card_id."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO rate_card (
                   job_id, total_budget, total_actual,
                   status, data_source, generated_date)
               VALUES (?, ?, ?, 'draft', ?, ?)
               ON CONFLICT(job_id) DO UPDATE SET
                   total_budget = excluded.total_budget,
                   total_actual = excluded.total_actual,
                   data_source = excluded.data_source,
                   generated_date = excluded.generated_date""",
            (
                job_id, card.total_budget, card.total_actual,
                card.data_source,
                card.generated_date.isoformat() if card.generated_date else datetime.now().isoformat(),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT card_id FROM rate_card WHERE job_id = ?", (job_id,),
        ).fetchone()
        return row["card_id"]
    finally:
        conn.close()


def upsert_rate_items(items: list[RateItemResult], card_id: int) -> int:
    """Insert or update rate items for a card. Returns count inserted."""
    conn = get_connection()
    try:
        count = 0
        for item in items:
            conn.execute(
                """INSERT INTO rate_item (
                       card_id, discipline, activity, description, unit,
                       bgt_mh_per_unit, bgt_cost_per_unit,
                       act_mh_per_unit, act_cost_per_unit,
                       rec_rate, rec_basis,
                       qty_budget, qty_actual,
                       confidence, confidence_reason,
                       variance_pct, variance_flag,
                       timecard_count, work_days, crew_size_avg,
                       daily_qty_avg, daily_qty_peak,
                       total_hours, total_qty,
                       total_labor_cost, total_equip_cost,
                       crew_breakdown)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(card_id, activity) DO UPDATE SET
                       discipline = excluded.discipline,
                       description = excluded.description,
                       unit = excluded.unit,
                       bgt_mh_per_unit = excluded.bgt_mh_per_unit,
                       bgt_cost_per_unit = excluded.bgt_cost_per_unit,
                       act_mh_per_unit = excluded.act_mh_per_unit,
                       act_cost_per_unit = excluded.act_cost_per_unit,
                       rec_rate = excluded.rec_rate,
                       rec_basis = excluded.rec_basis,
                       qty_budget = excluded.qty_budget,
                       qty_actual = excluded.qty_actual,
                       confidence = excluded.confidence,
                       confidence_reason = excluded.confidence_reason,
                       variance_pct = excluded.variance_pct,
                       variance_flag = excluded.variance_flag,
                       timecard_count = excluded.timecard_count,
                       work_days = excluded.work_days,
                       crew_size_avg = excluded.crew_size_avg,
                       daily_qty_avg = excluded.daily_qty_avg,
                       daily_qty_peak = excluded.daily_qty_peak,
                       total_hours = excluded.total_hours,
                       total_qty = excluded.total_qty,
                       total_labor_cost = excluded.total_labor_cost,
                       total_equip_cost = excluded.total_equip_cost,
                       crew_breakdown = excluded.crew_breakdown""",
                (
                    card_id, item.discipline, item.activity,
                    item.description, item.unit,
                    item.bgt_mh_per_unit, item.bgt_cost_per_unit,
                    item.act_mh_per_unit, item.act_cost_per_unit,
                    item.rec_rate, item.rec_basis,
                    item.qty_budget, item.qty_actual,
                    item.confidence, item.confidence_reason,
                    item.variance_pct, item.variance_flag,
                    item.timecard_count, item.work_days, item.crew_size_avg,
                    item.daily_qty_avg, item.daily_qty_peak,
                    item.total_hours, item.total_qty,
                    item.total_labor_cost, item.total_equip_cost,
                    item.crew_breakdown,
                ),
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Readers — DB -> dicts
# ─────────────────────────────────────────────────────────────

def get_job_profile(job_id: int) -> dict | None:
    """Get a rich data profile for a job — timecards, cost codes, crew, date range, top activities.

    Returns a single dict with everything needed for the Job Intelligence detail card.
    """
    conn = get_connection()
    try:
        # Core job info
        job = conn.execute("SELECT * FROM job WHERE job_id = ?", (job_id,)).fetchone()
        if not job:
            return None
        job = dict(job)

        # Timecard stats
        tc = conn.execute("""
            SELECT COUNT(*) as tc_count,
                   COUNT(DISTINCT cost_code) as tc_cost_codes,
                   COUNT(DISTINCT employee_id) as employee_count,
                   COUNT(DISTINCT foreman_id) as foreman_count,
                   COUNT(DISTINCT date) as work_days,
                   MIN(date) as first_date,
                   MAX(date) as last_date,
                   ROUND(SUM(hours), 0) as total_actual_hrs
            FROM hj_timecard WHERE job_id = ?
        """, (job_id,)).fetchone()
        tc = dict(tc) if tc else {}

        # Cost code stats
        cc = conn.execute("""
            SELECT COUNT(*) as cc_count,
                   SUM(CASE WHEN bgt_labor_hrs > 0 THEN 1 ELSE 0 END) as cc_with_budget,
                   SUM(CASE WHEN act_labor_hrs > 0 THEN 1 ELSE 0 END) as cc_with_actuals,
                   ROUND(SUM(bgt_labor_hrs), 0) as total_budget_hrs,
                   ROUND(SUM(act_labor_hrs), 0) as total_actual_hrs_cc,
                   ROUND(SUM(bgt_total), 0) as total_budget_cost,
                   ROUND(SUM(act_total), 0) as total_actual_cost,
                   COUNT(DISTINCT discipline) as discipline_count
            FROM hj_costcode WHERE job_id = ?
        """, (job_id,)).fetchone()
        cc = dict(cc) if cc else {}

        # Top 5 cost codes by actual hours (from timecards)
        top_codes = conn.execute("""
            SELECT t.cost_code,
                   cc.description,
                   cc.unit,
                   ROUND(SUM(t.hours), 1) as actual_hrs,
                   COUNT(DISTINCT t.employee_id) as workers,
                   cc.bgt_labor_hrs as budget_hrs
            FROM hj_timecard t
            LEFT JOIN hj_costcode cc ON cc.job_id = ? AND cc.code = t.cost_code
            WHERE t.job_id = ?
            GROUP BY t.cost_code
            ORDER BY actual_hrs DESC
            LIMIT 5
        """, (job_id, job_id)).fetchall()
        top_codes = [dict(r) for r in top_codes]

        # Rate card confidence breakdown
        rc = conn.execute("""
            SELECT rc.card_id, rc.status,
                   COUNT(ri.item_id) as rate_items,
                   SUM(CASE WHEN ri.variance_flag THEN 1 ELSE 0 END) as flagged,
                   SUM(CASE WHEN ri.confidence = 'strong' THEN 1 ELSE 0 END) as conf_strong,
                   SUM(CASE WHEN ri.confidence = 'moderate' THEN 1 ELSE 0 END) as conf_moderate,
                   SUM(CASE WHEN ri.confidence = 'limited' THEN 1 ELSE 0 END) as conf_limited,
                   SUM(CASE WHEN ri.confidence = 'none' THEN 1 ELSE 0 END) as conf_none
            FROM rate_card rc
            LEFT JOIN rate_item ri ON ri.card_id = rc.card_id
            WHERE rc.job_id = ?
            GROUP BY rc.card_id
        """, (job_id,)).fetchone()
        rc = dict(rc) if rc else {}

        # Compute a data richness score (0-100)
        has_timecards = 1 if (tc.get("tc_count") or 0) > 0 else 0
        has_budget = 1 if (cc.get("cc_with_budget") or 0) > 0 else 0
        has_actuals = 1 if (cc.get("cc_with_actuals") or 0) > 0 else 0
        has_multi_crew = 1 if (tc.get("employee_count") or 0) >= 5 else 0
        has_duration = 1 if (tc.get("work_days") or 0) >= 20 else 0
        strong_pct = 0
        if rc.get("rate_items") and rc["rate_items"] > 0:
            strong_pct = ((rc.get("conf_strong") or 0) + (rc.get("conf_moderate") or 0)) / rc["rate_items"]
        data_richness = int(
            (has_timecards * 25) +
            (has_budget * 20) +
            (has_actuals * 20) +
            (has_multi_crew * 10) +
            (has_duration * 10) +
            (strong_pct * 15)
        )

        return {
            "job": job,
            "timecards": tc,
            "cost_codes": cc,
            "top_codes": top_codes,
            "rate_card": rc,
            "data_richness": min(data_richness, 100),
        }
    finally:
        conn.close()


def get_job_by_number(job_number: str) -> dict | None:
    """Get a job by its job number."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM job WHERE job_number = ?", (job_number,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_jobs() -> list[dict]:
    """Get all jobs from the v2.0 job table."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM job ORDER BY job_number",
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_cost_codes_for_job(job_id: int) -> list[dict]:
    """Get all cost codes for a job."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM hj_costcode WHERE job_id = ? ORDER BY code",
            (job_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_rate_card_for_job(job_id: int) -> dict | None:
    """Get the rate card for a specific job."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM rate_card WHERE job_id = ?", (job_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_rate_items_for_card(card_id: int) -> list[dict]:
    """Get all rate items for a rate card."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM rate_item WHERE card_id = ? ORDER BY discipline, activity",
            (card_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_flagged_items_for_card(card_id: int) -> list[dict]:
    """Get rate items with variance_flag = TRUE for a card."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM rate_item WHERE card_id = ? AND variance_flag = 1 ORDER BY discipline, activity",
            (card_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_rate_cards_by_status(status: str) -> list[dict]:
    """Get all rate cards with a given status, joined with job info."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT rc.*, j.job_number, j.name as job_name
               FROM rate_card rc
               JOIN job j ON rc.job_id = j.job_id
               WHERE rc.status = ?
               ORDER BY j.job_number""",
            (status,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_rate_cards() -> list[dict]:
    """Get all rate cards with job info, flagged count, cost code count, and actual hours."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT rc.*, j.job_number, j.name as job_name, j.status as job_status,
                      (SELECT COUNT(*) FROM rate_item ri
                       WHERE ri.card_id = rc.card_id AND ri.variance_flag = 1) as flagged_count,
                      (SELECT COUNT(*) FROM hj_costcode cc
                       WHERE cc.job_id = rc.job_id AND cc.act_labor_hrs > 0) as cc_with_actuals,
                      (SELECT ROUND(SUM(cc2.act_labor_hrs), 0) FROM hj_costcode cc2
                       WHERE cc2.job_id = rc.job_id) as total_actual_hrs
               FROM rate_card rc
               JOIN job j ON rc.job_id = j.job_id
               ORDER BY j.job_number""",
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_job_intelligence_insights() -> dict:
    """Compute cross-job insights for the intelligence dashboard."""
    conn = get_connection()
    try:
        # Top 5 jobs by actual hours (data-richest jobs)
        top_jobs = conn.execute("""
            SELECT j.job_number, j.name as job_name,
                   ROUND(SUM(cc.act_labor_hrs), 0) as total_hrs,
                   COUNT(CASE WHEN cc.act_labor_hrs > 0 THEN 1 END) as cc_with_data
            FROM hj_costcode cc
            JOIN job j ON j.job_id = cc.job_id
            GROUP BY cc.job_id
            HAVING total_hrs > 0
            ORDER BY total_hrs DESC
            LIMIT 5
        """).fetchall()

        # Discipline coverage
        disc_coverage = conn.execute("""
            SELECT discipline,
                   COUNT(*) as total_items,
                   SUM(CASE WHEN act_mh_per_unit > 0 THEN 1 ELSE 0 END) as with_actuals
            FROM rate_item
            WHERE discipline IS NOT NULL AND discipline != 'unmapped'
            GROUP BY discipline
            ORDER BY total_items DESC
        """).fetchall()

        # Overall stats
        overall = conn.execute("""
            SELECT COUNT(DISTINCT ri.card_id) as jobs_with_rates,
                   COUNT(*) as total_items,
                   SUM(CASE WHEN ri.act_mh_per_unit > 0 THEN 1 ELSE 0 END) as items_with_actuals
            FROM rate_item ri
        """).fetchone()

        return {
            "top_jobs": [dict(r) for r in top_jobs],
            "discipline_coverage": [dict(r) for r in disc_coverage],
            "total_rate_items": overall[1] if overall else 0,
            "items_with_actuals": overall[2] if overall else 0,
        }
    finally:
        conn.close()


def get_estimate_for_job(job_id: int) -> dict | None:
    """Get the linked estimate for a job."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT e.* FROM hb_estimate e
               JOIN job j ON j.estimate_id = e.estimate_id
               WHERE j.job_id = ?""",
            (job_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Sync Metadata
# ─────────────────────────────────────────────────────────────

def create_sync_record(
    source: str,
    sync_type: str,
    notes: str | None = None,
) -> int:
    """Create a new sync_metadata record. Returns sync_id."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO sync_metadata (source, sync_type, started_at, status, notes)
               VALUES (?, ?, ?, 'running', ?)""",
            (source, sync_type, datetime.now().isoformat(), notes),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_sync_record(
    sync_id: int,
    status: str,
    jobs_processed: int = 0,
    jobs_failed: int = 0,
    error_log: str | None = None,
) -> None:
    """Update a sync_metadata record with results."""
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE sync_metadata
               SET completed_at = ?, status = ?,
                   jobs_processed = ?, jobs_failed = ?, error_log = ?
               WHERE sync_id = ?""",
            (
                datetime.now().isoformat(), status,
                jobs_processed, jobs_failed, error_log,
                sync_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_last_sync(source: str | None = None) -> dict | None:
    """Get the most recent completed sync record."""
    conn = get_connection()
    try:
        if source:
            row = conn.execute(
                """SELECT * FROM sync_metadata
                   WHERE source = ? AND status = 'completed'
                   ORDER BY completed_at DESC LIMIT 1""",
                (source,),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT * FROM sync_metadata
                   WHERE status = 'completed'
                   ORDER BY completed_at DESC LIMIT 1""",
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_sync_history(limit: int = 10) -> list[dict]:
    """Get recent sync records for the UI."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM sync_metadata
               ORDER BY started_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
