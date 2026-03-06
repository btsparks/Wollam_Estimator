"""
Lessons Learned Capture and Indexing

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

from app.database import get_connection


class LessonsLearnedCapture:
    """Manages lessons learned capture, storage, and retrieval."""

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
        conn = get_connection()
        try:
            cursor = conn.execute(
                """INSERT INTO lesson_learned
                       (job_id, discipline, category, description,
                        impact, recommendation, pm_name, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pm_interview')""",
                (job_id, discipline, category, description,
                 impact, recommendation, pm_name),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

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
            keyword: Full-text search in description and recommendation.

        Returns:
            List of matching lesson dicts.
        """
        conn = get_connection()
        try:
            query = """
                SELECT ll.*, j.job_number, j.name as job_name
                FROM lesson_learned ll
                JOIN job j ON ll.job_id = j.job_id
                WHERE 1=1
            """
            params: list[Any] = []

            if discipline:
                query += " AND ll.discipline = ?"
                params.append(discipline)
            if category:
                query += " AND ll.category = ?"
                params.append(category)
            if keyword:
                query += " AND (ll.description LIKE ? OR ll.recommendation LIKE ?)"
                params.extend([f"%{keyword}%", f"%{keyword}%"])

            query += " ORDER BY ll.captured_date DESC"

            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_lessons_for_job(self, job_id: int) -> list[dict[str, Any]]:
        """
        Get all lessons learned for a specific job.

        Args:
            job_id: Database job ID.

        Returns:
            List of lesson dicts for the job.
        """
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT * FROM lesson_learned
                   WHERE job_id = ?
                   ORDER BY discipline, category""",
                (job_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
