"""MEGA SYNC — Pull everything available from HCSS APIs.

Syncs ALL available data in the optimal order:
  Phase 1: Bulk reference data (fast, single-call endpoints)
    - Employees roster
    - Pay items (all jobs)
    - Forecasts (all jobs)
    - E360 mechanic timecards
  Phase 2: Re-sync ALL timecards for employee_code + equipment data
    (adaptive pacing, resume support)
  Phase 3: Aggregate actuals + regenerate rate cards

Run: PYTHONUNBUFFERED=1 python scripts/sync_everything.py [--phase 1|2|3|all] [--force-resync]

Options:
  --phase 1        Only sync bulk reference data
  --phase 2        Only re-sync timecards
  --phase 3        Only aggregate + regenerate
  --phase all      Do everything (default)
  --force-resync   Re-sync ALL timecard jobs, even those already synced with equipment data
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

import httpx
from app.database import init_db, get_connection
from app.hcss.auth import HCSSAuth
from app.hcss.heavyjob import _flatten_timecard, _flatten_equipment

BU_ID = "319078ad-cbfe-49e7-a8b4-b62fe0be273d"
HJ_BASE = "https://api.hcssapps.com/heavyjob"
E360_BASE = "https://api.hcssapps.com/e360"

# Adaptive pacing for timecard sync — conservative to avoid 429 death spiral
INITIAL_CONCURRENCY = 2
INITIAL_DELAY = 1.0  # ~1 req/s baseline
FALLBACK_CONCURRENCY = 1
FALLBACK_DELAY = 2.0

# Shared state
current_concurrency = INITIAL_CONCURRENCY
current_delay = INITIAL_DELAY
rate_limit_hits = 0
jobs_since_last_429 = 0
request_lock = asyncio.Lock()
last_request_time = 0.0


class RateLimitHit(Exception):
    pass


async def api_get(http, url, headers, params=None):
    """Single API GET with adaptive pacing."""
    global last_request_time, rate_limit_hits, current_concurrency, current_delay, jobs_since_last_429

    async with request_lock:
        now = time.time()
        wait = max(0, current_delay - (now - last_request_time))
        if wait > 0:
            await asyncio.sleep(wait)
        last_request_time = time.time()

    try:
        resp = await http.get(url, params=params, headers=headers, timeout=30.0)
    except Exception as e:
        print(f"    Network error: {e}", flush=True)
        return None

    if resp.status_code == 429:
        rate_limit_hits += 1
        retry_after = int(resp.headers.get("Retry-After", "60"))

        if rate_limit_hits >= 5:
            raise RateLimitHit(
                f"429 Rate Limited x{rate_limit_hits} (Retry-After: {retry_after}s). "
                f"Stopping -- re-run in 5 minutes."
            )

        wait_time = max(retry_after, 60)
        print(f"    429 hit #{rate_limit_hits} -- waiting {wait_time}s then slowing down...", flush=True)
        current_concurrency = FALLBACK_CONCURRENCY
        current_delay = FALLBACK_DELAY
        jobs_since_last_429 = 0
        await asyncio.sleep(wait_time)

        try:
            resp = await http.get(url, params=params, headers=headers, timeout=30.0)
        except Exception as e:
            print(f"    Network error on retry: {e}", flush=True)
            return None

        if resp.status_code == 429:
            rate_limit_hits += 1
            raise RateLimitHit(f"429 again after backoff. Stopping.")

    if resp.status_code != 200:
        print(f"    HTTP {resp.status_code}", flush=True)
        return None

    return resp.json()


# ─────────────────────────────────────────────────────────────
# Phase 1: Bulk reference data
# ─────────────────────────────────────────────────────────────

async def sync_employees(http, headers):
    """Sync employee roster — ACTIVE employees only.

    HCSS returns 500K+ employee records (every employee ever created).
    We only store active, non-deleted ones. This still gets us the full
    roster of current employees with trade codes, names, etc.
    """
    print("\n--- EMPLOYEES ---", flush=True)
    stored = 0
    skipped = 0
    skip = 0
    take = 1000
    total_fetched = 0

    conn = get_connection()
    try:
        conn.execute("DELETE FROM hj_employee")

        while True:
            data = await api_get(http, f"{HJ_BASE}/api/v1/employees",
                                 headers, {"businessUnitId": BU_ID, "skip": skip, "take": take})
            if not data:
                break

            records = data.get("results", data) if isinstance(data, dict) else data
            if isinstance(records, dict):
                records = [records]
            total_fetched += len(records)

            for emp in records:
                # Only store active, non-deleted employees
                if emp.get("isDeleted", False) or not emp.get("isActive", True):
                    skipped += 1
                    continue
                conn.execute("""
                    INSERT OR REPLACE INTO hj_employee (hcss_id, code, first_name, last_name,
                        middle_initial, suffix, nick_name, email, phone,
                        is_salaried, is_active, is_deleted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    emp.get("Id") or emp.get("id"),
                    emp.get("code"),
                    emp.get("firstName"),
                    emp.get("lastName"),
                    emp.get("middleInitial"),
                    emp.get("suffix"),
                    emp.get("nickName"),
                    emp.get("email"),
                    emp.get("otherPhone"),
                    emp.get("isSalaried", False),
                    True,
                    False,
                ))
                stored += 1

            if total_fetched % 10000 == 0:
                print(f"  ...{total_fetched} scanned, {stored} active stored, {skipped} inactive/deleted", flush=True)
                conn.commit()

            if len(records) < take:
                break
            skip += take

            # Safety cap — if we've scanned 500K+ records, that's enough
            if total_fetched >= 500000:
                print(f"  Reached 500K scan limit, stopping employee fetch", flush=True)
                break

        conn.commit()
    finally:
        conn.close()

    print(f"  Synced {stored} active employees (scanned {total_fetched}, skipped {skipped})", flush=True)
    return stored


async def sync_pay_items(http, headers):
    """Sync all pay items (SOV data). Streams and commits in batches."""
    print("\n--- PAY ITEMS ---", flush=True)

    # Build job lookup: hcss_job_id -> job_id
    conn = get_connection()
    try:
        job_lookup = {}
        for row in conn.execute("SELECT job_id, hcss_job_id FROM job WHERE hcss_job_id IS NOT NULL"):
            job_lookup[row["hcss_job_id"]] = row["job_id"]
    finally:
        conn.close()

    stored = 0
    skip = 0
    take = 1000
    total_fetched = 0

    conn = get_connection()
    try:
        conn.execute("DELETE FROM hj_pay_item")

        while True:
            data = await api_get(http, f"{HJ_BASE}/api/v1/payItems",
                                 headers, {"businessUnitId": BU_ID, "skip": skip, "take": take})
            if not data:
                break

            records = data.get("results", data) if isinstance(data, dict) else data
            if isinstance(records, dict):
                records = [records]
            total_fetched += len(records)

            for item in records:
                if item.get("isDeleted", False):
                    continue
                hcss_job_id = item.get("jobId")
                linked = json.dumps(item.get("linkedCostCodes", []))
                conn.execute("""
                    INSERT INTO hj_pay_item (hcss_id, job_id, hcss_job_id, pay_item,
                        description, status, owner_code, contract_qty, unit,
                        unit_price, stop_overruns, linked_cost_codes, is_deleted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get("id"),
                    job_lookup.get(hcss_job_id),
                    hcss_job_id,
                    item.get("payItem"),
                    item.get("description"),
                    item.get("status"),
                    item.get("ownerCode"),
                    item.get("contractQuantity"),
                    item.get("unitOfMeasure"),
                    item.get("unitPrice"),
                    item.get("stopOverruns", False),
                    linked,
                    False,
                ))
                stored += 1

            if total_fetched % 5000 == 0:
                print(f"  ...{total_fetched} fetched, {stored} stored", flush=True)
                conn.commit()

            if len(records) < take:
                break
            skip += take

        conn.commit()
        jobs_with = conn.execute("SELECT COUNT(DISTINCT hcss_job_id) FROM hj_pay_item").fetchone()[0]
    finally:
        conn.close()

    print(f"  Synced {stored} pay items across {jobs_with} jobs (from {total_fetched} total)", flush=True)
    return stored


async def sync_forecasts(http, headers):
    """Sync all job forecasts."""
    print("\n--- FORECASTS ---", flush=True)
    all_forecasts = []
    skip = 0
    take = 1000

    while True:
        data = await api_get(http, f"{HJ_BASE}/api/v1/forecasts",
                             headers, {"businessUnitId": BU_ID, "skip": skip, "take": take})
        if not data:
            break

        records = data.get("results", data) if isinstance(data, dict) else data
        if isinstance(records, dict):
            records = [records]
        all_forecasts.extend(records)
        print(f"  Fetched {len(all_forecasts)} forecasts...", flush=True)

        if len(records) < take:
            break
        skip += take

    if not all_forecasts:
        print("  No forecasts found!", flush=True)
        return 0

    # Build job lookup
    conn = get_connection()
    try:
        job_lookup = {}
        for row in conn.execute("SELECT job_id, job_number FROM job"):
            job_lookup[row["job_number"]] = row["job_id"]

        conn.execute("DELETE FROM hj_forecast")
        for fc in all_forecasts:
            job_code = fc.get("jobCode")
            conn.execute("""
                INSERT INTO hj_forecast (hcss_id, hcss_forecast_id, job_id, job_code,
                    job_description, job_status, forecast_date, forecast_status,
                    to_date_total_cost, cost_to_completion, cost_at_completion,
                    budget_total, variance, contract_revenue, to_date_revenue,
                    revenue_to_completion, forecast_revenue, margin_percent,
                    markup_percent, create_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fc.get("id"),
                fc.get("forecastId"),
                job_lookup.get(job_code),
                job_code,
                fc.get("jobDescription"),
                fc.get("jobStatus"),
                fc.get("forecastDate"),
                fc.get("forecastStatus"),
                fc.get("toDateTotalCost"),
                fc.get("costToCompletion"),
                fc.get("costAtCompletion"),
                fc.get("budgetTotal"),
                fc.get("variance"),
                fc.get("contractRevenue"),
                fc.get("toDateRevenue"),
                fc.get("revenueToCompletion"),
                fc.get("forecastRevenue"),
                fc.get("marginPercent"),
                fc.get("markupPercent"),
                fc.get("createDate"),
            ))
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM hj_forecast").fetchone()[0]
    finally:
        conn.close()

    print(f"  Synced {count} forecasts", flush=True)
    return count


async def sync_e360_timecards(http, headers):
    """Sync E360 equipment mechanic timecards."""
    print("\n--- E360 TIMECARDS ---", flush=True)
    all_timecards = []
    skip = 0
    take = 100  # E360 uses smaller pages

    while True:
        data = await api_get(http, f"{E360_BASE}/api/v2/timecards",
                             headers, {"businessUnitId": BU_ID, "skip": skip, "take": take})
        if not data:
            break

        records = data.get("results", data) if isinstance(data, dict) else data
        if isinstance(records, dict):
            records = [records]
        all_timecards.extend(records)

        if len(all_timecards) % 500 == 0 or len(records) < take:
            print(f"  Fetched {len(all_timecards)} E360 timecards...", flush=True)

        if len(records) < take:
            break
        skip += take

    if not all_timecards:
        print("  No E360 timecards found!", flush=True)
        return 0

    conn = get_connection()
    try:
        conn.execute("DELETE FROM e360_timecard")
        total_details = 0
        for tc in all_timecards:
            details = tc.get("details", [])
            for detail in details:
                conn.execute("""
                    INSERT INTO e360_timecard (hcss_id, timecard_id, timecard_date,
                        mechanic_id, mechanic_code, payclass, status, approval_level1,
                        equipment_name, equipment_code, work_type, work_code,
                        item_code, regular_hours, overtime_hours, double_time_hours,
                        damage_related, on_site)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    detail.get("id"),
                    tc.get("timeCardId"),
                    tc.get("timeCardDate"),
                    tc.get("mechanicId"),
                    tc.get("mechanicCode"),
                    tc.get("payclass"),
                    tc.get("status"),
                    tc.get("approvalLevel1"),
                    detail.get("equipmentName"),
                    detail.get("equipmentAccountingCode"),
                    detail.get("workType"),
                    detail.get("workCode"),
                    detail.get("itemCode"),
                    detail.get("regularHours", 0),
                    detail.get("overtimeHours", 0),
                    detail.get("doubleTimeHours", 0),
                    detail.get("damageRelated", False),
                    detail.get("onSite", False),
                ))
                total_details += 1

        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM e360_timecard").fetchone()[0]
        equip_count = conn.execute("SELECT COUNT(DISTINCT equipment_name) FROM e360_timecard").fetchone()[0]
    finally:
        conn.close()

    print(f"  Synced {count} E360 entries across {equip_count} pieces of equipment", flush=True)
    return count


# ─────────────────────────────────────────────────────────────
# Phase 2: Re-sync timecards for employee_code + equipment
# ─────────────────────────────────────────────────────────────

async def fetch_timecard_summaries(http, headers, hcss_job_id):
    """Fetch all timecard summaries for a job using cursor pagination."""
    all_records = []
    params = {"jobId": hcss_job_id, "take": 1000}

    while True:
        data = await api_get(http, f"{HJ_BASE}/api/v1/timeCardInfo", headers, params)
        if data is None:
            return all_records

        records = data.get("results", [])
        all_records.extend(records)

        next_cursor = data.get("metadata", {}).get("nextCursor")
        if not next_cursor or len(records) < 1000:
            break
        params["cursor"] = next_cursor

    return all_records


async def fetch_details_concurrent(http, headers, tc_ids):
    """Fetch timecard details concurrently. Returns (labor_rows, equip_rows)."""
    sem = asyncio.Semaphore(current_concurrency)
    results = {}

    async def fetch_one(idx, tid):
        async with sem:
            detail = await api_get(http, f"{HJ_BASE}/api/v1/timeCards/{tid}", headers)
            if detail:
                results[idx] = detail

    chunk_size = 50
    for chunk_start in range(0, len(tc_ids), chunk_size):
        chunk_end = min(chunk_start + chunk_size, len(tc_ids))
        chunk = tc_ids[chunk_start:chunk_end]

        tasks = [fetch_one(chunk_start + j, tid) for j, tid in enumerate(chunk)]
        await asyncio.gather(*tasks)

        if chunk_end < len(tc_ids) and chunk_end % 200 == 0:
            print(f"    ...{chunk_end}/{len(tc_ids)} details ({current_concurrency}x @ {current_delay:.2f}s)", flush=True)

    flat_rows = []
    equip_rows = []
    for idx in sorted(results.keys()):
        flat_rows.extend(_flatten_timecard(results[idx]))
        equip_rows.extend(_flatten_equipment(results[idx]))

    return flat_rows, equip_rows


async def resync_timecards(http, headers, force_all=False):
    """Re-sync all timecards to get employee_code + equipment data."""
    global rate_limit_hits, current_concurrency, current_delay, jobs_since_last_429

    print("\n--- TIMECARD RE-SYNC ---", flush=True)

    conn = get_connection()
    try:
        jobs = conn.execute("""
            SELECT job_id, hcss_job_id, job_number, name
            FROM job
            WHERE job_number GLOB '[0-9]*'
              AND CAST(job_number AS INTEGER) >= 8400
              AND hcss_job_id IS NOT NULL
            ORDER BY job_number
        """).fetchall()

        if force_all:
            # Re-sync everything
            remaining = list(jobs)
            print(f"  Force re-sync: ALL {len(remaining)} jobs", flush=True)
        else:
            # Only re-sync jobs that don't have pay_class_code data yet.
            # A job is "re-synced" if it has ANY timecard row with pay_class_code populated.
            # (This field is only set by the v1.9+ sync code, so old syncs are properly re-done.)
            jobs_resynced = set(
                r[0] for r in conn.execute(
                    """SELECT DISTINCT job_id FROM hj_timecard
                       WHERE pay_class_code IS NOT NULL AND pay_class_code != ''"""
                ).fetchall()
            )
            remaining = [j for j in jobs if j["job_id"] not in jobs_resynced]
            print(f"  Total jobs: {len(jobs)} | Already re-synced: {len(jobs_resynced)} | Need re-sync: {len(remaining)}", flush=True)
    finally:
        conn.close()

    if not remaining:
        print("  All jobs already have equipment data!", flush=True)
        return 0

    start = time.time()
    total_tc = 0
    total_labor_rows = 0
    total_equip_rows = 0
    jobs_done = 0
    rate_limited = False

    for i, job in enumerate(remaining):
        job_id = job["job_id"]
        hcss_job_id = job["hcss_job_id"]
        job_number = job["job_number"]
        job_name = (job["name"] or "")[:40]

        try:
            token = await auth_global.get_token()
            headers["Authorization"] = f"Bearer {token}"

            # Summaries
            summaries = await fetch_timecard_summaries(http, headers, hcss_job_id)
            tc_count = len(summaries)

            if tc_count == 0:
                elapsed = time.time() - start
                print(f"  [{i+1}/{len(remaining)}] {job_number:6s} |    0 tc |     0 L |    0 E | {elapsed:.0f}s", flush=True)
                continue

            # Details
            tc_ids = [s.get("id") for s in summaries if s.get("id")]
            flat_rows, equip_rows = await fetch_details_concurrent(http, headers, tc_ids)

            # Save labor timecards
            conn = get_connection()
            try:
                conn.execute("DELETE FROM hj_timecard WHERE job_id = ?", (job_id,))
                for tc in flat_rows:
                    conn.execute(
                        """INSERT INTO hj_timecard (
                               hcss_tc_id, job_id, cost_code, date,
                               employee_id, employee_name, employee_code, hours,
                               equip_id, equip_hours, foreman_id,
                               status, quantity,
                               pay_class_code, pay_class_desc, foreman_name)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (tc.id, job_id, tc.costCode, tc.tc_date,
                         tc.employeeId, tc.employeeName, tc.employeeCode, tc.hours,
                         tc.equipmentId, tc.equipmentHours, tc.foremanId,
                         tc.status, tc.quantity,
                         tc.payClassCode, tc.payClassDesc, tc.foremanName),
                    )

                # Save equipment
                conn.execute("DELETE FROM hj_equipment_entry WHERE job_id = ?", (job_id,))
                for eq in equip_rows:
                    conn.execute(
                        """INSERT INTO hj_equipment_entry (
                               hcss_tc_id, job_id, cost_code, date,
                               equipment_id, equipment_code, equipment_desc,
                               hours, cost_code_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (eq.id, job_id, eq.costCode, eq.tc_date,
                         eq.equipmentId, eq.equipmentCode, eq.equipmentDesc,
                         eq.hours, eq.costCodeId),
                    )
                conn.commit()
            finally:
                conn.close()

            total_tc += tc_count
            total_labor_rows += len(flat_rows)
            total_equip_rows += len(equip_rows)
            jobs_done += 1
            jobs_since_last_429 += 1
            elapsed = time.time() - start
            pace = f"{current_concurrency}x@{current_delay:.1f}s"
            print(
                f"  [{i+1}/{len(remaining)}] {job_number:6s} | {tc_count:4d} tc | {len(flat_rows):5d} L | {len(equip_rows):4d} E | "
                f"{elapsed:.0f}s | {pace} | {job_name}",
                flush=True,
            )

            # Restore pace after clean runs
            if jobs_since_last_429 >= 5:
                if rate_limit_hits > 0:
                    rate_limit_hits = max(0, rate_limit_hits - 1)
                if current_concurrency < INITIAL_CONCURRENCY:
                    current_concurrency = INITIAL_CONCURRENCY
                    current_delay = INITIAL_DELAY
                    print(f"    Restored pace to {current_concurrency}x @ {current_delay}s", flush=True)

        except RateLimitHit as e:
            print(f"\n  RATE LIMITED: {e}", flush=True)
            print(f"  Synced {jobs_done} jobs this run before hitting limit.", flush=True)
            rate_limited = True
            break

        except Exception as e:
            print(f"  [{i+1}/{len(remaining)}] {job_number} ERROR: {e}", flush=True)

    elapsed = time.time() - start
    print(f"\n  Re-sync: {elapsed:.0f}s ({elapsed/60:.1f}min) | {jobs_done} jobs | {total_tc} tc | {total_labor_rows} labor | {total_equip_rows} equip", flush=True)
    if rate_limited:
        print("  Re-run this script to continue.", flush=True)

    return jobs_done


# ─────────────────────────────────────────────────────────────
# Phase 3: Aggregate + regenerate
# ─────────────────────────────────────────────────────────────

def aggregate_actuals():
    """Aggregate timecard hours/quantities into hj_costcode."""
    print("\n--- AGGREGATE ACTUALS ---", flush=True)

    conn = get_connection()
    try:
        actual_hours = conn.execute("""
            SELECT job_id, cost_code, SUM(hours) as total_hours
            FROM hj_timecard GROUP BY job_id, cost_code
        """).fetchall()

        actual_qty = conn.execute("""
            SELECT job_id, cost_code, SUM(daily_qty) as total_qty
            FROM (
                SELECT DISTINCT job_id, cost_code, date, quantity as daily_qty
                FROM hj_timecard WHERE quantity IS NOT NULL AND quantity > 0
            ) GROUP BY job_id, cost_code
        """).fetchall()

        hours_lookup = {(r["job_id"], r["cost_code"]): r["total_hours"] for r in actual_hours}
        qty_lookup = {(r["job_id"], r["cost_code"]): r["total_qty"] for r in actual_qty}

        updated = 0
        for key, hours in hours_lookup.items():
            job_id, cost_code = key
            conn.execute(
                "UPDATE hj_costcode SET act_labor_hrs = ?, act_qty = ? WHERE job_id = ? AND code = ?",
                (hours, qty_lookup.get(key), job_id, cost_code),
            )
            updated += 1

        conn.commit()

        with_hrs = conn.execute("SELECT COUNT(*) FROM hj_costcode WHERE act_labor_hrs > 0").fetchone()[0]
        with_qty = conn.execute("SELECT COUNT(*) FROM hj_costcode WHERE act_qty > 0").fetchone()[0]
        total_cc = conn.execute("SELECT COUNT(*) FROM hj_costcode").fetchone()[0]
        total_tc = conn.execute("SELECT COUNT(*) FROM hj_timecard").fetchone()[0]
        total_eq = conn.execute("SELECT COUNT(*) FROM hj_equipment_entry").fetchone()[0]
        with_emp = conn.execute("SELECT COUNT(*) FROM hj_timecard WHERE employee_code IS NOT NULL AND employee_code != ''").fetchone()[0]
    finally:
        conn.close()

    print(f"  Updated {updated} cost codes", flush=True)
    print(f"  Timecard rows: {total_tc} | With employee_code: {with_emp} ({with_emp/max(total_tc,1)*100:.1f}%)", flush=True)
    print(f"  Equipment entries: {total_eq}", flush=True)
    print(f"  Cost codes with actual hrs: {with_hrs}/{total_cc} ({with_hrs/max(total_cc,1)*100:.1f}%)", flush=True)
    print(f"  Cost codes with actual qty: {with_qty}/{total_cc} ({with_qty/max(total_cc,1)*100:.1f}%)", flush=True)


# Global auth reference (needed for token refresh during re-sync)
auth_global = None


async def main():
    global auth_global

    parser = argparse.ArgumentParser(description="WEIS Mega Sync")
    parser.add_argument("--phase", default="all", choices=["1", "2", "3", "all"])
    parser.add_argument("--force-resync", action="store_true")
    args = parser.parse_args()

    init_db()

    auth_global = HCSSAuth()
    if not auth_global.is_configured:
        print("HCSS not configured")
        return

    auth_global._access_token = None
    auth_global._token_expires_at = 0
    token = await auth_global.get_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    print("=" * 70)
    print("WEIS MEGA SYNC")
    print("=" * 70)
    overall_start = time.time()

    async with httpx.AsyncClient(
        limits=httpx.Limits(max_connections=10),
        timeout=httpx.Timeout(30.0),
    ) as http:

        # Phase 1: Bulk reference data
        if args.phase in ("1", "all"):
            print(f"\n{'='*70}")
            print("PHASE 1: Bulk Reference Data")
            print(f"{'='*70}")

            employees = await sync_employees(http, headers)
            await asyncio.sleep(1)  # brief pause between endpoint groups

            pay_items = await sync_pay_items(http, headers)
            await asyncio.sleep(1)

            forecasts = await sync_forecasts(http, headers)
            await asyncio.sleep(1)

            e360 = await sync_e360_timecards(http, headers)

            print(f"\n  Phase 1 complete: {employees} employees, {pay_items} pay items, {forecasts} forecasts, {e360} E360 entries")

        # Phase 2: Timecard re-sync
        if args.phase in ("2", "all"):
            print(f"\n{'='*70}")
            print("PHASE 2: Timecard Re-Sync (employee_code + equipment)")
            print(f"{'='*70}")

            await resync_timecards(http, headers, force_all=args.force_resync)

        # Phase 3: Aggregate
        if args.phase in ("3", "all"):
            print(f"\n{'='*70}")
            print("PHASE 3: Aggregate Actuals")
            print(f"{'='*70}")

            aggregate_actuals()

            print("\n  To regenerate rate cards, run:")
            print("  python scripts/generate_rate_cards.py --force")

    elapsed = time.time() - overall_start
    print(f"\n{'='*70}")
    print(f"DONE in {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
