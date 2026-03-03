"""Chief Estimator Brief agent — synthesizes all agent reports into one decision document."""

import json
from app.agents.base import BidAgent, DEFAULT_TOOLS, DEFAULT_TOOL_FUNCTIONS
from app import query


class ChiefEstimatorAgent(BidAgent):
    AGENT_NAME = "chief_estimator"
    AGENT_DISPLAY_NAME = "Chief Estimator Brief"

    def get_tools(self) -> list[dict]:
        tools = list(DEFAULT_TOOLS)
        tools.append({
            "name": "get_agent_reports",
            "description": (
                "Get all completed agent reports for the current bid. Returns summaries "
                "from Document Control, Legal, Quality, Safety, and Subcontract agents."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "bid_id": {
                        "type": "integer",
                        "description": "Bid ID. If omitted, uses the focus bid.",
                    },
                },
                "required": [],
            },
        })
        return tools

    def get_tool_functions(self) -> dict:
        funcs = dict(DEFAULT_TOOL_FUNCTIONS)
        funcs["get_agent_reports"] = self._get_agent_reports_for_tool
        return funcs

    @staticmethod
    def _get_agent_reports_for_tool(bid_id: int = None) -> list[dict]:
        """Get agent report summaries with full report data for synthesis."""
        if bid_id is None:
            focus = query.get_focus_bid()
            if focus:
                bid_id = focus["id"]
            else:
                return []

        reports = query.get_agent_reports(bid_id)
        results = []
        for r in reports:
            d = {
                "agent_name": r["agent_name"],
                "status": r["status"],
                "risk_rating": r.get("risk_rating"),
                "flags_count": r.get("flags_count", 0),
                "summary_text": r.get("summary_text", ""),
            }
            if r.get("report_json") and r["status"] == "complete":
                try:
                    d["report"] = json.loads(r["report_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(d)
        return results

    def check_document_relevance(self, bid_context: dict) -> dict | None:
        """Exit early if no agent reports are available to synthesize."""
        reports = query.get_agent_reports(bid_context["bid_id"])
        completed = [r for r in reports if r["status"] == "complete"]
        if not completed:
            return {
                "executive_summary": "No completed agent reports available to synthesize. Run the individual agents first (Document Control, Legal, Quality, Safety, Subcontract).",
                "go_no_go": None,
                "flags_count": 0,
                "top_risks": [],
                "cost_adders": [],
                "sub_packages": [],
                "missing_information": ["All agent reports — none have been run yet"],
                "recommended_actions": ["Run all 5 intelligence agents before generating the Chief Estimator Brief"],
            }
        return None

    def get_system_prompt(self, bid_context: dict) -> str:
        doc_list = "\n".join(
            f"  - [{d.get('doc_category', 'general')}] {d['filename']} (ID: {d['id']})"
            for d in bid_context.get("documents", [])
        )
        return f"""You are the Chief Estimator for Wollam Construction.

## Role
You synthesize all intelligence agent reports into a single executive decision document — the Chief Estimator Brief. This is the document that drives the bid/no-bid decision and summarizes everything the estimating team needs to know.

## Bid Context
- **Bid Name:** {bid_context['bid_name']}
- **Bid Number:** {bid_context.get('bid_number', 'N/A')}
- **Owner:** {bid_context.get('owner', 'N/A')}
- **GC:** {bid_context.get('general_contractor', 'N/A')}
- **Bid Date:** {bid_context.get('bid_date', 'N/A')}
- **Documents:** {bid_context['total_documents']} ({bid_context['total_words']:,} words)

### Documents
{doc_list}

## Instructions
1. Call `get_agent_reports` to get all completed agent analysis reports.
2. Review each agent's findings, risk ratings, and flags.
3. Synthesize into a unified brief with a clear recommendation.
4. If any critical information is missing, note it clearly.

## Output Format
Return ONLY a JSON object:
```json
{{{{
  "executive_summary": "3-5 sentence overview of this bid opportunity — scope, risk posture, and recommendation",
  "go_no_go": "GO|CONDITIONAL_GO|NO_GO",
  "go_no_go_rationale": "2-3 sentences explaining the recommendation",
  "flags_count": 0,
  "risk_rating": "LOW|MEDIUM|HIGH|DO_NOT_BID",
  "top_risks": [
    {{{{
      "risk": "description of risk",
      "source_agent": "which agent identified this",
      "severity": "LOW|MEDIUM|HIGH",
      "mitigation": "recommended mitigation"
    }}}}
  ],
  "cost_adders": [
    {{{{
      "item": "description of cost adder",
      "source_agent": "quality|safety|legal|subcontract",
      "estimated_impact": "qualitative impact description",
      "include_in_estimate": true
    }}}}
  ],
  "sub_packages": [
    {{{{
      "package": "package name",
      "estimated_scope": "brief scope description",
      "historical_subs": ["sub names from database"]
    }}}}
  ],
  "document_completeness": "COMPLETE|PARTIAL|INSUFFICIENT",
  "missing_information": ["list of critical missing items"],
  "key_dates": {{{{
    "bid_due": "date or NOT FOUND",
    "pre_bid_meeting": "date or NOT FOUND",
    "rfi_deadline": "date or NOT FOUND"
  }}}},
  "recommended_actions": ["prioritized list of next steps for the estimating team"],
  "agent_coverage": [
    {{{{
      "agent": "agent name",
      "status": "complete|error|pending",
      "key_finding": "one-line summary of most important finding"
    }}}}
  ]
}}}}
```

## Rules
- Base your brief ENTIRELY on the agent reports — don't re-analyze documents.
- If an agent hasn't run or errored, note it as a gap.
- Be direct and actionable — estimators need decisions, not academic analysis.
- go_no_go: GO = proceed with bid, CONDITIONAL_GO = proceed but address specific items first, NO_GO = do not bid.
- flags_count = total critical flags across all agents.
- Prioritize risks by severity and cost impact.
"""

    def get_task_prompt(self, bid_context: dict) -> str:
        return (
            f"Synthesize all agent reports for the '{bid_context['bid_name']}' bid into "
            "a Chief Estimator Brief. Call `get_agent_reports` to retrieve the reports, "
            "then produce your synthesis as JSON. Include a go/no-go recommendation, "
            "top risks, cost adders, sub packages, and recommended next steps."
        )

    def parse_report(self, raw_text: str) -> dict:
        report = self._extract_json_from_text(raw_text)
        if "flags_count" not in report:
            report["flags_count"] = len(report.get("top_risks", []))
        if "risk_rating" not in report:
            # Derive from go_no_go
            go = report.get("go_no_go", "")
            if go == "NO_GO":
                report["risk_rating"] = "DO_NOT_BID"
            elif go == "CONDITIONAL_GO":
                report["risk_rating"] = "HIGH"
            else:
                report["risk_rating"] = "MEDIUM"
        return report
