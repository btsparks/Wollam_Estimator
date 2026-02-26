"""Tests for WEIS query functions.

Validates that query functions return correct data from the database.
These tests run against the live database and do not require an API key.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import query


def test_search_unit_costs_by_activity():
    results = query.search_unit_costs(activity="wall form")
    assert len(results) >= 1
    r = results[0]
    assert r["activity"] == "Wall Form/Strip"
    assert r["recommended_rate"] == 0.28
    assert r["unit"] == "MH/SF"
    assert r["confidence"] == "HIGH"
    assert r["job_number"] == "8553"


def test_search_unit_costs_by_discipline():
    results = query.search_unit_costs(discipline="CONCRETE")
    assert len(results) >= 10
    for r in results:
        assert r["discipline_code"] == "CONCRETE"


def test_search_unit_costs_by_discipline_name():
    results = query.search_unit_costs(discipline="Piping")
    assert len(results) >= 10
    for r in results:
        assert r["discipline_code"] == "PIPING"


def test_search_cost_codes():
    results = query.search_cost_codes(cost_code="2340")
    assert len(results) == 1
    r = results[0]
    assert r["description"] == "CW_F/S Walls"
    assert r["discipline_code"] == "CONCRETE"


def test_search_cost_codes_by_discipline():
    results = query.search_cost_codes(discipline="EARTHWORK")
    assert len(results) >= 15
    for r in results:
        assert r["discipline_code"] == "EARTHWORK"


def test_search_cost_codes_over_budget():
    results = query.search_cost_codes(over_budget_only=True)
    assert len(results) >= 5
    for r in results:
        assert r["over_budget_flag"] == 1


def test_search_production_rates():
    results = query.search_production_rates(activity="excavation")
    assert len(results) >= 1
    r = results[0]
    assert r["recommended_rate"] == 700
    assert "CY" in r["production_unit"]


def test_search_crew_configs():
    results = query.search_crew_configs(activity="mat pour")
    assert len(results) >= 1
    r = results[0]
    assert r["total_crew_size"] >= 20


def test_search_material_costs():
    results = query.search_material_costs(material="concrete")
    assert len(results) >= 1
    found_ready_mix = any("Ready Mix" in r["material_type"] for r in results)
    assert found_ready_mix


def test_search_material_costs_by_vendor():
    results = query.search_material_costs(vendor="Rhine")
    assert len(results) >= 1
    assert results[0]["vendor"] == "Rhine Construction"


def test_search_subcontractors():
    results = query.search_subcontractors(name="Champion")
    assert len(results) == 1
    r = results[0]
    assert r["actual_amount"] == 3539407
    assert r["scope_category"] == "rebar"


def test_search_subcontractors_by_scope():
    results = query.search_subcontractors(scope="electrical")
    assert len(results) >= 1
    assert any("Hunt" in (r.get("sub_name") or "") for r in results)


def test_search_lessons_learned():
    results = query.search_lessons_learned(discipline="CONCRETE")
    assert len(results) >= 3
    for r in results:
        assert r["discipline_code"] == "CONCRETE"


def test_search_lessons_by_severity():
    results = query.search_lessons_learned(severity="HIGH")
    assert len(results) >= 10
    for r in results:
        assert r["severity"] == "HIGH"


def test_search_lessons_by_keyword():
    results = query.search_lessons_learned(keyword="grout")
    assert len(results) >= 1
    assert any("grout" in r["title"].lower() for r in results)


def test_search_benchmark_rates():
    results = query.search_benchmark_rates(activity="wall form")
    assert len(results) >= 1
    r = results[0]
    assert r["typical_rate"] == 0.28
    assert r["low_rate"] <= r["typical_rate"] <= r["high_rate"]


def test_get_project_summary():
    results = query.get_project_summary(job_number="8553")
    assert len(results) == 1
    p = results[0]
    assert p["total_actual_cost"] == 35571414
    assert p["cpi"] == 1.37


def test_get_discipline_summary():
    results = query.get_discipline_summary(job_number="8553")
    assert len(results) == 8


def test_get_gc_breakdown():
    results = query.get_gc_breakdown(job_number="8553")
    assert len(results) == 15


def test_get_database_overview():
    overview = query.get_database_overview()
    assert len(overview["projects"]) == 1
    assert overview["record_counts"]["cost_codes"] == 115
    assert len(overview["disciplines"]) == 8


def test_run_read_query():
    results = query.run_read_query("SELECT COUNT(*) as total FROM unit_costs")
    assert results[0]["total"] == 65


def test_run_read_query_blocks_writes():
    import pytest
    with pytest.raises(ValueError):
        query.run_read_query("DELETE FROM projects")
    with pytest.raises(ValueError):
        query.run_read_query("DROP TABLE projects")


# MVP Test Questions (data retrieval only, no AI formatting)
# These verify the query layer can find the right data for each MVP question

def test_mvp_q1_flanged_joints():
    """Q1: What did we pay for 20-inch flanged joints?"""
    results = query.search_unit_costs(activity="Flanged Bolt-up 20")
    assert len(results) >= 1
    r = results[0]
    assert r["recommended_rate"] == 7.0
    assert "MH" in r["unit"]


def test_mvp_q2_concrete_material_cost():
    """Q2: What was our concrete material cost per CY?"""
    results = query.search_unit_costs(activity="Concrete Material")
    assert len(results) >= 1
    assert any(r["recommended_rate"] == 210 for r in results)


def test_mvp_q3_mat_pour_crew():
    """Q3: What crew did we use for mat pours?"""
    results = query.search_crew_configs(activity="mat pour")
    assert len(results) >= 1


def test_mvp_q4_excavation_production():
    """Q4: What production rate on structural excavation?"""
    results = query.search_production_rates(activity="excavation")
    assert len(results) >= 1


def test_mvp_q5_steel_erection_cost():
    """Q5: What did steel erection cost per ton?"""
    results = query.search_subcontractors(name="J&M")
    assert len(results) >= 1
    assert results[0]["unit_cost"] == 3766


def test_mvp_q6_gc_percentage():
    """Q6: What was our general conditions percentage?"""
    results = query.search_unit_costs(activity="Total GC")
    assert len(results) >= 1


def test_mvp_q7_piping_lessons():
    """Q7: What lessons on piping from Job 8553?"""
    results = query.search_lessons_learned(discipline="PIPING")
    assert len(results) >= 2


def test_mvp_q8_rebar_sub():
    """Q8: What sub for rebar and at what cost per pound?"""
    results = query.search_subcontractors(scope="rebar")
    assert len(results) >= 1
    r = results[0]
    assert "Champion" in r["sub_name"]
    assert r["unit_cost"] == 1.30


def test_mvp_q9_all_in_concrete():
    """Q9: What was the all-in cost per CY for concrete?"""
    results = query.search_unit_costs(activity="All-In Concrete")
    assert len(results) >= 1
    assert results[0]["recommended_rate"] == 867


def test_mvp_q10_electrical_sf():
    """Q10: What was the electrical subcontractor cost per SF?"""
    results = query.search_unit_costs(activity="Heavy Industrial Electrical")
    assert len(results) >= 1
    assert results[0]["recommended_rate"] == 138


# =========================================================================
# Discipline-Specific Questions (10)
# Cover all 8 disciplines + cross-discipline queries
# =========================================================================

def test_discipline_earthwork_fill_production():
    """Earthwork: What is the structural fill place & compact production rate?"""
    results = query.search_production_rates(activity="fill")
    assert len(results) >= 1
    fill = [r for r in results if "Fill P/C" in r["activity"]]
    assert len(fill) >= 1
    assert fill[0]["recommended_rate"] == 180
    assert "TON" in fill[0]["production_unit"]


def test_discipline_earthwork_tailings_cost():
    """Earthwork: What did tailings excavation cost per CY (short haul)?"""
    results = query.search_unit_costs(activity="tailings", discipline="EARTHWORK")
    assert len(results) >= 1
    short_haul = [r for r in results if "short" in r["activity"].lower()]
    assert len(short_haul) >= 1
    assert short_haul[0]["recommended_rate"] == 1.38


def test_discipline_concrete_wall_form_production():
    """Concrete: What was the wall formwork production rate?"""
    results = query.search_production_rates(activity="wall form")
    assert len(results) >= 1
    assert results[0]["recommended_rate"] == 400
    assert "SF" in results[0]["production_unit"]
    assert results[0]["discipline_code"] == "CONCRETE"


def test_discipline_concrete_pumping_cost():
    """Concrete: What did concrete pumping cost per CY?"""
    results = query.search_unit_costs(activity="Concrete Pumping")
    assert len(results) >= 1
    assert results[0]["recommended_rate"] == 17.5
    assert "CY" in results[0]["unit"]


def test_discipline_steel_handrail_rate():
    """Steel: What was the handrail installation rate?"""
    results = query.search_unit_costs(activity="Handrail", discipline="STEEL")
    assert len(results) >= 1
    assert results[0]["recommended_rate"] == 0.58
    assert "MH/LF" in results[0]["unit"]


def test_discipline_steel_pipe_support():
    """Steel: What did ground pipe supports cost in MH?"""
    results = query.search_benchmark_rates(activity="Pipe Support - Ground")
    assert len(results) >= 1
    assert results[0]["typical_rate"] == 5.0


def test_discipline_piping_field_weld():
    """Piping: What is the field weld rate for CS 12-24in pipe?"""
    results = query.search_unit_costs(activity="Field Weld - CS 12-24")
    assert len(results) >= 1
    assert results[0]["recommended_rate"] == 16.0
    assert "MH" in results[0]["unit"]


def test_discipline_mechanical_epoxy_grout():
    """Mechanical: What was the epoxy grout labor rate?"""
    results = query.search_unit_costs(activity="Epoxy Grout", discipline="MECHANICAL")
    assert len(results) >= 1
    grout_labor = [r for r in results if "MH" in r["unit"]]
    assert len(grout_labor) >= 1
    assert grout_labor[0]["recommended_rate"] == 50.0


def test_discipline_electrical_duct_bank():
    """Electrical: What did duct bank excavation/backfill cost per LF?"""
    results = query.search_unit_costs(activity="Duct Bank EX", discipline="ELECTRICAL")
    assert len(results) >= 1
    assert results[0]["recommended_rate"] == 10.0
    assert "LF" in results[0]["unit"]


def test_cross_discipline_budget_performance():
    """Cross-discipline: Which disciplines came in under budget?"""
    discs = query.get_discipline_summary(job_number="8553")
    under_budget = [d for d in discs if d.get("variance_pct") and d["variance_pct"] < 0]
    # Multiple disciplines should be under budget on this CPI=1.37 project
    assert len(under_budget) >= 4


# =========================================================================
# Lessons Learned & Edge Cases (10)
# =========================================================================

def test_lesson_wall_supports_over_budget():
    """Lesson: Steel wall supports went 140% over budget."""
    results = query.search_lessons_learned(keyword="wall support")
    assert len(results) >= 1
    assert results[0]["severity"] == "HIGH"
    assert results[0]["discipline_code"] == "STEEL"


def test_lesson_3_pour_strategy():
    """Lesson: 3-pour strategy saved ~$1.5M on concrete."""
    results = query.search_lessons_learned(keyword="pour strategy")
    assert len(results) >= 1
    assert results[0]["discipline_code"] == "CONCRETE"


def test_lesson_mine_site_training():
    """Lesson: Mine site training was 380% over budget."""
    results = query.search_lessons_learned(keyword="training")
    assert len(results) >= 1
    assert results[0]["severity"] == "HIGH"


def test_lesson_equipment_pad_embeds():
    """Lesson: Equipment pad embeds add 40-50% to F/S rates."""
    results = query.search_lessons_learned(keyword="embed")
    assert len(results) >= 1
    assert results[0]["category"] == "scope_gap"


def test_edge_vendor_search():
    """Edge: Search materials by vendor name (For-Shor)."""
    results = query.search_material_costs(vendor="For-Shor")
    assert len(results) >= 1
    assert any("For-Shor" in (r.get("vendor") or "") for r in results)


def test_edge_gc_management_rate():
    """Edge: GC management daily rate from unit costs."""
    results = query.search_unit_costs(activity="Management", discipline="GCONDITIONS")
    assert len(results) >= 1
    assert results[0]["recommended_rate"] == 2500.0
    assert "DAY" in results[0]["unit"]


def test_edge_benchmark_rate_range():
    """Edge: Benchmark rates include low, typical, and high values."""
    results = query.search_benchmark_rates(activity="wall form")
    assert len(results) >= 1
    r = results[0]
    assert r["low_rate"] is not None
    assert r["typical_rate"] is not None
    assert r["high_rate"] is not None
    assert r["low_rate"] <= r["typical_rate"] <= r["high_rate"]


def test_edge_over_budget_cost_codes_count():
    """Edge: Multiple cost codes went over budget."""
    results = query.search_cost_codes(over_budget_only=True)
    assert len(results) >= 5
    # Every result must have the flag set
    for r in results:
        assert r["over_budget_flag"] == 1
    # Verify they span multiple disciplines
    disciplines = set(r["discipline_code"] for r in results)
    assert len(disciplines) >= 2


def test_edge_lessons_by_category_scope_gap():
    """Edge: Filter lessons by scope_gap category."""
    results = query.search_lessons_learned(category="scope_gap")
    assert len(results) >= 2
    for r in results:
        assert "scope_gap" in r["category"]


def test_edge_all_subcontractors():
    """Edge: Retrieve all subcontractors (no filter)."""
    results = query.search_subcontractors()
    assert len(results) == 9
    names = [r["sub_name"] for r in results]
    assert "Champion/Iron Mountain" in names
    assert "Hunt Electric (IES)" in names
    assert "J&M Steel Solutions" in names
