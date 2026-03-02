"""BidAgent base class — tool-use loop for bid document review agents."""

import json
import time
from abc import ABC, abstractmethod
from anthropic import Anthropic
from app.config import ANTHROPIC_API_KEY
from app import query

MODEL = "claude-sonnet-4-20250514"
MAX_TOOL_ROUNDS = 8
MAX_TOKENS = 4096

# ---------------------------------------------------------------------------
# Default Tool Definitions (all agents get these)
# ---------------------------------------------------------------------------

DEFAULT_TOOLS = [
    {
        "name": "search_bid_documents",
        "description": (
            "Search bid document text for keywords. Returns matching chunks with "
            "document filename, category, and section heading. Use targeted keywords "
            "— not full sentences."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "Keywords to search for in bid document text.",
                },
                "bid_id": {
                    "type": "integer",
                    "description": "Bid ID. If omitted, uses the focus bid.",
                },
                "doc_category": {
                    "type": "string",
                    "description": "Filter by category: rfp, addendum, specification, scope, bid_form, schedule, general",
                },
            },
            "required": ["query_text"],
        },
    },
    {
        "name": "read_document_chunks",
        "description": (
            "Read sequential chunks from bid documents. Use this to read through "
            "document sections in order (e.g., read the first 5 chunks of a spec, "
            "then the next 5). Max 10 chunks per call."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "bid_id": {
                    "type": "integer",
                    "description": "Bid ID. If omitted, uses the focus bid.",
                },
                "document_id": {
                    "type": "integer",
                    "description": "Specific document ID to read. If omitted, reads all docs.",
                },
                "start_chunk": {
                    "type": "integer",
                    "description": "Starting chunk index (0-based). Default 0.",
                },
                "max_chunks": {
                    "type": "integer",
                    "description": "Number of chunks to return (max 10). Default 5.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_bid_overview",
        "description": (
            "Get bid metadata: name, owner, GC, bid date, document count, "
            "word count, categories."
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
    },
    {
        "name": "get_bid_documents",
        "description": (
            "Get the list of uploaded documents for a bid, with filename, category, "
            "label, word count, and extraction status."
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
    },
]

# Default tool function mapping
DEFAULT_TOOL_FUNCTIONS = {
    "search_bid_documents": query.search_bid_documents,
    "read_document_chunks": query.read_document_chunks,
    "get_bid_overview": query.get_bid_overview,
    "get_bid_documents": query.get_bid_documents_list,
}

# Extended tools some agents can add
EXTENDED_TOOLS = {
    "search_lessons_learned": {
        "name": "search_lessons_learned",
        "description": (
            "Search historical lessons learned from past projects. "
            "Filter by category (estimating, production_variance, scope_gap, "
            "material, design, subcontractor), discipline, severity, or keyword."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category filter."},
                "discipline": {"type": "string", "description": "Discipline filter."},
                "severity": {"type": "string", "description": "HIGH, MEDIUM, or LOW."},
                "keyword": {"type": "string", "description": "Keyword to search."},
            },
            "required": [],
        },
    },
    "search_subcontractors": {
        "name": "search_subcontractors",
        "description": (
            "Search historical subcontractor records: name, scope, contract/actual amounts, "
            "performance rating."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Sub name (partial match)."},
                "scope": {"type": "string", "description": "Scope description (partial match)."},
                "discipline": {"type": "string", "description": "Discipline filter."},
            },
            "required": [],
        },
    },
    "search_material_costs": {
        "name": "search_material_costs",
        "description": (
            "Search historical material cost records: type, vendor, unit cost, total cost."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "material": {"type": "string", "description": "Material type to search."},
                "discipline": {"type": "string", "description": "Discipline filter."},
                "vendor": {"type": "string", "description": "Vendor name to search."},
            },
            "required": [],
        },
    },
}

EXTENDED_TOOL_FUNCTIONS = {
    "search_lessons_learned": query.search_lessons_learned,
    "search_subcontractors": query.search_subcontractors,
    "search_material_costs": query.search_material_costs,
}


# ---------------------------------------------------------------------------
# BidAgent Base Class
# ---------------------------------------------------------------------------


class BidAgent(ABC):
    """Abstract base for bid document review agents.

    Each agent gets a system prompt, a set of tools, and a task prompt.
    The run() method executes a full tool-use loop and saves the report.
    """

    AGENT_NAME: str = ""
    AGENT_DISPLAY_NAME: str = ""
    AGENT_VERSION: str = "1.0"

    @abstractmethod
    def get_system_prompt(self, bid_context: dict) -> str:
        """Return the agent's system prompt with bid context injected."""

    @abstractmethod
    def get_task_prompt(self, bid_context: dict) -> str:
        """Return the task message sent as the user prompt."""

    @abstractmethod
    def parse_report(self, raw_text: str) -> dict:
        """Parse the agent's final text response into a structured report dict."""

    def get_tools(self) -> list[dict]:
        """Return tool definitions. Override to add agent-specific tools."""
        return list(DEFAULT_TOOLS)

    def get_tool_functions(self) -> dict:
        """Return tool name → function mapping. Override to add more."""
        return dict(DEFAULT_TOOL_FUNCTIONS)

    def _build_bid_context(self, bid_id: int) -> dict:
        """Gather bid metadata and document list for prompt injection."""
        overview = query.get_bid_overview(bid_id)
        docs = query.get_bid_documents_list(bid_id)
        return {
            "bid_id": bid_id,
            "bid_name": overview.get("bid_name", "Unknown"),
            "bid_number": overview.get("bid_number", ""),
            "owner": overview.get("owner", ""),
            "general_contractor": overview.get("general_contractor", ""),
            "bid_date": overview.get("bid_date", ""),
            "total_documents": overview.get("total_documents", 0),
            "total_chunks": overview.get("total_chunks", 0),
            "total_words": overview.get("total_words", 0),
            "categories": overview.get("categories", []),
            "documents": docs,
        }

    def _execute_tool(self, name: str, input_args: dict) -> str:
        """Execute a tool call and return JSON string result."""
        funcs = self.get_tool_functions()
        func = funcs.get(name)
        if not func:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            result = func(**input_args)
            return json.dumps(result, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def run(self, bid_id: int, progress_callback=None) -> dict:
        """Execute the full agent workflow.

        1. Build bid context
        2. Create pending report in DB
        3. Run tool-use loop with Claude
        4. Parse response into structured report
        5. Save report to DB

        Args:
            bid_id: The bid to analyze.
            progress_callback: Optional callable(message: str) for progress updates.

        Returns:
            The final report dict.
        """
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not set.")

        start_time = time.time()
        total_tokens = 0

        # Create pending report
        query.upsert_agent_report(
            bid_id, self.AGENT_NAME,
            agent_version=self.AGENT_VERSION,
            status="running",
        )

        if progress_callback:
            progress_callback(f"{self.AGENT_DISPLAY_NAME}: Building context...")

        try:
            bid_context = self._build_bid_context(bid_id)
            system_prompt = self.get_system_prompt(bid_context)
            task_prompt = self.get_task_prompt(bid_context)
            tools = self.get_tools()

            client = Anthropic(api_key=ANTHROPIC_API_KEY)
            messages = [{"role": "user", "content": task_prompt}]

            if progress_callback:
                progress_callback(f"{self.AGENT_DISPLAY_NAME}: Analyzing documents...")

            # Tool-use loop
            for round_num in range(MAX_TOOL_ROUNDS):
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=system_prompt,
                    tools=tools,
                    messages=messages,
                )

                total_tokens += response.usage.input_tokens + response.usage.output_tokens
                messages.append({"role": "assistant", "content": response.content})

                # Check for tool use
                tool_uses = [b for b in response.content if b.type == "tool_use"]
                if not tool_uses:
                    break

                if progress_callback:
                    progress_callback(
                        f"{self.AGENT_DISPLAY_NAME}: Searching documents "
                        f"(round {round_num + 1}/{MAX_TOOL_ROUNDS})..."
                    )

                # Execute tools
                tool_results = []
                for tool_block in tool_uses:
                    result = self._execute_tool(tool_block.name, tool_block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": result,
                    })

                messages.append({"role": "user", "content": tool_results})

            # Extract final text
            text_parts = [b.text for b in response.content if hasattr(b, "text")]
            raw_text = "\n".join(text_parts) if text_parts else ""

            if progress_callback:
                progress_callback(f"{self.AGENT_DISPLAY_NAME}: Building report...")

            # Parse into structured report
            report = self.parse_report(raw_text)
            duration = time.time() - start_time

            # Save completed report
            summary = report.get("executive_summary", "")[:500]
            flags = report.get("flags_count", 0)
            risk = report.get("risk_rating")

            query.upsert_agent_report(
                bid_id, self.AGENT_NAME,
                agent_version=self.AGENT_VERSION,
                status="complete",
                report_json=json.dumps(report),
                summary_text=summary,
                risk_rating=risk,
                flags_count=flags,
                input_doc_count=bid_context["total_documents"],
                input_chunk_count=bid_context["total_chunks"],
                tokens_used=total_tokens,
                duration_seconds=round(duration, 1),
                error_message=None,
            )

            if progress_callback:
                progress_callback(f"{self.AGENT_DISPLAY_NAME}: Complete.")

            return report

        except Exception as e:
            duration = time.time() - start_time
            query.upsert_agent_report(
                bid_id, self.AGENT_NAME,
                agent_version=self.AGENT_VERSION,
                status="error",
                error_message=str(e)[:500],
                duration_seconds=round(duration, 1),
                tokens_used=total_tokens,
            )
            raise

    @staticmethod
    def _extract_json_from_text(text: str) -> dict:
        """Extract a JSON object from agent response text.

        Handles both raw JSON and JSON within markdown code fences.
        """
        # Try the whole text as JSON
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass

        # Try to extract from code fences
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Last resort: find first { to last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return {"parse_error": "Could not extract JSON from agent response", "raw_text": text[:2000]}
