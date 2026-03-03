"""
PM Interview Workflow — Stub for Phase D

Guides Project Managers through a structured interview to add context
to auto-generated rate cards. The interview is the critical human
touchpoint — it's where raw numbers become meaningful intelligence.

Interview question types:

    VARIANCE — "Cost code 2215 (Wall F/S) ran 15% over budget.
                What drove this?" Required for every flagged item.

    LESSONS  — "What should future estimators know about concrete
                on this project?" One question per discipline.

    CONTEXT  — "What went well?" and "What were the challenges?"
               General project-level questions.

    RATE_CONFIRM — "The recommended rate for wall forming is 0.25 MH/SF.
                    Do you agree, or would you adjust?" PM can override.

Designed to be completable in 15-30 minutes. Variance questions are
required (blocking); lessons and context are encouraged but not blocking.
"""

from __future__ import annotations

from typing import Any

from app.transform.rate_card import RateCardResult


class PMInterviewWorkflow:
    """
    Manages the PM interview process for rate card review.

    Generates questions from rate card data, collects PM responses,
    and updates the rate card with PM context.

    Phase D implementation.
    """

    def __init__(self, rate_card: RateCardResult | None = None):
        """
        Args:
            rate_card: Rate card to generate interview questions from.
        """
        self._card = rate_card

    def generate_questions(self) -> list[dict[str, Any]]:
        """
        Auto-generate interview questions from rate card data.

        Creates four types of questions:
            1. VARIANCE — one per flagged item (>20% variance)
            2. LESSONS — one per discipline present in the rate card
            3. CONTEXT — project-level "what went well/wrong" questions
            4. RATE_CONFIRM — one per item where PM override might be needed

        Returns:
            List of question dicts with keys: type, code, discipline,
            question_text, required (bool), current_value, context.
        """
        raise NotImplementedError("Phase D — PM interview workflow not yet implemented")

    def submit_response(self, question_id: str, response: str) -> None:
        """
        Record the PM's response to a question.

        Args:
            question_id: ID of the question being answered.
            response: PM's text response.
        """
        raise NotImplementedError("Phase D — PM interview workflow not yet implemented")

    def override_rate(self, activity: str, new_rate: float, reason: str) -> None:
        """
        PM overrides the recommended rate for an activity.

        The original calculated rate is preserved; the override is tracked
        separately with rec_basis='pm_override'.

        Args:
            activity: Cost code (e.g., '2215').
            new_rate: PM's overridden rate.
            reason: PM's explanation for the override.
        """
        raise NotImplementedError("Phase D — PM interview workflow not yet implemented")

    def is_complete(self) -> bool:
        """
        Check if all required questions have been answered.

        Required questions are VARIANCE questions — one per flagged item.
        The rate card can't move to 'approved' until all required questions
        have responses.

        Returns:
            True if all required questions answered.
        """
        raise NotImplementedError("Phase D — PM interview workflow not yet implemented")

    def finalize(self) -> RateCardResult:
        """
        Finalize the interview and update the rate card.

        Applies PM overrides, records variance explanations, and
        changes rate card status to 'approved'.

        Returns:
            Updated RateCardResult with PM context applied.
        """
        raise NotImplementedError("Phase D — PM interview workflow not yet implemented")
