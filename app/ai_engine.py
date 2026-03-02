"""WEIS AI Query Engine.

Uses Claude API with tool use to translate natural language questions
into database queries and format responses with source citations.
"""

import json
from anthropic import Anthropic
from app.config import ANTHROPIC_API_KEY
from app import query

# ---------------------------------------------------------------------------
# Tool Definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "search_unit_costs",
        "description": (
            "Search for unit cost rates (labor rates, material costs, recommended estimating rates). "
            "Use this when the user asks about costs per unit, MH/unit rates, $/unit rates, "
            "or recommended rates for specific activities. Examples: 'wall forming rate', "
            "'concrete cost per CY', 'pipe support labor'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity": {
                    "type": "string",
                    "description": "Activity name to search for (partial match). Examples: 'wall form', 'grout', 'excavation', 'flanged'"
                },
                "discipline": {
                    "type": "string",
                    "description": "Discipline filter. Use codes: CONCRETE, EARTHWORK, STEEL, PIPING, MECHANICAL, ELECTRICAL, BUILDING, GCONDITIONS"
                },
                "unit": {
                    "type": "string",
                    "description": "Unit type filter. Examples: 'MH/SF', '$/CY', 'MH/EA', '$/TON'"
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_cost_codes",
        "description": (
            "Search for cost code records with budget vs actual costs and manhours. "
            "Use this when the user asks about specific cost codes, budget vs actual performance, "
            "or wants to see the breakdown of costs within a discipline."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cost_code": {
                    "type": "string",
                    "description": "Cost code number (partial match). Examples: '23' for all concrete codes, '2340' for specific code"
                },
                "description": {
                    "type": "string",
                    "description": "Description to search (partial match). Examples: 'wall', 'pour', 'excavation'"
                },
                "discipline": {
                    "type": "string",
                    "description": "Discipline filter"
                },
                "over_budget_only": {
                    "type": "boolean",
                    "description": "If true, only return cost codes that went over budget"
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_production_rates",
        "description": (
            "Search for production rates (output per hour/shift). "
            "Use this when the user asks about production speed, CY/hour, tons/shift, "
            "or how fast work was completed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity": {
                    "type": "string",
                    "description": "Activity to search for. Examples: 'excavation', 'fill', 'formwork', 'erection'"
                },
                "discipline": {
                    "type": "string",
                    "description": "Discipline filter"
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_crew_configs",
        "description": (
            "Search for crew configurations (crew composition, equipment, size). "
            "Use this when the user asks about crew makeup, how many people on a crew, "
            "what equipment was used, or staffing for specific activities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity": {
                    "type": "string",
                    "description": "Activity to search for. Examples: 'excavation', 'wall', 'mat pour', 'pipe'"
                },
                "discipline": {
                    "type": "string",
                    "description": "Discipline filter"
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_material_costs",
        "description": (
            "Search for material cost records (vendor, unit cost, total cost). "
            "Use this when the user asks about material prices, vendor information, "
            "or what materials cost on a project."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "material": {
                    "type": "string",
                    "description": "Material type to search. Examples: 'concrete', 'steel', 'pipe', 'rebar', 'grout'"
                },
                "discipline": {
                    "type": "string",
                    "description": "Discipline filter"
                },
                "vendor": {
                    "type": "string",
                    "description": "Vendor name to search. Examples: 'Rhine', 'Geneva', 'For-Shor'"
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_subcontractors",
        "description": (
            "Search for subcontractor records (name, scope, contract/actual amounts). "
            "Use this when the user asks about subs, subcontractors, who did specific work, "
            "or subcontract costs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Subcontractor name (partial match). Examples: 'Champion', 'J&M', 'Hunt', 'Terracon'"
                },
                "scope": {
                    "type": "string",
                    "description": "Scope description (partial match). Examples: 'rebar', 'electrical', 'survey', 'testing'"
                },
                "discipline": {
                    "type": "string",
                    "description": "Discipline filter"
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_lessons_learned",
        "description": (
            "Search for lessons learned from completed projects. "
            "Use this when the user asks about lessons, what went wrong, what to watch out for, "
            "recommendations, or past mistakes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category filter: estimating, production_variance, scope_gap, material, design, subcontractor"
                },
                "discipline": {
                    "type": "string",
                    "description": "Discipline filter"
                },
                "severity": {
                    "type": "string",
                    "description": "Severity filter: HIGH, MEDIUM, LOW"
                },
                "keyword": {
                    "type": "string",
                    "description": "Keyword to search in title and description. Examples: 'grout', 'slope', 'training'"
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_benchmark_rates",
        "description": (
            "Search for benchmark rates (compiled reference rates across projects). "
            "Use this when the user asks for benchmark or reference rates, typical ranges, "
            "or what to use for estimating."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity": {
                    "type": "string",
                    "description": "Activity to search for"
                },
                "discipline": {
                    "type": "string",
                    "description": "Discipline code filter"
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_project_summary",
        "description": (
            "Get project-level summary data (total cost, MH, CPI, margin, dates). "
            "Use this when the user asks about overall project performance, total cost, "
            "or general project information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_number": {
                    "type": "string",
                    "description": "Job number. Example: '8553'"
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_discipline_summary",
        "description": (
            "Get discipline-level breakdown (cost and MH by discipline). "
            "Use this when the user asks about cost breakdown by discipline, "
            "which disciplines were over/under budget, or discipline-level performance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_number": {
                    "type": "string",
                    "description": "Job number. Example: '8553'"
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_gc_breakdown",
        "description": (
            "Get general conditions cost breakdown (management, safety, survey, QC, insurance, etc.). "
            "Use this when the user asks about general conditions, overhead, GC percentage, "
            "or specific GC line items."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_number": {
                    "type": "string",
                    "description": "Job number. Example: '8553'"
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_database_overview",
        "description": (
            "Get a summary of all data available in the database (projects, record counts, disciplines). "
            "Use this when the user asks what data is available, what projects are in the system, "
            "or for a general status check."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # --- Active Bid Document Tools (Phase 2.4) ---
    {
        "name": "search_bid_documents",
        "description": (
            "Search the text of uploaded bid documents (RFPs, specs, addenda, scope docs) for keywords. "
            "Use this when the user asks about bid scope, RFP requirements, spec details, "
            "or anything about the current bid documents. "
            "Defaults to the focus bid if no bid_id is specified."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "Keywords to search for in bid document text. Examples: 'concrete', 'pipe support spacing', 'liquidated damages'"
                },
                "bid_id": {
                    "type": "integer",
                    "description": "Specific bid ID to search. If omitted, searches the focus bid."
                },
                "doc_category": {
                    "type": "string",
                    "description": "Filter by document category: rfp, addendum, specification, scope, bid_form, schedule, general"
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
            "Get an overview of a bid's uploaded documents: document count, categories, total word count. "
            "Use this when the user asks what documents are uploaded for a bid, or for bid status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "bid_id": {
                    "type": "integer",
                    "description": "Bid ID to get overview for. If omitted, uses the focus bid."
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_active_bids",
        "description": (
            "List all active bids with their status, owner, GC, and document count. "
            "Use this when the user asks what bids are in the system or wants to see all active bids."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

# ---------------------------------------------------------------------------
# Tool Executor
# ---------------------------------------------------------------------------

TOOL_FUNCTIONS = {
    "search_unit_costs": query.search_unit_costs,
    "search_cost_codes": query.search_cost_codes,
    "search_production_rates": query.search_production_rates,
    "search_crew_configs": query.search_crew_configs,
    "search_material_costs": query.search_material_costs,
    "search_subcontractors": query.search_subcontractors,
    "search_lessons_learned": query.search_lessons_learned,
    "search_benchmark_rates": query.search_benchmark_rates,
    "get_project_summary": query.get_project_summary,
    "get_discipline_summary": query.get_discipline_summary,
    "get_gc_breakdown": query.get_gc_breakdown,
    "get_database_overview": query.get_database_overview,
    # Phase 2.4 — Active Bid Documents
    "search_bid_documents": query.search_bid_documents,
    "read_document_chunks": query.read_document_chunks,
    "get_bid_overview": query.get_bid_overview,
    "list_active_bids": lambda: query.get_active_bids(),
}


def execute_tool(name: str, input_args: dict) -> str:
    """Execute a tool and return JSON string result."""
    func = TOOL_FUNCTIONS.get(name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = func(**input_args)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """You are WEIS (Wollam Estimating Intelligence System), an AI assistant for Wollam Construction, a Utah-based industrial heavy civil contractor.

Your job is to answer questions about historical job cost data from completed projects AND active bid documents. You have access to a database containing unit costs, production rates, crew configurations, material costs, subcontractor records, lessons learned, benchmark rates, and uploaded bid documents (RFPs, specs, addenda).

## Rules

1. ALWAYS cite your source: include the job number, discipline, and cost code when available.
2. ALWAYS include a confidence level:
   - HIGH: Multiple data points or validated actual data from completed projects
   - MEDIUM: Single project source, validated data
   - LOW: Limited data, may not apply broadly
   - ASSUMPTION: No direct data, using extrapolation or general knowledge
3. If the data doesn't support an answer, say "I don't have sufficient data to answer that" rather than guessing.
4. Distinguish between BUDGET rates (what was estimated) and ACTUAL rates (what was achieved) and RECOMMENDED rates (what to use going forward).
5. When giving rates, always include the unit (MH/SF, $/CY, $/TON, etc.).
6. Use the search tools to find relevant data before answering. Don't rely on memory — always query the database.
7. Keep answers practical and concise. This is a tool for estimators, not an academic exercise.
8. If a tool returns empty results, do NOT keep calling more tools hoping to find data. After 1-2 empty searches on a topic, conclude that the data doesn't exist and tell the user.
9. When asked about $/unit costs (dollars per ton, per SF, per pound, etc.), check BOTH unit_costs AND subcontractors — subcontractor records often have the dollar-per-unit pricing while unit_costs may have labor MH rates.

## Bid Document Rules

10. When the user asks about bid scope, RFP requirements, or spec details, use `search_bid_documents` FIRST.
11. When the user asks to compare bid scope vs historical data, search bid docs first, THEN search historical data, and combine the results into a cross-referenced answer.
12. When citing bid document answers, include the document filename and section heading when available.
13. References to "the RFP", "the specs", "the bid docs", or "the scope" without specifying which bid should default to the FOCUS bid.
14. If no focus bid is set and the user asks about bid docs, let them know they need to set a focus bid or specify which bid.

## Available Data

{{AVAILABLE_DATA}}

{{ACTIVE_BIDS}}

## Response Format

Keep responses well-structured. Use this general pattern:
- Lead with the direct answer
- Include the rate/cost with units
- Cite the source (Job #, discipline, cost code if applicable)
- Note the confidence level
- Add relevant context or caveats if important
"""


def _build_available_data() -> str:
    """Query database for all projects and build the Available Data section dynamically."""
    try:
        overview = query.get_database_overview()
    except Exception:
        return "No data currently loaded in the database."

    projects = overview.get("projects", [])
    counts = overview.get("record_counts", {})

    if not projects:
        return "No projects currently loaded in the database."

    lines = ["The database currently contains data from:"]

    for proj in projects:
        job = proj.get("job_number", "?")
        name = proj.get("job_name", "Unknown")
        owner = proj.get("owner", "")
        cost = proj.get("total_actual_cost")
        mh = proj.get("total_actual_mh")
        cpi = proj.get("cpi")

        header = f"- Job {job}: {name}"
        if owner:
            header += f" ({owner})"
        lines.append(header)

        details = []
        if cost:
            details.append(f"${cost / 1_000_000:.1f}M actual cost")
        if mh:
            details.append(f"{mh:,.0f} MH")
        if cpi:
            details.append(f"CPI {cpi:.2f}")
        if details:
            lines.append(f"  - {', '.join(details)}")

    # Discipline list
    discs = overview.get("disciplines", [])
    if discs:
        disc_names = [d.get("discipline_name", d.get("discipline_code", "?")) for d in discs]
        lines.append(f"  - Disciplines: {', '.join(disc_names)}")

    # Aggregate record counts
    count_parts = []
    label_map = {
        "cost_codes": "cost codes",
        "unit_costs": "unit cost rates",
        "production_rates": "production rates",
        "crew_configurations": "crew configs",
        "material_costs": "material costs",
        "subcontractors": "subcontractors",
        "lessons_learned": "lessons learned",
        "benchmark_rates": "benchmark rates",
    }
    for key, label in label_map.items():
        c = counts.get(key, 0)
        if c > 0:
            count_parts.append(f"{c} {label}")
    if count_parts:
        lines.append(f"  - {', '.join(count_parts)}")

    return "\n".join(lines)


def _build_active_bids() -> str:
    """Query database for active bids and build the Active Bids section dynamically."""
    try:
        bids = query.get_active_bids()
    except Exception:
        return ""

    if not bids:
        return ""

    lines = ["## Active Bids", ""]

    for bid in bids:
        focus = " **[FOCUS]**" if bid.get("is_focus") else ""
        name = bid.get("bid_name", "Unnamed")
        number = bid.get("bid_number", "")
        header = f"- {name}"
        if number:
            header += f" (#{number})"
        header += focus
        lines.append(header)

        details = []
        if bid.get("owner"):
            details.append(f"Owner: {bid['owner']}")
        if bid.get("general_contractor"):
            details.append(f"GC: {bid['general_contractor']}")
        if bid.get("bid_date"):
            details.append(f"Bid Date: {bid['bid_date']}")
        if bid.get("doc_count"):
            details.append(f"{bid['doc_count']} documents ({bid.get('total_words', 0):,} words)")
        if details:
            lines.append(f"  - {', '.join(details)}")

    return "\n".join(lines)


def build_system_prompt() -> str:
    """Build the full system prompt with dynamic data section."""
    available = _build_available_data()
    active_bids = _build_active_bids()
    prompt = SYSTEM_PROMPT_TEMPLATE.replace("{{AVAILABLE_DATA}}", available)
    prompt = prompt.replace("{{ACTIVE_BIDS}}", active_bids)
    return prompt

# ---------------------------------------------------------------------------
# Query Engine
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-20250514"
MAX_TOOL_ROUNDS = 5


class QueryEngine:
    """Manages conversations with Claude for database queries."""

    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key."
            )
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.conversation: list[dict] = []

    def reset(self):
        """Clear conversation history."""
        self.conversation = []

    def ask(self, question: str) -> str:
        """Ask a question and get a sourced answer.

        Handles the full tool-use loop: sends question to Claude,
        executes any tool calls, returns final text response.
        """
        self.conversation.append({"role": "user", "content": question})

        system_prompt = build_system_prompt()

        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=system_prompt,
                tools=TOOLS,
                messages=self.conversation,
            )

            # Add assistant response to conversation
            self.conversation.append({"role": "assistant", "content": response.content})

            # Check if Claude wants to use tools
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                # No tool calls — extract and return text
                text_parts = [b.text for b in response.content if hasattr(b, "text")]
                return "\n".join(text_parts) if text_parts else "(No response)"

            # Execute all tool calls and add results
            tool_results = []
            for tool_block in tool_uses:
                result = execute_tool(tool_block.name, tool_block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": result,
                })

            self.conversation.append({"role": "user", "content": tool_results})

        # Exhausted tool rounds
        return "(Query required too many steps. Please try a more specific question.)"

    def get_status(self) -> dict:
        """Get database status without using AI."""
        return query.get_database_overview()
