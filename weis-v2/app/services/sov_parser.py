"""AI-powered bid schedule of values parser.

Takes uploaded bid schedule files (Excel, PDF, Word, CSV, TXT),
extracts text, and uses Claude Haiku to parse into structured
SOV line items.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic

from app.config import ANTHROPIC_API_KEY
from app.services.document_extract import extract_text

logger = logging.getLogger(__name__)

SOV_PARSE_PROMPT = """You are parsing a construction bid schedule of values from an owner's RFP package.

Your task: Extract every bid schedule line item from the document text below and return them as a JSON array.

Each item should have these fields:
- "item_number": The owner's item number exactly as written (e.g., "1", "1.1", "001", "A-1"). Use null if no number.
- "description": The line item description. Keep it verbatim from the document.
- "unit": The unit of measure (LS, LF, CY, EA, SF, TON, SY, GAL, HR, MO, etc.). Use null if not specified.
- "quantity": The quantity as a number (strip commas). Use null if blank or not specified.

Rules:
- Ignore header rows, section headers, subtotals, totals, and formatting artifacts
- Preserve the owner's item numbering exactly — do not renumber
- Extract units exactly as written
- Extract quantities as plain numbers (no commas, no dollar signs)
- Skip any pricing/dollar columns — we only need item_number, description, unit, quantity
- If a row looks like a section header with sub-items beneath it, include it as its own item
- Handle merged cells, multi-page tables, and messy formatting gracefully

Return ONLY valid JSON — no markdown, no code fences, no explanation. Just the array.

Example output:
[
  {"item_number": "1", "description": "Mobilization / Demobilization", "unit": "LS", "quantity": 1},
  {"item_number": "2", "description": "Excavation", "unit": "CY", "quantity": 5000},
  {"item_number": "3", "description": "6-inch PVC Pipe", "unit": "LF", "quantity": null}
]

Document text to parse:
"""


def parse_sov_file(filepath: Path) -> list[dict]:
    """Parse a bid schedule file into structured SOV items.

    Args:
        filepath: Path to the uploaded file (Excel, PDF, Word, CSV, TXT)

    Returns:
        List of dicts with keys: item_number, description, unit, quantity
    """
    # Extract text from the file
    raw_text = extract_text(filepath)

    if not raw_text or not raw_text.strip():
        raise ValueError("No text could be extracted from the uploaded file")

    # Send to Claude Haiku for parsing
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": SOV_PARSE_PROMPT + raw_text[:60_000],
            }
        ],
    )

    # Extract the response text
    result_text = response.content[0].text.strip()

    # Strip markdown code fences if present
    if result_text.startswith("```"):
        lines = result_text.split("\n")
        # Remove first and last lines (``` markers)
        lines = [l for l in lines if not l.strip().startswith("```")]
        result_text = "\n".join(lines)

    # Parse JSON
    try:
        items = json.loads(result_text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        logger.error(f"Response text: {result_text[:500]}")
        raise ValueError(f"AI returned invalid JSON. Please try again or use a different file format.")

    if not isinstance(items, list):
        raise ValueError("AI returned unexpected format — expected a list of items")

    # Normalize items
    normalized = []
    for item in items:
        normalized.append({
            "item_number": item.get("item_number"),
            "description": item.get("description", ""),
            "unit": item.get("unit"),
            "quantity": _parse_quantity(item.get("quantity")),
        })

    return normalized


def _parse_quantity(val) -> float | None:
    """Parse a quantity value into a float, handling various formats."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.strip().replace(",", "").replace("$", "")
        if not val:
            return None
        try:
            return float(val)
        except ValueError:
            return None
    return None
