"""Historical rate lookup for SOV items.

Bridges Phase 1 (197 jobs of actuals) with Phase 2 (active bids).
Uses Claude Haiku to map SOV descriptions to likely cost codes/disciplines,
then queries the rate_item table for matching rates across all jobs.
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass, field

import anthropic

from app.config import ANTHROPIC_API_KEY
from app.database import get_connection

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"


@dataclass
class RateMatch:
    """A matching historical rate for a SOV item."""
    cost_code: str
    description: str
    unit: str
    mh_per_unit: float  # Median across jobs
    dollar_per_unit: float  # Median across jobs
    job_count: int
    confidence: str  # high/medium/low
    min_rate: float
    max_rate: float
    source_jobs: list[str] = field(default_factory=list)
    pm_context: str | None = None


MAPPING_PROMPT = """You are matching construction bid SOV line items to Wollam Construction's historical cost codes.

Given a SOV item description, return the most likely cost code patterns and discipline keywords
that would match this work in a heavy civil construction database.

Wollam's disciplines: earthwork, concrete, structural_steel, piping, electrical,
mechanical, building, general_conditions

Return a JSON object:
{
  "discipline_keywords": ["earthwork", "excavation"],
  "description_keywords": ["excavation", "fill", "grading", "backfill"],
  "unit_match": "CY"
}

Rules:
- Focus on the actual work being described, not administrative overhead
- Return 2-5 keywords that would appear in cost code descriptions
- Use the unit that matches the historical data (CY, LF, SF, EA, TON, DAY, LS, etc.)
- Return ONLY valid JSON
"""


def _map_sov_to_keywords(description: str, unit: str | None) -> dict:
    """Use Claude Haiku to map a SOV description to cost code keywords."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_msg = f"SOV Item: {description}"
    if unit:
        user_msg += f" (Unit: {unit})"

    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=MAPPING_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text.strip()
    # Strip code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"discipline_keywords": [], "description_keywords": [description.lower().split()[:3]]}


def _search_rate_items(keywords: list[str], unit: str | None) -> list[dict]:
    """Search rate_item table for matching cost codes."""
    conn = get_connection()
    try:
        # Build LIKE conditions for keyword matching
        conditions = []
        params = []
        for kw in keywords:
            conditions.append("(LOWER(ri.description) LIKE ? OR LOWER(ri.activity) LIKE ?)")
            params.extend([f"%{kw.lower()}%", f"%{kw.lower()}%"])

        if not conditions:
            return []

        where = " OR ".join(conditions)

        # Optional unit filter
        unit_clause = ""
        if unit:
            unit_clause = " AND LOWER(ri.unit) = ?"
            params.append(unit.lower())

        query = f"""
            SELECT ri.activity as cost_code, ri.description, ri.unit,
                   ri.act_mh_per_unit, ri.act_cost_per_unit,
                   ri.confidence, ri.timecard_count, ri.total_hours, ri.total_qty,
                   j.job_number, j.name as job_name
            FROM rate_item ri
            JOIN rate_card rc ON ri.card_id = rc.card_id
            JOIN job j ON rc.job_id = j.job_id
            WHERE ({where}){unit_clause}
              AND ri.act_mh_per_unit IS NOT NULL
              AND ri.act_mh_per_unit > 0
              AND ri.timecard_count >= 2
            ORDER BY ri.timecard_count DESC
            LIMIT 100
        """

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _load_pm_context(cost_code: str) -> str | None:
    """Load PM context for a cost code if it exists."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT notes FROM cc_context
               WHERE cost_code = ? AND notes IS NOT NULL AND notes != ''
               LIMIT 1""",
            (cost_code,),
        ).fetchone()
        return row["notes"] if row else None
    finally:
        conn.close()


def lookup_rates_for_sov_item(
    description: str,
    unit: str | None = None,
    quantity: float | None = None,
) -> list[RateMatch]:
    """Find matching historical rates for a SOV line item.

    1. Uses Claude Haiku to map the SOV description to likely cost codes
    2. Queries rate_item table for matching codes across all jobs
    3. Calculates statistics and returns ranked matches
    """
    # Step 1: Map description to keywords
    mapping = _map_sov_to_keywords(description, unit)
    keywords = mapping.get("description_keywords", [])
    unit_match = mapping.get("unit_match") or unit

    if not keywords:
        return []

    # Step 2: Search rate items
    raw_matches = _search_rate_items(keywords, unit_match)

    if not raw_matches:
        # Try without unit filter
        raw_matches = _search_rate_items(keywords, None)

    if not raw_matches:
        return []

    # Step 3: Group by cost code and calculate statistics
    by_code: dict[str, list[dict]] = {}
    for m in raw_matches:
        code = m["cost_code"]
        if code not in by_code:
            by_code[code] = []
        by_code[code].append(m)

    results = []
    for code, items in by_code.items():
        mh_rates = [i["act_mh_per_unit"] for i in items if i["act_mh_per_unit"]]
        cost_rates = [i["act_cost_per_unit"] for i in items if i["act_cost_per_unit"]]

        if not mh_rates:
            continue

        median_mh = statistics.median(mh_rates)
        median_cost = statistics.median(cost_rates) if cost_rates else 0.0
        job_numbers = list(set(i["job_number"] for i in items))

        # Determine confidence from data richness
        total_tc = sum(i["timecard_count"] for i in items)
        if total_tc >= 50 and len(job_numbers) >= 3:
            confidence = "high"
        elif total_tc >= 10 and len(job_numbers) >= 2:
            confidence = "medium"
        else:
            confidence = "low"

        pm_ctx = _load_pm_context(code)

        results.append(RateMatch(
            cost_code=code,
            description=items[0]["description"],
            unit=items[0]["unit"] or "",
            mh_per_unit=round(median_mh, 4),
            dollar_per_unit=round(median_cost, 4),
            job_count=len(job_numbers),
            confidence=confidence,
            min_rate=round(min(mh_rates), 4),
            max_rate=round(max(mh_rates), 4),
            source_jobs=job_numbers[:10],
            pm_context=pm_ctx,
        ))

    # Sort by confidence then job count
    conf_order = {"high": 0, "medium": 1, "low": 2}
    results.sort(key=lambda r: (conf_order.get(r.confidence, 3), -r.job_count))

    return results[:20]


def auto_populate_sov_rates(bid_id: int) -> dict:
    """Attempt to find historical rates for all SOV items in a bid.

    Never overwrites manually-set prices.
    Returns: {matched, ambiguous, no_match, skipped}
    """
    conn = get_connection()
    try:
        items = conn.execute(
            """SELECT id, description, unit, quantity, unit_price, mapped_by
               FROM bid_sov_item WHERE bid_id = ? AND COALESCE(in_scope, 1) = 1
               ORDER BY sort_order""",
            (bid_id,),
        ).fetchall()
    finally:
        conn.close()

    matched = 0
    ambiguous = 0
    no_match = 0
    skipped = 0

    for item in items:
        # Skip manually-priced items
        if item["unit_price"] is not None and item["mapped_by"] == "manual":
            skipped += 1
            continue

        try:
            matches = lookup_rates_for_sov_item(
                item["description"],
                item["unit"],
                item["quantity"],
            )
        except Exception as e:
            logger.warning("Rate lookup failed for item %d: %s", item["id"], e)
            no_match += 1
            continue

        if not matches:
            no_match += 1
            continue

        top = matches[0]
        conn = get_connection()
        try:
            if top.confidence == "high" and len(matches) == 1:
                # High confidence single match — auto-populate
                conn.execute(
                    """UPDATE bid_sov_item
                       SET unit_price = ?, rate_source = ?, rate_confidence = ?,
                           cost_code = ?, discipline = ?, mapped_by = 'ai_rate_lookup',
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (
                        top.dollar_per_unit,
                        f"Historical: {top.job_count} jobs, median $/unit (codes: {', '.join(top.source_jobs[:3])})",
                        top.confidence,
                        top.cost_code,
                        None,
                        item["id"],
                    ),
                )
                conn.commit()
                matched += 1
            else:
                # Ambiguous — store candidates but don't set price
                candidates = ", ".join(
                    f"{m.cost_code} ({m.confidence}, {m.job_count} jobs)"
                    for m in matches[:3]
                )
                conn.execute(
                    """UPDATE bid_sov_item
                       SET rate_source = ?, rate_confidence = ?,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = ? AND (unit_price IS NULL OR mapped_by != 'manual')""",
                    (
                        f"Candidates: {candidates}",
                        "ambiguous",
                        item["id"],
                    ),
                )
                conn.commit()
                ambiguous += 1
        finally:
            conn.close()

    return {
        "matched": matched,
        "ambiguous": ambiguous,
        "no_match": no_match,
        "skipped": skipped,
        "total": len(items),
    }
