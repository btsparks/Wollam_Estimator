"""
PM Interview Workflow

Guides Project Managers through a structured interview to add context
to auto-generated rate cards. The interview is the critical human
touchpoint — it's where raw numbers become meaningful intelligence.

Interview question types:

    VARIANCE — "Cost code 2340 (Wall F/S) ran 15% over budget.
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

from dataclasses import dataclass, field
from typing import Any

from app.database import get_connection
from app.transform.rate_card import RateCardResult, RateItemResult


@dataclass
class InterviewQuestion:
    """A single PM interview question."""
    id: str
    type: str           # VARIANCE, LESSONS, CONTEXT, RATE_CONFIRM
    discipline: str | None = None
    activity: str | None = None
    question_text: str = ""
    required: bool = False
    response: str | None = None
    override_rate: float | None = None
    override_reason: str | None = None


class PMInterviewWorkflow:
    """
    Manages the PM interview process for rate card review.

    Generates questions from rate card data, collects PM responses,
    and updates the rate card with PM context.
    """

    def __init__(self, rate_card: RateCardResult | None = None):
        self._card = rate_card
        self._questions: list[InterviewQuestion] = []
        self._overrides: dict[str, tuple[float, str]] = {}  # activity -> (rate, reason)

    @property
    def questions(self) -> list[InterviewQuestion]:
        return self._questions

    def generate_questions(self) -> list[dict[str, Any]]:
        """
        Auto-generate interview questions from rate card data.

        Creates four types of questions:
            1. VARIANCE — one per flagged item (>20% variance), required
            2. LESSONS — one per discipline present in the rate card
            3. CONTEXT — project-level "what went well/wrong" questions
            4. RATE_CONFIRM — items with moderate/limited confidence

        Returns:
            List of question dicts.
        """
        if not self._card:
            return []

        self._questions = []
        q_index = 0

        # 1. VARIANCE questions — one per flagged item (required)
        for item in self._card.flagged_items:
            direction = "over" if (item.variance_pct or 0) > 0 else "under"
            pct = abs(item.variance_pct or 0)
            q = InterviewQuestion(
                id=f"VAR-{q_index}",
                type="VARIANCE",
                discipline=item.discipline,
                activity=item.activity,
                question_text=(
                    f"Cost code {item.activity} ({item.description or 'N/A'}) "
                    f"ran {pct:.0f}% {direction} budget. What drove this variance?"
                ),
                required=True,
            )
            self._questions.append(q)
            q_index += 1

        # 2. LESSONS — one per discipline
        disciplines_seen: set[str] = set()
        for item in self._card.items:
            if item.discipline not in disciplines_seen and item.discipline != "unmapped":
                disciplines_seen.add(item.discipline)
                q = InterviewQuestion(
                    id=f"LES-{q_index}",
                    type="LESSONS",
                    discipline=item.discipline,
                    question_text=(
                        f"What should future estimators know about "
                        f"{item.discipline.replace('_', ' ')} on this project?"
                    ),
                    required=False,
                )
                self._questions.append(q)
                q_index += 1

        # 3. CONTEXT — project-level questions
        q = InterviewQuestion(
            id=f"CTX-{q_index}",
            type="CONTEXT",
            question_text="What went well on this project that should be repeated?",
            required=False,
        )
        self._questions.append(q)
        q_index += 1

        q = InterviewQuestion(
            id=f"CTX-{q_index}",
            type="CONTEXT",
            question_text="What were the biggest challenges or surprises?",
            required=False,
        )
        self._questions.append(q)
        q_index += 1

        # 4. RATE_CONFIRM — items with moderate or limited confidence
        for item in self._card.items:
            if item.confidence in ("moderate", "limited") and item.rec_rate is not None:
                unit = item.unit or "unit"
                q = InterviewQuestion(
                    id=f"RC-{q_index}",
                    type="RATE_CONFIRM",
                    discipline=item.discipline,
                    activity=item.activity,
                    question_text=(
                        f"The recommended rate for {item.description or item.activity} is "
                        f"{item.rec_rate:.4f} MH/{unit}. "
                        f"Do you agree, or would you adjust?"
                    ),
                    required=False,
                )
                self._questions.append(q)
                q_index += 1

        return [self._question_to_dict(q) for q in self._questions]

    def submit_response(self, question_id: str, response: str) -> None:
        """
        Record the PM's response to a question.

        Args:
            question_id: ID of the question being answered.
            response: PM's text response.

        Raises:
            ValueError: If question_id not found.
        """
        for q in self._questions:
            if q.id == question_id:
                q.response = response
                return
        raise ValueError(f"Question '{question_id}' not found")

    def override_rate(self, activity: str, new_rate: float, reason: str) -> None:
        """
        PM overrides the recommended rate for an activity.

        The original calculated rate is preserved; the override is tracked
        separately with rec_basis='pm_override'.

        Args:
            activity: Cost code (e.g., '2340').
            new_rate: PM's overridden rate.
            reason: PM's explanation for the override.
        """
        self._overrides[activity] = (new_rate, reason)

    def is_complete(self) -> bool:
        """
        Check if all required questions have been answered.

        Required questions are VARIANCE questions — one per flagged item.
        The rate card can't move to 'approved' until all required questions
        have responses.

        Returns:
            True if all required questions answered.
        """
        for q in self._questions:
            if q.required and not q.response:
                return False
        return True

    def finalize(self, pm_name: str | None = None) -> dict[str, Any]:
        """
        Finalize the interview and apply results to the database.

        Applies:
            - Variance explanations on rate_items
            - Rate overrides as pm_override
            - Lessons to lesson_learned table

        Args:
            pm_name: Name of the PM who completed the interview.

        Returns:
            Summary dict with counts of updates applied.

        Raises:
            ValueError: If required questions unanswered or no card loaded.
        """
        if not self._card:
            raise ValueError("No rate card loaded")
        if not self.is_complete():
            raise ValueError("All required (VARIANCE) questions must be answered before finalizing")

        conn = get_connection()
        explanations_applied = 0
        overrides_applied = 0
        lessons_captured = 0

        try:
            # Get the card_id from the DB
            card_row = conn.execute(
                "SELECT card_id, job_id FROM rate_card rc "
                "JOIN job j ON rc.job_id = j.job_id "
                "WHERE j.job_number = ?",
                (self._card.job_number,),
            ).fetchone()

            if not card_row:
                raise ValueError(f"Rate card for job {self._card.job_number} not found in DB")

            card_id = card_row["card_id"]
            job_id = card_row["job_id"]

            # Apply variance explanations
            for q in self._questions:
                if q.type == "VARIANCE" and q.response and q.activity:
                    conn.execute(
                        """UPDATE rate_item
                           SET variance_explanation = ?
                           WHERE card_id = ? AND activity = ?""",
                        (q.response, card_id, q.activity),
                    )
                    explanations_applied += 1

            # Apply rate overrides
            for activity, (rate, reason) in self._overrides.items():
                conn.execute(
                    """UPDATE rate_item
                       SET rec_rate = ?, rec_basis = 'pm_override',
                           variance_explanation = COALESCE(variance_explanation, '') || ?
                       WHERE card_id = ? AND activity = ?""",
                    (rate, f"\nPM Override: {reason}", card_id, activity),
                )
                overrides_applied += 1

            # Capture lessons from LESSONS questions
            for q in self._questions:
                if q.type == "LESSONS" and q.response:
                    conn.execute(
                        """INSERT INTO lesson_learned
                               (job_id, discipline, category, description,
                                pm_name, source)
                           VALUES (?, ?, 'process', ?, ?, 'pm_interview')""",
                        (job_id, q.discipline, q.response, pm_name),
                    )
                    lessons_captured += 1

            # Capture CONTEXT responses as general lessons
            for q in self._questions:
                if q.type == "CONTEXT" and q.response:
                    category = "success" if "well" in q.question_text.lower() else "risk"
                    conn.execute(
                        """INSERT INTO lesson_learned
                               (job_id, category, description, pm_name, source)
                           VALUES (?, ?, ?, ?, 'pm_interview')""",
                        (job_id, category, q.response, pm_name),
                    )
                    lessons_captured += 1

            conn.commit()
        finally:
            conn.close()

        return {
            "explanations_applied": explanations_applied,
            "overrides_applied": overrides_applied,
            "lessons_captured": lessons_captured,
        }

    @staticmethod
    def _question_to_dict(q: InterviewQuestion) -> dict[str, Any]:
        """Convert an InterviewQuestion to a dict for the UI."""
        return {
            "id": q.id,
            "type": q.type,
            "discipline": q.discipline,
            "activity": q.activity,
            "question_text": q.question_text,
            "required": q.required,
            "response": q.response,
        }
