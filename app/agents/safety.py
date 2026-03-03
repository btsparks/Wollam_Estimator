"""Safety Manager agent."""

from app.agents.base import BidAgent, DEFAULT_TOOLS, DEFAULT_TOOL_FUNCTIONS, EXTENDED_TOOLS, EXTENDED_TOOL_FUNCTIONS


class SafetyAgent(BidAgent):
    AGENT_NAME = "safety"
    AGENT_DISPLAY_NAME = "Safety Manager"

    def get_tools(self) -> list[dict]:
        tools = list(DEFAULT_TOOLS)
        tools.append(EXTENDED_TOOLS["search_lessons_learned"])
        return tools

    def get_tool_functions(self) -> dict:
        funcs = dict(DEFAULT_TOOL_FUNCTIONS)
        funcs["search_lessons_learned"] = EXTENDED_TOOL_FUNCTIONS["search_lessons_learned"]
        return funcs

    def check_document_relevance(self, bid_context: dict) -> dict | None:
        """Exit early if no documents are uploaded."""
        docs = bid_context.get("documents", [])
        if not docs:
            return {
                "executive_summary": "No documents uploaded for this bid. Cannot perform safety analysis.",
                "flags_count": 0,
                "findings": [],
                "cost_impact_summary": "No documents available for safety review.",
                "workforce_availability_flags": [],
            }

        total_words = sum(d.get("word_count", 0) or 0 for d in docs)
        if total_words < 200:
            return {
                "executive_summary": f"Uploaded documents contain only {total_words:,} words — insufficient for meaningful safety analysis. Upload safety plans, project specs, or RFP.",
                "flags_count": 0,
                "findings": [],
                "cost_impact_summary": "Insufficient documents for safety review.",
                "workforce_availability_flags": [],
            }

        return None

    def get_system_prompt(self, bid_context: dict) -> str:
        doc_list = "\n".join(
            f"  - [{d.get('doc_category', 'general')}] {d['filename']} (ID: {d['id']})"
            for d in bid_context.get("documents", [])
        )
        return f"""You are the Safety Manager agent for Wollam Construction's estimating team.

## Role
You extract site-specific safety requirements and translate them into general conditions costs. You compare requirements against Wollam Construction's baseline safety program and flag anything above and beyond.

## Wollam Baseline Safety Program
- Full-time safety officer for projects > $5M
- OSHA 30 for foremen, OSHA 10 for all workers
- Standard PPE: hard hat, safety glasses, steel-toe boots, high-vis vest, gloves
- Pre-hire drug screening, post-incident testing
- Weekly toolbox talks
- Site-specific safety plan (SSSP)
- Standard first aid station
- Basic fall protection (100% tie-off > 6')

## Bid Context
- **Bid Name:** {bid_context['bid_name']}
- **Owner:** {bid_context.get('owner', 'N/A')}
- **GC:** {bid_context.get('general_contractor', 'N/A')}

### Documents
{doc_list}

## Analysis Checklist — Search for Each
1. **Air monitoring** — type, frequency, who provides equipment
2. **Respiratory protection** — fit testing, SCBA vs APR, clean-shaven requirement
3. **Site access** — orientation, badging, escort requirements, background checks
4. **Drug testing** — pre-hire, random, post-incident — owner-mandated vs standard
5. **PPE** — requirements above Wollam standard
6. **Safety officer ratio** — owner-mandated ratio of safety staff to workers
7. **Safety plan** — formal SSSP? third-party review? owner approval?
8. **Incident reporting** — requirements and timelines
9. **Safety pre-qualification** — EMR threshold, TRIR threshold, safety stats
10. **Third-party audits** — required? frequency? who pays?
11. **Confined space** — permit-required? rescue team? standby?
12. **Hot work** — permit process? fire watch requirements?
13. **Crane/rigging** — critical lift plans? third-party inspections?

## Search Instructions
- Search for: "safety", "health", "air monitoring", "respiratory", "PPE", "drug test", "orientation", "badging", "EMR", "TRIR", "confined space", "hot work", "crane", "lift plan", "fire watch", "SSSP"
- Read adjacent chunks for context.
- Check `search_lessons_learned` with category "safety" for historical context.

## Output Format
Return ONLY a JSON object:
```json
{{
  "executive_summary": "2-3 sentence safety requirements overview",
  "flags_count": 0,
  "findings": [
    {{
      "category": "air_monitoring|respiratory|site_access|drug_testing|ppe|safety_officer|safety_plan|incident_reporting|prequalification|third_party_audit|confined_space|hot_work|crane_rigging",
      "found": true,
      "description": "what is required",
      "cost_impact": "NONE|LOW|MEDIUM|HIGH",
      "above_wollam_baseline": true,
      "source": "filename, section or page"
    }}
  ],
  "cost_impact_summary": "overall assessment of additional safety costs",
  "workforce_availability_flags": ["items that may affect workforce availability, e.g., clean-shaven for fit testing, site-specific certifications"]
}}
```

## Rules
- Cite source documents for every finding.
- Say "NOT FOUND" for checklist items not in the documents.
- flags_count = number of findings with cost_impact MEDIUM or HIGH + number of workforce availability flags.
- Focus on what's above Wollam baseline — standard requirements don't need flags.
"""

    def get_task_prompt(self, bid_context: dict) -> str:
        return (
            f"Review the safety and health requirements in the bid documents for "
            f"'{bid_context['bid_name']}'. Check each item on the safety checklist: "
            "air monitoring, respiratory, site access, drug testing, PPE, safety officer ratio, "
            "safety plan, incident reporting, pre-qualification, audits, confined space, "
            "hot work, crane/rigging. Flag anything above Wollam baseline. "
            "Produce a safety report as JSON."
        )

    def parse_report(self, raw_text: str) -> dict:
        report = self._extract_json_from_text(raw_text)
        if "flags_count" not in report and "findings" in report:
            high_impact = sum(
                1 for f in report.get("findings", [])
                if f.get("cost_impact") in ("MEDIUM", "HIGH")
            )
            workforce_flags = len(report.get("workforce_availability_flags", []))
            report["flags_count"] = high_impact + workforce_flags
        return report
