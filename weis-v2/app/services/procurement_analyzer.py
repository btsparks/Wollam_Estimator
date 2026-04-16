"""Procurement gap analyzer — cross-references SOV, agents, and vendor directory."""

import logging
from app.database import get_connection

logger = logging.getLogger(__name__)


def analyze_procurement_gaps(bid_id: int) -> list[dict]:
    """Cross-reference SOV items, agent findings, and vendor trades to find gaps.

    Only analyzes in-scope SOV items. Out-of-scope items are invisible.
    Returns suggestions (does NOT auto-create).
    """
    conn = get_connection()
    try:
        # 1. Get in-scope subcontract SOV items
        sub_items = conn.execute(
            """SELECT s.id, s.item_number, s.description, s.work_type
               FROM bid_sov_item s
               WHERE s.bid_id = ? AND COALESCE(s.in_scope, 1) = 1 AND s.work_type = 'subcontract'
               ORDER BY s.sort_order""",
            (bid_id,),
        ).fetchall()

        # 2. Get existing procurement items for this bid
        existing = conn.execute(
            "SELECT id, name, trade_match FROM procurement_item WHERE bid_id = ?", (bid_id,)
        ).fetchall()
        existing_names = {e["name"].lower() for e in existing}

        # 3. Get linked SOV items
        linked_sov_ids = set()
        for e in existing:
            links = conn.execute(
                "SELECT sov_item_id FROM procurement_sov_link WHERE procurement_item_id = ?",
                (e["id"],),
            ).fetchall()
            for lnk in links:
                linked_sov_ids.add(lnk["sov_item_id"])

        # 4. Get vendor trades for matching
        trades = conn.execute(
            "SELECT DISTINCT trade FROM vendor_directory WHERE is_active = 1"
        ).fetchall()
        trade_names = [t["trade"].lower() for t in trades]

        # 5. Get agent reports for additional suggestions
        agent_findings = []
        reports = conn.execute(
            "SELECT agent_name, report_json FROM agent_reports WHERE bid_id = ? AND status = 'complete'",
            (bid_id,),
        ).fetchall()

        import json
        for r in reports:
            try:
                rj = json.loads(r["report_json"]) if isinstance(r["report_json"], str) else (r["report_json"] or {})
            except (json.JSONDecodeError, TypeError):
                continue

            # QA/QC: testing requirements
            for test in rj.get("testing_requirements", []):
                agent_findings.append({
                    "name": f"Testing: {test.get('test', 'Unknown')}",
                    "type": "testing",
                    "source": f"QA/QC Agent: {test.get('test', '')} per {test.get('spec_section', '')}",
                })

            # Subcontract: recommended scopes
            for scope in rj.get("recommended_sub_scopes", []):
                agent_findings.append({
                    "name": f"{scope.get('discipline', 'Sub')} Subcontract",
                    "type": "subcontract",
                    "trade": scope.get("discipline"),
                    "source": f"Subcontract Agent: {scope.get('scope_summary', '')}",
                })

        suggestions = []
        suggestion_id = 0

        # Suggest procurement items for unlinked subcontract SOV items
        for item in sub_items:
            if item["id"] not in linked_sov_ids:
                desc = item["description"] or ""
                # Try to match to a vendor trade
                trade_match = None
                desc_lower = desc.lower()
                for tn in trade_names:
                    if tn in desc_lower or desc_lower in tn:
                        trade_match = tn.title()
                        break

                name = f"{desc[:80]} Subcontract" if desc else f"SOV Item {item['item_number']} Sub"
                if name.lower() not in existing_names:
                    suggestion_id += 1
                    suggestions.append({
                        "suggestion_id": suggestion_id,
                        "name": name,
                        "procurement_type": "subcontract",
                        "trade_match": trade_match,
                        "ai_source": f"SOV item '{desc}' designated as subcontract with no procurement link",
                        "related_sov_items": [item["id"]],
                    })

        # Add agent-sourced suggestions not already covered
        for af in agent_findings:
            if af["name"].lower() not in existing_names:
                # Dedup against already-suggested names
                if not any(s["name"].lower() == af["name"].lower() for s in suggestions):
                    suggestion_id += 1
                    suggestions.append({
                        "suggestion_id": suggestion_id,
                        "name": af["name"],
                        "procurement_type": af["type"],
                        "trade_match": af.get("trade"),
                        "ai_source": af["source"],
                        "related_sov_items": [],
                    })

        return suggestions
    finally:
        conn.close()


def suggest_vendors(procurement_item_id: int) -> list[dict]:
    """Suggest vendors matching a procurement item's trade."""
    conn = get_connection()
    try:
        item = conn.execute(
            "SELECT trade_match FROM procurement_item WHERE id = ?", (procurement_item_id,)
        ).fetchone()
        if not item or not item["trade_match"]:
            return []

        trade = item["trade_match"]
        # Search by exact match first, then fuzzy
        vendors = conn.execute(
            """SELECT * FROM vendor_directory
               WHERE is_active = 1 AND (trade = ? OR trade LIKE ? OR ? LIKE '%' || trade || '%')
               ORDER BY company ASC""",
            (trade, f"%{trade}%", trade),
        ).fetchall()
        return [dict(v) for v in vendors]
    finally:
        conn.close()
