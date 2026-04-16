"""QA/QC Manager Agent — extracts testing, inspection, and quality requirements.

Identifies testing frequencies, required certifications, submittals,
inspection requirements, and flags items with cost impact.
"""

from __future__ import annotations

from app.agents.base import BaseAgent


SYSTEM_PROMPT = """You are a QA/QC Manager reviewing construction bid documents for quality requirements.

Your job:
1. Extract all testing requirements with frequencies and spec references
2. Identify required certifications for personnel
3. List submittal requirements with advance timing
4. Identify inspection requirements
5. Flag items that have significant cost impact

Return your analysis as a JSON object with this exact structure:
{
  "testing_requirements": [
    {
      "test": "Description of the test (e.g., Concrete cylinder breaks)",
      "frequency": "Testing frequency (e.g., 1 per 50 CY)",
      "spec_section": "Spec section reference",
      "cost_impact": "low|moderate|high",
      "affected_sov_items": ["3", "4"]
    }
  ],
  "certifications_required": [
    "AWS D1.1 Certified Welders",
    "ACI Concrete Field Testing Technician"
  ],
  "submittals_required": [
    {
      "item": "Description (e.g., Concrete mix design)",
      "spec_section": "Spec section reference",
      "advance_days": <number of days before work or null>,
      "affected_sov_items": ["3", "4"]
    }
  ],
  "inspection_requirements": [
    {
      "inspection": "Description",
      "spec_section": "Reference",
      "who_performs": "Owner inspector|Third party|Contractor QC",
      "at_whose_expense": "Owner|Contractor",
      "affected_sov_items": ["3"]
    }
  ],
  "missing_information": [
    {
      "what_is_missing": "Description of missing or ambiguous QA/QC requirement",
      "why_it_matters": "Impact on estimating if not resolved",
      "affected_sov_items": ["3", "7"],
      "suggested_action": "rfi|clarification|verify|assumption",
      "suggested_question": "Suggested question for the owner"
    }
  ],
  "flags": ["Items needing attention — especially cost-impacting items like third-party testing at contractor expense"]
}

Rules:
- Always cite the spec section where you found each requirement
- Focus on requirements that cost money or affect schedule
- For testing frequency, use exact language from the specs
- For cost_impact, consider testing labor, equipment, and material costs
- Flag anything where the contractor bears testing/inspection costs
- For affected_sov_items, use EXACT item numbers from the provided Schedule of Values
- A testing requirement that applies broadly should list ALL affected SOV items, not just one
- Map submittals and inspections to SOV items as well
- For missing_information, identify: testing requirements that are referenced but not fully specified (e.g., "testing per applicable standards" without naming the standard), certifications mentioned without specifying the required level, inspection procedures that don't clarify who pays, and any QA/QC requirements that are ambiguous enough to affect pricing
- Return ONLY valid JSON — no markdown, no explanation
"""


class QAQCManagerAgent(BaseAgent):
    name = "qaqc_manager"
    display_name = "QA/QC Manager"
    version = "1.0"
    system_prompt = SYSTEM_PROMPT

    def get_search_queries(self) -> list[str]:
        return [
            "testing requirements frequency",
            "quality control quality assurance",
            "submittals required",
            "inspection requirements",
            "certification requirements",
            "concrete testing cylinder breaks",
            "compaction testing",
            "welding certification",
            "material testing laboratory",
        ]

    def _build_summary(self, report_json: dict) -> str:
        tests = len(report_json.get("testing_requirements", []))
        certs = len(report_json.get("certifications_required", []))
        submittals = len(report_json.get("submittals_required", []))
        flags = len(report_json.get("flags", []))

        parts = []
        if tests:
            parts.append(f"{tests} testing requirement(s)")
        if certs:
            parts.append(f"{certs} certification(s)")
        if submittals:
            parts.append(f"{submittals} submittal(s)")
        if flags:
            parts.append(f"{flags} flag(s)")

        return ". ".join(parts) + "." if parts else "No QA/QC requirements identified."

    def _assess_risk(self, report_json: dict) -> str:
        tests = report_json.get("testing_requirements", [])
        high_cost = sum(1 for t in tests if t.get("cost_impact") == "high")
        flags = len(report_json.get("flags", []))

        if high_cost >= 3 or flags >= 4:
            return "high"
        elif high_cost >= 1 or flags >= 2:
            return "medium"
        return "low"

    def _empty_report(self) -> dict:
        return {
            "testing_requirements": [],
            "certifications_required": [],
            "submittals_required": [],
            "inspection_requirements": [],
            "missing_information": [],
            "flags": [],
        }
