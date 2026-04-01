"""Re-sync timecards for jobs with incomplete data.

Uses corrected auth URL (api.hcssapps.com). For each job:
1. Fetch ALL timecard summaries (cursor pagination, with retry)
2. Fetch detail for each summary
3. Flatten into timecard + equipment rows
4. ONLY replace DB data if new count >= old count (safety check)

Run: PYTHONIOENCODING=utf-8 python scripts/resync_incomplete_timecards.py
"""
import asyncio
import httpx
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

TOKEN_URL = "https://api.hcssapps.com/identity/connect/token"
HJ_BASE = "https://api.hcssapps.com/heavyjob"
CLIENT_ID = "g12nyfypxc3qps438ryqvz0971o62g3o"
CLIENT_SECRET = "lKMwGiG1EeP105QPX4F1BHIZVKyTNlOzO04Uqujl"

from app.database import get_connection
from app.hcss.heavyjob import _flatten_timecard, _flatten_equipment

# Jobs needing re-sync
# Pass --all to re-sync ALL jobs (needed to capture notes)
# Default: only the 8 jobs with incomplete timecard coverage
INCOMPLETE_JOBS = ["8462", "8465", "8512", "8522", "8544", "8545", "8552", "8553"]


async def get_token(http):
    resp = await http.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "heavyjob:read timecards:read",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


async def fetch_all_summaries(http, headers, hcss_job_id, job_num):
    """Fetch ALL timecard summaries with cursor pagination. Raises on failure."""
    all_records = []
    params = {"jobId": hcss_job_id, "take": 1000}
    page = 0

    while True:
        page += 1
        resp = await http.get(
            f"{HJ_BASE}/api/v1/timeCardInfo",
            params=params, headers=headers, timeout=30.0,
        )

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "60"))
            print(f"    429 on summaries page {page} - waiting {retry_after}s...", flush=True)
            await asyncio.sleep(retry_after)
            resp = await http.get(
                f"{HJ_BASE}/api/v1/timeCardInfo",
                params=params, headers=headers, timeout=30.0,
            )

        if resp.status_code != 200:
            raise Exception(f"Summaries page {page} failed: HTTP {resp.status_code}")

        data = resp.json()
        records = data.get("results", [])
        all_records.extend(records)

        next_cursor = data.get("metadata", {}).get("nextCursor")
        print(
            f"    Summaries page {page}: {len(records)} "
            f"(total: {len(all_records)}, more: {'yes' if next_cursor else 'no'})",
            flush=True,
        )

        if not next_cursor or len(records) < 1000:
            break
        params["cursor"] = next_cursor
        await asyncio.sleep(0.5)

    return all_records


async def fetch_details(http, headers, summaries, job_num):
    """Fetch detail for each timecard summary. Returns (labor_rows, equip_rows, failed)."""
    tc_ids = [s.get("id") for s in summaries if s.get("id")]
    all_labor = []
    all_equip = []
    failed = 0

    for i, tc_id in enumerate(tc_ids):
        try:
            resp = await http.get(
                f"{HJ_BASE}/api/v1/timeCards/{tc_id}",
                headers=headers, timeout=30.0,
            )

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "60"))
                print(f"    429 on detail {i+1}/{len(tc_ids)} - waiting {retry_after}s...", flush=True)
                await asyncio.sleep(retry_after)
                resp = await http.get(
                    f"{HJ_BASE}/api/v1/timeCards/{tc_id}",
                    headers=headers, timeout=30.0,
                )

            if resp.status_code != 200:
                failed += 1
                continue

            detail = resp.json()
            all_labor.extend(_flatten_timecard(detail))
            all_equip.extend(_flatten_equipment(detail))

        except Exception:
            failed += 1

        if (i + 1) % 200 == 0:
            print(f"    Details: {i+1}/{len(tc_ids)} ({failed} failed)", flush=True)

        # Stay under ~2 req/s
        await asyncio.sleep(0.5)

    return all_labor, all_equip, failed


async def main():
    start = time.time()

    async with httpx.AsyncClient(timeout=30.0) as http:
        token = await get_token(http)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        token_time = time.time()
        print("Authenticated\n", flush=True)

        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--all", action="store_true", help="Re-sync ALL jobs (to capture notes)")
        parser.add_argument("--start", type=int, default=0, help="Skip first N jobs (resume from index N)")
        args = parser.parse_args()

        conn = get_connection()
        if args.all:
            # Incomplete jobs first, then everything else
            incomplete_set = set(INCOMPLETE_JOBS)
            priority_jobs = conn.execute("""
                SELECT job_id, job_number, name, hcss_job_id
                FROM job WHERE hcss_job_id IS NOT NULL
                  AND job_number IN ({})
                ORDER BY job_number
            """.format(",".join(f"'{j}'" for j in INCOMPLETE_JOBS))).fetchall()
            remaining_jobs = conn.execute("""
                SELECT job_id, job_number, name, hcss_job_id
                FROM job WHERE hcss_job_id IS NOT NULL
                  AND job_number NOT IN ({})
                ORDER BY job_number
            """.format(",".join(f"'{j}'" for j in INCOMPLETE_JOBS))).fetchall()
            jobs = list(priority_jobs) + list(remaining_jobs)
            print(f"Priority: {len(priority_jobs)} incomplete jobs first, then {len(remaining_jobs)} remaining\n", flush=True)
        else:
            placeholders = ",".join(f"'{j}'" for j in INCOMPLETE_JOBS)
            jobs = conn.execute(f"""
                SELECT job_id, job_number, name, hcss_job_id
                FROM job WHERE job_number IN ({placeholders})
                ORDER BY job_number
            """).fetchall()

        old_counts = {}
        for job in jobs:
            row = conn.execute(
                "SELECT COUNT(*) as c, COALESCE(SUM(hours),0) as h FROM hj_timecard WHERE job_id=?",
                (job["job_id"],),
            ).fetchone()
            old_counts[job["job_id"]] = {"count": row["c"], "hours": row["h"]}
        conn.close()

        if args.start > 0:
            print(f"Skipping first {args.start} jobs, resuming from index {args.start}\n", flush=True)
        print(f"Re-syncing timecards for {len(jobs)} jobs ({len(jobs) - args.start} remaining)\n", flush=True)

        for i, job in enumerate(jobs):
            if i < args.start:
                continue
            job_id = job["job_id"]
            hcss_id = job["hcss_job_id"]
            job_num = job["job_number"]
            job_name = (job["name"] or "")[:35]
            old = old_counts[job_id]

            print(f"\n[{i+1}/{len(jobs)}] JOB {job_num} - {job_name}", flush=True)
            print(f"  Current: {old['count']:,} TC rows, {old['hours']:,.1f} hrs", flush=True)

            # Refresh token if >45 min old
            if time.time() - token_time > 2700:
                token = await get_token(http)
                headers["Authorization"] = f"Bearer {token}"
                token_time = time.time()
                print("  [token refreshed]", flush=True)

            try:
                # Step 1: Get all summaries
                summaries = await fetch_all_summaries(http, headers, hcss_id, job_num)
                print(f"  Summaries: {len(summaries)}", flush=True)

                if not summaries:
                    print("  SKIP: No summaries returned", flush=True)
                    continue

                # Step 2: Fetch all details
                labor_rows, equip_rows, failed = await fetch_details(
                    http, headers, summaries, job_num,
                )
                new_hrs = sum(tc.hours or 0 for tc in labor_rows)
                print(
                    f"  Fetched: {len(labor_rows):,} labor rows ({new_hrs:,.1f} hrs), "
                    f"{len(equip_rows):,} equip rows, {failed} failures",
                    flush=True,
                )

                # Step 3: Safety check
                if old["count"] > 0 and len(labor_rows) < old["count"] * 0.9:
                    print(
                        f"  SAFETY SKIP: New ({len(labor_rows)}) < 90% of old ({old['count']})",
                        flush=True,
                    )
                    continue

                # Step 4: Replace in DB
                conn = get_connection()
                try:
                    conn.execute("DELETE FROM hj_timecard WHERE job_id = ?", (job_id,))
                    for tc in labor_rows:
                        conn.execute(
                            """INSERT INTO hj_timecard (
                                   hcss_tc_id, job_id, cost_code, date,
                                   employee_id, employee_name, employee_code, hours,
                                   equip_id, equip_hours, foreman_id,
                                   status, quantity,
                                   pay_class_code, pay_class_desc, foreman_name,
                                   notes)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                tc.id, job_id, tc.costCode, tc.tc_date,
                                tc.employeeId, tc.employeeName, tc.employeeCode, tc.hours,
                                tc.equipmentId, tc.equipmentHours, tc.foremanId,
                                tc.status, tc.quantity,
                                tc.payClassCode, tc.payClassDesc, tc.foremanName,
                                tc.notes,
                            ),
                        )

                    conn.execute("DELETE FROM hj_equipment_entry WHERE job_id = ?", (job_id,))
                    for eq in equip_rows:
                        conn.execute(
                            """INSERT INTO hj_equipment_entry (
                                   hcss_tc_id, job_id, cost_code, date,
                                   equipment_id, equipment_code, equipment_desc,
                                   hours, cost_code_id)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                eq.id, job_id, eq.costCode, eq.tc_date,
                                eq.equipmentId, eq.equipmentCode, eq.equipmentDesc,
                                eq.hours, eq.costCodeId,
                            ),
                        )

                    conn.commit()
                    improvement = new_hrs - old["hours"]
                    print(
                        f"  SAVED: {len(labor_rows):,} labor + {len(equip_rows):,} equip",
                        flush=True,
                    )
                    print(
                        f"  RESULT: {old['hours']:,.1f} -> {new_hrs:,.1f} hrs "
                        f"(+{improvement:,.1f})",
                        flush=True,
                    )
                finally:
                    conn.close()

            except Exception as e:
                print(f"  ERROR: {e}", flush=True)

    elapsed = time.time() - start
    print(f"\n{'='*70}", flush=True)
    print(f"DONE in {elapsed:.0f}s ({elapsed/60:.1f}min)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
