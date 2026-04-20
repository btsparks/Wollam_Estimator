"""SQL tool — safe read-only query execution against WEIS database.

Migrated from app/services/sql_tool.py into the chat tool registry pattern.
"""

from app.services.chat_tools.base import ChatTool
from app.services.sql_tool import execute_sql, SCHEMA_DESCRIPTION


class RunSqlTool(ChatTool):
    name = "run_sql"
    description = (
        "Execute a read-only SQL SELECT query against the WEIS SQLite database. "
        "Returns columns, rows, and row count. Use this to look up historical "
        "field data, rates, PM context, estimates, and documents before answering."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A SQL SELECT query. Must be read-only (no INSERT/UPDATE/DELETE/DROP).",
            }
        },
        "required": ["query"],
    }
    contexts = ["bid", "historical"]

    def execute(self, **kwargs) -> dict:
        query = kwargs.get("query", "")
        return execute_sql(query)

    def format_for_claude(self, result: dict) -> str:
        """Format SQL results as tab-separated text for Claude."""
        if result.get("error"):
            return f"SQL Error: {result['error']}"

        columns = result.get("columns", [])
        rows = result.get("rows", [])

        if not columns:
            return "Query returned no results."

        lines = ["\t".join(str(c) for c in columns)]
        for row in rows:
            lines.append("\t".join(str(v) if v is not None else "NULL" for v in row))

        text = "\n".join(lines)
        if result.get("truncated"):
            text += f"\n... (truncated at {result['row_count']} rows)"
        return text
