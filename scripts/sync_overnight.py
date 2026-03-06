"""Overnight timecard sync — keeps retrying with cooldowns until all jobs are done.

Run with: PYTHONUNBUFFERED=1 python scripts/sync_overnight.py
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import init_db, get_connection

COOLDOWN_MINUTES = 15
MAX_RUNS = 50  # safety limit


def jobs_remaining():
    init_db()
    conn = get_connection()
    try:
        total = conn.execute("""
            SELECT COUNT(*) FROM job
            WHERE job_number GLOB '[0-9]*'
              AND CAST(job_number AS INTEGER) >= 8400
              AND hcss_job_id IS NOT NULL
        """).fetchone()[0]
        synced = conn.execute("SELECT COUNT(DISTINCT job_id) FROM hj_timecard").fetchone()[0]
        rows = conn.execute("SELECT COUNT(*) FROM hj_timecard").fetchone()[0]
        return total, synced, rows
    finally:
        conn.close()


def main():
    print(f"=== Overnight Timecard Sync ===")
    print(f"Cooldown between runs: {COOLDOWN_MINUTES} min")
    print(f"Max runs: {MAX_RUNS}")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    for run_num in range(1, MAX_RUNS + 1):
        total, synced, rows = jobs_remaining()
        print(f"--- Run {run_num} | {synced}/{total} jobs synced | {rows:,} rows | {time.strftime('%H:%M:%S')} ---")

        if synced >= total:
            print("All jobs synced!")
            break

        # Run the sync script
        result = subprocess.run(
            [sys.executable, "scripts/sync_timecards.py"],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=False,
        )

        # Check progress after run
        _, new_synced, new_rows = jobs_remaining()
        gained = new_synced - synced
        gained_rows = new_rows - rows
        print(f"  -> Gained {gained} jobs, {gained_rows:,} rows this run")

        if new_synced >= total:
            print(f"\nAll {total} jobs synced! Total rows: {new_rows:,}")
            break

        # Cooldown
        print(f"  -> Cooling down {COOLDOWN_MINUTES} min until {time.strftime('%H:%M:%S', time.localtime(time.time() + COOLDOWN_MINUTES * 60))}")
        time.sleep(COOLDOWN_MINUTES * 60)

    # Final summary
    total, synced, rows = jobs_remaining()
    print(f"\n{'='*60}")
    print(f"Final: {synced}/{total} jobs | {rows:,} timecard rows")
    print(f"Finished: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    if synced >= total:
        print("\nRunning rate card regeneration...")
        subprocess.run(
            [sys.executable, "scripts/generate_rate_cards.py", "--force"],
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        print("Rate cards regenerated!")


if __name__ == "__main__":
    main()
