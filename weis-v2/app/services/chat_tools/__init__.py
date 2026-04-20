"""Chat tool registry — discovers and serves tools by context.

Usage:
    tools = get_tools_for_context("bid")      # all bid-chat tools
    tools = get_tools_for_context("historical")  # all historical-chat tools
    tool = get_tool_by_name("read_document")   # specific tool by name
"""

from __future__ import annotations

from app.services.chat_tools.base import ChatTool
from app.services.chat_tools.sql import RunSqlTool
from app.services.chat_tools.documents import (
    ListBidDocumentsTool,
    ReadDocumentTool,
    ViewDrawingPagesTool,
)
from app.services.chat_tools.search import SearchBidDocumentsTool
from app.services.chat_tools.addenda import ListAddendaTool, FindAddendumChangesTool
from app.services.chat_tools.historical import ListHistoricalJobsTool

# All registered tools
_ALL_TOOLS: list[ChatTool] = [
    RunSqlTool(),
    ListBidDocumentsTool(),
    ReadDocumentTool(),
    ViewDrawingPagesTool(),
    SearchBidDocumentsTool(),
    ListAddendaTool(),
    FindAddendumChangesTool(),
    ListHistoricalJobsTool(),
]

_TOOL_MAP: dict[str, ChatTool] = {t.name: t for t in _ALL_TOOLS}


def get_tools_for_context(context: str) -> list[ChatTool]:
    """Return all tools available for a given chat context ('bid' or 'historical')."""
    return [t for t in _ALL_TOOLS if context in t.contexts or "all" in t.contexts]


def get_tool_by_name(name: str) -> ChatTool | None:
    """Return a specific tool by its name."""
    return _TOOL_MAP.get(name)


def get_anthropic_definitions(context: str) -> list[dict]:
    """Return Anthropic API tool definitions for a context."""
    return [t.anthropic_definition() for t in get_tools_for_context(context)]
