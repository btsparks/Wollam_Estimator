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
