"""Base class for all WEIS chat tools.

Each tool has a name, description, input schema, context tags,
and an execute method. The chat engine discovers tools through
the registry in __init__.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ChatTool(ABC):
    """Base class for agentic chat tools."""

    name: str
    description: str
    input_schema: dict
    contexts: list[str]  # ["bid", "historical", "all"]

    def anthropic_definition(self) -> dict:
        """Return the Anthropic API tool definition."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    @abstractmethod
    def execute(self, **kwargs) -> dict | list:
        """Execute the tool and return structured output."""
        ...

    def format_for_claude(self, result: Any) -> str | list:
        """Format the tool result for inclusion in a Claude tool_result message.

        By default returns a JSON-like text string. Override for tools
        that need multi-block results (e.g., PDF vision).
        """
        import json
        if isinstance(result, (dict, list)):
            return json.dumps(result, default=str)
        return str(result)
