"""
Rate Card Export — Stub for Phase D

Exports rate cards and knowledge base data to various formats
for use outside the WEIS system:
    - Markdown (for documentation and JCD-compatible output)
    - Excel (for sharing with estimators who prefer spreadsheets)
    - PDF (for formal bid documentation)

The markdown export is particularly important — it produces output
in the same format as the legacy JCD files, allowing comparison
between API-generated and manually-cataloged data.
"""

from __future__ import annotations

from typing import Any


class RateCardExport:
    """
    Exports rate cards and knowledge base data to external formats.

    Phase D implementation.
    """

    def to_markdown(self, card_id: int) -> str:
        """
        Export a rate card as JCD-compatible markdown.

        Produces output matching the legacy JCD format for comparison
        and documentation purposes.

        Args:
            card_id: Database rate_card ID.

        Returns:
            Markdown string.
        """
        raise NotImplementedError("Phase D — markdown export not yet implemented")

    def to_excel(self, card_id: int, output_path: str) -> str:
        """
        Export a rate card as an Excel workbook.

        Args:
            card_id: Database rate_card ID.
            output_path: File path for the output .xlsx file.

        Returns:
            Path to the created file.
        """
        raise NotImplementedError("Phase D — Excel export not yet implemented")

    def export_rate_library(self, output_path: str, format: str = "excel") -> str:
        """
        Export the full rate library (knowledge base).

        Args:
            output_path: File path for the output file.
            format: 'excel', 'markdown', or 'csv'.

        Returns:
            Path to the created file.
        """
        raise NotImplementedError("Phase D — rate library export not yet implemented")
