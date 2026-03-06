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


def get_project_records(project_id: int) -> dict[str, list[dict]]:
    """Get all data records for a project, organized by table.

    Returns a dict keyed by table name, each value a list of record dicts.
    Joins discipline name onto child records for readability.
    """
    conn = get_connection()
    try:
        results = {}

        results["cost_codes"] = _rows_to_dicts(conn.execute(
            "SELECT cc.cost_code, cc.description, cc.unit, "
            "cc.budget_qty, cc.actual_qty, cc.budget_cost, cc.actual_cost, "
            "cc.budget_mh, cc.actual_mh, cc.budget_mh_per_unit, cc.actual_mh_per_unit, "
            "cc.over_budget_flag, d.discipline_name "
            "FROM cost_codes cc "
            "LEFT JOIN disciplines d ON cc.discipline_id = d.id "
            "WHERE cc.project_id = ? ORDER BY d.discipline_name, cc.cost_code",
            (project_id,),
        ).fetchall())

        results["unit_costs"] = _rows_to_dicts(conn.execute(
            "SELECT uc.activity, uc.unit, uc.budget_rate, uc.actual_rate, "
            "uc.recommended_rate, uc.rate_basis, uc.confidence, "
            "uc.mh_per_unit_budget, uc.mh_per_unit_actual, uc.project_conditions, "
            "d.discipline_name "
            "FROM unit_costs uc "
            "LEFT JOIN disciplines d ON uc.discipline_id = d.id "
            "WHERE uc.project_id = ? ORDER BY d.discipline_name, uc.activity",
            (project_id,),
        ).fetchall())

        results["production_rates"] = _rows_to_dicts(conn.execute(
            "SELECT pr.activity, pr.unit, pr.production_unit, "
            "pr.budget_rate, pr.actual_rate, pr.recommended_rate, "
            "pr.crew_size, pr.equipment_primary, pr.confidence, "
            "d.discipline_name "
            "FROM production_rates pr "
            "LEFT JOIN disciplines d ON pr.discipline_id = d.id "
            "WHERE pr.project_id = ? ORDER BY d.discipline_name, pr.activity",
            (project_id,),
        ).fetchall())

        results["crew_configurations"] = _rows_to_dicts(conn.execute(
            "SELECT cr.activity, cr.crew_description, "
            "cr.foreman, cr.journeyman, cr.apprentice, cr.laborer, "
            "cr.operator, cr.ironworker, cr.pipefitter, cr.electrician, "
            "cr.total_crew_size, cr.equipment_list, cr.shift_hours, "
            "d.discipline_name "
            "FROM crew_configurations cr "
            "LEFT JOIN disciplines d ON cr.discipline_id = d.id "
            "WHERE cr.project_id = ? ORDER BY d.discipline_name, cr.activity",
            (project_id,),
        ).fetchall())

        results["material_costs"] = _rows_to_dicts(conn.execute(
            "SELECT mc.material_type, mc.material_description, mc.vendor, "
            "mc.unit, mc.quantity, mc.unit_cost, mc.total_cost, "
            "mc.po_number, d.discipline_name "
            "FROM material_costs mc "
            "LEFT JOIN disciplines d ON mc.discipline_id = d.id "
            "WHERE mc.project_id = ? ORDER BY d.discipline_name, mc.material_type",
            (project_id,),
        ).fetchall())

        results["subcontractors"] = _rows_to_dicts(conn.execute(
            "SELECT s.sub_name, s.scope_description, s.scope_category, "
            "s.contract_amount, s.actual_amount, s.unit, s.quantity, s.unit_cost, "
            "s.performance_rating, s.would_use_again, d.discipline_name "
            "FROM subcontractors s "
            "LEFT JOIN disciplines d ON s.discipline_id = d.id "
            "WHERE s.project_id = ? ORDER BY d.discipline_name, s.sub_name",
            (project_id,),
        ).fetchall())

        results["lessons_learned"] = _rows_to_dicts(conn.execute(
            "SELECT ll.category, ll.severity, ll.title, ll.description, "
            "ll.impact, ll.recommendation, ll.applies_to, d.discipline_name "
            "FROM lessons_learned ll "
            "LEFT JOIN disciplines d ON ll.discipline_id = d.id "
            "WHERE ll.project_id = ? ORDER BY ll.severity DESC, ll.category",
            (project_id,),
        ).fetchall())

        results["general_conditions_breakdown"] = _rows_to_dicts(conn.execute(
            "SELECT gc.category, gc.description, gc.cost_code, "
            "gc.budget_cost, gc.actual_cost, gc.unit, gc.rate, "
            "gc.duration, gc.pct_of_total_job "
            "FROM general_conditions_breakdown gc "
            "WHERE gc.project_id = ? ORDER BY gc.actual_cost DESC",
            (project_id,),
        ).fetchall())

        return results
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Active Bid Functions (Phase 2.4)
# ---------------------------------------------------------------------------


def get_active_bids(status: str = None) -> list[dict]:
    """Get all active bids, optionally filtered by status."""
    conn = get_connection()
    try:
        sql = """
            SELECT ab.*,
                   (SELECT COUNT(*) FROM bid_documents WHERE bid_id = ab.id) as doc_count,
                   (SELECT COALESCE(SUM(word_count), 0) FROM bid_documents WHERE bid_id = ab.id) as total_words
            FROM active_bids ab
            WHERE 1=1
        """
        params = []
        if status:
            sql += " AND ab.status = ?"
            params.append(status)
        sql += " ORDER BY ab.is_focus DESC, ab.updated_at DESC"
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def get_focus_bid() -> dict | None:
    """Get the currently focused bid, or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM active_bids WHERE is_focus = 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_focus_bid(bid_id: int) -> None:
    """Set a bid as the focus bid (clears any existing focus)."""
    conn = get_connection()
    try:
        conn.execute("UPDATE active_bids SET is_focus = 0 WHERE is_focus = 1")
        conn.execute(
            "UPDATE active_bids SET is_focus = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (bid_id,),
        )
        conn.commit()
    finally:
        conn.close()


def clear_focus_bid() -> None:
    """Clear the focus bid."""
    conn = get_connection()
    try:
        conn.execute("UPDATE active_bids SET is_focus = 0 WHERE is_focus = 1")
        conn.commit()
    finally:
        conn.close()


def create_active_bid(bid_name: str, bid_number: str = None, owner: str = None,
                      general_contractor: str = None, bid_date: str = None,
                      project_type: str = None, location: str = None,
                      estimated_value: float = None, notes: str = None) -> int:
    """Create a new active bid. Returns the new bid ID."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO active_bids
               (bid_name, bid_number, owner, general_contractor, bid_date,
                project_type, location, estimated_value, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bid_name, bid_number, owner, general_contractor, bid_date,
             project_type, location, estimated_value, notes),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def delete_bid_cascade(bid_id: int) -> dict:
    """Delete a bid and all its documents, chunks, and agent reports.

    Returns dict with counts of deleted records.
    """
    conn = get_connection()
    try:
        deleted = {}

        # Delete chat messages (may not exist on older schemas)
        try:
            cursor = conn.execute(
                "DELETE FROM bid_chat_messages WHERE bid_id = ?", (bid_id,)
            )
            deleted["chat_messages"] = cursor.rowcount
        except Exception:
            deleted["chat_messages"] = 0

        # Delete agent reports (may not exist on older schemas)
        try:
            cursor = conn.execute(
                "DELETE FROM agent_reports WHERE bid_id = ?", (bid_id,)
            )
            deleted["agent_reports"] = cursor.rowcount
        except Exception:
            deleted["agent_reports"] = 0

        cursor = conn.execute(
            "DELETE FROM bid_document_chunks WHERE bid_id = ?", (bid_id,)
        )
        deleted["chunks"] = cursor.rowcount

        cursor = conn.execute(
            "DELETE FROM bid_documents WHERE bid_id = ?", (bid_id,)
        )
        deleted["documents"] = cursor.rowcount

        cursor = conn.execute(
            "DELETE FROM active_bids WHERE id = ?", (bid_id,)
        )
        deleted["bids"] = cursor.rowcount

        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_bid_document(bid_id: int, filename: str, file_type: str,
                        file_size_bytes: int = None, doc_category: str = "general",
                        doc_label: str = None, extraction_status: str = "pending",
                        extraction_warning: str = None, page_count: int = None,
                        word_count: int = None) -> int:
    """Insert a bid document record. Returns the new document ID."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO bid_documents
               (bid_id, filename, file_type, file_size_bytes, doc_category,
                doc_label, extraction_status, extraction_warning, page_count, word_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bid_id, filename, file_type, file_size_bytes, doc_category,
             doc_label, extraction_status, extraction_warning, page_count, word_count),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def insert_bid_chunks(document_id: int, bid_id: int, chunks: list[dict]) -> int:
    """Insert text chunks for a bid document. Returns number inserted."""
    conn = get_connection()
    try:
        for chunk in chunks:
            conn.execute(
                """INSERT INTO bid_document_chunks
                   (document_id, bid_id, chunk_index, chunk_text, section_heading)
                   VALUES (?, ?, ?, ?, ?)""",
                (document_id, bid_id, chunk["chunk_index"],
                 chunk["chunk_text"], chunk.get("section_heading")),
            )
        conn.commit()
        return len(chunks)
    finally:
        conn.close()


def get_bid_documents(bid_id: int) -> list[dict]:
    """Get all documents for a bid."""
    conn = get_connection()
    try:
        return _rows_to_dicts(conn.execute(
            """SELECT bd.*, ab.bid_name
               FROM bid_documents bd
               JOIN active_bids ab ON bd.bid_id = ab.id
               WHERE bd.bid_id = ?
               ORDER BY bd.created_at DESC""",
            (bid_id,),
        ).fetchall())
    finally:
        conn.close()


def search_bid_documents(query_text: str, bid_id: int = None,
                         doc_category: str = None,
                         limit: int = 20) -> list[dict]:
    """Search bid document chunks by keyword.

    If bid_id is None, defaults to the focus bid.
    Returns matching chunks with document and bid context.
    """
    conn = get_connection()
    try:
        # Default to focus bid if none specified
        if bid_id is None:
            focus = conn.execute(
                "SELECT id FROM active_bids WHERE is_focus = 1"
            ).fetchone()
            if focus:
                bid_id = focus["id"]
            else:
                return []

        sql = """
            SELECT c.chunk_text, c.section_heading, c.chunk_index,
                   d.filename, d.doc_category, d.doc_label,
                   b.bid_name, b.bid_number, b.id as bid_id
            FROM bid_document_chunks c
            JOIN bid_documents d ON c.document_id = d.id
            JOIN active_bids b ON c.bid_id = b.id
            WHERE c.bid_id = ?
              AND c.chunk_text LIKE ?
        """
        params = [bid_id, f"%{query_text}%"]

        if doc_category:
            sql += " AND d.doc_category = ?"
            params.append(doc_category)

        sql += f" ORDER BY c.chunk_index LIMIT {limit}"
        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def get_bid_overview(bid_id: int = None) -> dict:
    """Get document count, categories, word count for a bid.

    If bid_id is None, defaults to the focus bid.
    """
    conn = get_connection()
    try:
        if bid_id is None:
            focus = conn.execute(
                "SELECT id FROM active_bids WHERE is_focus = 1"
            ).fetchone()
            if focus:
                bid_id = focus["id"]
            else:
                return {"error": "No focus bid set and no bid_id specified."}

        bid = conn.execute(
            "SELECT * FROM active_bids WHERE id = ?", (bid_id,)
        ).fetchone()
        if not bid:
            return {"error": f"Bid {bid_id} not found."}

        docs = conn.execute(
            """SELECT doc_category, COUNT(*) as count,
                      COALESCE(SUM(word_count), 0) as words
               FROM bid_documents WHERE bid_id = ?
               GROUP BY doc_category""",
            (bid_id,),
        ).fetchall()

        total_docs = conn.execute(
            "SELECT COUNT(*) as c FROM bid_documents WHERE bid_id = ?", (bid_id,)
        ).fetchone()

        total_chunks = conn.execute(
            "SELECT COUNT(*) as c FROM bid_document_chunks WHERE bid_id = ?", (bid_id,)
        ).fetchone()

        total_words = conn.execute(
            "SELECT COALESCE(SUM(word_count), 0) as w FROM bid_documents WHERE bid_id = ?",
            (bid_id,),
        ).fetchone()

        return {
            "bid_id": bid_id,
            "bid_name": bid["bid_name"],
            "bid_number": bid["bid_number"],
            "owner": bid["owner"],
            "general_contractor": bid["general_contractor"],
            "bid_date": bid["bid_date"],
            "status": bid["status"],
            "total_documents": total_docs["c"],
            "total_chunks": total_chunks["c"],
            "total_words": total_words["w"],
            "categories": _rows_to_dicts(docs),
        }
    finally:
        conn.close()


def delete_bid_document(document_id: int) -> dict:
    """Delete a single bid document and its chunks."""
    conn = get_connection()
    try:
        deleted = {}
        cursor = conn.execute(
            "DELETE FROM bid_document_chunks WHERE document_id = ?", (document_id,)
        )
        deleted["chunks"] = cursor.rowcount

        cursor = conn.execute(
            "DELETE FROM bid_documents WHERE id = ?", (document_id,)
        )
        deleted["documents"] = cursor.rowcount

        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Database Overview
# ---------------------------------------------------------------------------


def get_database_overview() -> dict:
    """Get a summary of all data in the database."""
    conn = get_connection()
    try:
        overview = {"projects": [], "record_counts": {}, "disciplines": []}

        # Projects
        projects = conn.execute(
            "SELECT job_number, job_name, owner, total_actual_cost, total_actual_mh "
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


# ---------------------------------------------------------------------------
# Read Document Chunks (Phase 3 — Agent Tool)
# ---------------------------------------------------------------------------


def read_document_chunks(bid_id: int = None, document_id: int = None,
                         start_chunk: int = 0, max_chunks: int = 5) -> list[dict]:
    """Read sequential chunks from bid documents.

    Lets agents read document sections in order, not just keyword search.
    Capped at 10 chunks per call to manage context size.

    Args:
        bid_id: Bid to read from. Defaults to focus bid.
        document_id: Specific document to read. If None, reads all docs for the bid.
        start_chunk: Starting chunk index (0-based).
        max_chunks: Number of chunks to return (capped at 10).
    """
    max_chunks = min(max_chunks, 10)
    conn = get_connection()
    try:
        if bid_id is None:
            focus = conn.execute(
                "SELECT id FROM active_bids WHERE is_focus = 1"
            ).fetchone()
            if focus:
                bid_id = focus["id"]
            else:
                return []

        sql = """
            SELECT c.chunk_index, c.chunk_text, c.section_heading,
                   d.filename, d.doc_category, d.doc_label
            FROM bid_document_chunks c
            JOIN bid_documents d ON c.document_id = d.id
            WHERE c.bid_id = ?
        """
        params: list = [bid_id]

        if document_id is not None:
            sql += " AND c.document_id = ?"
            params.append(document_id)

        sql += " ORDER BY d.id, c.chunk_index LIMIT ? OFFSET ?"
        params.extend([max_chunks, start_chunk])

        return _rows_to_dicts(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def get_bid_documents_list(bid_id: int = None) -> list[dict]:
    """Get document list for a bid (lightweight, for agent context).

    Returns id, filename, doc_category, doc_label, word_count per doc.
    Defaults to focus bid.
    """
    conn = get_connection()
    try:
        if bid_id is None:
            focus = conn.execute(
                "SELECT id FROM active_bids WHERE is_focus = 1"
            ).fetchone()
            if focus:
                bid_id = focus["id"]
            else:
                return []

        return _rows_to_dicts(conn.execute(
            """SELECT id, filename, doc_category, doc_label, word_count,
                      page_count, extraction_status
               FROM bid_documents WHERE bid_id = ?
               ORDER BY doc_category, filename""",
            (bid_id,),
        ).fetchall())
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agent Report CRUD (Phase 3)
# ---------------------------------------------------------------------------


def upsert_agent_report(bid_id: int, agent_name: str, **kwargs) -> int:
    """Insert or update an agent report.

    Uses the unique constraint on (bid_id, agent_name) to upsert.
    Returns the report ID.

    Accepted kwargs: agent_version, status, report_json, summary_text,
    risk_rating, flags_count, input_doc_count, input_chunk_count,
    tokens_used, duration_seconds, error_message.
    """
    conn = get_connection()
    try:
        # Check if report exists
        existing = conn.execute(
            "SELECT id FROM agent_reports WHERE bid_id = ? AND agent_name = ?",
            (bid_id, agent_name),
        ).fetchone()

        if existing:
            # Update
            set_parts = ["updated_at = CURRENT_TIMESTAMP"]
            params = []
            for key, val in kwargs.items():
                set_parts.append(f"{key} = ?")
                params.append(val)
            params.extend([bid_id, agent_name])
            conn.execute(
                f"UPDATE agent_reports SET {', '.join(set_parts)} "
                "WHERE bid_id = ? AND agent_name = ?",
                params,
            )
            conn.commit()
            return existing["id"]
        else:
            # Insert
            cols = ["bid_id", "agent_name"] + list(kwargs.keys())
            placeholders = ["?"] * len(cols)
            vals = [bid_id, agent_name] + list(kwargs.values())
            cursor = conn.execute(
                f"INSERT INTO agent_reports ({', '.join(cols)}) "
                f"VALUES ({', '.join(placeholders)})",
                vals,
            )
            conn.commit()
            return cursor.lastrowid
    finally:
        conn.close()


def get_agent_reports(bid_id: int) -> list[dict]:
    """Get all agent reports for a bid."""
    conn = get_connection()
    try:
        return _rows_to_dicts(conn.execute(
            "SELECT * FROM agent_reports WHERE bid_id = ? ORDER BY agent_name",
            (bid_id,),
        ).fetchall())
    finally:
        conn.close()


def get_agent_report(bid_id: int, agent_name: str) -> dict | None:
    """Get a single agent report by bid and agent name."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM agent_reports WHERE bid_id = ? AND agent_name = ?",
            (bid_id, agent_name),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_agent_status(bid_id: int, agent_name: str, status: str,
                        error_message: str = None) -> None:
    """Update just the status (and optional error) of an agent report."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE agent_reports SET status = ?, error_message = ?, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE bid_id = ? AND agent_name = ?",
            (status, error_message, bid_id, agent_name),
        )
        conn.commit()
    finally:
        conn.close()


def delete_agent_reports(bid_id: int) -> int:
    """Delete all agent reports for a bid. Returns count deleted."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM agent_reports WHERE bid_id = ?", (bid_id,)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_agent_report_summaries(bid_id: int) -> list[dict]:
    """Get lightweight summaries of all completed agent reports for a bid.

    Used by chat to reference agent findings without re-analyzing docs.
    Returns agent_name, summary_text, risk_rating, flags_count, and
    a truncated executive_summary from report_json.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT agent_name, summary_text, risk_rating, flags_count,
                      report_json, tokens_used, duration_seconds, updated_at
               FROM agent_reports
               WHERE bid_id = ? AND status = 'complete'
               ORDER BY agent_name""",
            (bid_id,),
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            # Parse report_json to extract key findings
            if d.get("report_json"):
                import json
                try:
                    report = json.loads(d["report_json"])
                    d["executive_summary"] = report.get("executive_summary", "")
                    d["findings_count"] = len(report.get("findings", []))
                    # For subcontract, count packages
                    if "identified_packages" in report:
                        d["packages_count"] = len(report["identified_packages"])
                except (json.JSONDecodeError, TypeError):
                    pass
            del d["report_json"]  # Don't send full JSON to chat
            results.append(d)
        return results
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Bid Chat Messages (Phase 3 — Priority 1)
# ---------------------------------------------------------------------------


def get_chat_messages(bid_id: int, limit: int = 50) -> list[dict]:
    """Get chat messages for a bid, oldest first."""
    conn = get_connection()
    try:
        return _rows_to_dicts(conn.execute(
            """SELECT id, role, content, created_at
               FROM bid_chat_messages
               WHERE bid_id = ?
               ORDER BY id ASC
               LIMIT ?""",
            (bid_id, limit),
        ).fetchall())
    finally:
        conn.close()


def insert_chat_message(bid_id: int, role: str, content: str) -> int:
    """Insert a chat message. Returns the new message ID."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO bid_chat_messages (bid_id, role, content) VALUES (?, ?, ?)",
            (bid_id, role, content),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def clear_chat_messages(bid_id: int) -> int:
    """Delete all chat messages for a bid. Returns count deleted."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM bid_chat_messages WHERE bid_id = ?", (bid_id,)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Staleness Detection (Phase 3 — Priority 2)
# ---------------------------------------------------------------------------


def get_bid_staleness(bid_id: int) -> dict:
    """Check if agent reports are stale relative to uploaded documents.

    Returns:
        dict with newest_doc_time, oldest_report_time, is_stale, and per-agent status.
    """
    conn = get_connection()
    try:
        newest_doc = conn.execute(
            "SELECT MAX(created_at) as t FROM bid_documents WHERE bid_id = ?",
            (bid_id,),
        ).fetchone()

        reports = conn.execute(
            """SELECT agent_name, updated_at, status
               FROM agent_reports WHERE bid_id = ?""",
            (bid_id,),
        ).fetchall()

        newest_doc_time = newest_doc["t"] if newest_doc else None
        agent_status = {}
        is_stale = False

        for r in reports:
            stale = False
            if newest_doc_time and r["updated_at"] and r["status"] == "complete":
                stale = r["updated_at"] < newest_doc_time
                if stale:
                    is_stale = True
            agent_status[r["agent_name"]] = {
                "updated_at": r["updated_at"],
                "status": r["status"],
                "is_stale": stale,
            }

        return {
            "newest_doc_time": newest_doc_time,
            "is_stale": is_stale,
            "agents": agent_status,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Document Replacement (Phase 3 — Priority 4)
# ---------------------------------------------------------------------------


def get_report_diff(bid_id: int, agent_name: str, new_report: dict) -> dict | None:
    """Compare a new report against the existing one and produce a diff summary.

    Returns None if no previous report exists. Otherwise returns a dict with:
    - previous_flags, new_flags
    - previous_risk, new_risk
    - findings_added, findings_removed (count)
    - summary: human-readable change description
    """
    existing = get_agent_report(bid_id, agent_name)
    if not existing or not existing.get("report_json"):
        return None

    import json
    try:
        old_report = json.loads(existing["report_json"])
    except (json.JSONDecodeError, TypeError):
        return None

    old_flags = old_report.get("flags_count", 0) or 0
    new_flags = new_report.get("flags_count", 0) or 0
    old_risk = old_report.get("risk_rating")
    new_risk = new_report.get("risk_rating")

    # Count findings
    old_findings = len(old_report.get("findings", []))
    new_findings = len(new_report.get("findings", []))

    # Count packages (for subcontract)
    old_packages = len(old_report.get("identified_packages", []))
    new_packages = len(new_report.get("identified_packages", []))

    # Build summary
    changes = []
    if new_flags != old_flags:
        changes.append(f"Flags: {old_flags} → {new_flags}")
    if new_risk != old_risk:
        changes.append(f"Risk: {old_risk or 'N/A'} → {new_risk or 'N/A'}")
    if new_findings != old_findings:
        changes.append(f"Findings: {old_findings} → {new_findings}")
    if new_packages != old_packages:
        changes.append(f"Packages: {old_packages} → {new_packages}")

    return {
        "previous_flags": old_flags,
        "new_flags": new_flags,
        "previous_risk": old_risk,
        "new_risk": new_risk,
        "findings_added": max(0, new_findings - old_findings),
        "findings_removed": max(0, old_findings - new_findings),
        "packages_added": max(0, new_packages - old_packages),
        "packages_removed": max(0, old_packages - new_packages),
        "summary": " | ".join(changes) if changes else "No significant changes",
    }


# ---------------------------------------------------------------------------
# Bid SOV Items (Phase 4 — Schedule of Values)
# ---------------------------------------------------------------------------


def get_sov_items(bid_id: int) -> list[dict]:
    """Get all SOV line items for a bid, ordered by sort_order."""
    conn = get_connection()
    try:
        return _rows_to_dicts(conn.execute(
            "SELECT * FROM bid_sov_item WHERE bid_id = ? ORDER BY sort_order, id",
            (bid_id,),
        ).fetchall())
    finally:
        conn.close()


def insert_sov_item(bid_id: int, item_number: str = None,
                    description: str = "", quantity: float = None,
                    unit: str = None, owner_amount: float = None,
                    cost_code: str = None, discipline: str = None,
                    notes: str = None, sort_order: int = 0) -> int:
    """Insert a new SOV line item. Returns the new item ID."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO bid_sov_item
               (bid_id, item_number, description, quantity, unit, owner_amount,
                cost_code, discipline, notes, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bid_id, item_number, description, quantity, unit, owner_amount,
             cost_code, discipline, notes, sort_order),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_sov_item(item_id: int, **kwargs) -> bool:
    """Update an SOV item. Pass any column=value pairs. Returns True if updated."""
    allowed = {
        "item_number", "description", "quantity", "unit", "owner_amount",
        "cost_code", "discipline", "mapped_by", "unit_price", "total_price",
        "rate_source", "rate_confidence", "notes", "sort_order",
        "pm_quantity", "pm_unit", "quantity_status", "quantity_notes",
        "quantity_verified_at",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False

    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [item_id]

    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE bid_sov_item SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            vals,
        )
        conn.commit()
        return True
    finally:
        conn.close()


def delete_sov_item(item_id: int) -> bool:
    """Delete an SOV item. Returns True if deleted."""
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM bid_sov_item WHERE id = ?", (item_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_all_sov_items(bid_id: int) -> int:
    """Delete all SOV items for a bid. Returns count deleted."""
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM bid_sov_item WHERE bid_id = ?", (bid_id,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_sov_summary(bid_id: int) -> dict:
    """Get SOV summary stats for a bid."""
    conn = get_connection()
    try:
        items = _rows_to_dicts(conn.execute(
            "SELECT * FROM bid_sov_item WHERE bid_id = ? ORDER BY sort_order, id",
            (bid_id,),
        ).fetchall())

        total = len(items)
        mapped = sum(1 for i in items if i.get("cost_code"))
        unmapped = total - mapped
        bid_total = sum(i["total_price"] or 0 for i in items)
        disciplines = sorted(set(
            i["discipline"] for i in items
            if i.get("discipline")
        ))

        return {
            "total_items": total,
            "mapped": mapped,
            "unmapped": unmapped,
            "bid_total": bid_total,
            "disciplines": disciplines,
        }
    finally:
        conn.close()


def get_available_cost_codes() -> list[dict]:
    """Get known cost codes from rate_library for mapping suggestions."""
    conn = get_connection()
    try:
        return _rows_to_dicts(conn.execute(
            """SELECT DISTINCT discipline, activity as cost_code, description,
                      rate, unit, confidence
               FROM rate_library
               ORDER BY discipline, activity"""
        ).fetchall())
    finally:
        conn.close()


def update_pm_quantity(item_id: int, pm_quantity: float | None,
                       pm_unit: str | None = None,
                       quantity_status: str = "verified",
                       quantity_notes: str | None = None) -> bool:
    """Update PM-verified quantity for an SOV item."""
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE bid_sov_item
               SET pm_quantity = ?, pm_unit = ?, quantity_status = ?,
                   quantity_notes = ?, quantity_verified_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (pm_quantity, pm_unit, quantity_status, quantity_notes, item_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_quantity_register(bid_id: int) -> list[dict]:
    """Get quantity register data for a bid — owner vs PM quantities with variance."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, item_number, description, quantity, unit, owner_amount,
                      cost_code, discipline, pm_quantity, pm_unit,
                      quantity_status, quantity_notes, quantity_verified_at
               FROM bid_sov_item
               WHERE bid_id = ?
               ORDER BY sort_order, id""",
            (bid_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            owner_q = d["quantity"]
            pm_q = d["pm_quantity"]
            if owner_q and pm_q:
                d["variance"] = pm_q - owner_q
                d["variance_pct"] = ((pm_q - owner_q) / owner_q * 100) if owner_q else 0
            else:
                d["variance"] = None
                d["variance_pct"] = None
            result.append(d)
        return result
    finally:
        conn.close()


def get_quantity_summary(bid_id: int) -> dict:
    """Get quantity register summary stats."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT
                COUNT(*) as total_items,
                SUM(CASE WHEN quantity_status = 'verified' THEN 1 ELSE 0 END) as verified,
                SUM(CASE WHEN quantity_status = 'flagged' THEN 1 ELSE 0 END) as flagged,
                SUM(CASE WHEN quantity_status = 'accepted' THEN 1 ELSE 0 END) as accepted,
                SUM(CASE WHEN quantity_status = 'pending' OR quantity_status IS NULL
                    THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN pm_quantity IS NOT NULL THEN 1 ELSE 0 END) as has_pm_qty
               FROM bid_sov_item WHERE bid_id = ?""",
            (bid_id,),
        ).fetchone()
        return dict(row) if row else {
            "total_items": 0, "verified": 0, "flagged": 0,
            "accepted": 0, "pending": 0, "has_pm_qty": 0,
        }
    finally:
        conn.close()


def get_rate_application_data(bid_id: int, labor_rate: float = 85.0) -> list[dict]:
    """Get SOV items with matched KB rates and calculated pricing.

    labor_rate: blended $/MH used to convert MH-based rates to dollar amounts.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT s.id, s.item_number, s.description, s.quantity, s.unit,
                      s.owner_amount, s.cost_code, s.discipline,
                      s.unit_price, s.total_price, s.rate_source, s.rate_confidence,
                      s.pm_quantity,
                      r.rate as kb_rate, r.unit as kb_unit, r.confidence as kb_confidence,
                      r.description as kb_description, r.rate_type as kb_rate_type,
                      r.source_jobs as kb_source_jobs
               FROM bid_sov_item s
               LEFT JOIN rate_library r ON s.cost_code = r.activity
               WHERE s.bid_id = ?
               ORDER BY s.sort_order, s.id""",
            (bid_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            kb_rate = d.get("kb_rate")
            qty = d.get("pm_quantity") or d.get("quantity")
            if kb_rate and qty:
                d["est_mh"] = round(kb_rate * qty, 1)
                d["est_unit_price"] = round(kb_rate * labor_rate, 2)
                d["est_total"] = round(kb_rate * qty * labor_rate, 0)
            else:
                d["est_mh"] = None
                d["est_unit_price"] = None
                d["est_total"] = None
            # Owner vs estimate delta
            if d.get("est_total") and d.get("owner_amount"):
                d["delta"] = d["est_total"] - d["owner_amount"]
                d["delta_pct"] = round(
                    (d["est_total"] - d["owner_amount"]) / d["owner_amount"] * 100, 1
                )
            else:
                d["delta"] = None
                d["delta_pct"] = None
            result.append(d)
        return result
    finally:
        conn.close()


def apply_rate_to_item(item_id: int, unit_price: float, total_price: float,
                       rate_source: str, rate_confidence: str) -> bool:
    """Apply a calculated rate to an SOV item."""
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE bid_sov_item
               SET unit_price = ?, total_price = ?, rate_source = ?,
                   rate_confidence = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (unit_price, total_price, rate_source, rate_confidence, item_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def apply_all_rates(bid_id: int, labor_rate: float = 85.0) -> int:
    """Apply KB rates to all mapped SOV items. Returns count of items updated."""
    items = get_rate_application_data(bid_id, labor_rate)
    count = 0
    for item in items:
        if item.get("est_unit_price") and item.get("est_total"):
            source = f"KB rate {item['cost_code']} from Job {item.get('kb_source_jobs', '?')}"
            apply_rate_to_item(
                item["id"], item["est_unit_price"], item["est_total"],
                source, item.get("kb_confidence") or "limited",
            )
            count += 1
    return count


def get_rate_application_summary(bid_id: int, labor_rate: float = 85.0) -> dict:
    """Get summary stats for rate application."""
    items = get_rate_application_data(bid_id, labor_rate)
    total = len(items)
    has_rate = sum(1 for i in items if i.get("kb_rate"))
    applied = sum(1 for i in items if i.get("total_price"))
    est_total = sum(i.get("est_total") or 0 for i in items)
    owner_total = sum(i.get("owner_amount") or 0 for i in items)
    return {
        "total_items": total,
        "has_kb_rate": has_rate,
        "rates_applied": applied,
        "est_total": est_total,
        "owner_total": owner_total,
        "delta": est_total - owner_total if est_total and owner_total else None,
    }


# ---------------------------------------------------------------------------
# Bid Activities (Phase 4b — Activity-level estimating)
# ---------------------------------------------------------------------------


def insert_activity(bid_sov_item_id: int, description: str = "",
                    activity_number: str = None, quantity: float = None,
                    unit: str = None, unit_rate_mh: float = None,
                    labor_rate: float = None, cost_code: str = None,
                    discipline: str = None, source: str = "manual",
                    confidence: str = None, notes: str = None,
                    sort_order: int = 0) -> int:
    """Insert a new activity under a SOV item. Returns the new activity ID."""
    conn = get_connection()
    try:
        # Calculate prices if we have rate + qty + labor
        unit_price = None
        total_price = None
        if unit_rate_mh and labor_rate:
            unit_price = round(unit_rate_mh * labor_rate, 2)
            if quantity:
                total_price = round(unit_rate_mh * quantity * labor_rate, 2)

        cursor = conn.execute(
            """INSERT INTO bid_activity
               (bid_sov_item_id, activity_number, description, quantity, unit,
                unit_rate_mh, labor_rate, unit_price, total_price,
                cost_code, discipline, source, confidence, notes, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bid_sov_item_id, activity_number, description, quantity, unit,
             unit_rate_mh, labor_rate, unit_price, total_price,
             cost_code, discipline, source, confidence, notes, sort_order),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_activity(activity_id: int, **kwargs) -> bool:
    """Update an activity. Pass any column=value pairs. Returns True if updated."""
    allowed = {
        "activity_number", "description", "quantity", "unit",
        "unit_rate_mh", "labor_rate", "unit_price", "total_price",
        "cost_code", "discipline", "source", "confidence", "notes", "sort_order",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False

    # Recalculate prices if rate components changed
    if any(k in fields for k in ("unit_rate_mh", "labor_rate", "quantity")):
        # Need current values to fill in what's not being updated
        conn = get_connection()
        try:
            cur = conn.execute("SELECT * FROM bid_activity WHERE id = ?", (activity_id,))
            row = cur.fetchone()
            if row:
                current = dict(row)
                rate = fields.get("unit_rate_mh", current["unit_rate_mh"])
                lr = fields.get("labor_rate", current["labor_rate"])
                qty = fields.get("quantity", current["quantity"])
                if rate and lr:
                    fields["unit_price"] = round(rate * lr, 2)
                    if qty:
                        fields["total_price"] = round(rate * qty * lr, 2)
        finally:
            conn.close()

    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [activity_id]

    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE bid_activity SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            vals,
        )
        conn.commit()
        return True
    finally:
        conn.close()


def delete_activity(activity_id: int) -> bool:
    """Delete an activity. Returns True if deleted."""
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM bid_activity WHERE id = ?", (activity_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_activities_for_item(bid_sov_item_id: int) -> list[dict]:
    """Get all activities under a SOV item, ordered by sort_order."""
    conn = get_connection()
    try:
        return _rows_to_dicts(conn.execute(
            "SELECT * FROM bid_activity WHERE bid_sov_item_id = ? ORDER BY sort_order, id",
            (bid_sov_item_id,),
        ).fetchall())
    finally:
        conn.close()


def get_activities_for_bid(bid_id: int) -> list[dict]:
    """Get all activities for a bid (across all SOV items), with parent item info."""
    conn = get_connection()
    try:
        return _rows_to_dicts(conn.execute(
            """SELECT a.*, s.item_number as parent_item_number,
                      s.description as parent_description,
                      s.quantity as parent_quantity, s.unit as parent_unit
               FROM bid_activity a
               JOIN bid_sov_item s ON a.bid_sov_item_id = s.id
               WHERE s.bid_id = ?
               ORDER BY s.sort_order, s.id, a.sort_order, a.id""",
            (bid_id,),
        ).fetchall())
    finally:
        conn.close()


def get_activity_summary_for_item(bid_sov_item_id: int) -> dict:
    """Get summary of activities under a SOV item."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT
                COUNT(*) as activity_count,
                SUM(total_price) as total_price,
                SUM(CASE WHEN unit_rate_mh IS NOT NULL THEN quantity * unit_rate_mh ELSE 0 END) as total_mh
               FROM bid_activity WHERE bid_sov_item_id = ?""",
            (bid_sov_item_id,),
        ).fetchone()
        return dict(row) if row else {"activity_count": 0, "total_price": None, "total_mh": 0}
    finally:
        conn.close()


def get_bid_activity_rollup(bid_id: int) -> dict:
    """Roll up all activities across all SOV items for a bid."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT
                COUNT(a.id) as total_activities,
                COUNT(DISTINCT a.bid_sov_item_id) as items_with_activities,
                SUM(a.total_price) as grand_total,
                SUM(CASE WHEN a.unit_rate_mh IS NOT NULL
                    THEN a.quantity * a.unit_rate_mh ELSE 0 END) as total_mh,
                SUM(CASE WHEN a.cost_code IS NOT NULL THEN 1 ELSE 0 END) as coded_activities
               FROM bid_activity a
               JOIN bid_sov_item s ON a.bid_sov_item_id = s.id
               WHERE s.bid_id = ?""",
            (bid_id,),
        ).fetchone()
        return dict(row) if row else {
            "total_activities": 0, "items_with_activities": 0,
            "grand_total": None, "total_mh": 0, "coded_activities": 0,
        }
    finally:
        conn.close()


def delete_activities_for_item(bid_sov_item_id: int) -> int:
    """Delete all activities for a SOV item. Returns count deleted."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM bid_activity WHERE bid_sov_item_id = ?", (bid_sov_item_id,),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_activity_rate_data(bid_id: int, labor_rate: float = 85.0) -> list[dict]:
    """Get activities with matched KB rates for the Rate Application page.

    Joins activities to rate_library via cost_code. Calculates estimated
    MH, unit price, and total for activities missing rates.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT a.id, a.bid_sov_item_id, a.activity_number, a.description,
                      a.quantity, a.unit, a.unit_rate_mh, a.labor_rate,
                      a.unit_price, a.total_price, a.cost_code, a.discipline,
                      a.source, a.confidence, a.notes,
                      s.item_number as parent_item_number,
                      s.description as parent_description,
                      r.rate as kb_rate, r.unit as kb_unit,
                      r.confidence as kb_confidence,
                      r.description as kb_description,
                      r.source_jobs as kb_source_jobs
               FROM bid_activity a
               JOIN bid_sov_item s ON a.bid_sov_item_id = s.id
               LEFT JOIN rate_library r ON a.cost_code = r.activity
               WHERE s.bid_id = ?
               ORDER BY s.sort_order, s.id, a.sort_order, a.id""",
            (bid_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            kb_rate = d.get("kb_rate")
            qty = d.get("quantity")
            if kb_rate and qty:
                d["est_mh"] = round(kb_rate * qty, 1)
                d["est_unit_price"] = round(kb_rate * labor_rate, 2)
                d["est_total"] = round(kb_rate * qty * labor_rate, 0)
            else:
                d["est_mh"] = None
                d["est_unit_price"] = None
                d["est_total"] = None
            result.append(d)
        return result
    finally:
        conn.close()


def apply_rate_to_activity(activity_id: int, unit_rate_mh: float,
                           labor_rate: float, unit_price: float,
                           total_price: float, source: str,
                           confidence: str) -> bool:
    """Apply a KB rate to an activity."""
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE bid_activity
               SET unit_rate_mh = ?, labor_rate = ?, unit_price = ?,
                   total_price = ?, source = ?, confidence = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (unit_rate_mh, labor_rate, unit_price, total_price,
             source, confidence, activity_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def apply_all_activity_rates(bid_id: int, labor_rate: float = 85.0) -> int:
    """Apply KB rates to all coded activities for a bid. Returns count updated."""
    activities = get_activity_rate_data(bid_id, labor_rate)
    count = 0
    for act in activities:
        if act.get("kb_rate") and act.get("quantity") and act.get("est_total"):
            source = f"KB rate {act['cost_code']} from Job {act.get('kb_source_jobs', '?')}"
            apply_rate_to_activity(
                act["id"], act["kb_rate"], labor_rate,
                act["est_unit_price"], act["est_total"],
                source, act.get("kb_confidence") or "limited",
            )
            count += 1
    return count


def get_activity_rate_summary(bid_id: int, labor_rate: float = 85.0) -> dict:
    """Get summary stats for activity-level rate application."""
    activities = get_activity_rate_data(bid_id, labor_rate)
    total = len(activities)
    has_rate = sum(1 for a in activities if a.get("kb_rate"))
    applied = sum(1 for a in activities if a.get("total_price"))
    est_total = sum(a.get("est_total") or 0 for a in activities)
    return {
        "total_activities": total,
        "has_kb_rate": has_rate,
        "rates_applied": applied,
        "est_total": est_total,
    }


def find_document_by_filename(bid_id: int, filename: str) -> dict | None:
    """Find an existing document by filename within a bid."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM bid_documents WHERE bid_id = ? AND filename = ?",
            (bid_id, filename),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def replace_bid_document(old_doc_id: int, bid_id: int, filename: str,
                         file_type: str, file_size_bytes: int,
                         file_hash: str, doc_category: str,
                         doc_label: str, extraction_status: str,
                         extraction_warning: str, page_count: int,
                         word_count: int, old_version: int) -> int:
    """Replace a document: archive old chunks, insert new doc record.

    Returns the new document ID.
    """
    conn = get_connection()
    try:
        # Delete old chunks
        conn.execute(
            "DELETE FROM bid_document_chunks WHERE document_id = ?", (old_doc_id,)
        )
        # Delete old document record
        conn.execute(
            "DELETE FROM bid_documents WHERE id = ?", (old_doc_id,)
        )

        # Insert new version
        cursor = conn.execute(
            """INSERT INTO bid_documents
               (bid_id, filename, file_type, file_size_bytes, doc_category,
                doc_label, extraction_status, extraction_warning, page_count,
                word_count, file_hash, version, supersedes_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bid_id, filename, file_type, file_size_bytes, doc_category,
             doc_label, extraction_status, extraction_warning, page_count,
             word_count, file_hash, old_version + 1, old_doc_id),
        )
        conn.commit()
        return cursor.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
