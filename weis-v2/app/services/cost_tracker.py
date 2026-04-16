"""API cost tracking — logs every Anthropic API call and provides per-bid summaries.

Haiku pricing (as of 2025):
  Input:  $1.00 per 1M tokens
  Output: $5.00 per 1M tokens
"""

from __future__ import annotations

import logging
from app.database import get_connection

logger = logging.getLogger(__name__)

# Claude Haiku pricing
HAIKU_INPUT_COST_PER_TOKEN = 1.00 / 1_000_000
HAIKU_OUTPUT_COST_PER_TOKEN = 5.00 / 1_000_000


def log_api_call(
    bid_id: int | None,
    operation: str,
    model: str = "claude-haiku-4-5-20251001",
    input_tokens: int = 0,
    output_tokens: int = 0,
    detail: str | None = None,
):
    """Log a single API call with token counts and calculated cost."""
    total = input_tokens + output_tokens
    cost = (input_tokens * HAIKU_INPUT_COST_PER_TOKEN) + (output_tokens * HAIKU_OUTPUT_COST_PER_TOKEN)

    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO api_usage_log
               (bid_id, operation, model, input_tokens, output_tokens, total_tokens, cost_usd, detail)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (bid_id, operation, model, input_tokens, output_tokens, total, round(cost, 6), detail),
        )
        conn.commit()
    except Exception as e:
        logger.warning("Failed to log API usage: %s", e)
    finally:
        conn.close()


def get_bid_cost_summary(bid_id: int) -> dict:
    """Get cost breakdown for a specific bid."""
    conn = get_connection()
    try:
        # From api_usage_log
        usage_rows = conn.execute(
            """SELECT operation,
                      COUNT(*) as call_count,
                      SUM(input_tokens) as input_tokens,
                      SUM(output_tokens) as output_tokens,
                      SUM(total_tokens) as total_tokens,
                      SUM(cost_usd) as cost_usd
               FROM api_usage_log
               WHERE bid_id = ?
               GROUP BY operation
               ORDER BY cost_usd DESC""",
            (bid_id,),
        ).fetchall()

        # From agent_reports (historical — may not be in usage log yet)
        agent_rows = conn.execute(
            """SELECT agent_name, tokens_used, duration_seconds, updated_at
               FROM agent_reports
               WHERE bid_id = ? AND tokens_used > 0""",
            (bid_id,),
        ).fetchall()

        # Calculate agent cost estimate (approximate — we don't have input/output split)
        agent_total_tokens = sum(r["tokens_used"] or 0 for r in agent_rows)
        # Rough estimate: 80% input, 20% output for agents
        agent_cost_est = (agent_total_tokens * 0.8 * HAIKU_INPUT_COST_PER_TOKEN) + \
                         (agent_total_tokens * 0.2 * HAIKU_OUTPUT_COST_PER_TOKEN)

        # Usage log totals
        log_total_tokens = sum(r["total_tokens"] or 0 for r in usage_rows)
        log_total_cost = sum(r["cost_usd"] or 0 for r in usage_rows)

        return {
            "bid_id": bid_id,
            "usage_log": [dict(r) for r in usage_rows],
            "agent_reports": [
                {
                    "agent_name": r["agent_name"],
                    "tokens_used": r["tokens_used"],
                    "duration_seconds": r["duration_seconds"],
                }
                for r in agent_rows
            ],
            "totals": {
                "logged_tokens": log_total_tokens,
                "logged_cost_usd": round(log_total_cost, 4),
                "agent_tokens": agent_total_tokens,
                "agent_cost_est_usd": round(agent_cost_est, 4),
                "combined_tokens": log_total_tokens + agent_total_tokens,
                "combined_cost_est_usd": round(log_total_cost + agent_cost_est, 4),
            },
        }
    finally:
        conn.close()


def get_all_bids_cost() -> list[dict]:
    """Get cost totals across all bids."""
    conn = get_connection()
    try:
        # Usage log per bid
        usage = conn.execute(
            """SELECT bid_id,
                      SUM(total_tokens) as log_tokens,
                      SUM(cost_usd) as log_cost
               FROM api_usage_log
               WHERE bid_id IS NOT NULL
               GROUP BY bid_id""",
        ).fetchall()
        usage_map = {r["bid_id"]: dict(r) for r in usage}

        # Agent tokens per bid
        agents = conn.execute(
            """SELECT bid_id,
                      SUM(tokens_used) as agent_tokens
               FROM agent_reports
               WHERE tokens_used > 0
               GROUP BY bid_id""",
        ).fetchall()
        agent_map = {r["bid_id"]: r["agent_tokens"] or 0 for r in agents}

        all_bid_ids = set(usage_map.keys()) | set(agent_map.keys())
        results = []
        for bid_id in sorted(all_bid_ids):
            log_tokens = usage_map.get(bid_id, {}).get("log_tokens", 0) or 0
            log_cost = usage_map.get(bid_id, {}).get("log_cost", 0) or 0
            a_tokens = agent_map.get(bid_id, 0)
            a_cost = (a_tokens * 0.8 * HAIKU_INPUT_COST_PER_TOKEN) + (a_tokens * 0.2 * HAIKU_OUTPUT_COST_PER_TOKEN)
            results.append({
                "bid_id": bid_id,
                "total_tokens": log_tokens + a_tokens,
                "total_cost_est_usd": round(log_cost + a_cost, 4),
            })
        return results
    finally:
        conn.close()
