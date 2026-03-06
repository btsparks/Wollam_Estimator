"""
Knowledge Base Aggregation

Processes approved rate cards into the Tier 3 knowledge base tables:
    rate_library — aggregated rates across all approved jobs
    benchmark    — roll-up benchmarks for high-level estimating

For each (discipline, activity) pair across all approved cards:
    - Average recommended rate
    - Min, max, standard deviation
    - Number of jobs contributing
    - Source job numbers

Triggered by review.approve() after a card moves to 'approved' status.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from app.database import get_connection


def aggregate_card(card_id: int) -> dict[str, Any]:
    """
    Process a single approved card into rate_library/benchmark tables.

    Rebuilds the rate_library entries for all (discipline, activity) pairs
    that appear in this card, incorporating data from all approved cards.

    Args:
        card_id: The approved rate card to process.

    Returns:
        Dict with rates_updated, benchmarks_updated counts.
    """
    conn = get_connection()
    try:
        # Verify card is approved
        card = conn.execute(
            "SELECT card_id, job_id, status FROM rate_card WHERE card_id = ?",
            (card_id,),
        ).fetchone()
        if not card or card["status"] != "approved":
            return {"rates_updated": 0, "benchmarks_updated": 0}

        # Get all unique (discipline, activity) pairs from this card
        pairs = conn.execute(
            """SELECT DISTINCT discipline, activity
               FROM rate_item WHERE card_id = ?""",
            (card_id,),
        ).fetchall()

        rates_updated = 0
        for pair in pairs:
            disc = pair["discipline"]
            act = pair["activity"]
            rates_updated += _rebuild_rate_entry(conn, disc, act)

        # Rebuild benchmarks
        benchmarks_updated = _rebuild_benchmarks(conn)

        conn.commit()
        return {
            "rates_updated": rates_updated,
            "benchmarks_updated": benchmarks_updated,
        }
    finally:
        conn.close()


def rebuild_all() -> dict[str, Any]:
    """
    Full rebuild of rate_library and benchmark from all approved cards.

    Returns:
        Dict with rates_updated, benchmarks_updated counts.
    """
    conn = get_connection()
    try:
        # Clear existing
        conn.execute("DELETE FROM rate_library")
        conn.execute("DELETE FROM benchmark")

        # Get all unique (discipline, activity) from approved cards
        pairs = conn.execute(
            """SELECT DISTINCT ri.discipline, ri.activity
               FROM rate_item ri
               JOIN rate_card rc ON ri.card_id = rc.card_id
               WHERE rc.status = 'approved'""",
        ).fetchall()

        rates_updated = 0
        for pair in pairs:
            rates_updated += _rebuild_rate_entry(conn, pair["discipline"], pair["activity"])

        benchmarks_updated = _rebuild_benchmarks(conn)
        conn.commit()

        return {
            "rates_updated": rates_updated,
            "benchmarks_updated": benchmarks_updated,
        }
    finally:
        conn.close()


def _rebuild_rate_entry(conn, discipline: str, activity: str) -> int:
    """Rebuild a single rate_library entry from all approved cards."""
    # Get all approved rate items for this (discipline, activity)
    rows = conn.execute(
        """SELECT ri.rec_rate, ri.unit, ri.description, ri.confidence,
                  j.job_number
           FROM rate_item ri
           JOIN rate_card rc ON ri.card_id = rc.card_id
           JOIN job j ON rc.job_id = j.job_id
           WHERE rc.status = 'approved'
             AND ri.discipline = ? AND ri.activity = ?
             AND ri.rec_rate IS NOT NULL""",
        (discipline, activity),
    ).fetchall()

    if not rows:
        return 0

    rates = [r["rec_rate"] for r in rows]
    avg_rate = sum(rates) / len(rates)
    rate_low = min(rates)
    rate_high = max(rates)
    std_dev = _std_dev(rates) if len(rates) > 1 else None
    jobs_count = len(rates)
    source_jobs = ",".join(sorted(set(r["job_number"] for r in rows)))
    unit = rows[0]["unit"] or "MH/unit"
    description = rows[0]["description"]

    # Confidence based on job count
    if jobs_count >= 3:
        confidence = "strong"
    elif jobs_count >= 2:
        confidence = "moderate"
    else:
        confidence = "limited"

    conn.execute(
        """INSERT INTO rate_library
               (discipline, activity, description, rate, unit, rate_type,
                confidence, jobs_count, source_jobs,
                rate_low, rate_high, std_dev, last_updated)
           VALUES (?, ?, ?, ?, ?, 'labor', ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(discipline, activity, rate_type) DO UPDATE SET
               description = excluded.description,
               rate = excluded.rate,
               unit = excluded.unit,
               confidence = excluded.confidence,
               jobs_count = excluded.jobs_count,
               source_jobs = excluded.source_jobs,
               rate_low = excluded.rate_low,
               rate_high = excluded.rate_high,
               std_dev = excluded.std_dev,
               last_updated = excluded.last_updated""",
        (
            discipline, activity, description,
            round(avg_rate, 6), unit,
            confidence, jobs_count, source_jobs,
            round(rate_low, 6), round(rate_high, 6),
            round(std_dev, 6) if std_dev else None,
            datetime.now().isoformat(),
        ),
    )
    return 1


def _rebuild_benchmarks(conn) -> int:
    """Rebuild benchmark table from all approved rate cards."""
    count = 0

    # Benchmark: all_in_concrete (total concrete cost / total CY)
    concrete_rows = conn.execute(
        """SELECT rc.total_budget, rc.total_actual, j.job_number, j.project_type
           FROM rate_card rc
           JOIN job j ON rc.job_id = j.job_id
           WHERE rc.status = 'approved'
             AND rc.total_actual IS NOT NULL AND rc.total_actual > 0""",
    ).fetchall()

    # Benchmark: gc_percent (GC cost codes as % of total)
    gc_rows = conn.execute(
        """SELECT j.job_number, j.project_type,
                  SUM(CASE WHEN ri.discipline = 'general_conditions'
                      THEN COALESCE(ri.qty_actual * ri.act_cost_per_unit, 0) ELSE 0 END) as gc_cost,
                  SUM(COALESCE(ri.qty_actual * ri.act_cost_per_unit, 0)) as total_cost
           FROM rate_item ri
           JOIN rate_card rc ON ri.card_id = rc.card_id
           JOIN job j ON rc.job_id = j.job_id
           WHERE rc.status = 'approved'
           GROUP BY j.job_id
           HAVING total_cost > 0""",
    ).fetchall()

    if gc_rows:
        gc_pcts = [r["gc_cost"] / r["total_cost"] * 100
                   for r in gc_rows
                   if r["total_cost"] > 0 and r["gc_cost"] > 0]
        if gc_pcts:
            avg_gc = sum(gc_pcts) / len(gc_pcts)
            project_type = gc_rows[0]["project_type"] or "industrial"
            source_jobs = ",".join(sorted(set(r["job_number"] for r in gc_rows)))

            conn.execute(
                """INSERT INTO benchmark
                       (metric, description, value, unit, project_type,
                        jobs_count, std_dev, range_low, range_high,
                        source_jobs, last_updated)
                   VALUES ('gc_percent', 'General Conditions as % of Total',
                           ?, '%', ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(metric, project_type) DO UPDATE SET
                       value = excluded.value,
                       jobs_count = excluded.jobs_count,
                       std_dev = excluded.std_dev,
                       range_low = excluded.range_low,
                       range_high = excluded.range_high,
                       source_jobs = excluded.source_jobs,
                       last_updated = excluded.last_updated""",
                (
                    round(avg_gc, 2), project_type,
                    len(gc_pcts),
                    round(_std_dev(gc_pcts), 2) if len(gc_pcts) > 1 else None,
                    round(min(gc_pcts), 2), round(max(gc_pcts), 2),
                    source_jobs, datetime.now().isoformat(),
                ),
            )
            count += 1

    return count


def _std_dev(values: list[float]) -> float:
    """Calculate population standard deviation."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    return math.sqrt(variance)
