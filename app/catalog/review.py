"""
Rate Card Review and Approval Workflow

Manages the rate card lifecycle:
    draft → pending_review → approved

A rate card is auto-generated in 'draft' status. When ready for PM
review, it moves to 'pending_review'. After the PM completes the
interview (explains variances, captures lessons), it moves to 'approved'.

Only approved rate cards feed into the knowledge base (rate_library
and benchmark tables).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.database import get_connection


class RateCardReview:
    """Manages rate card review and approval workflow."""

    def submit_for_review(self, card_id: int) -> None:
        """
        Move a rate card from 'draft' to 'pending_review'.

        Args:
            card_id: Database rate_card ID.

        Raises:
            ValueError: If card not found or not in 'draft' status.
        """
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT status FROM rate_card WHERE card_id = ?", (card_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Rate card {card_id} not found")
            if row["status"] != "draft":
                raise ValueError(
                    f"Card {card_id} is '{row['status']}', must be 'draft' to submit for review"
                )

            conn.execute(
                "UPDATE rate_card SET status = 'pending_review' WHERE card_id = ?",
                (card_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def approve(self, card_id: int, pm_name: str, notes: str | None = None) -> None:
        """
        Approve a rate card after PM review.

        Moves the card to 'approved' status and triggers knowledge base
        aggregation for this card's rates.

        Args:
            card_id: Database rate_card ID.
            pm_name: Name of the approving PM.
            notes: Optional PM notes.

        Raises:
            ValueError: If card not found or not in 'pending_review' status.
        """
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT status FROM rate_card WHERE card_id = ?", (card_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Rate card {card_id} not found")
            if row["status"] != "pending_review":
                raise ValueError(
                    f"Card {card_id} is '{row['status']}', must be 'pending_review' to approve"
                )

            conn.execute(
                """UPDATE rate_card
                   SET status = 'approved',
                       pm_reviewed = 1,
                       pm_name = ?,
                       pm_notes = ?,
                       review_date = ?
                   WHERE card_id = ?""",
                (pm_name, notes, datetime.now().isoformat(), card_id),
            )
            conn.commit()
        finally:
            conn.close()

        # Trigger KB aggregation after commit
        from app.catalog.aggregate import aggregate_card
        aggregate_card(card_id)

    def reject(self, card_id: int, reason: str) -> None:
        """
        Reject a rate card — sends it back to 'draft' for rework.

        Args:
            card_id: Database rate_card ID.
            reason: Why the card was rejected.

        Raises:
            ValueError: If card not found or not in 'pending_review' status.
        """
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT status FROM rate_card WHERE card_id = ?", (card_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Rate card {card_id} not found")
            if row["status"] != "pending_review":
                raise ValueError(
                    f"Card {card_id} is '{row['status']}', must be 'pending_review' to reject"
                )

            conn.execute(
                """UPDATE rate_card
                   SET status = 'draft',
                       pm_notes = ?
                   WHERE card_id = ?""",
                (f"REJECTED: {reason}", card_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_pending_reviews(self) -> list[dict[str, Any]]:
        """
        Get all rate cards awaiting PM review, with job details.

        Returns:
            List of pending rate card summary dicts.
        """
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT rc.*, j.job_number, j.name as job_name,
                          (SELECT COUNT(*) FROM rate_item ri
                           WHERE ri.card_id = rc.card_id AND ri.variance_flag = 1) as flagged_count
                   FROM rate_card rc
                   JOIN job j ON rc.job_id = j.job_id
                   WHERE rc.status = 'pending_review'
                   ORDER BY j.job_number""",
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_all_cards(self) -> list[dict[str, Any]]:
        """
        Get all rate cards with job info and flagged item count.

        Returns:
            List of all rate card summary dicts.
        """
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT rc.*, j.job_number, j.name as job_name,
                          (SELECT COUNT(*) FROM rate_item ri
                           WHERE ri.card_id = rc.card_id AND ri.variance_flag = 1) as flagged_count
                   FROM rate_card rc
                   JOIN job j ON rc.job_id = j.job_id
                   ORDER BY j.job_number""",
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
