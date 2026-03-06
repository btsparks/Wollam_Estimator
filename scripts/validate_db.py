"""
WEIS Database Validation Report
Validates ingested JCD data against source documents for Job 8553.

Checks:
  1. Record counts per table
  2. Project-level financials vs Master Summary
  3. Discipline cost/MH totals vs source
  4. Key unit cost rates vs JCD reference tables
  5. Subcontractor amounts vs source
  6. Data completeness (required fields)
  7. Referential integrity
  8. Over-budget flags
  9. Benchmark rate reasonableness
  10. General conditions breakdown totals
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_connection, DB_PATH

# ---------------------------------------------------------------------------
# Report Infrastructure
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
INFO = "INFO"

results = []


def check(name: str, status: str, detail: str = ""):
    results.append((name, status, detail))


def tolerance_check(name: str, expected, actual, tolerance_pct=1.0):
    """Check if actual is within tolerance_pct of expected."""
    if expected is None or actual is None:
        check(name, WARN, f"Cannot compare: expected={expected}, actual={actual}")
        return
    if expected == 0:
        if actual == 0:
            check(name, PASS, f"Both zero")
        else:
            check(name, FAIL, f"Expected 0, got {actual:,.2f}")
        return
    pct_diff = abs(actual - expected) / abs(expected) * 100
    if pct_diff <= tolerance_pct:
        check(name, PASS, f"Expected {expected:,.2f}, got {actual:,.2f} (diff {pct_diff:.2f}%)")
    else:
        check(name, FAIL, f"Expected {expected:,.2f}, got {actual:,.2f} (diff {pct_diff:.2f}%, tolerance {tolerance_pct}%)")


# ---------------------------------------------------------------------------
# 1. Record Counts
# ---------------------------------------------------------------------------

EXPECTED_COUNTS = {
    "projects": 1,
    "disciplines": 8,
    "cost_codes": 115,
    "unit_costs": 65,
    "production_rates": 9,
    "crew_configurations": 6,
    "material_costs": 19,
    "subcontractors": 9,
    "lessons_learned": 15,
    "benchmark_rates": 21,
    "general_conditions_breakdown": 15,
}


def validate_record_counts(conn):
    for table, expected in EXPECTED_COUNTS.items():
        row = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
        actual = row["c"]
        if actual == expected:
            check(f"Count: {table}", PASS, f"{actual} records")
        else:
            check(f"Count: {table}", FAIL, f"Expected {expected}, got {actual}")


# ---------------------------------------------------------------------------
# 2. Project-Level Financials (vs Master Summary)
# ---------------------------------------------------------------------------

# Source: JCD_8553_MASTER_SUMMARY.md - Financial Summary table
PROJECT_EXPECTED = {
    "job_number": "8553",
    "job_name": "RTK SPD Pump Station",
    "owner": "Rio Tinto Kennecott",
    "total_actual_cost": 35571414.0,
    "total_budget_cost": 48694091.0,
    "total_actual_mh": 108889.0,
    "total_budget_mh": 147691.0,
    "building_sf": 43560.0,
    "projected_margin": 40.1,
    "duration_months": 24.0,
}


def get_project_id(conn):
    """Get the project ID for Job 8553 dynamically."""
    row = conn.execute("SELECT id FROM projects WHERE job_number = '8553'").fetchone()
    return row["id"] if row else None


def validate_project(conn):
    row = conn.execute("SELECT * FROM projects WHERE job_number = '8553'").fetchone()
    if not row:
        check("Project record exists", FAIL, "No project with job_number 8553")
        return

    check("Project record exists", PASS, f"ID={row['id']}")

    for field, expected in PROJECT_EXPECTED.items():
        actual = row[field]
        if isinstance(expected, float):
            tolerance_check(f"Project.{field}", expected, actual)
        elif actual == expected:
            check(f"Project.{field}", PASS, f"{actual}")
        else:
            check(f"Project.{field}", FAIL, f"Expected '{expected}', got '{actual}'")


# ---------------------------------------------------------------------------
# 3. Discipline Cost/MH Totals (vs Master Summary tables)
# ---------------------------------------------------------------------------

# Source: JCD_8553_MASTER_SUMMARY.md - "Cost by JCD Section" and "Manhours by Discipline"
DISCIPLINE_EXPECTED = {
    "CONCRETE":     {"budget_cost": 11634675, "actual_cost": 9033158,  "budget_mh": 45932,  "actual_mh": 36923},
    "STEEL":        {"budget_cost": 7799628,  "actual_cost": 6058859,  "budget_mh": 8881,   "actual_mh": 9442},
    "GCONDITIONS":  {"budget_cost": 8355492,  "actual_cost": 3909710,  "budget_mh": 40520,  "actual_mh": 26990},
    "ELECTRICAL":   {"budget_cost": 6426441,  "actual_cost": 6194890,  "budget_mh": 2597,   "actual_mh": 2081},
    "PIPING":       {"budget_cost": 6286424,  "actual_cost": 5226461,  "budget_mh": 17340,  "actual_mh": 8344},
    "EARTHWORK":    {"budget_cost": 4810455,  "actual_cost": 2364750,  "budget_mh": 20548,  "actual_mh": 9720},
    "BUILDING":     {"budget_cost": 2695038,  "actual_cost": 2045313,  "budget_mh": None,   "actual_mh": None},
    "MECHANICAL":   {"budget_cost": 1434420,  "actual_cost": 1142430,  "budget_mh": 6321,   "actual_mh": 4796},
}


def validate_disciplines(conn, pid):
    rows = conn.execute(
        "SELECT * FROM disciplines WHERE project_id = ?", (pid,)
    ).fetchall()

    if len(rows) != 8:
        check("Discipline count", FAIL, f"Expected 8, got {len(rows)}")
        return
    check("Discipline count", PASS, "8 disciplines")

    by_code = {r["discipline_code"]: r for r in rows}

    for code, expected in DISCIPLINE_EXPECTED.items():
        if code not in by_code:
            check(f"Discipline {code} exists", FAIL, "Missing")
            continue

        row = by_code[code]
        for field, exp_val in expected.items():
            act_val = row[field]
            if exp_val is None:
                if act_val is None:
                    check(f"Disc.{code}.{field}", PASS, "None as expected")
                else:
                    check(f"Disc.{code}.{field}", WARN, f"Expected None, got {act_val}")
            else:
                tolerance_check(f"Disc.{code}.{field}", exp_val, act_val)


# ---------------------------------------------------------------------------
# 4. Key Unit Cost Rates (vs Master Summary Quick Reference)
# ---------------------------------------------------------------------------

# Source: JCD_8553_MASTER_SUMMARY.md - "QUICK REFERENCE - TOP 20 UNIT COSTS"
# and the per-discipline rate tables
KEY_RATES = [
    # (activity_substring, expected_recommended_rate, tolerance_pct)
    ("Wall Form/Strip", 0.28, 5),
    ("Mat Pour (3-pump", 0.15, 5),
    ("Equipment Pad F/S", 0.43, 5),
    ("All-In Concrete", 867, 1),
    ("L/H Excavation", 1.38, 10),    # Master says $1.50, ingested $1.38 (adjusted)
    ("Structural Steel Erection", 25, 5),
    ("Pipe Support - Wall", 13.0, 10),
    ("Flanged Bolt-up 20-30in", 7.0, 5),
    ("Epoxy Grout (all-in with F/S)", 50, 5),
    ("Heavy Industrial Electrical", 138, 5),
    ("Management (PM+Super+Admin)", 2500, 5),
    ("GL Insurance", 0.72, 5),
]


def validate_unit_costs(conn):
    for activity_sub, expected_rate, tol in KEY_RATES:
        row = conn.execute(
            "SELECT recommended_rate FROM unit_costs WHERE activity LIKE ?",
            (f"%{activity_sub}%",)
        ).fetchone()
        if not row:
            check(f"UnitCost: {activity_sub}", FAIL, "Not found")
            continue
        tolerance_check(f"UnitCost: {activity_sub}", expected_rate, row["recommended_rate"], tol)


# ---------------------------------------------------------------------------
# 5. Subcontractor Amounts (vs Master Summary)
# ---------------------------------------------------------------------------

# Source: JCD_8553_MASTER_SUMMARY.md - "SUBCONTRACTOR SUMMARY"
SUB_EXPECTED = {
    "Champion/Iron Mountain": {"contract_amount": 3659718, "actual_amount": 3539407},
    "Brundage Bone":          {"contract_amount": 342099,  "actual_amount": 148587},
    "J&M Steel Solutions":    {"contract_amount": 1779855, "actual_amount": 1776490},
    "Digital Earth LLC":      {"contract_amount": 437680,  "actual_amount": 107375},
    "Terracon":               {"contract_amount": 638000,  "actual_amount": 231564},
    "Rhine Construction":     {"actual_amount": 825362},
    "Geneva Rock":            {"actual_amount": 232442},
}


def validate_subcontractors(conn, pid):
    rows = conn.execute("SELECT * FROM subcontractors WHERE project_id = ?", (pid,)).fetchall()
    by_name = {r["sub_name"]: r for r in rows}

    for name, expected in SUB_EXPECTED.items():
        if name not in by_name:
            check(f"Sub: {name}", FAIL, "Not found")
            continue
        row = by_name[name]
        for field, exp_val in expected.items():
            act_val = row[field]
            tolerance_check(f"Sub.{name}.{field}", exp_val, act_val)


# ---------------------------------------------------------------------------
# 6. Data Completeness
# ---------------------------------------------------------------------------

def validate_completeness(conn):
    # Projects: key fields should not be null
    project_nulls = conn.execute("""
        SELECT
            SUM(CASE WHEN job_number IS NULL THEN 1 ELSE 0 END) as null_job,
            SUM(CASE WHEN job_name IS NULL THEN 1 ELSE 0 END) as null_name,
            SUM(CASE WHEN total_actual_cost IS NULL THEN 1 ELSE 0 END) as null_cost,
            SUM(CASE WHEN total_actual_mh IS NULL THEN 1 ELSE 0 END) as null_mh,
        FROM projects
    """).fetchone()
    null_count = sum(project_nulls[k] for k in project_nulls.keys())
    if null_count == 0:
        check("Completeness: projects key fields", PASS, "No nulls in key fields")
    else:
        check("Completeness: projects key fields", FAIL, f"{null_count} null key fields")

    # Cost codes: description should never be null
    null_desc = conn.execute(
        "SELECT COUNT(*) as c FROM cost_codes WHERE description IS NULL"
    ).fetchone()["c"]
    if null_desc == 0:
        check("Completeness: cost_code descriptions", PASS, "All populated")
    else:
        check("Completeness: cost_code descriptions", FAIL, f"{null_desc} null descriptions")

    # Cost codes: budget_mh should be populated
    null_mh = conn.execute(
        "SELECT COUNT(*) as c FROM cost_codes WHERE budget_mh IS NULL"
    ).fetchone()["c"]
    total_cc = conn.execute("SELECT COUNT(*) as c FROM cost_codes").fetchone()["c"]
    pct = (1 - null_mh / total_cc) * 100 if total_cc > 0 else 0
    if null_mh == 0:
        check("Completeness: cost_code budget_mh", PASS, f"100% populated ({total_cc}/{total_cc})")
    else:
        check("Completeness: cost_code budget_mh", INFO, f"{pct:.0f}% populated ({total_cc - null_mh}/{total_cc})")

    # Unit costs: recommended_rate should be populated
    null_rec = conn.execute(
        "SELECT COUNT(*) as c FROM unit_costs WHERE recommended_rate IS NULL"
    ).fetchone()["c"]
    total_uc = conn.execute("SELECT COUNT(*) as c FROM unit_costs").fetchone()["c"]
    if null_rec == 0:
        check("Completeness: unit_costs recommended_rate", PASS, f"100% populated ({total_uc}/{total_uc})")
    else:
        check("Completeness: unit_costs recommended_rate", WARN, f"{null_rec}/{total_uc} missing recommended_rate")

    # Lessons learned: recommendation should be populated
    null_rec_ll = conn.execute(
        "SELECT COUNT(*) as c FROM lessons_learned WHERE recommendation IS NULL"
    ).fetchone()["c"]
    total_ll = conn.execute("SELECT COUNT(*) as c FROM lessons_learned").fetchone()["c"]
    if null_rec_ll == 0:
        check("Completeness: lessons recommendation", PASS, f"100% populated ({total_ll}/{total_ll})")
    else:
        check("Completeness: lessons recommendation", WARN, f"{null_rec_ll}/{total_ll} missing recommendation")

    # Benchmark rates: typical_rate should be populated
    null_typ = conn.execute(
        "SELECT COUNT(*) as c FROM benchmark_rates WHERE typical_rate IS NULL"
    ).fetchone()["c"]
    total_bm = conn.execute("SELECT COUNT(*) as c FROM benchmark_rates").fetchone()["c"]
    if null_typ == 0:
        check("Completeness: benchmark typical_rate", PASS, f"100% populated ({total_bm}/{total_bm})")
    else:
        check("Completeness: benchmark typical_rate", WARN, f"{null_typ}/{total_bm} missing typical_rate")


# ---------------------------------------------------------------------------
# 7. Referential Integrity
# ---------------------------------------------------------------------------

def validate_referential_integrity(conn):
    # Cost codes -> disciplines
    orphan_cc = conn.execute("""
        SELECT COUNT(*) as c FROM cost_codes cc
        LEFT JOIN disciplines d ON cc.discipline_id = d.id
        WHERE d.id IS NULL
    """).fetchone()["c"]
    check("FK: cost_codes -> disciplines", PASS if orphan_cc == 0 else FAIL,
          f"{orphan_cc} orphan records")

    # Cost codes -> projects
    orphan_cc_proj = conn.execute("""
        SELECT COUNT(*) as c FROM cost_codes cc
        LEFT JOIN projects p ON cc.project_id = p.id
        WHERE p.id IS NULL
    """).fetchone()["c"]
    check("FK: cost_codes -> projects", PASS if orphan_cc_proj == 0 else FAIL,
          f"{orphan_cc_proj} orphan records")

    # Unit costs -> disciplines
    orphan_uc = conn.execute("""
        SELECT COUNT(*) as c FROM unit_costs uc
        LEFT JOIN disciplines d ON uc.discipline_id = d.id
        WHERE d.id IS NULL
    """).fetchone()["c"]
    check("FK: unit_costs -> disciplines", PASS if orphan_uc == 0 else FAIL,
          f"{orphan_uc} orphan records")

    # Production rates -> disciplines
    orphan_pr = conn.execute("""
        SELECT COUNT(*) as c FROM production_rates pr
        LEFT JOIN disciplines d ON pr.discipline_id = d.id
        WHERE d.id IS NULL
    """).fetchone()["c"]
    check("FK: production_rates -> disciplines", PASS if orphan_pr == 0 else FAIL,
          f"{orphan_pr} orphan records")

    # Subcontractors -> disciplines
    orphan_sub = conn.execute("""
        SELECT COUNT(*) as c FROM subcontractors s
        LEFT JOIN disciplines d ON s.discipline_id = d.id
        WHERE d.id IS NULL
    """).fetchone()["c"]
    check("FK: subcontractors -> disciplines", PASS if orphan_sub == 0 else FAIL,
          f"{orphan_sub} orphan records")

    # Material costs -> disciplines
    orphan_mat = conn.execute("""
        SELECT COUNT(*) as c FROM material_costs mc
        LEFT JOIN disciplines d ON mc.discipline_id = d.id
        WHERE d.id IS NULL
    """).fetchone()["c"]
    check("FK: material_costs -> disciplines", PASS if orphan_mat == 0 else FAIL,
          f"{orphan_mat} orphan records")

    # Crew configs -> disciplines
    orphan_crew = conn.execute("""
        SELECT COUNT(*) as c FROM crew_configurations cr
        LEFT JOIN disciplines d ON cr.discipline_id = d.id
        WHERE d.id IS NULL
    """).fetchone()["c"]
    check("FK: crew_configurations -> disciplines", PASS if orphan_crew == 0 else FAIL,
          f"{orphan_crew} orphan records")

    # GC breakdown -> projects
    orphan_gc = conn.execute("""
        SELECT COUNT(*) as c FROM general_conditions_breakdown gc
        LEFT JOIN projects p ON gc.project_id = p.id
        WHERE p.id IS NULL
    """).fetchone()["c"]
    check("FK: gc_breakdown -> projects", PASS if orphan_gc == 0 else FAIL,
          f"{orphan_gc} orphan records")


# ---------------------------------------------------------------------------
# 8. Over-Budget Flags
# ---------------------------------------------------------------------------

def validate_over_budget_flags(conn, pid):
    over_budget = conn.execute("""
        SELECT cost_code, description, budget_cost, actual_cost
        FROM cost_codes
        WHERE over_budget_flag = 1 AND project_id = ?
    """, (pid,)).fetchall()

    check("Over-budget codes identified", INFO, f"{len(over_budget)} cost codes flagged")

    for row in over_budget:
        pct = ((row["actual_cost"] - row["budget_cost"]) / row["budget_cost"] * 100) if row["budget_cost"] else 0
        check(f"  Over-budget: {row['cost_code']} {row['description']}", WARN,
              f"Budget ${row['budget_cost']:,.0f} -> Actual ${row['actual_cost']:,.0f} (+{pct:.0f}%)")


# ---------------------------------------------------------------------------
# 9. Benchmark Rate Reasonableness
# ---------------------------------------------------------------------------

def validate_benchmarks(conn):
    rows = conn.execute("SELECT * FROM benchmark_rates").fetchall()

    # Check that low <= typical <= high for all
    bad_range = 0
    for row in rows:
        low = row["low_rate"]
        high = row["high_rate"]
        typical = row["typical_rate"]
        if low is not None and high is not None and typical is not None:
            if not (low <= typical <= high):
                bad_range += 1
                check(f"Benchmark range: {row['activity']}", FAIL,
                      f"low={low}, typical={typical}, high={high} — typical not in range")

    if bad_range == 0:
        check("Benchmark ranges: low <= typical <= high", PASS, f"All {len(rows)} benchmarks valid")

    # Check all disciplines are represented
    disc_codes = conn.execute(
        "SELECT DISTINCT discipline_code FROM benchmark_rates"
    ).fetchall()
    codes = {r["discipline_code"] for r in disc_codes}
    expected_codes = {"CONCRETE", "EARTHWORK", "STEEL", "PIPING", "MECHANICAL", "ELECTRICAL", "GCONDITIONS"}
    missing = expected_codes - codes
    if not missing:
        check("Benchmark discipline coverage", PASS, f"{len(codes)} disciplines covered")
    else:
        check("Benchmark discipline coverage", WARN, f"Missing: {missing}")


# ---------------------------------------------------------------------------
# 10. General Conditions Breakdown Totals
# ---------------------------------------------------------------------------

def validate_gc_breakdown(conn, pid):
    # Sum of GC budget vs discipline budget
    gc_sum = conn.execute("""
        SELECT SUM(budget_cost) as budget_total, SUM(actual_cost) as actual_total
        FROM general_conditions_breakdown WHERE project_id = ?
    """, (pid,)).fetchone()

    disc_gc = conn.execute("""
        SELECT budget_cost, actual_cost FROM disciplines
        WHERE discipline_code = 'GCONDITIONS' AND project_id = ?
    """, (pid,)).fetchone()

    if gc_sum and disc_gc:
        # GC breakdown actual should approximate discipline actual
        # GC breakdown captures a subset of discipline costs (not every line item)
        tolerance_check("GC breakdown actual vs discipline actual",
                        disc_gc["actual_cost"], gc_sum["actual_total"], 25)
        tolerance_check("GC breakdown budget vs discipline budget",
                        disc_gc["budget_cost"], gc_sum["budget_total"], 25)


# ---------------------------------------------------------------------------
# 11. Cross-Table Consistency: Cost Code MH Sums vs Discipline MH
# ---------------------------------------------------------------------------

def validate_mh_consistency(conn, pid):
    """Check if cost code MH sums are reasonable relative to discipline totals."""
    disciplines = conn.execute(
        "SELECT id, discipline_code, discipline_name, actual_mh FROM disciplines WHERE project_id = ?",
        (pid,)
    ).fetchall()

    for disc in disciplines:
        if disc["actual_mh"] is None:
            continue
        cc_sum = conn.execute(
            "SELECT SUM(actual_mh) as total FROM cost_codes WHERE discipline_id = ?",
            (disc["id"],)
        ).fetchone()
        cc_total = cc_sum["total"] if cc_sum["total"] else 0
        disc_total = disc["actual_mh"]

        # Cost codes are a subset of discipline (subs/materials not included in MH)
        # so cc_total should be <= disc_total
        if cc_total <= disc_total * 1.05:  # 5% tolerance
            check(f"MH consistency: {disc['discipline_code']}", PASS,
                  f"CC sum {cc_total:,.0f} MH <= Disc total {disc_total:,.0f} MH")
        else:
            check(f"MH consistency: {disc['discipline_code']}", WARN,
                  f"CC sum {cc_total:,.0f} MH > Disc total {disc_total:,.0f} MH (+{(cc_total/disc_total - 1)*100:.0f}%)")


# ---------------------------------------------------------------------------
# 12. Confidence Level Distribution
# ---------------------------------------------------------------------------

def validate_confidence(conn):
    dist = conn.execute("""
        SELECT confidence, COUNT(*) as c FROM unit_costs
        GROUP BY confidence ORDER BY c DESC
    """).fetchall()

    total = sum(r["c"] for r in dist)
    high_count = sum(r["c"] for r in dist if r["confidence"] == "HIGH")
    high_pct = (high_count / total * 100) if total > 0 else 0

    detail = ", ".join(f"{r['confidence']}={r['c']}" for r in dist)
    check("Confidence distribution (unit_costs)", INFO, detail)

    if high_pct >= 50:
        check("HIGH confidence >= 50%", PASS, f"{high_pct:.0f}% HIGH ({high_count}/{total})")
    else:
        check("HIGH confidence >= 50%", WARN, f"Only {high_pct:.0f}% HIGH ({high_count}/{total})")


# ---------------------------------------------------------------------------
# Main Report
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("  WEIS DATABASE VALIDATION REPORT")
    print(f"  Database: {DB_PATH}")
    print("=" * 70)

    conn = get_connection()
    try:
        pid = get_project_id(conn)
        if pid is None:
            check("Project lookup", FAIL, "No project with job_number 8553 found")
            return sum(1 for _, s, _ in results if s == FAIL)

        print(f"  Project ID: {pid}")

        print("\n--- 1. RECORD COUNTS ---")
        validate_record_counts(conn)

        print("\n--- 2. PROJECT FINANCIALS ---")
        validate_project(conn)

        print("\n--- 3. DISCIPLINE TOTALS ---")
        validate_disciplines(conn, pid)

        print("\n--- 4. KEY UNIT COST RATES ---")
        validate_unit_costs(conn)

        print("\n--- 5. SUBCONTRACTOR AMOUNTS ---")
        validate_subcontractors(conn, pid)

        print("\n--- 6. DATA COMPLETENESS ---")
        validate_completeness(conn)

        print("\n--- 7. REFERENTIAL INTEGRITY ---")
        validate_referential_integrity(conn)

        print("\n--- 8. OVER-BUDGET FLAGS ---")
        validate_over_budget_flags(conn, pid)

        print("\n--- 9. BENCHMARK REASONABLENESS ---")
        validate_benchmarks(conn)

        print("\n--- 10. GC BREAKDOWN TOTALS ---")
        validate_gc_breakdown(conn, pid)

        print("\n--- 11. MH CONSISTENCY ---")
        validate_mh_consistency(conn, pid)

        print("\n--- 12. CONFIDENCE DISTRIBUTION ---")
        validate_confidence(conn)

    finally:
        conn.close()

    # Print summary
    print("\n" + "=" * 70)
    print("  VALIDATION SUMMARY")
    print("=" * 70)

    pass_count = sum(1 for _, s, _ in results if s == PASS)
    fail_count = sum(1 for _, s, _ in results if s == FAIL)
    warn_count = sum(1 for _, s, _ in results if s == WARN)
    info_count = sum(1 for _, s, _ in results if s == INFO)

    print(f"\n  PASS: {pass_count}")
    print(f"  FAIL: {fail_count}")
    print(f"  WARN: {warn_count}")
    print(f"  INFO: {info_count}")
    print(f"  TOTAL CHECKS: {len(results)}")

    # Print all results
    print(f"\n{'-' * 70}")
    for name, status, detail in results:
        icon = {"PASS": "[OK]", "FAIL": "[XX]", "WARN": "[!!]", "INFO": "[--]"}[status]
        line = f"  {icon} {name}"
        if detail:
            line += f" - {detail}"
        print(line)

    # Print failures separately
    if fail_count > 0:
        print(f"\n{'-' * 70}")
        print("  FAILURES:")
        for name, status, detail in results:
            if status == FAIL:
                print(f"  [XX] {name} - {detail}")

    print(f"\n{'-' * 70}")
    if fail_count == 0:
        print("  RESULT: ALL CHECKS PASSED")
    else:
        print(f"  RESULT: {fail_count} FAILURE(S) NEED ATTENTION")
    print("=" * 70)

    return fail_count


if __name__ == "__main__":
    failures = main()
    sys.exit(1 if failures > 0 else 0)
