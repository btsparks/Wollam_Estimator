"""WEIS database query functions.

Pure database queries that return structured results with source citations.
These are used both by the AI engine (tool calls) and directly for testing.
"""

import sqlite3
from app.database import get_connection


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    """Convert sqlite3.Row objects to plain dicts."""
    return [dict(r) for r in rows]


def search_unit_costs(activity: str = None, discipline: str = None,
                      unit: str = None, confidence: str = None,
                      limit: int = 50) -> list[dict]:
    """Search unit cost records.

    Args:
        activity: Partial match on activity name (e.g., 'wall form', 'grout')
        discipline: Discipline code or name (e.g., 'CONCRETE', 'concrete')
        unit: Unit type (e.g., 'MH/SF', '$/CY')
        confidence: Confidence level filter (HIGH, MEDIUM, LOW)
        limit: Max results
    """
    conn = get_connection()
    try:
        sql = """
            SELECT uc.*, d.discipline_code, d.discipline_name,
                   p.job_number, p.job_name
            FROM unit_costs uc
            JOIN disciplines d ON uc.discipline_id = d.id
            JOIN projects p ON uc.project_id = p.id
            WHERE 1=1
        """
        params = []

        if activity:
            sql += " AND uc.activity LIKE ?"
            params.append(f"%{activity}%")
        if discipline:
            sql += " AND (d.discipline_code LIKE ? OR d.discipline_name LIKE ?)"
            params.extend([f"%{discipline}%", f"%{discipline}%"])
        if unit:
            sql += " AND uc.unit LIKE ?"
            params.append(f"%{unit}%")
        if confidence:
            sql += " AND uc.confidence = ?"
            params.append(confidence.upper())

        sql += f" ORDER BY d.discipline_name, uc.activity LIMIT {limit}"
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def search_cost_codes(cost_code: str = None, description: str = None,
                      discipline: str = None, over_budget_only: bool = False,
                      limit: int = 50) -> list[dict]:
    """Search cost code records.

    Args:
        cost_code: Partial match on cost code (e.g., '23', '2340')
        description: Partial match on description (e.g., 'wall', 'pour')
        discipline: Discipline code or name
        over_budget_only: If True, only return codes that went over budget
        limit: Max results
    """
    conn = get_connection()
    try:
        sql = """
            SELECT cc.*, d.discipline_code, d.discipline_name,
                   p.job_number, p.job_name
            FROM cost_codes cc
            JOIN disciplines d ON cc.discipline_id = d.id
            JOIN projects p ON cc.project_id = p.id
            WHERE 1=1
        """
        params = []

        if cost_code:
            sql += " AND cc.cost_code LIKE ?"
            params.append(f"%{cost_code}%")
        if description:
            sql += " AND cc.description LIKE ?"
            params.append(f"%{description}%")
        if discipline:
            sql += " AND (d.discipline_code LIKE ? OR d.discipline_name LIKE ?)"
            params.extend([f"%{discipline}%", f"%{discipline}%"])
        if over_budget_only:
            sql += " AND cc.over_budget_flag = 1"

        sql += f" ORDER BY cc.cost_code LIMIT {limit}"
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def search_production_rates(activity: str = None, discipline: str = None,
                            limit: int = 50) -> list[dict]:
    """Search production rate records."""
    conn = get_connection()
    try:
        sql = """
            SELECT pr.*, d.discipline_code, d.discipline_name,
                   p.job_number, p.job_name
            FROM production_rates pr
            JOIN disciplines d ON pr.discipline_id = d.id
            JOIN projects p ON pr.project_id = p.id
            WHERE 1=1
        """
        params = []

        if activity:
            sql += " AND pr.activity LIKE ?"
            params.append(f"%{activity}%")
        if discipline:
            sql += " AND (d.discipline_code LIKE ? OR d.discipline_name LIKE ?)"
            params.extend([f"%{discipline}%", f"%{discipline}%"])

        sql += f" ORDER BY d.discipline_name, pr.activity LIMIT {limit}"
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def search_crew_configs(activity: str = None, discipline: str = None,
                        limit: int = 50) -> list[dict]:
    """Search crew configuration records."""
    conn = get_connection()
    try:
        sql = """
            SELECT cr.*, d.discipline_code, d.discipline_name,
                   p.job_number, p.job_name
            FROM crew_configurations cr
            JOIN disciplines d ON cr.discipline_id = d.id
            JOIN projects p ON cr.project_id = p.id
            WHERE 1=1
        """
        params = []

        if activity:
            sql += " AND (cr.activity LIKE ? OR cr.crew_description LIKE ?)"
            params.extend([f"%{activity}%", f"%{activity}%"])
        if discipline:
            sql += " AND (d.discipline_code LIKE ? OR d.discipline_name LIKE ?)"
            params.extend([f"%{discipline}%", f"%{discipline}%"])

        sql += f" ORDER BY d.discipline_name LIMIT {limit}"
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def search_material_costs(material: str = None, discipline: str = None,
                          vendor: str = None, limit: int = 50) -> list[dict]:
    """Search material cost records."""
    conn = get_connection()
    try:
        sql = """
            SELECT mc.*, d.discipline_code, d.discipline_name,
                   p.job_number, p.job_name
            FROM material_costs mc
            JOIN disciplines d ON mc.discipline_id = d.id
            JOIN projects p ON mc.project_id = p.id
            WHERE 1=1
        """
        params = []

        if material:
            sql += " AND (mc.material_type LIKE ? OR mc.material_description LIKE ?)"
            params.extend([f"%{material}%", f"%{material}%"])
        if discipline:
            sql += " AND (d.discipline_code LIKE ? OR d.discipline_name LIKE ?)"
            params.extend([f"%{discipline}%", f"%{discipline}%"])
        if vendor:
            sql += " AND mc.vendor LIKE ?"
            params.append(f"%{vendor}%")

        sql += f" ORDER BY d.discipline_name, mc.material_type LIMIT {limit}"
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def search_subcontractors(name: str = None, scope: str = None,
                          discipline: str = None,
                          limit: int = 50) -> list[dict]:
    """Search subcontractor records."""
    conn = get_connection()
    try:
        sql = """
            SELECT s.*, d.discipline_code, d.discipline_name,
                   p.job_number, p.job_name
            FROM subcontractors s
            JOIN disciplines d ON s.discipline_id = d.id
            JOIN projects p ON s.project_id = p.id
            WHERE 1=1
        """
        params = []

        if name:
            sql += " AND s.sub_name LIKE ?"
            params.append(f"%{name}%")
        if scope:
            sql += " AND (s.scope_description LIKE ? OR s.scope_category LIKE ?)"
            params.extend([f"%{scope}%", f"%{scope}%"])
        if discipline:
            sql += " AND (d.discipline_code LIKE ? OR d.discipline_name LIKE ?)"
            params.extend([f"%{discipline}%", f"%{discipline}%"])

        sql += f" ORDER BY s.sub_name LIMIT {limit}"
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def search_lessons_learned(category: str = None, discipline: str = None,
                           severity: str = None, keyword: str = None,
                           limit: int = 50) -> list[dict]:
    """Search lessons learned records.

    Args:
        category: Category filter (estimating, production_variance, scope_gap, etc.)
        discipline: Discipline code or name
        severity: Severity filter (HIGH, MEDIUM, LOW)
        keyword: Search title and description text
        limit: Max results
    """
    conn = get_connection()
    try:
        sql = """
            SELECT ll.*, d.discipline_code, d.discipline_name,
                   p.job_number, p.job_name
            FROM lessons_learned ll
            LEFT JOIN disciplines d ON ll.discipline_id = d.id
            JOIN projects p ON ll.project_id = p.id
            WHERE 1=1
        """
        params = []

        if category:
            sql += " AND ll.category LIKE ?"
            params.append(f"%{category}%")
        if discipline:
            sql += " AND (d.discipline_code LIKE ? OR d.discipline_name LIKE ?)"
            params.extend([f"%{discipline}%", f"%{discipline}%"])
        if severity:
            sql += " AND ll.severity = ?"
            params.append(severity.upper())
        if keyword:
            sql += " AND (ll.title LIKE ? OR ll.description LIKE ? OR ll.recommendation LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

        sql += f" ORDER BY ll.severity DESC, ll.category LIMIT {limit}"
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def search_benchmark_rates(activity: str = None, discipline: str = None,
                           rate_type: str = None,
                           limit: int = 50) -> list[dict]:
    """Search benchmark rate records."""
    conn = get_connection()
    try:
        sql = """
            SELECT * FROM benchmark_rates WHERE 1=1
        """
        params = []

        if activity:
            sql += " AND activity LIKE ?"
            params.append(f"%{activity}%")
        if discipline:
            sql += " AND discipline_code LIKE ?"
            params.append(f"%{discipline}%")
        if rate_type:
            sql += " AND rate_type = ?"
            params.append(rate_type)

        sql += f" ORDER BY discipline_code, activity LIMIT {limit}"
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def get_project_summary(job_number: str = None) -> list[dict]:
    """Get project-level summary data."""
    conn = get_connection()
    try:
        sql = "SELECT * FROM projects"
        params = []
        if job_number:
            sql += " WHERE job_number = ?"
            params.append(job_number)
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def get_discipline_summary(job_number: str = None) -> list[dict]:
    """Get discipline breakdown for a project."""
    conn = get_connection()
    try:
        sql = """
            SELECT d.*, p.job_number, p.job_name
            FROM disciplines d
            JOIN projects p ON d.project_id = p.id
        """
        params = []
        if job_number:
            sql += " WHERE p.job_number = ?"
            params.append(job_number)
        sql += " ORDER BY d.actual_cost DESC"
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def get_gc_breakdown(job_number: str = None) -> list[dict]:
    """Get general conditions breakdown."""
    conn = get_connection()
    try:
        sql = """
            SELECT gc.*, p.job_number, p.job_name
            FROM general_conditions_breakdown gc
            JOIN projects p ON gc.project_id = p.id
        """
        params = []
        if job_number:
            sql += " WHERE p.job_number = ?"
            params.append(job_number)
        sql += " ORDER BY gc.actual_cost DESC"
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def run_read_query(sql: str) -> list[dict]:
    """Execute a read-only SQL query. Only SELECT statements allowed.

    This is used by the AI engine for flexible queries that don't fit
    the pre-built search functions.
    """
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    # Block dangerous keywords
    for keyword in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
                    "ATTACH", "DETACH", "PRAGMA"]:
        if keyword in sql_stripped:
            raise ValueError(f"Query contains disallowed keyword: {keyword}")

    conn = get_connection()
    try:
        rows = conn.execute(sql).fetchall()
        return _rows_to_dicts(rows)
    finally:
        conn.close()


def get_all_projects_with_detail() -> list[dict]:
    """Get all projects with per-table record counts and discipline list.

    Returns a list of project dicts, each augmented with:
      - record_counts: {table_name: count} for that project
      - disciplines: list of discipline dicts with budget/actual/variance
      - total_records: sum of all record counts
    """
    conn = get_connection()
    try:
        projects = _rows_to_dicts(conn.execute("SELECT * FROM projects ORDER BY job_number").fetchall())

        child_tables = [
            "disciplines", "cost_codes", "unit_costs", "production_rates",
            "crew_configurations", "material_costs", "subcontractors",
            "lessons_learned", "general_conditions_breakdown",
        ]

        for proj in projects:
            pid = proj["id"]

            # Per-table record counts
            counts = {}
            for table in child_tables:
                row = conn.execute(
                    f"SELECT COUNT(*) as c FROM {table} WHERE project_id = ?", (pid,)
                ).fetchone()
                counts[table] = row["c"]
            proj["record_counts"] = counts
            proj["total_records"] = sum(counts.values())

            # Discipline breakdown
            discs = conn.execute(
                "SELECT discipline_code, discipline_name, budget_cost, actual_cost, "
                "variance_cost, budget_mh, actual_mh, variance_mh "
                "FROM disciplines WHERE project_id = ? ORDER BY actual_cost DESC",
                (pid,),
            ).fetchall()
            proj["disciplines_detail"] = _rows_to_dicts(discs)

        return projects
    finally:
        conn.close()


def get_database_overview() -> dict:
    """Get a summary of all data in the database."""
    conn = get_connection()
    try:
        overview = {"projects": [], "record_counts": {}, "disciplines": []}

        # Projects
        projects = conn.execute(
            "SELECT job_number, job_name, owner, total_actual_cost, total_actual_mh, cpi "
            "FROM projects"
        ).fetchall()
        overview["projects"] = _rows_to_dicts(projects)

        # Record counts
        tables = [
            "projects", "disciplines", "cost_codes", "unit_costs",
            "production_rates", "crew_configurations", "material_costs",
            "subcontractors", "lessons_learned", "benchmark_rates",
            "general_conditions_breakdown",
        ]
        for table in tables:
            row = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
            overview["record_counts"][table] = row["c"]

        # Disciplines
        discs = conn.execute(
            "SELECT discipline_code, discipline_name FROM disciplines "
            "ORDER BY discipline_name"
        ).fetchall()
        overview["disciplines"] = _rows_to_dicts(discs)

        return overview
    finally:
        conn.close()
