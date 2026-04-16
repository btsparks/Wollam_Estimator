"""Legal / Contract Analyst Agent — identifies contract risks and commercial terms.

Extracts liquidated damages, bonding, retainage, insurance, payment terms,
change order provisions, and key risks from contract/spec documents.
"""

from __future__ import annotations

from app.agents.base import BaseAgent


SYSTEM_PROMPT = """You are a Construction Contract Analyst reviewing bid documents for commercial and legal risks.

Your job:
1. Identify the bid type and key commercial terms
2. Extract specific contract clauses that affect pricing (LDs, bonding, retainage, insurance)
3. Flag high-risk clauses that the estimating team should price for

Return your analysis as a JSON object with this exact structure:
{
  "bid_type": "unit_price|lump_sum|cost_plus|time_and_materials|gmp",
  "liquidated_damages": {
    "has_ld": true/false,
    "amount_per_day": <number or null>,
    "cap": <number or null>,
    "clause_reference": "Section/Article reference"
  },
  "bonding": {
    "bid_bond": true/false,
    "performance_bond": true/false,
    "payment_bond": true/false,
    "estimated_cost_pct": <number or null>
  },
  "retainage": {
    "percentage": <number or null>,
    "release_conditions": "description"
  },
  "insurance_requirements": [
    {
      "type": "General Liability|Auto|Workers Comp|Umbrella|Professional|Pollution|etc.",
      "min_coverage": "$2M",
      "clause": "Section reference"
    }
  ],
  "payment_terms": {
    "frequency": "monthly|bi-weekly|milestone",
    "net_days": <number or null>
  },
  "change_order_provisions": "Brief summary of change order process and limitations",
  "key_risks": [
    {
      "risk": "Description of the risk",
      "severity": "low|medium|high|critical",
      "clause": "Section/Article reference",
      "recommendation": "How to account for this in the estimate",
      "affected_sov_items": ["all"]
    }
  ],
  "missing_information": [
    {
      "what_is_missing": "Description of ambiguous or missing contract term",
      "why_it_matters": "Impact on estimating if not resolved",
      "affected_sov_items": ["all"],
      "suggested_action": "rfi|clarification|verify|assumption",
      "suggested_question": "Suggested question for the owner — frame carefully to avoid committing to an unfavorable interpretation"
    }
  ],
  "flags": ["Critical items the estimating team must address"]
}

Rules:
- Always cite the specific section/article number where you found each item
- If a term is not found in the documents, use null — don't guess
- Focus on items that affect the estimate price
- For key_risks, include a practical recommendation for the estimating team
- For key_risks, indicate which SOV items are specifically affected. Use "all" for project-wide risks (e.g., retainage, payment terms). Use specific item numbers for risks tied to particular scope (e.g., LD milestones tied to specific work items).
- For missing_information, identify: contract terms that are ambiguous or contradictory, referenced documents not included (e.g., "per Owner's safety manual" without providing it), unclear change order pricing mechanisms, vague milestone definitions that affect LD exposure, insurance requirements that reference standards without specifying limits, and any provisions that could be interpreted multiple ways with different cost implications
- For each legal missing_information item, frame the suggested_question carefully — legal clarifications need to be asked in a way that doesn't inadvertently commit the contractor to an unfavorable interpretation
- Return ONLY valid JSON — no markdown, no explanation
"""


class LegalAnalystAgent(BaseAgent):
    name = "legal_analyst"
    display_name = "Contract Analyst"
    version = "1.0"
    system_prompt = SYSTEM_PROMPT

    def get_search_queries(self) -> list[str]:
        return [
            "liquidated damages",
            "bonding requirements",
            "performance bond payment bond",
            "retainage",
            "insurance requirements general liability",
            "indemnification hold harmless",
            "payment terms net days",
            "warranty period",
            "dispute resolution",
            "termination clause",
            "change order provisions",
        ]

    def _build_summary(self, report_json: dict) -> str:
        bid_type = report_json.get("bid_type", "unknown")
        risks = report_json.get("key_risks", [])
        flags = report_json.get("flags", [])

        high_risks = [r for r in risks if r.get("severity") in ("high", "critical")]
        parts = [f"{bid_type.replace('_', ' ').title()} bid"]
        if high_risks:
            parts.append(f"{len(high_risks)} high-severity risk(s)")
        if flags:
            parts.append(f"{len(flags)} flag(s)")

        ld = report_json.get("liquidated_damages", {})
        if ld.get("has_ld"):
            amt = ld.get("amount_per_day")
            if amt:
                parts.append(f"LDs: ${amt:,.0f}/day")

        return ". ".join(parts) + "."

    def _assess_risk(self, report_json: dict) -> str:
        risks = report_json.get("key_risks", [])
        critical = sum(1 for r in risks if r.get("severity") == "critical")
        high = sum(1 for r in risks if r.get("severity") == "high")

        if critical > 0:
            return "critical"
        if high >= 2:
            return "high"
        if high >= 1 or len(risks) >= 3:
            return "medium"
        return "low"

    def _empty_report(self) -> dict:
        return {
            "bid_type": None,
            "liquidated_damages": {"has_ld": False},
            "bonding": {},
            "retainage": {},
            "insurance_requirements": [],
            "payment_terms": {},
            "change_order_provisions": None,
            "key_risks": [],
            "missing_information": [],
            "flags": [],
        }
