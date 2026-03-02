"""Subcontract / Procurement agent (preliminary scope identification)."""

from app.agents.base import BidAgent, DEFAULT_TOOLS, DEFAULT_TOOL_FUNCTIONS, EXTENDED_TOOLS, EXTENDED_TOOL_FUNCTIONS


class SubcontractAgent(BidAgent):
    AGENT_NAME = "subcontract"
    AGENT_DISPLAY_NAME = "Subcontract / Procurement"

    def get_tools(self) -> list[dict]:
        tools = list(DEFAULT_TOOLS)
        tools.append(EXTENDED_TOOLS["search_subcontractors"])
        tools.append(EXTENDED_TOOLS["search_material_costs"])
        tools.append(EXTENDED_TOOLS["search_lessons_learned"])
        return tools

    def get_tool_functions(self) -> dict:
        funcs = dict(DEFAULT_TOOL_FUNCTIONS)
        funcs["search_subcontractors"] = EXTENDED_TOOL_FUNCTIONS["search_subcontractors"]
        funcs["search_material_costs"] = EXTENDED_TOOL_FUNCTIONS["search_material_costs"]
        funcs["search_lessons_learned"] = EXTENDED_TOOL_FUNCTIONS["search_lessons_learned"]
        return funcs

    def get_system_prompt(self, bid_context: dict) -> str:
        doc_list = "\n".join(
            f"  - [{d.get('doc_category', 'general')}] {d['filename']} (ID: {d['id']})"
            for d in bid_context.get("documents", [])
        )
        return f"""You are the Subcontract / Procurement Manager agent for Wollam Construction's estimating team.

## Role
This is a PRELIMINARY analysis. You identify sub-eligible scope from the bid documents and cross-reference with Wollam's historical subcontractor database. Full scope sheets and RFQ packages come later after takeoff.

## Wollam Typical Sub Packages
- Rebar (furnish and install)
- Concrete pumping
- Structural steel erection
- Electrical
- Building erection / metal buildings
- Survey
- Testing and inspection (soils, concrete, steel)
- Crane and rigging (if not self-performed)
- Specialty coatings / painting
- Insulation
- Fireproofing
- Roofing

## Bid Context
- **Bid Name:** {bid_context['bid_name']}
- **Owner:** {bid_context.get('owner', 'N/A')}
- **GC:** {bid_context.get('general_contractor', 'N/A')}

### Documents
{doc_list}

## Instructions
1. Search bid documents for scope items that are typically subcontracted.
2. For each identified package, note the spec sections and scope description.
3. Use `search_subcontractors` to find historical subs Wollam has used for similar scope.
4. Use `search_material_costs` for long-lead or specialty material items.
5. Identify items Wollam should self-perform vs subcontract.
6. Flag long-lead items, sole-source requirements, or owner-directed subs.

## Output Format
Return ONLY a JSON object:
```json
{{
  "executive_summary": "2-3 sentence overview of sub scope",
  "flags_count": 0,
  "identified_packages": [
    {{
      "package_name": "e.g., Rebar Furnish & Install",
      "discipline": "e.g., Concrete",
      "scope_description": "brief description of the sub scope",
      "spec_sections": ["list of relevant spec sections found"],
      "historical_subs": [
        {{
          "sub_name": "name from database",
          "past_project": "job number or name",
          "performance": "rating if available",
          "cost": "contract amount if available"
        }}
      ]
    }}
  ],
  "self_perform_recommendations": ["scope items Wollam should self-perform"],
  "sub_eligible_scopes": ["all identified sub-eligible scope items"],
  "procurement_flags": ["long-lead items, sole-source, owner-directed, etc."]
}}
```

## Rules
- Cite source documents for every identified scope.
- Only report historical subs that actually exist in the database.
- flags_count = number of procurement flags (long-lead, sole-source, etc.).
- This is preliminary — don't create full scope sheets or RFQ packages.
"""

    def get_task_prompt(self, bid_context: dict) -> str:
        return (
            f"Review the bid documents for '{bid_context['bid_name']}' and identify "
            "sub-eligible scope. Check each typical sub package (rebar, concrete pumping, "
            "steel erection, electrical, building erection, survey, testing, crane, "
            "coatings, insulation, fireproofing, roofing). Cross-reference with historical "
            "subcontractor database. Identify long-lead items and procurement flags. "
            "Produce a preliminary subcontract report as JSON."
        )

    def parse_report(self, raw_text: str) -> dict:
        report = self._extract_json_from_text(raw_text)
        if "flags_count" not in report:
            report["flags_count"] = len(report.get("procurement_flags", []))
        return report
