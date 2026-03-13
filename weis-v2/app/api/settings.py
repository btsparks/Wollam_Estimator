"""Settings API — labor/equipment rate management and cost recalculation."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path

from app.database import get_connection
from app.services.rate_import import (
    parse_pay_class_file,
    parse_equipment_file,
    import_labor_rates,
    import_equipment_rates,
)
from app.services.cost_recalc import (
    get_recast_costs_by_job,
    get_recast_summary_all_jobs,
    get_rate_coverage,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Path to HJ rate files (in parent directory)
HJ_RATES_DIR = Path(__file__).parent.parent.parent.parent / "HJ Rates"


# ── Rate listing endpoints ──────────────────────────────────────────

@router.get("/labor-rates")
async def list_labor_rates():
    """List all labor rates."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT lr.*,
                   COALESCE(tc.total_hours, 0) as actual_hours,
                   COALESCE(tc.job_count, 0) as job_count
            FROM labor_rate lr
            LEFT JOIN (
                SELECT pay_class_code,
                       ROUND(SUM(hours), 0) as total_hours,
                       COUNT(DISTINCT job_id) as job_count
                FROM hj_timecard
                WHERE pay_class_code IS NOT NULL
                GROUP BY pay_class_code
            ) tc ON lr.pay_class_code = tc.pay_class_code
            ORDER BY lr.pay_class_code
        """).fetchall()
        return {"rates": [dict(r) for r in rows], "count": len(rows)}
    finally:
        conn.close()


@router.get("/equipment-rates")
async def list_equipment_rates(group: str = None):
    """List equipment rates, optionally filtered by group."""
    conn = get_connection()
    try:
        if group:
            rows = conn.execute("""
                SELECT er.*,
                       COALESCE(eq.total_hours, 0) as actual_hours,
                       COALESCE(eq.job_count, 0) as job_count
                FROM equipment_rate er
                LEFT JOIN (
                    SELECT equipment_code,
                           ROUND(SUM(hours), 0) as total_hours,
                           COUNT(DISTINCT job_id) as job_count
                    FROM hj_equipment_entry
                    GROUP BY equipment_code
                ) eq ON er.equipment_code = eq.equipment_code
                WHERE er.group_name = ?
                ORDER BY er.equipment_code
            """, (group,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT er.*,
                       COALESCE(eq.total_hours, 0) as actual_hours,
                       COALESCE(eq.job_count, 0) as job_count
                FROM equipment_rate er
                LEFT JOIN (
                    SELECT equipment_code,
                           ROUND(SUM(hours), 0) as total_hours,
                           COUNT(DISTINCT job_id) as job_count
                    FROM hj_equipment_entry
                    GROUP BY equipment_code
                ) eq ON er.equipment_code = eq.equipment_code
                ORDER BY er.group_name, er.equipment_code
            """).fetchall()
        return {"rates": [dict(r) for r in rows], "count": len(rows)}
    finally:
        conn.close()


@router.get("/equipment-groups")
async def list_equipment_groups():
    """List equipment groups with aggregate stats."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT er.group_name,
                   COUNT(*) as item_count,
                   ROUND(AVG(er.base_rate), 2) as avg_rate,
                   ROUND(MIN(er.base_rate), 2) as min_rate,
                   ROUND(MAX(er.base_rate), 2) as max_rate,
                   COALESCE(SUM(eq.total_hours), 0) as total_actual_hours
            FROM equipment_rate er
            LEFT JOIN (
                SELECT equipment_code, SUM(hours) as total_hours
                FROM hj_equipment_entry
                GROUP BY equipment_code
            ) eq ON er.equipment_code = eq.equipment_code
            WHERE er.group_name != ''
            GROUP BY er.group_name
            ORDER BY er.group_name
        """).fetchall()
        return {"groups": [dict(r) for r in rows]}
    finally:
        conn.close()


# ── Rate editing endpoints ──────────────────────────────────────────

class LaborRateUpdate(BaseModel):
    base_rate: float | None = None
    tax_pct: float | None = None
    fringe_non_ot: float | None = None
    description: str | None = None


@router.patch("/labor-rates/{pay_class_code}")
async def update_labor_rate(pay_class_code: str, update: LaborRateUpdate):
    """Update a labor rate. Recalculates loaded_rate automatically."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM labor_rate WHERE pay_class_code = ?",
            (pay_class_code,)
        ).fetchone()
        if not existing:
            raise HTTPException(404, f"Pay class {pay_class_code} not found")

        base = update.base_rate if update.base_rate is not None else existing["base_rate"]
        tax = update.tax_pct if update.tax_pct is not None else existing["tax_pct"]
        fringe = update.fringe_non_ot if update.fringe_non_ot is not None else existing["fringe_non_ot"]
        desc = update.description if update.description is not None else existing["description"]
        loaded = round(base + (base * tax / 100) + fringe, 2)

        conn.execute("""
            UPDATE labor_rate SET
                base_rate = ?, tax_pct = ?, fringe_non_ot = ?,
                description = ?, loaded_rate = ?, source = 'manual',
                updated_at = CURRENT_TIMESTAMP
            WHERE pay_class_code = ?
        """, (base, tax, fringe, desc, loaded, pay_class_code))
        conn.commit()
        return {"status": "updated", "pay_class_code": pay_class_code, "loaded_rate": loaded}
    finally:
        conn.close()


class LaborRateCreate(BaseModel):
    pay_class_code: str
    description: str
    base_rate: float
    tax_pct: float = 15.45
    fringe_non_ot: float = 10.50
    ot_factor: float = 1.50
    ot2_factor: float = 2.00


@router.post("/labor-rates")
async def create_labor_rate(rate: LaborRateCreate):
    """Add a new labor rate (for unmapped pay classes)."""
    conn = get_connection()
    try:
        loaded = round(rate.base_rate + (rate.base_rate * rate.tax_pct / 100) + rate.fringe_non_ot, 2)
        conn.execute("""
            INSERT INTO labor_rate (
                pay_class_code, description, base_rate, ot_factor, ot2_factor,
                tax_pct, fringe_non_ot, loaded_rate, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manual')
        """, (
            rate.pay_class_code, rate.description, rate.base_rate,
            rate.ot_factor, rate.ot2_factor, rate.tax_pct, rate.fringe_non_ot, loaded,
        ))
        conn.commit()
        return {"status": "created", "pay_class_code": rate.pay_class_code, "loaded_rate": loaded}
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise HTTPException(409, f"Pay class {rate.pay_class_code} already exists")
        raise
    finally:
        conn.close()


class EquipmentRateUpdate(BaseModel):
    base_rate: float | None = None
    group_name: str | None = None
    description: str | None = None


@router.patch("/equipment-rates/{equipment_code:path}")
async def update_equipment_rate(equipment_code: str, update: EquipmentRateUpdate):
    """Update an equipment rate."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT * FROM equipment_rate WHERE equipment_code = ?",
            (equipment_code,)
        ).fetchone()
        if not existing:
            raise HTTPException(404, f"Equipment {equipment_code} not found")

        sets = []
        params = []
        if update.base_rate is not None:
            sets.append("base_rate = ?")
            params.append(update.base_rate)
        if update.group_name is not None:
            sets.append("group_name = ?")
            params.append(update.group_name)
        if update.description is not None:
            sets.append("description = ?")
            params.append(update.description)
        sets.append("source = 'manual'")
        sets.append("updated_at = CURRENT_TIMESTAMP")
        params.append(equipment_code)

        conn.execute(
            f"UPDATE equipment_rate SET {', '.join(sets)} WHERE equipment_code = ?",
            params,
        )
        conn.commit()
        return {"status": "updated", "equipment_code": equipment_code}
    finally:
        conn.close()


# ── Import endpoints ────────────────────────────────────────────────

@router.post("/import-rates")
async def import_rates_from_files():
    """Import labor and equipment rates from HeavyJob export files."""
    pay_class_file = HJ_RATES_DIR / "PayClass.txt"
    equipment_file = HJ_RATES_DIR / "EquipmentSetup.txt"

    if not pay_class_file.exists():
        raise HTTPException(404, f"PayClass.txt not found at {HJ_RATES_DIR}")
    if not equipment_file.exists():
        raise HTTPException(404, f"EquipmentSetup.txt not found at {HJ_RATES_DIR}")

    conn = get_connection()
    try:
        labor_rates = parse_pay_class_file(pay_class_file)
        labor_count = import_labor_rates(conn, labor_rates)

        equip_items = parse_equipment_file(equipment_file)
        equip_count = import_equipment_rates(conn, equip_items)

        coverage = get_rate_coverage(conn)

        return {
            "status": "imported",
            "labor_rates_imported": labor_count,
            "equipment_rates_imported": equip_count,
            "coverage": coverage,
        }
    finally:
        conn.close()


# ── Recast cost endpoints ──────────────────────────────────────────

@router.get("/recast/{job_id}")
async def get_recast_for_job(job_id: int):
    """Get recast costs for a specific job."""
    conn = get_connection()
    try:
        job = conn.execute("SELECT * FROM job WHERE job_id = ?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, f"Job {job_id} not found")
        result = get_recast_costs_by_job(conn, job_id)
        return result
    finally:
        conn.close()


@router.get("/recast-summary")
async def get_recast_summary():
    """Get recast cost totals for all jobs."""
    conn = get_connection()
    try:
        return {"jobs": get_recast_summary_all_jobs(conn)}
    finally:
        conn.close()


@router.get("/rate-coverage")
async def get_coverage():
    """Check rate mapping coverage against actual data."""
    conn = get_connection()
    try:
        coverage = get_rate_coverage(conn)

        # Also get unmapped codes
        unmapped_labor = conn.execute("""
            SELECT t.pay_class_code, ROUND(SUM(t.hours), 0) as hours,
                   COUNT(DISTINCT t.job_id) as jobs
            FROM hj_timecard t
            LEFT JOIN labor_rate lr ON t.pay_class_code = lr.pay_class_code
            WHERE t.pay_class_code IS NOT NULL AND lr.pay_class_code IS NULL
            GROUP BY t.pay_class_code
            ORDER BY hours DESC
        """).fetchall()

        unmapped_equip = conn.execute("""
            SELECT e.equipment_code, ROUND(SUM(e.hours), 0) as hours,
                   COUNT(DISTINCT e.job_id) as jobs
            FROM hj_equipment_entry e
            LEFT JOIN equipment_rate er ON e.equipment_code = er.equipment_code
            WHERE e.equipment_code IS NOT NULL AND er.equipment_code IS NULL
            GROUP BY e.equipment_code
            ORDER BY hours DESC
            LIMIT 50
        """).fetchall()

        coverage["unmapped_labor"] = [dict(r) for r in unmapped_labor]
        coverage["unmapped_equipment"] = [dict(r) for r in unmapped_equip]
        return coverage
    finally:
        conn.close()
