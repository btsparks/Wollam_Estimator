"""
Lessons Learned Capture and Indexing — Stub for Phase D

Captures, stores, and indexes lessons learned from PM interviews.
Each lesson is tagged by discipline, category, and impact level
for retrieval by the Estimator Agent on future bids.

Categories:
    variance — explains a budget-to-actual variance
    success  — what went well, should be repeated
    risk     — what went wrong, watch for on future bids
    process  — process improvements or workflow changes
"""

from __future__ import annotations

from typing import Any


class LessonsLearnedCapture:
    """
    Manages lessons learned capture, storage, and retrieval.

    Phase D implementation.
    """

    def capture_lesson(
        self,
        job_id: int,
        discipline: str | None,
        category: str,
        description: str,
        impact: str | None = None,
        recommendation: str | None = None,
        pm_name: str | None = None,
    ) -> int:
        """
        Capture a single lesson learned.

        Args:
            job_id: Database job ID.
            discipline: Discipline key (e.g., 'concrete').
            category: 'variance', 'success', 'risk', 'process'.
            description: What happened.
            impact: 'high', 'medium', 'low'.
            recommendation: What to do differently.
            pm_name: PM who provided the lesson.

        Returns:
            Database ID of the created lesson.
        """
        raise NotImplementedError("Phase D — lessons learned capture not yet implemented")

    def search_lessons(
        self,
        discipline: str | None = None,
        category: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search lessons learned by discipline, category, or keyword.

        Args:
            discipline: Filter by discipline.
            category: Filter by category.
            keyword: Full-text search.

        Returns:
            List of matching lesson dicts.
        """
        raise NotImplementedError("Phase D — lessons learned search not yet implemented")

    def get_lessons_for_job(self, job_id: int) -> list[dict[str, Any]]:
        """
        Get all lessons learned for a specific job.

        Args:
            job_id: Database job ID.

        Returns:
            List of lesson dicts for the job.
        """
        raise NotImplementedError("Phase D — lessons learned retrieval not yet implemented")
