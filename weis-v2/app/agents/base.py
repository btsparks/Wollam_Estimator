"""Base agent class and report dataclass for bid intelligence agents.

All agents follow the same pattern:
1. Receive chunked document text + bid context
2. Send chunks to Claude Haiku with agent-specific system prompt
3. Process in batches to stay under token limits
4. Return structured JSON findings as an AgentReport
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from app.config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_CHUNK_CHARS = 100_000  # ~25K tokens — safe batch size for Haiku


@dataclass
class AgentReport:
    """Structured output from an agent run."""

    agent_name: str
    status: str = "complete"  # "complete" or "error"
    summary_text: str = ""
    report_json: dict = field(default_factory=dict)
    risk_rating: str = "low"  # "low", "medium", "high", "critical"
    flags_count: int = 0
    tokens_used: int = 0
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    input_doc_count: int = 0
    input_chunk_count: int = 0


class BaseAgent:
    """Abstract base class for bid intelligence agents.

    Subclasses must set:
        name: str
        display_name: str
        system_prompt: str

    And implement:
        _parse_response(response_text: str) -> dict
    """

    name: str = ""
    display_name: str = ""
    version: str = "1.0"
    system_prompt: str = ""

    def run(
        self,
        bid_id: int,
        doc_chunks: list[dict],
        context: dict,
    ) -> AgentReport:
        """Execute the agent against bid document chunks.

        Args:
            bid_id: The bid being analyzed
            doc_chunks: List of {chunk_text, section_heading, filename, doc_category}
            context: Additional context (SOV items, bid metadata, etc.)

        Returns:
            AgentReport with structured findings
        """
        start = time.time()
        report = AgentReport(
            agent_name=self.name,
            input_doc_count=len(set(c.get("filename", "") for c in doc_chunks)),
            input_chunk_count=len(doc_chunks),
        )

        if not doc_chunks:
            report.summary_text = "No documents available for analysis."
            report.report_json = self._empty_report()
            report.duration_seconds = time.time() - start
            return report

        try:
            # Build the user message with document chunks in batches
            batches = self._build_batches(doc_chunks)
            all_responses = []
            total_tokens = 0

            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

            for batch_text in batches:
                user_message = self._build_user_message(batch_text, context)

                response = client.messages.create(
                    model=MODEL,
                    max_tokens=4096,
                    system=self.system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )

                total_tokens += (
                    response.usage.input_tokens + response.usage.output_tokens
                )
                all_responses.append(response.content[0].text)

            # Parse and merge responses
            if len(all_responses) == 1:
                parsed = self._parse_response(all_responses[0])
            else:
                parsed = self._merge_responses(all_responses)

            report.report_json = parsed
            report.summary_text = self._build_summary(parsed)
            report.risk_rating = self._assess_risk(parsed)
            report.flags_count = len(parsed.get("flags", []))
            report.tokens_used = total_tokens

        except Exception as e:
            logger.error("Agent %s failed for bid %d: %s", self.name, bid_id, e)
            report.status = "error"
            report.error_message = str(e)

        report.duration_seconds = time.time() - start
        return report

    def _build_batches(self, doc_chunks: list[dict]) -> list[str]:
        """Group chunks into batches that fit within token limits."""
        batches = []
        current_batch = []
        current_size = 0

        for chunk in doc_chunks:
            header = ""
            if chunk.get("filename"):
                header += f"\n[File: {chunk['filename']}"
                if chunk.get("doc_category"):
                    header += f" | Category: {chunk['doc_category']}"
                if chunk.get("section_heading"):
                    header += f" | Section: {chunk['section_heading']}"
                header += "]\n"

            chunk_text = header + chunk.get("chunk_text", "")
            chunk_len = len(chunk_text)

            if current_size + chunk_len > MAX_CHUNK_CHARS and current_batch:
                batches.append("\n\n---\n\n".join(current_batch))
                current_batch = []
                current_size = 0

            current_batch.append(chunk_text)
            current_size += chunk_len

        if current_batch:
            batches.append("\n\n---\n\n".join(current_batch))

        return batches

    def _build_user_message(self, document_text: str, context: dict) -> str:
        """Build the user message sent to Claude.

        Subclasses can override to add context-specific info.
        """
        parts = []

        # Add bid metadata
        if context.get("bid_name"):
            parts.append(f"Bid Project: {context['bid_name']}")
        if context.get("owner"):
            parts.append(f"Owner: {context['owner']}")
        if context.get("location"):
            parts.append(f"Location: {context['location']}")

        # Add SOV items if available
        sov_items = context.get("sov_items", [])
        if sov_items:
            sov_text = "Schedule of Values Items:\n"
            for item in sov_items:
                sov_text += f"  - {item.get('item_number', '?')}: {item.get('description', '')} ({item.get('quantity', '')} {item.get('unit', '')})\n"
            parts.append(sov_text)

        parts.append(f"Document Text:\n\n{document_text}")

        return "\n\n".join(parts)

    def _parse_response(self, response_text: str) -> dict:
        """Parse Claude's response into structured JSON.

        Subclasses should override this for custom parsing.
        """
        # Strip markdown code fences
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {"raw_response": response_text, "parse_error": True}

    def _merge_responses(self, responses: list[str]) -> dict:
        """Merge multiple batch responses into one report.

        Subclasses should override for agent-specific merging.
        Default: parse each and merge lists/flags.
        """
        merged = {}
        for resp in responses:
            parsed = self._parse_response(resp)
            for key, val in parsed.items():
                if key not in merged:
                    merged[key] = val
                elif isinstance(val, list) and isinstance(merged[key], list):
                    merged[key].extend(val)
                elif isinstance(val, int) and isinstance(merged[key], int):
                    merged[key] += val
        return merged

    def _build_summary(self, report_json: dict) -> str:
        """Build a plain-language summary from the report.

        Subclasses should override.
        """
        flags = report_json.get("flags", [])
        if flags:
            return f"{len(flags)} item(s) flagged for review."
        return "Analysis complete. No items flagged."

    def _assess_risk(self, report_json: dict) -> str:
        """Assess overall risk rating from the report.

        Subclasses should override.
        """
        flags = report_json.get("flags", [])
        if len(flags) >= 5:
            return "high"
        elif len(flags) >= 2:
            return "medium"
        elif len(flags) >= 1:
            return "low"
        return "low"

    def _empty_report(self) -> dict:
        """Return an empty report structure. Subclasses should override."""
        return {"flags": []}
