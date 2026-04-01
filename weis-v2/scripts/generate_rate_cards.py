"""Regenerate rate cards for all jobs from current hj_costcode + hj_timecard data.

Usage:
    python scripts/generate_rate_cards.py          # Only jobs with existing rate cards
    python scripts/generate_rate_cards.py --all     # All jobs with cost codes
    python scripts/generate_rate_cards.py --force   # Same as --all (regenerate everything)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_connection
from app.transform.rate_card import RateCardGenerator
from app.hcss.storage import upsert_rate_card, upsert_rate_items


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", "--force", action="store_true",
                        help="Regenerate for ALL jobs (not just ones with existing cards)")
    args = parser.parse_args()

    start = time.time()
    conn = get_connection()

    if args.all:
        # All jobs that have cost codes with actuals
        jobs = conn.execute("""
            SELECT DISTINCT j.job_id, j.job_number, j.name
            FROM job j
            JOIN hj_costcode cc ON cc.job_id = j.job_id
            WHERE cc.act_labor_hrs > 0 OR cc.act_total > 0
            ORDER BY j.job_number
        """).fetchall()
    else:
        # Only jobs that already have rate cards
        jobs = conn.execute("""
            SELECT j.job_id, j.job_number, j.name
            FROM job j
            JOIN rate_card rc ON rc.job_id = j.job_id
            ORDER BY j.job_number
        """).fetchall()

    conn.close()

    print(f"Regenerating rate cards for {len(jobs)} jobs\n")
    generator = RateCardGenerator()
    success = 0
    errors = 0

    for i, job in enumerate(jobs):
        job_id = job["job_id"]
        job_num = job["job_number"]
        job_name = (job["name"] or "")[:40]

        try:
            # Get cost codes for this job
            conn = get_connection()
            cost_codes = conn.execute(
                "SELECT * FROM hj_costcode WHERE job_id = ? ORDER BY code",
                (job_id,),
            ).fetchall()
            cost_codes = [dict(cc) for cc in cost_codes]
            conn.close()

            if not cost_codes:
                continue

            # Generate rate card
            card = generator.generate_rate_card(job_num, job_name, cost_codes)

            # Save to DB
            card_id = upsert_rate_card(card, job_id)
            item_count = upsert_rate_items(card.items, card_id)

            success += 1
            if (i + 1) % 20 == 0 or (i + 1) == len(jobs):
                print(f"  [{i+1}/{len(jobs)}] {job_num} - {item_count} items", flush=True)

        except Exception as e:
            errors += 1
            print(f"  ERROR on {job_num}: {e}", flush=True)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s — {success} cards generated, {errors} errors")


if __name__ == "__main__":
    main()
