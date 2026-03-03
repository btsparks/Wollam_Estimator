"""
Rate Card Review and Approval — Stub for Phase D

Manages the rate card lifecycle:
    draft → pending_review → approved

A rate card is auto-generated in 'draft' status. When ready for PM
review, it moves to 'pending_review'. After the PM completes the
interview (explains variances, captures lessons), it moves to 'approved'.

Only approved rate cards feed into the knowledge base (rate_library
and benchmark tables).
"""

from __future__ import annotations

from typing import Any


class RateCardReview:
    """
    Manages rate card review and approval workflow.

    Phase D implementation.
    """

    def submit_for_review(self, card_id: int) -> None:
        """
        Move a rate card from 'draft' to 'pending_review'.

        Triggers PM notification (Phase D).

        Args:
            card_id: Database rate_card ID.
        """
        raise NotImplementedError("Phase D — rate card review not yet implemented")

    def approve(self, card_id: int, pm_name: str, notes: str | None = None) -> None:
        """
        Approve a rate card after PM review.

        Moves the card to 'approved' status and triggers knowledge base
        aggregation for this card's rates.

        Args:
            card_id: Database rate_card ID.
            pm_name: Name of the approving PM.
            notes: Optional PM notes.
        """
        raise NotImplementedError("Phase D — rate card approval not yet implemented")

    def reject(self, card_id: int, reason: str) -> None:
        """
        Reject a rate card — sends it back to 'draft' for rework.

        Args:
            card_id: Database rate_card ID.
            reason: Why the card was rejected.
        """
        raise NotImplementedError("Phase D — rate card rejection not yet implemented")

    def get_pending_reviews(self) -> list[dict[str, Any]]:
        """
        Get all rate cards awaiting PM review.

        Returns:
            List of pending rate card summary dicts.
        """
        raise NotImplementedError("Phase D — pending review list not yet implemented")
