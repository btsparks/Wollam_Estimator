"""Subcontract Manager Agent — identifies sub-eligible scope and self-perform recommendations.

Analyzes bid documents and SOV items to recommend which scopes should be
subcontracted vs. self-performed, based on specialty requirements and
Wollam's core competencies (heavy civil, earthwork, concrete, piping).
"""

from __future__ import annotations

from app.agents.base import BaseAgent


SYSTEM_PROMPT = """You are a Subcontract Manager for Wollam Construction, a Utah-based industrial heavy civil contractor.

Wollam's core competencies (self-perform):
- Earthwork (excavation, grading, backfill, compaction)
- Concrete (forming, rebar, placement, finishing)
- Piping (HDPE, steel, underground utilities)
- Structural steel erection
- General conditions / site management

Typically subcontracted:
- Electrical
- Mechanical equipment installation (specialty)
- Roofing / building envelope
- Painting / coatings
- Fencing
- Landscaping
- Surveying (unless Wollam has in-house)

Your job:
1. Review the bid documents and SOV items
2. Recommend which scopes to subcontract vs. self-perform
3. Identify special requirements that affect subcontractor selection
4. Flag flow-down clauses that must be passed to subs

Return your analysis as a JSON object with this exact structure:
{
  "recommended_sub_scopes": [
    {
      "discipline": "Electrical",
      "sov_items": ["15", "16"],
      "spec_sections": ["26000-26999"],
      "estimated_value_pct": 15,
      "scope_summary": "Complete electrical including switchgear, conduit, wire, lighting",
      "special_requirements": ["Licensed electrician required", "NFPA 70E compliance"],
      "flow_down_items": ["LD clause applies to milestone 3", "Retainage 10%"]
    }
  ],
  "self_perform_recommended": [
    {
      "discipline": "Earthwork",
      "reason": "Core competency — extensive historical data",
      "sov_items": ["1", "2"]
    }
  ],
  "flags": ["MBE/WBE requirements", "Pre-qualification requirements for subs", "etc."]
}

Rules:
- Always reference specific SOV items and spec sections
- estimated_value_pct is a rough estimate of that scope's share of total bid
- Include flow_down_items that affect subcontractor pricing (LDs, retainage, bonding, insurance)
- Flag any diversity requirements (MBE/WBE/DBE), pre-qualification, or licensing
- Return ONLY valid JSON — no markdown, no explanation
"""


class SubcontractManagerAgent(BaseAgent):
    name = "subcontract_manager"
    display_name = "Subcontract Manager"
    version = "1.0"
    system_prompt = SYSTEM_PROMPT

    def _build_summary(self, report_json: dict) -> str:
        sub_scopes = report_json.get("recommended_sub_scopes", [])
        self_perform = report_json.get("self_perform_recommended", [])
        flags = report_json.get("flags", [])

        parts = []
        if sub_scopes:
            disciplines = [s.get("discipline", "?") for s in sub_scopes]
            parts.append(f"Sub: {', '.join(disciplines)}")
        if self_perform:
            disciplines = [s.get("discipline", "?") for s in self_perform]
            parts.append(f"Self-perform: {', '.join(disciplines)}")
        if flags:
            parts.append(f"{len(flags)} flag(s)")

        return ". ".join(parts) + "." if parts else "No subcontract analysis available."

    def _assess_risk(self, report_json: dict) -> str:
        flags = report_json.get("flags", [])
        sub_scopes = report_json.get("recommended_sub_scopes", [])

        # High risk if many specialty subs needed or significant flags
        special_req_count = sum(
            len(s.get("special_requirements", []))
            for s in sub_scopes
        )

        if len(flags) >= 4 or special_req_count >= 6:
            return "high"
        elif len(flags) >= 2 or special_req_count >= 3:
            return "medium"
        return "low"

    def _empty_report(self) -> dict:
        return {
            "recommended_sub_scopes": [],
            "self_perform_recommended": [],
            "flags": [],
        }
