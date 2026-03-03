"""Document Control / Bid Coordinator agent."""

import json
from app.agents.base import BidAgent
from app import query


class DocumentControlAgent(BidAgent):
    AGENT_NAME = "document_control"
    AGENT_DISPLAY_NAME = "Document Control"

    def _get_previous_report(self, bid_id: int) -> dict | None:
        """Get the previous Document Control report for change detection."""
        report_row = query.get_agent_report(bid_id, self.AGENT_NAME)
        if report_row and report_row.get("report_json") and report_row["status"] == "complete":
            try:
                return json.loads(report_row["report_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    def get_system_prompt(self, bid_context: dict) -> str:
        doc_list = "\n".join(
            f"  - [{d.get('doc_category', 'general')}] {d['filename']} "
            f"({d.get('word_count', 0):,} words, ID: {d['id']})"
            for d in bid_context.get("documents", [])
        )
        return f"""You are the Document Control / Bid Coordinator agent for Wollam Construction's estimating team.

## Role
You manage the bid document set. Your job is to review all uploaded documents, create a master document register, assess completeness, identify missing documents, and extract key dates.

## Bid Context
- **Bid Name:** {bid_context['bid_name']}
- **Bid Number:** {bid_context.get('bid_number', 'N/A')}
- **Owner:** {bid_context.get('owner', 'N/A')}
- **General Contractor:** {bid_context.get('general_contractor', 'N/A')}
- **Bid Date:** {bid_context.get('bid_date', 'N/A')}
- **Documents:** {bid_context['total_documents']} ({bid_context['total_words']:,} words)

### Document List
{doc_list}

## Instructions
1. Use `get_bid_documents` to see the full document list.
2. Use `read_document_chunks` to scan through each document and understand its contents.
3. Use `search_bid_documents` for specific items like dates, deadlines, or scope references.
4. Classify each document and assess what's present vs missing.
5. Extract any key dates (bid due, pre-bid meeting, RFI deadline, etc.).

## Output Format
Return ONLY a JSON object (no other text) with this exact structure:
```json
{{
  "executive_summary": "2-3 sentence overview of the document set",
  "flags_count": 0,
  "document_register": [
    {{
      "filename": "string",
      "category": "rfp|specification|addendum|scope|bid_form|schedule|general",
      "word_count": 0,
      "key_contents": "brief description of what this document covers"
    }}
  ],
  "completeness_assessment": {{
    "has_rfp": true,
    "has_specs": false,
    "has_drawings_list": false,
    "has_schedule": false,
    "has_bid_form": false,
    "has_contract_terms": false,
    "has_safety_requirements": false,
    "has_quality_requirements": false,
    "has_insurance_requirements": false
  }},
  "missing_documents": ["list of documents that appear to be missing"],
  "recommended_actions": ["list of recommended next steps"],
  "key_dates": {{
    "bid_due": "date or NOT FOUND",
    "pre_bid_meeting": "date or NOT FOUND",
    "rfi_deadline": "date or NOT FOUND",
    "site_visit": "date or NOT FOUND",
    "other": []
  }}
}}
```

## Change Log (if re-running)
If a previous report existed, include a `change_log` in your JSON output:
```json
"change_log": {{
  "documents_added": ["list of new documents since last run"],
  "documents_removed": ["list of documents no longer present"],
  "documents_changed": ["list of documents that appear to have been updated"],
  "affected_agents": ["list of agent names that should re-run based on changes: legal, quality, safety, subcontract"],
  "change_summary": "1-2 sentence summary of what changed"
}}
```
If this is the first run (no previous report), omit `change_log` from your output.

## Rules
- Cite source documents for every finding.
- Say "NOT FOUND" when something is not present — never guess.
- flags_count = number of missing critical documents + number of urgent actions needed.
"""

    def get_task_prompt(self, bid_context: dict) -> str:
        base_prompt = (
            f"Review all uploaded documents for the '{bid_context['bid_name']}' bid. "
            "Create a document register, assess completeness, identify missing documents, "
            "and extract key dates. Return your analysis as a JSON report."
        )

        # Include previous report context for change detection
        prev_report = self._get_previous_report(bid_context["bid_id"])
        if prev_report:
            prev_docs = prev_report.get("document_register", [])
            prev_filenames = [d.get("filename", "") for d in prev_docs]
            base_prompt += (
                f"\n\nIMPORTANT: This is a RE-RUN. The previous report covered these documents: "
                f"{', '.join(prev_filenames)}. "
                "Compare the current document set against this previous list and include a "
                "`change_log` section in your output documenting what's new, removed, or changed. "
                "Also indicate which other agents (legal, quality, safety, subcontract) should "
                "re-run based on what changed."
            )

        return base_prompt

    def parse_report(self, raw_text: str) -> dict:
        report = self._extract_json_from_text(raw_text)
        # Ensure flags_count is set
        if "flags_count" not in report and "missing_documents" in report:
            report["flags_count"] = len(report.get("missing_documents", []))
        return report
