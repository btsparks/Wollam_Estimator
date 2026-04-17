"""Procurement gap analyzer — cross-references SOV, agents, and vendor directory.

The procurement register tracks external pricing needed for the bid. The gap
analysis identifies SOV items that need procurement but don't have it yet.

Key rules:
- ONLY in-scope SOV items are visible (out-of-scope = invisible)
- ONLY items with work_type='subcontract' generate procurement suggestions
- Items with work_type='undecided' or 'self_perform' are excluded
- Agent findings only produce suggestions when tied to a subcontract SOV item
"""

import json
import logging
from app.database import get_connection

logger = logging.getLogger(__name__)


def analyze_procurement_gaps(bid_id: int) -> list[dict]:
    """Cross-reference in-scope subcontract SOV items against existing procurement items.

    Returns suggestions for missing procurement items. Does NOT auto-create.
    """
    conn = get_connection()
    try:
        # 1. Get ALL in-scope SOV items (we need the full list for context)
        all_in_scope = conn.execute(
            """SELECT s.id, s.item_number, s.description, s.work_type
               FROM bid_sov_item s
               WHERE s.bid_id = ? AND COALESCE(s.in_scope, 1) = 1
               ORDER BY s.sort_order""",
            (bid_id,),
        ).fetchall()

        # Only subcontract items need procurement
        sub_items = [i for i in all_in_scope if i["work_type"] == "subcontract"]

        # Count undecided for guidance message
        undecided_count = sum(1 for i in all_in_scope if (i["work_type"] or "undecided") == "undecided")

        # 2. Get existing procurement items and their SOV links
        existing = conn.execute(
            "SELECT id, name, trade_match FROM procurement_item WHERE bid_id = ?", (bid_id,)
        ).fetchall()
        existing_names = {e["name"].lower() for e in existing}

        linked_sov_ids = set()
        for e in existing:
            links = conn.execute(
                "SELECT sov_item_id FROM procurement_sov_link WHERE procurement_item_id = ?",
                (e["id"],),
            ).fetchall()
            for lnk in links:
                linked_sov_ids.add(lnk["sov_item_id"])

        # 3. Get vendor trades for matching
        trades = conn.execute(
            "SELECT DISTINCT trade FROM vendor_directory WHERE is_active = 1"
        ).fetchall()
        trade_names = [t["trade"].lower() for t in trades]

        suggestions = []
        suggestion_id = 0

        # 4. Suggest procurement items for UNLINKED SUBCONTRACT SOV items only
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
                        "ai_source": f"SOV item '{item['item_number'] or ''}' ({desc[:60]}) — designated subcontract, no procurement link",
                        "related_sov_items": [item["id"]],
                    })

        # 5. Agent-sourced suggestions — ONLY if they relate to subcontract SOV items
        #    We match agent findings against subcontract item descriptions to avoid
        #    suggesting procurement for self-perform or undecided work.
        if sub_items:
            reports = conn.execute(
                "SELECT agent_name, report_json FROM agent_reports WHERE bid_id = ? AND status = 'complete'",
                (bid_id,),
            ).fetchall()

            sub_descriptions = {i["id"]: (i["description"] or "").lower() for i in sub_items}
            sub_desc_text = " ".join(sub_descriptions.values())

            for r in reports:
                try:
                    rj = json.loads(r["report_json"]) if isinstance(r["report_json"], str) else (r["report_json"] or {})
                except (json.JSONDecodeError, TypeError):
                    continue

                # QA/QC testing — only suggest if the test relates to a subcontract scope
                for test in rj.get("testing_requirements", []):
                    test_name = test.get("test", "")
                    # Check if any subcontract SOV description mentions this test topic
                    test_lower = test_name.lower()
                    if any(kw in sub_desc_text for kw in test_lower.split()[:3] if len(kw) > 3):
                        name = f"Testing: {test_name}"
                        if name.lower() not in existing_names and not any(s["name"].lower() == name.lower() for s in suggestions):
                            suggestion_id += 1
                            suggestions.append({
                                "suggestion_id": suggestion_id,
                                "name": name,
                                "procurement_type": "testing",
                                "trade_match": None,
                                "ai_source": f"QA/QC Agent: {test_name} per {test.get('spec_section', '')}",
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
        vendors = conn.execute(
            """SELECT * FROM vendor_directory
               WHERE is_active = 1 AND (trade = ? OR trade LIKE ? OR ? LIKE '%' || trade || '%')
               ORDER BY company ASC""",
            (trade, f"%{trade}%", trade),
        ).fetchall()
        return [dict(v) for v in vendors]
    finally:
        conn.close()
