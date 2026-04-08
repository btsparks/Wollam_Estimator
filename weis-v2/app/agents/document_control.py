"""Document Control Agent — analyzes bid document completeness and changes.

Produces a document index, identifies addendum changes and their impact,
and flags missing documents referenced in the package.
"""

from __future__ import annotations

from app.agents.base import BaseAgent


SYSTEM_PROMPT = """You are a Document Control Manager reviewing a construction bid package.

Your job:
1. Create a structured index of all documents reviewed, noting key sections in each
2. Identify addendum changes and their impact on scope/SOV items
3. Flag any documents that are referenced but missing from the package

Return your analysis as a JSON object with this exact structure:
{
  "documents_reviewed": <number>,
  "document_index": [
    {
      "filename": "...",
      "category": "spec|drawing|contract|bid_schedule|addendum_package|general",
      "sections": ["Section 03300 - Cast-in-Place Concrete", ...],
      "relevance_to_sov": ["Relates to SOV item 3", ...]
    }
  ],
  "addendum_changes": [
    {
      "addendum": <number>,
      "document": "filename",
      "changes": "Description of what changed",
      "affected_sov_items": ["3", "7"],
      "impact": "Brief description of scope/cost impact"
    }
  ],
  "missing_documents": ["No geotechnical report found", ...],
  "flags": ["List of any concerns or items needing attention"]
}

Rules:
- Be specific about section numbers and spec references
- Only flag documents as missing if they are explicitly referenced in other documents
- For addendum changes, focus on scope changes that affect pricing
- Return ONLY valid JSON — no markdown, no explanation
"""


class DocumentControlAgent(BaseAgent):
    name = "document_control"
    display_name = "Document Control Manager"
    version = "1.0"
    system_prompt = SYSTEM_PROMPT

    def _build_summary(self, report_json: dict) -> str:
        docs = report_json.get("documents_reviewed", 0)
        changes = len(report_json.get("addendum_changes", []))
        missing = len(report_json.get("missing_documents", []))
        flags = len(report_json.get("flags", []))

        parts = [f"{docs} documents indexed"]
        if changes:
            parts.append(f"{changes} addendum change(s)")
        if missing:
            parts.append(f"{missing} missing document(s)")
        if flags:
            parts.append(f"{flags} flag(s)")
        return ". ".join(parts) + "."

    def _assess_risk(self, report_json: dict) -> str:
        missing = len(report_json.get("missing_documents", []))
        flags = len(report_json.get("flags", []))
        total = missing + flags
        if total >= 5:
            return "high"
        elif total >= 2:
            return "medium"
        return "low"

    def _empty_report(self) -> dict:
        return {
            "documents_reviewed": 0,
            "document_index": [],
            "addendum_changes": [],
            "missing_documents": [],
            "flags": [],
        }
