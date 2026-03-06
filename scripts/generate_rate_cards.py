"""Batch-generate rate cards for all jobs that have cost codes.

Reads cost code data from hj_costcode, runs each through the
RateCardGenerator, and stores results in rate_card + rate_item tables.

Usage:
    python scripts/generate_rate_cards.py          # New jobs only
    python scripts/generate_rate_cards.py --force   # Regenerate ALL
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import init_db, get_connection
from app.transform.rate_card import RateCardGenerator
from app.hcss.storage import (
    upsert_rate_card,
    upsert_rate_items,
    get_cost_codes_for_job,
)


def main():
    force = "--force" in sys.argv

    init_db()
    conn = get_connection()

    try:
        if force:
            # Regenerate everything
            conn.execute("DELETE FROM rate_item")
            conn.execute("DELETE FROM rate_card")
            conn.commit()
            print("Cleared existing rate cards (--force mode)")
            rows = conn.execute("""
                SELECT DISTINCT j.job_id, j.job_number, j.name, j.status
                FROM job j
                JOIN hj_costcode cc ON cc.job_id = j.job_id
                ORDER BY j.job_number
            """).fetchall()
        else:
            # Find jobs with cost codes but no rate card
            rows = conn.execute("""
                SELECT DISTINCT j.job_id, j.job_number, j.name, j.status
                FROM job j
                JOIN hj_costcode cc ON cc.job_id = j.job_id
                LEFT JOIN rate_card rc ON rc.job_id = j.job_id
                WHERE rc.card_id IS NULL
                ORDER BY j.job_number
            """).fetchall()
    finally:
        conn.close()

    print(f"Jobs needing rate cards: {len(rows)}")
    if not rows:
        print("Nothing to do.")
        return

    generator = RateCardGenerator()
    start = time.time()
    generated = 0
    skipped = 0

    for i, row in enumerate(rows):
        job_id = row["job_id"]
        job_number = row["job_number"] or "???"
        job_name = row["name"] or ""
        status = row["status"] or "unknown"

        # Get cost codes from DB (returns list of dicts)
        cost_codes = get_cost_codes_for_job(job_id)
        if not cost_codes:
            skipped += 1
            continue

        # Generate rate card
        card = generator.generate_rate_card(
            job_number=job_number,
            job_name=job_name,
            cost_codes=cost_codes,
        )

        # Store rate card
        card_id = upsert_rate_card(card, job_id)

        # Store rate items
        item_count = 0
        if card.items:
            item_count = upsert_rate_items(card.items, card_id)

        generated += 1
        elapsed = time.time() - start
        rate = generated / elapsed if elapsed > 0 else 0
        print(
            f"  [{i+1}/{len(rows)}] {job_number:6s} | {status:10s} | "
            f"{len(cost_codes):3d} cc | {item_count:3d} items | "
            f"{rate:.0f}/s | {job_name[:40]}"
        )

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"Rate card generation complete in {elapsed:.1f}s")
    print(f"  Generated: {generated}")
    print(f"  Skipped (no cost codes): {skipped}")

    # Summary stats
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM rate_card").fetchone()[0]
        with_items = conn.execute("""
            SELECT COUNT(DISTINCT rc.card_id)
            FROM rate_card rc
            JOIN rate_item ri ON ri.card_id = rc.card_id
        """).fetchone()[0]
        total_items = conn.execute("SELECT COUNT(*) FROM rate_item").fetchone()[0]
        flagged = conn.execute(
            "SELECT COUNT(*) FROM rate_item WHERE variance_flag = 1"
        ).fetchone()[0]
    finally:
        conn.close()

    print(f"  Total rate cards: {total}")
    print(f"  Cards with items: {with_items}")
    print(f"  Total rate items: {total_items}")
    print(f"  Flagged items: {flagged}")


if __name__ == "__main__":
    main()
