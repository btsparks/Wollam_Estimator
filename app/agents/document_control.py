"""Document Control / Bid Coordinator agent."""

from app.agents.base import BidAgent


class DocumentControlAgent(BidAgent):
    AGENT_NAME = "document_control"
    AGENT_DISPLAY_NAME = "Document Control"

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

## Rules
- Cite source documents for every finding.
- Say "NOT FOUND" when something is not present — never guess.
- flags_count = number of missing critical documents + number of urgent actions needed.
"""

    def get_task_prompt(self, bid_context: dict) -> str:
        return (
            f"Review all uploaded documents for the '{bid_context['bid_name']}' bid. "
            "Create a document register, assess completeness, identify missing documents, "
            "and extract key dates. Return your analysis as a JSON report."
        )

    def parse_report(self, raw_text: str) -> dict:
        report = self._extract_json_from_text(raw_text)
        # Ensure flags_count is set
        if "flags_count" not in report and "missing_documents" in report:
            report["flags_count"] = len(report.get("missing_documents", []))
        return report
