"""Sync actual timecard data from HCSS HeavyJob for all jobs >= 8400.

For each job:
  1. Fetch timecard summaries via /api/v1/timeCardInfo (cursor pagination)
  2. Fetch detail for each timecard via /api/v1/timeCards/{id}
  3. Flatten into per-employee-per-cost-code rows
  4. Upsert into hj_timecard table
  5. Aggregate actual hours/quantities per cost code
  6. Update hj_costcode with actual values

This gives us actual MH/unit -- the most valuable metric for estimating.

Rate limit strategy: ONE request at a time, fixed 1s delay between requests.
On the FIRST 429, stop immediately (don't keep digging a deeper hole).
Re-run later -- the script resumes automatically from where it stopped.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

import httpx
from app.database import init_db, get_connection
from app.hcss.auth import HCSSAuth
from app.hcss.heavyjob import _flatten_timecard

BU_ID = "319078ad-cbfe-49e7-a8b4-b62fe0be273d"
HJ_BASE = "https://api.hcssapps.com/heavyjob"

# Fixed delay between every API request
REQUEST_DELAY = 1.0


class RateLimitHit(Exception):
    """Raised on the first 429 to stop everything cleanly."""
    pass


async def api_get(http, url, headers, params=None):
    """Single API GET with fixed pacing. Raises RateLimitHit on 429."""
    await asyncio.sleep(REQUEST_DELAY)
    try:
        resp = await http.get(url, params=params, headers=headers, timeout=30.0)
    except Exception as e:
        print(f"    Network error: {e}", flush=True)
        return None

    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After", "?")
        raise RateLimitHit(
            f"429 Rate Limited (Retry-After: {retry_after}s). "
            f"Stop and re-run in 5-10 minutes."
        )

    if resp.status_code != 200:
        print(f"    HTTP {resp.status_code}", flush=True)
        return None

    return resp.json()


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


async def main():
    init_db()

    auth = HCSSAuth()
    if not auth.is_configured:
        print("HCSS not configured")
        return

    auth._access_token = None
    auth._token_expires_at = 0
    token = await auth.get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

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

        synced_jobs = set(
            r[0] for r in conn.execute(
                "SELECT DISTINCT job_id FROM hj_timecard"
            ).fetchall()
        )
    finally:
        conn.close()

    remaining = [j for j in jobs if j["job_id"] not in synced_jobs]
    print(f"Total jobs: {len(jobs)} | Already synced: {len(jobs)-len(remaining)} | Remaining: {len(remaining)}")

    if not remaining:
        print("All jobs synced!")
    else:
        start = time.time()
        total_tc = 0
        total_rows = 0
        jobs_done = 0
        rate_limited = False

        async with httpx.AsyncClient(
            limits=httpx.Limits(max_connections=2),
            timeout=httpx.Timeout(30.0),
        ) as http:
            for i, job in enumerate(remaining):
                job_id = job["job_id"]
                hcss_job_id = job["hcss_job_id"]
                job_number = job["job_number"]
                job_name = (job["name"] or "")[:40]

                try:
                    token = await auth.get_token()
                    headers["Authorization"] = f"Bearer {token}"

                    # Summaries
                    summaries = await fetch_timecard_summaries(http, headers, hcss_job_id)
                    tc_count = len(summaries)

                    if tc_count == 0:
                        elapsed = time.time() - start
                        print(f"  [{i+1}/{len(remaining)}] {job_number:6s} |    0 tc |     0 rows | {elapsed:.0f}s", flush=True)
                        continue

                    # Details — one at a time
                    tc_ids = [s.get("id") for s in summaries if s.get("id")]
                    flat_rows = []

                    for j, tid in enumerate(tc_ids):
                        detail = await api_get(http, f"{HJ_BASE}/api/v1/timeCards/{tid}", headers)
                        if detail:
                            flat_rows.extend(_flatten_timecard(detail))
                        if (j + 1) % 100 == 0:
                            print(f"    ...{j+1}/{len(tc_ids)} details", flush=True)

                    # Save
                    if flat_rows:
                        conn = get_connection()
                        try:
                            conn.execute("DELETE FROM hj_timecard WHERE job_id = ?", (job_id,))
                            for tc in flat_rows:
                                conn.execute(
                                    """INSERT INTO hj_timecard (
                                           hcss_tc_id, job_id, cost_code, date,
                                           employee_id, employee_name, hours,
                                           equip_id, equip_hours, foreman_id,
                                           status, quantity)
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                    (tc.id, job_id, tc.costCode, tc.tc_date,
                                     tc.employeeId, tc.employeeName, tc.hours,
                                     tc.equipmentId, tc.equipmentHours, tc.foremanId,
                                     tc.status, tc.quantity),
                                )
                            conn.commit()
                        finally:
                            conn.close()

                    total_tc += tc_count
                    total_rows += len(flat_rows)
                    jobs_done += 1
                    elapsed = time.time() - start
                    print(
                        f"  [{i+1}/{len(remaining)}] {job_number:6s} | {tc_count:4d} tc | {len(flat_rows):5d} rows | "
                        f"{elapsed:.0f}s | {job_name}",
                        flush=True,
                    )

                except RateLimitHit as e:
                    print(f"\n  RATE LIMITED: {e}", flush=True)
                    print(f"  Synced {jobs_done} jobs this run before hitting limit.", flush=True)
                    rate_limited = True
                    break

                except Exception as e:
                    print(f"  [{i+1}/{len(remaining)}] {job_number} ERROR: {e}", flush=True)

        elapsed = time.time() - start
        print(f"\nSync phase: {elapsed:.0f}s ({elapsed/60:.1f}min) | {jobs_done} jobs | {total_tc} tc | {total_rows} rows")
        if rate_limited:
            print("Re-run this script in 5-10 minutes to continue.")

    # Aggregate actuals
    print(f"\n{'='*60}")
    print("Aggregating actual hours/quantities per cost code...")

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
    finally:
        conn.close()

    print(f"Updated {updated} cost codes")
    print(f"\n{'='*60}")
    print(f"TOTALS: {total_tc} timecard rows | {with_hrs}/{total_cc} with actual hrs ({with_hrs/total_cc*100:.1f}%) | {with_qty}/{total_cc} with actual qty ({with_qty/total_cc*100:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
