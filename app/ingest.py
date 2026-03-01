"""WEIS JCD Ingestion via AI Extraction.

Uses Claude API to parse uploaded JCD markdown into structured JSON
matching the database schema, then validates and inserts into SQLite.
"""

import json
from anthropic import Anthropic
from app.config import ANTHROPIC_API_KEY
from app.database import get_connection

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8192

EXTRACTION_SYSTEM_PROMPT = """You are a construction job cost data extraction engine for Wollam Construction.

Your task: parse a JCD (Job Cost Data) markdown document and return ONLY a single JSON object matching the exact schema below. No commentary, no markdown fences — just valid JSON.

## JSON Schema

{
  "project": {
    "job_number": "string (REQUIRED)",
    "job_name": "string (REQUIRED)",
    "owner": "string or null",
    "project_type": "string or null (e.g., 'Industrial', 'Heavy Civil')",
    "contract_type": "string or null (e.g., 'Cost Plus', 'Lump Sum')",
    "location": "string or null",
    "start_date": "YYYY-MM-DD or null",
    "end_date": "YYYY-MM-DD or null",
    "duration_months": "number or null",
    "contract_value": "number or null",
    "total_actual_cost": "number or null",
    "total_budget_cost": "number or null",
    "total_actual_mh": "number or null",
    "total_budget_mh": "number or null",
    "building_sf": "number or null",
    "cpi": "number or null",
    "projected_margin": "number or null",
    "notes": "string or null"
  },
  "discipline": {
    "discipline_code": "string (REQUIRED — e.g., CONCRETE, EARTHWORK, STEEL, PIPING, MECHANICAL, ELECTRICAL, BUILDING, GCONDITIONS)",
    "discipline_name": "string (REQUIRED — full name like 'Concrete', 'Structural Steel')",
    "budget_cost": "number or null",
    "actual_cost": "number or null",
    "variance_cost": "number or null",
    "variance_pct": "number or null",
    "budget_mh": "number or null",
    "actual_mh": "number or null",
    "variance_mh": "number or null",
    "self_perform_cost": "number or null",
    "subcontract_cost": "number or null",
    "material_cost": "number or null",
    "notes": "string or null"
  },
  "cost_codes": [
    {
      "cost_code": "string (REQUIRED)",
      "description": "string (REQUIRED)",
      "unit": "string or null",
      "budget_qty": "number or null",
      "actual_qty": "number or null",
      "budget_cost": "number or null",
      "actual_cost": "number or null",
      "budget_mh": "number or null",
      "actual_mh": "number or null",
      "budget_unit_cost": "number or null",
      "actual_unit_cost": "number or null",
      "notes": "string or null"
    }
  ],
  "unit_costs": [
    {
      "activity": "string (REQUIRED)",
      "unit": "string (REQUIRED — e.g., MH/SF, $/CY, MH/EA)",
      "budget_rate": "number or null",
      "actual_rate": "number or null",
      "recommended_rate": "number or null",
      "rate_basis": "string or null",
      "rate_notes": "string or null",
      "mh_per_unit_budget": "number or null",
      "mh_per_unit_actual": "number or null",
      "mh_per_unit_rec": "number or null",
      "project_conditions": "string or null",
      "confidence": "HIGH, MEDIUM, LOW, or ASSUMPTION"
    }
  ],
  "production_rates": [
    {
      "activity": "string (REQUIRED)",
      "unit": "string (REQUIRED)",
      "production_unit": "string (REQUIRED — e.g., CY/hr, SF/hr, TON/shift)",
      "budget_rate": "number or null",
      "actual_rate": "number or null",
      "recommended_rate": "number or null",
      "crew_size": "integer or null",
      "equipment_primary": "string or null",
      "equipment_secondary": "string or null",
      "conditions": "string or null",
      "notes": "string or null",
      "confidence": "HIGH, MEDIUM, LOW, or ASSUMPTION"
    }
  ],
  "crew_configurations": [
    {
      "activity": "string (REQUIRED)",
      "crew_description": "string (REQUIRED)",
      "foreman": "integer default 0",
      "journeyman": "integer default 0",
      "apprentice": "integer default 0",
      "laborer": "integer default 0",
      "operator": "integer default 0",
      "ironworker": "integer default 0",
      "pipefitter": "integer default 0",
      "electrician": "integer default 0",
      "other_trades": "string or null",
      "total_crew_size": "integer or null",
      "equipment_list": "string or null",
      "shift_hours": "number default 10",
      "notes": "string or null"
    }
  ],
  "material_costs": [
    {
      "cost_code": "string or null",
      "material_type": "string (REQUIRED)",
      "material_description": "string or null",
      "vendor": "string or null",
      "unit": "string or null",
      "quantity": "number or null",
      "unit_cost": "number or null",
      "total_cost": "number or null",
      "po_number": "string or null",
      "delivery_date": "YYYY-MM-DD or null",
      "notes": "string or null"
    }
  ],
  "subcontractors": [
    {
      "cost_code": "string or null",
      "sub_name": "string or null",
      "scope_description": "string (REQUIRED)",
      "scope_category": "string or null",
      "contract_amount": "number or null",
      "actual_amount": "number or null",
      "unit": "string or null",
      "quantity": "number or null",
      "unit_cost": "number or null",
      "sub_pct_of_discipline": "number or null",
      "performance_rating": "string or null",
      "would_use_again": "boolean or null",
      "notes": "string or null"
    }
  ],
  "lessons_learned": [
    {
      "category": "string (REQUIRED — one of: estimating, production_variance, scope_gap, material, design, subcontractor)",
      "severity": "HIGH, MEDIUM, or LOW",
      "title": "string (REQUIRED)",
      "description": "string (REQUIRED)",
      "impact": "string or null",
      "recommendation": "string or null",
      "applies_to": "string or null"
    }
  ],
  "_extraction_meta": {
    "file_type": "string (e.g., 'discipline_section', 'master_summary', 'full_jcd')",
    "sections_found": ["list of section names found in the document"],
    "sections_missing": ["list of expected sections not found"],
    "data_quality": "complete, partial, or minimal",
    "quality_notes": "string explaining quality assessment",
    "record_counts": {
      "cost_codes": 0,
      "unit_costs": 0,
      "production_rates": 0,
      "crew_configurations": 0,
      "material_costs": 0,
      "subcontractors": 0,
      "lessons_learned": 0
    }
  }
}

## Extraction Rules

1. Extract ALL data present in the document — do not skip records.
2. For missing fields, use null — never fabricate data.
3. Clean numbers: remove "$", ",", "%" signs. Convert "1,234.56" to 1234.56.
4. Discipline codes must be uppercase: CONCRETE, EARTHWORK, STEEL, PIPING, MECHANICAL, ELECTRICAL, BUILDING, GCONDITIONS.
5. Confidence levels: assign based on data quality (actual data = HIGH, budget only = MEDIUM, estimated = LOW, no data = ASSUMPTION).
6. If the document is a discipline section, fill in project-level fields only if they appear in the document.
7. If arrays have no data (e.g., no production rates found), return empty arrays [].
8. The _extraction_meta section is REQUIRED — always assess what was found and what's missing.
9. Return ONLY the JSON object. No explanation, no markdown code fences.
"""


def extract_jcd(markdown_content: str, filename: str, job_number: str) -> dict:
    """Send JCD markdown to Claude for structured extraction.

    Args:
        markdown_content: Full markdown text of the JCD file
        filename: Original filename (for context)
        job_number: Job number this data belongs to

    Returns:
        Parsed dict matching the extraction schema, or dict with 'error' key on failure.
    """
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    user_message = (
        f"Job Number: {job_number}\n"
        f"Filename: {filename}\n"
        f"---BEGIN JCD MARKDOWN---\n"
        f"{markdown_content}\n"
        f"---END JCD MARKDOWN---"
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        text = response.content[0].text.strip()

        # Strip markdown fences if Claude wrapped the JSON anyway
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        data = json.loads(text)

        # Ensure job_number is set
        if "project" in data:
            data["project"]["job_number"] = job_number

        return data

    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse extraction response as JSON: {e}"}
    except Exception as e:
        return {"error": f"Extraction API call failed: {e}"}


def validate_extraction(data: dict) -> list[str]:
    """Validate extracted data and return list of warnings.

    Returns empty list if everything looks good.
    """
    warnings = []

    if "error" in data:
        warnings.append(f"Extraction failed: {data['error']}")
        return warnings

    # Check required project fields
    project = data.get("project", {})
    if not project.get("job_number"):
        warnings.append("Missing required field: project.job_number")
    if not project.get("job_name"):
        warnings.append("Missing required field: project.job_name")

    # Check discipline
    discipline = data.get("discipline", {})
    if not discipline.get("discipline_code"):
        warnings.append("No discipline code detected — data may be a master summary")
    if not discipline.get("discipline_name"):
        warnings.append("No discipline name detected")

    # Flag empty data tables
    table_keys = [
        "cost_codes", "unit_costs", "production_rates",
        "crew_configurations", "material_costs", "subcontractors",
        "lessons_learned",
    ]
    empty_tables = [k for k in table_keys if not data.get(k)]
    if empty_tables:
        warnings.append(f"Empty data sections: {', '.join(empty_tables)}")

    # Check extraction meta quality
    meta = data.get("_extraction_meta", {})
    quality = meta.get("data_quality", "unknown")
    if quality == "minimal":
        warnings.append("Data quality assessed as MINIMAL — very limited data extracted")
    elif quality == "partial":
        warnings.append("Data quality assessed as PARTIAL — some sections missing")

    if meta.get("sections_missing"):
        warnings.append(f"Missing sections: {', '.join(meta['sections_missing'])}")

    return warnings


def ingest_extracted_data(data: dict, cataloged_by: str = "WEIS Upload") -> dict:
    """Insert extracted JCD data into the database.

    Creates/updates project record. If project already exists, updates only
    null fields (doesn't overwrite real data). Creates discipline and inserts
    all child records.

    Args:
        data: Validated extraction dict from extract_jcd()
        cataloged_by: Who cataloged this data

    Returns:
        Dict with project_id, discipline_id, record_counts, data_quality
    """
    conn = get_connection()
    try:
        project_data = data.get("project", {})
        discipline_data = data.get("discipline", {})
        meta = data.get("_extraction_meta", {})

        # --- Project ---
        job_number = project_data["job_number"]
        existing = conn.execute(
            "SELECT id FROM projects WHERE job_number = ?", (job_number,)
        ).fetchone()

        if existing:
            project_id = existing["id"]
            # Update only null fields on existing project
            updatable = [
                "job_name", "owner", "project_type", "contract_type", "location",
                "start_date", "end_date", "duration_months", "contract_value",
                "total_actual_cost", "total_budget_cost", "total_actual_mh",
                "total_budget_mh", "building_sf", "cpi", "projected_margin", "notes",
            ]
            for field in updatable:
                new_val = project_data.get(field)
                if new_val is not None:
                    conn.execute(
                        f"UPDATE projects SET {field} = COALESCE({field}, ?) WHERE id = ?",
                        (new_val, project_id),
                    )
        else:
            quality = meta.get("data_quality", "partial")
            cursor = conn.execute(
                """INSERT INTO projects (
                    job_number, job_name, owner, project_type, contract_type,
                    location, start_date, end_date, duration_months,
                    contract_value, total_actual_cost, total_budget_cost,
                    total_actual_mh, total_budget_mh, building_sf, cpi,
                    projected_margin, notes, cataloged_date, cataloged_by,
                    data_quality
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, DATE('now'), ?, ?)""",
                (
                    job_number,
                    project_data.get("job_name", f"Job {job_number}"),
                    project_data.get("owner"),
                    project_data.get("project_type"),
                    project_data.get("contract_type"),
                    project_data.get("location"),
                    project_data.get("start_date"),
                    project_data.get("end_date"),
                    project_data.get("duration_months"),
                    project_data.get("contract_value"),
                    project_data.get("total_actual_cost"),
                    project_data.get("total_budget_cost"),
                    project_data.get("total_actual_mh"),
                    project_data.get("total_budget_mh"),
                    project_data.get("building_sf"),
                    project_data.get("cpi"),
                    project_data.get("projected_margin"),
                    project_data.get("notes"),
                    cataloged_by,
                    quality,
                ),
            )
            project_id = cursor.lastrowid

        # --- Discipline ---
        discipline_id = None
        disc_code = discipline_data.get("discipline_code")
        if disc_code:
            # Check if discipline already exists for this project
            existing_disc = conn.execute(
                "SELECT id FROM disciplines WHERE project_id = ? AND discipline_code = ?",
                (project_id, disc_code),
            ).fetchone()

            if existing_disc:
                discipline_id = existing_disc["id"]
            else:
                cursor = conn.execute(
                    """INSERT INTO disciplines (
                        project_id, discipline_code, discipline_name,
                        budget_cost, actual_cost, variance_cost, variance_pct,
                        budget_mh, actual_mh, variance_mh,
                        self_perform_cost, subcontract_cost, material_cost, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        project_id,
                        disc_code,
                        discipline_data.get("discipline_name", disc_code),
                        discipline_data.get("budget_cost"),
                        discipline_data.get("actual_cost"),
                        discipline_data.get("variance_cost"),
                        discipline_data.get("variance_pct"),
                        discipline_data.get("budget_mh"),
                        discipline_data.get("actual_mh"),
                        discipline_data.get("variance_mh"),
                        discipline_data.get("self_perform_cost"),
                        discipline_data.get("subcontract_cost"),
                        discipline_data.get("material_cost"),
                        discipline_data.get("notes"),
                    ),
                )
                discipline_id = cursor.lastrowid

        # --- Child Records ---
        record_counts = {}

        # Cost Codes
        cost_codes = data.get("cost_codes", [])
        for cc in cost_codes:
            # Calculate derived fields
            budget_mh_per_unit = None
            actual_mh_per_unit = None
            over_budget = False

            if cc.get("budget_mh") and cc.get("budget_qty") and cc["budget_qty"] != 0:
                budget_mh_per_unit = cc["budget_mh"] / cc["budget_qty"]
            if cc.get("actual_mh") and cc.get("actual_qty") and cc["actual_qty"] != 0:
                actual_mh_per_unit = cc["actual_mh"] / cc["actual_qty"]
            if cc.get("actual_cost") and cc.get("budget_cost"):
                over_budget = cc["actual_cost"] > cc["budget_cost"]

            conn.execute(
                """INSERT INTO cost_codes (
                    project_id, discipline_id, cost_code, description, unit,
                    budget_qty, actual_qty, budget_cost, actual_cost,
                    budget_mh, actual_mh, budget_unit_cost, actual_unit_cost,
                    budget_mh_per_unit, actual_mh_per_unit, over_budget_flag, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id, discipline_id,
                    cc["cost_code"], cc["description"], cc.get("unit"),
                    cc.get("budget_qty"), cc.get("actual_qty"),
                    cc.get("budget_cost"), cc.get("actual_cost"),
                    cc.get("budget_mh"), cc.get("actual_mh"),
                    cc.get("budget_unit_cost"), cc.get("actual_unit_cost"),
                    budget_mh_per_unit, actual_mh_per_unit,
                    over_budget, cc.get("notes"),
                ),
            )
        record_counts["cost_codes"] = len(cost_codes)

        # Unit Costs
        unit_costs = data.get("unit_costs", [])
        for uc in unit_costs:
            conn.execute(
                """INSERT INTO unit_costs (
                    project_id, discipline_id, activity, unit,
                    budget_rate, actual_rate, recommended_rate,
                    rate_basis, rate_notes,
                    mh_per_unit_budget, mh_per_unit_actual, mh_per_unit_rec,
                    project_conditions, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id, discipline_id,
                    uc["activity"], uc["unit"],
                    uc.get("budget_rate"), uc.get("actual_rate"),
                    uc.get("recommended_rate"),
                    uc.get("rate_basis"), uc.get("rate_notes"),
                    uc.get("mh_per_unit_budget"), uc.get("mh_per_unit_actual"),
                    uc.get("mh_per_unit_rec"),
                    uc.get("project_conditions"),
                    uc.get("confidence", "MEDIUM"),
                ),
            )
        record_counts["unit_costs"] = len(unit_costs)

        # Production Rates
        prod_rates = data.get("production_rates", [])
        for pr in prod_rates:
            conn.execute(
                """INSERT INTO production_rates (
                    project_id, discipline_id, activity, unit, production_unit,
                    budget_rate, actual_rate, recommended_rate,
                    crew_size, equipment_primary, equipment_secondary,
                    conditions, notes, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id, discipline_id,
                    pr["activity"], pr["unit"], pr["production_unit"],
                    pr.get("budget_rate"), pr.get("actual_rate"),
                    pr.get("recommended_rate"),
                    pr.get("crew_size"), pr.get("equipment_primary"),
                    pr.get("equipment_secondary"),
                    pr.get("conditions"), pr.get("notes"),
                    pr.get("confidence", "MEDIUM"),
                ),
            )
        record_counts["production_rates"] = len(prod_rates)

        # Crew Configurations
        crews = data.get("crew_configurations", [])
        for cr in crews:
            conn.execute(
                """INSERT INTO crew_configurations (
                    project_id, discipline_id, activity, crew_description,
                    foreman, journeyman, apprentice, laborer, operator,
                    ironworker, pipefitter, electrician, other_trades,
                    total_crew_size, equipment_list, shift_hours, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id, discipline_id,
                    cr["activity"], cr["crew_description"],
                    cr.get("foreman", 0), cr.get("journeyman", 0),
                    cr.get("apprentice", 0), cr.get("laborer", 0),
                    cr.get("operator", 0), cr.get("ironworker", 0),
                    cr.get("pipefitter", 0), cr.get("electrician", 0),
                    cr.get("other_trades"),
                    cr.get("total_crew_size"), cr.get("equipment_list"),
                    cr.get("shift_hours", 10), cr.get("notes"),
                ),
            )
        record_counts["crew_configurations"] = len(crews)

        # Material Costs
        materials = data.get("material_costs", [])
        for mc in materials:
            conn.execute(
                """INSERT INTO material_costs (
                    project_id, discipline_id, cost_code, material_type,
                    material_description, vendor, unit, quantity,
                    unit_cost, total_cost, po_number, delivery_date, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id, discipline_id,
                    mc.get("cost_code"), mc["material_type"],
                    mc.get("material_description"), mc.get("vendor"),
                    mc.get("unit"), mc.get("quantity"),
                    mc.get("unit_cost"), mc.get("total_cost"),
                    mc.get("po_number"), mc.get("delivery_date"),
                    mc.get("notes"),
                ),
            )
        record_counts["material_costs"] = len(materials)

        # Subcontractors
        subs = data.get("subcontractors", [])
        for s in subs:
            conn.execute(
                """INSERT INTO subcontractors (
                    project_id, discipline_id, cost_code, sub_name,
                    scope_description, scope_category,
                    contract_amount, actual_amount, unit, quantity, unit_cost,
                    sub_pct_of_discipline, performance_rating, would_use_again, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id, discipline_id,
                    s.get("cost_code"), s.get("sub_name"),
                    s["scope_description"], s.get("scope_category"),
                    s.get("contract_amount"), s.get("actual_amount"),
                    s.get("unit"), s.get("quantity"), s.get("unit_cost"),
                    s.get("sub_pct_of_discipline"), s.get("performance_rating"),
                    s.get("would_use_again"), s.get("notes"),
                ),
            )
        record_counts["subcontractors"] = len(subs)

        # Lessons Learned
        lessons = data.get("lessons_learned", [])
        for ll in lessons:
            conn.execute(
                """INSERT INTO lessons_learned (
                    project_id, discipline_id, category, severity,
                    title, description, impact, recommendation, applies_to
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id, discipline_id,
                    ll["category"], ll.get("severity", "MEDIUM"),
                    ll["title"], ll["description"],
                    ll.get("impact"), ll.get("recommendation"),
                    ll.get("applies_to"),
                ),
            )
        record_counts["lessons_learned"] = len(lessons)

        conn.commit()

        # Update project data_quality based on completeness
        total = sum(record_counts.values())
        non_empty = sum(1 for v in record_counts.values() if v > 0)
        if non_empty >= 5 and total >= 20:
            quality = "complete"
        elif non_empty >= 2 and total >= 5:
            quality = "partial"
        else:
            quality = "minimal"

        conn.execute(
            "UPDATE projects SET data_quality = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (quality, project_id),
        )
        conn.commit()

        return {
            "project_id": project_id,
            "discipline_id": discipline_id,
            "job_number": job_number,
            "discipline_code": disc_code,
            "record_counts": record_counts,
            "total_records": sum(record_counts.values()),
            "data_quality": quality,
        }

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
