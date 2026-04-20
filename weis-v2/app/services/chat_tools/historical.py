"""Historical job browsing tool for the non-bid chat context."""

from __future__ import annotations

from app.database import get_connection
from app.services.chat_tools.base import ChatTool


class ListHistoricalJobsTool(ChatTool):
    name = "list_historical_jobs"
    description = (
        "Browse the historical job catalog. Filter by discipline, name, year, or whether "
        "the job has PM context or rate cards. Use this to explore what data is available "
        "before querying specific jobs."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "name_contains": {"type": "string", "description": "Filter by job name (partial match)"},
            "job_number_prefix": {"type": "string", "description": "Filter by job number prefix"},
            "status": {"type": "string", "description": "'Active' or 'Completed'"},
            "has_rate_card": {"type": "boolean", "description": "Only jobs with calculated rate cards"},
            "has_pm_context": {"type": "boolean", "description": "Only jobs with PM context"},
            "limit": {"type": "integer", "description": "Max results (default 50)", "default": 50},
        },
        "required": [],
    }
    contexts = ["historical"]

    def execute(self, **kwargs) -> list[dict]:
        clauses = ["1=1"]
        params: list = []

        if kwargs.get("name_contains"):
            clauses.append("j.name LIKE ?")
            params.append(f"%{kwargs['name_contains']}%")
        if kwargs.get("job_number_prefix"):
            clauses.append("j.job_number LIKE ?")
            params.append(f"{kwargs['job_number_prefix']}%")
        if kwargs.get("status"):
            clauses.append("j.status = ?")
            params.append(kwargs["status"])

        joins = ""
        if kwargs.get("has_rate_card"):
            joins += " INNER JOIN rate_card rc ON j.job_id = rc.job_id"
        if kwargs.get("has_pm_context"):
            joins += " INNER JOIN pm_context pm ON j.job_id = pm.job_id"

        limit = min(kwargs.get("limit", 50), 100)
        where = " AND ".join(clauses)

        conn = get_connection()
        try:
            rows = conn.execute(
                f"""SELECT j.job_id, j.job_number, j.name, j.status,
                           (SELECT COUNT(*) FROM hj_costcode cc WHERE cc.job_id = j.job_id) AS cost_code_count,
                           (SELECT COUNT(*) FROM rate_card rc2 WHERE rc2.job_id = j.job_id) > 0 AS has_rate_card,
                           (SELECT COUNT(*) FROM pm_context pm2 WHERE pm2.job_id = j.job_id) > 0 AS has_pm_context
                    FROM job j{joins}
                    WHERE {where}
                    ORDER BY j.job_number DESC
                    LIMIT ?""",
                params + [limit],
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
