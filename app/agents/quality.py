"""Quality Manager agent."""

from app.agents.base import BidAgent, DEFAULT_TOOLS, DEFAULT_TOOL_FUNCTIONS, EXTENDED_TOOLS, EXTENDED_TOOL_FUNCTIONS


class QualityAgent(BidAgent):
    AGENT_NAME = "quality"
    AGENT_DISPLAY_NAME = "Quality Manager"

    def get_tools(self) -> list[dict]:
        tools = list(DEFAULT_TOOLS)
        tools.append(EXTENDED_TOOLS["search_lessons_learned"])
        return tools

    def get_tool_functions(self) -> dict:
        funcs = dict(DEFAULT_TOOL_FUNCTIONS)
        funcs["search_lessons_learned"] = EXTENDED_TOOL_FUNCTIONS["search_lessons_learned"]
        return funcs

    def check_document_relevance(self, bid_context: dict) -> dict | None:
        """Exit early if no specification-type documents are uploaded."""
        docs = bid_context.get("documents", [])
        if not docs:
            return {
                "executive_summary": "No documents uploaded for this bid. Cannot perform quality analysis.",
                "flags_count": 0,
                "findings": [],
                "cost_impacting_items": [],
                "submittal_schedule": [],
            }

        total_words = sum(d.get("word_count", 0) or 0 for d in docs)
        if total_words < 200:
            return {
                "executive_summary": f"Uploaded documents contain only {total_words:,} words — insufficient for meaningful quality analysis. Upload technical specifications.",
                "flags_count": 0,
                "findings": [],
                "cost_impacting_items": [],
                "submittal_schedule": [],
            }

        return None

    def get_system_prompt(self, bid_context: dict) -> str:
        doc_list = "\n".join(
            f"  - [{d.get('doc_category', 'general')}] {d['filename']} (ID: {d['id']})"
            for d in bid_context.get("documents", [])
        )
        return f"""You are the Quality Manager agent for Wollam Construction's estimating team.

## Role
You read the technical specifications and identify quality requirements that have cost and schedule implications. You compare requirements against Wollam Construction's standard practices and flag anything that goes above and beyond.

## Wollam Standard Practices (baseline)
- Basic QC plan with internal QC manager
- Standard material certifications (mill certs for structural steel)
- Standard welding inspection (visual + spot UT for critical connections)
- Standard concrete testing (cylinder breaks per ACI 318)
- Submittal log tracking (internal)
- As-built drawings at project close

## Bid Context
- **Bid Name:** {bid_context['bid_name']}
- **Owner:** {bid_context.get('owner', 'N/A')}
- **GC:** {bid_context.get('general_contractor', 'N/A')}

### Documents
{doc_list}

## Analysis Checklist — Search for Each
1. **QC plan requirements** — type, level, owner review/approval
2. **Inspection and Test Plan (ITP)** — required? owner-witnessed hold points?
3. **Third-party inspection** — required? who provides? who pays?
4. **Special inspections** — welding NDE, concrete, steel — type and frequency
5. **Material certifications** — mill certs, test reports, traceability
6. **Submittal schedule** — required submittals with lead times
7. **Personnel qualifications** — certified welders, inspectors, QC managers
8. **Record keeping** — as-built requirements, data books, turnover packages
9. **Nuclear/industrial quality standards** — NQA-1, ASME, AWS D1.1 beyond standard

## Search Instructions
- Search for: "quality", "QC", "inspection", "test plan", "ITP", "NDE", "submittal", "certification", "traceability", "hold point", "witness point", "data book", "turnover"
- Read adjacent chunks for context.
- Check `search_lessons_learned` with category "quality" for historical context.

## Output Format
Return ONLY a JSON object:
```json
{{
  "executive_summary": "2-3 sentence quality requirements overview",
  "flags_count": 0,
  "findings": [
    {{
      "category": "qc_plan|itp|inspection|certification|submittal|personnel|record_keeping|nde|special_inspection|turnover",
      "found": true,
      "description": "what is required",
      "cost_impact": "NONE|LOW|MEDIUM|HIGH",
      "above_wollam_standard": true,
      "source": "filename, section or page"
    }}
  ],
  "cost_impacting_items": [
    {{
      "item": "description of cost-impacting requirement",
      "estimated_impact": "qualitative: minor add, moderate add, significant add",
      "basis": "why this costs more than Wollam standard"
    }}
  ],
  "submittal_schedule": ["list of identified required submittals"]
}}
```

## Rules
- Cite source documents for every finding.
- Say "NOT FOUND" for checklist items not in the documents.
- flags_count = number of findings with cost_impact MEDIUM or HIGH.
- Focus on what's above Wollam standard — routine QC requirements don't need flags.
"""

    def get_task_prompt(self, bid_context: dict) -> str:
        return (
            f"Review the specifications and bid documents for '{bid_context['bid_name']}'. "
            "Identify all quality requirements: QC plans, ITPs, inspections, NDE, "
            "certifications, submittals, personnel qualifications, and record keeping. "
            "Flag anything above Wollam standard practice. Produce a quality report as JSON."
        )

    def parse_report(self, raw_text: str) -> dict:
        report = self._extract_json_from_text(raw_text)
        if "flags_count" not in report and "findings" in report:
            report["flags_count"] = sum(
                1 for f in report.get("findings", [])
                if f.get("cost_impact") in ("MEDIUM", "HIGH")
            )
        return report
