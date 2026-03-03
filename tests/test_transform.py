"""
Tests for the Transformation Layer

Tests the discipline mapper, unit cost calculator, confidence assessment,
variance flagging, and rate card generation using hardcoded values from
Wollam's existing JCD data.

These tests validate the core business logic that transforms raw HCSS
cost code data into meaningful estimating rates.
"""

import pytest

from app.transform.mapper import DisciplineMapper
from app.transform.calculator import UnitCostCalculator


# ─────────────────────────────────────────────────────────────
# Discipline Mapper Tests
# ─────────────────────────────────────────────────────────────

class TestDisciplineMapper:
    """Test cost code to discipline mapping using known Wollam codes."""

    @pytest.fixture
    def mapper(self):
        return DisciplineMapper()

    def test_general_conditions_prefix(self, mapper):
        """Codes starting with 10xx map to general_conditions."""
        assert mapper.map_code("1005") == "general_conditions"
        assert mapper.map_code("1010") == "general_conditions"

    def test_earthwork_prefix(self, mapper):
        """Codes starting with 21xx map to earthwork."""
        assert mapper.map_code("2110") == "earthwork"
        assert mapper.map_code("2115") == "earthwork"
        assert mapper.map_code("2120") == "earthwork"

    def test_concrete_prefix(self, mapper):
        """Codes starting with 22xx/23xx map to concrete."""
        assert mapper.map_code("2200") == "concrete"
        assert mapper.map_code("2215") == "concrete"
        assert mapper.map_code("2220") == "concrete"

    def test_structural_steel_prefix(self, mapper):
        """Codes starting with 24xx map to structural_steel."""
        assert mapper.map_code("2400") == "structural_steel"

    def test_mechanical_piping_prefix(self, mapper):
        """Codes starting with 26xx/27xx map to mechanical_piping."""
        assert mapper.map_code("2600") == "mechanical_piping"
        assert mapper.map_code("2700") == "mechanical_piping"

    def test_electrical_prefix(self, mapper):
        """Codes starting with 28xx map to electrical."""
        assert mapper.map_code("2800") == "electrical"

    def test_ss_pipe_conveyance_specific_codes(self, mapper):
        """SS pipe conveyance uses specific codes, not prefixes."""
        assert mapper.map_code("2405") == "ss_pipe_conveyance"
        assert mapper.map_code("2410") == "ss_pipe_conveyance"
        assert mapper.map_code("2415") == "ss_pipe_conveyance"

    def test_change_orders_prefix(self, mapper):
        """Codes starting with 50xx-54xx map to change_orders."""
        assert mapper.map_code("5000") == "change_orders"
        assert mapper.map_code("5400") == "change_orders"

    def test_overrides_take_priority(self, mapper):
        """Manual overrides in config take highest priority."""
        # 5100 prefix would be change_orders, but override maps to ss_pipe_conveyance
        assert mapper.map_code("5100") == "ss_pipe_conveyance"
        assert mapper.map_code("5105") == "ss_pipe_conveyance"
        # 5110 override maps to mechanical_piping
        assert mapper.map_code("5110") == "mechanical_piping"

    def test_unmapped_code(self, mapper):
        """Unknown codes return 'unmapped' for manual review."""
        assert mapper.map_code("9999") == "unmapped"
        assert mapper.map_code("0000") == "unmapped"

    def test_material_prefix(self, mapper):
        """Material prefixes (31xx, 33xx, etc.) map to the correct discipline."""
        assert mapper.map_code("3100") == "earthwork"    # 31xx = earthwork materials
        assert mapper.map_code("3300") == "concrete"     # 33xx = concrete materials
        assert mapper.map_code("3400") == "structural_steel"  # 34xx
        assert mapper.map_code("3200") == "mechanical_piping"  # 32xx

    def test_sub_prefix(self, mapper):
        """Sub prefixes (40xx, 41xx, 42xx) map to the correct discipline."""
        assert mapper.map_code("4000") == "concrete"          # 40xx = concrete subs
        assert mapper.map_code("4100") == "electrical"        # 41xx = electrical subs
        assert mapper.map_code("4200") == "structural_steel"  # 42xx = steel subs

    def test_get_subcategory(self, mapper):
        """Subcategory lookup returns correct subcategory name."""
        assert mapper.get_subcategory("2215") == "forming"
        assert mapper.get_subcategory("2200") == "rebar"
        assert mapper.get_subcategory("2210") == "pouring"
        # Code with no subcategory
        assert mapper.get_subcategory("9999") is None

    def test_get_all_codes_for_discipline(self, mapper):
        """Can retrieve all known codes for a discipline."""
        concrete_codes = mapper.get_all_codes_for_discipline("concrete")
        assert "2200" in concrete_codes  # rebar
        assert "2215" in concrete_codes  # forming
        assert "3015" in concrete_codes  # override
        assert "4040" in concrete_codes  # override

    def test_whitespace_handling(self, mapper):
        """Cost codes with whitespace are handled gracefully."""
        assert mapper.map_code(" 2215 ") == "concrete"
        assert mapper.map_code("2215\t") == "concrete"

    def test_all_disciplines_listed(self, mapper):
        """All expected disciplines are present in config."""
        disciplines = mapper.all_disciplines
        assert "general_conditions" in disciplines
        assert "earthwork" in disciplines
        assert "concrete" in disciplines
        assert "structural_steel" in disciplines
        assert "mechanical_piping" in disciplines
        assert "electrical" in disciplines
        assert "ss_pipe_conveyance" in disciplines
        assert "change_orders" in disciplines


# ─────────────────────────────────────────────────────────────
# Unit Cost Calculator Tests
# ─────────────────────────────────────────────────────────────

class TestUnitCostCalculator:
    """Test unit cost calculation with known values from Wollam JCDs."""

    @pytest.fixture
    def calc(self):
        return UnitCostCalculator()

    def test_basic_labor_rate(self, calc):
        """Basic MH/unit calculation with known inputs."""
        result = calc.calculate_labor_rate(
            budget_hours=1400,
            actual_hours=1264,
            budget_qty=5000,
            actual_qty=5100,
            budget_cost=77000,
            actual_cost=69520,
        )
        assert result["bgt_mh_per_unit"] == pytest.approx(0.28, abs=0.01)
        assert result["act_mh_per_unit"] == pytest.approx(0.248, abs=0.01)
        assert result["bgt_cost_per_unit"] == pytest.approx(15.40, abs=0.10)
        assert result["act_cost_per_unit"] == pytest.approx(13.63, abs=0.10)

    def test_recommended_rate_actual_under_budget(self, calc):
        """When actual < budget, recommended rate weights 80% toward actual."""
        # actual=0.20, budget=0.28
        # rec = 0.20 + (0.28 - 0.20) * 0.2 = 0.20 + 0.016 = 0.216
        rate, basis = calc.calculate_recommended_rate(0.28, 0.20)
        assert rate == pytest.approx(0.216, abs=0.001)
        assert basis == "calculated"

    def test_recommended_rate_actual_over_budget(self, calc):
        """When actual > budget, recommended rate splits the difference 50/50."""
        # actual=0.35, budget=0.28
        # rec = 0.28 + (0.35 - 0.28) * 0.5 = 0.28 + 0.035 = 0.315
        rate, basis = calc.calculate_recommended_rate(0.28, 0.35)
        assert rate == pytest.approx(0.315, abs=0.001)
        assert basis == "calculated"

    def test_recommended_rate_actual_equals_budget(self, calc):
        """When actual == budget, recommended rate equals both."""
        rate, basis = calc.calculate_recommended_rate(0.28, 0.28)
        assert rate == pytest.approx(0.28, abs=0.001)
        assert basis == "calculated"

    def test_recommended_rate_actual_only(self, calc):
        """When only actual exists, use actual as recommended."""
        rate, basis = calc.calculate_recommended_rate(None, 0.25)
        assert rate == 0.25
        assert basis == "actual"

    def test_recommended_rate_budget_only(self, calc):
        """When only budget exists, use budget as recommended."""
        rate, basis = calc.calculate_recommended_rate(0.28, None)
        assert rate == 0.28
        assert basis == "budget"

    def test_recommended_rate_neither(self, calc):
        """When neither exists, return None."""
        rate, basis = calc.calculate_recommended_rate(None, None)
        assert rate is None
        assert basis is None

    def test_confidence_strong(self, calc):
        """Strong confidence: >=90% complete with both data sources."""
        level, reason = calc.assess_confidence(
            pct_complete=95.0,
            has_budget=True,
            has_actual=True,
            actual_qty=500,
        )
        assert level == "strong"

    def test_confidence_moderate(self, calc):
        """Moderate confidence: 50-89% complete with actual data."""
        level, reason = calc.assess_confidence(
            pct_complete=75.0,
            has_budget=True,
            has_actual=True,
            actual_qty=500,
        )
        assert level == "moderate"

    def test_confidence_limited_budget_only(self, calc):
        """Limited confidence: budget data only, no actuals."""
        level, reason = calc.assess_confidence(
            pct_complete=0,
            has_budget=True,
            has_actual=False,
        )
        assert level == "limited"

    def test_confidence_none(self, calc):
        """No confidence: no budget or actual data."""
        level, reason = calc.assess_confidence(
            pct_complete=0,
            has_budget=False,
            has_actual=False,
        )
        assert level == "none"

    def test_variance_flagging_over_threshold(self, calc):
        """Variance >20% gets flagged."""
        variance, flagged = calc.calculate_variance(0.28, 0.35)
        assert variance == pytest.approx(25.0, abs=1.0)
        assert flagged is True

    def test_variance_within_threshold(self, calc):
        """Variance <=20% is not flagged."""
        variance, flagged = calc.calculate_variance(0.28, 0.30)
        assert variance == pytest.approx(7.14, abs=1.0)
        assert flagged is False

    def test_variance_under_budget(self, calc):
        """Negative variance (under budget) can also be flagged if >20%."""
        variance, flagged = calc.calculate_variance(0.28, 0.20)
        assert variance < 0  # Under budget
        assert flagged is True  # But still >20% magnitude

    def test_variance_zero_budget(self, calc):
        """Zero budget returns None variance (can't divide by zero)."""
        variance, flagged = calc.calculate_variance(0, 100)
        assert variance is None
        assert flagged is False

    def test_variance_none_inputs(self, calc):
        """None inputs return None variance."""
        variance, flagged = calc.calculate_variance(None, 100)
        assert variance is None
        assert flagged is False

    def test_division_by_zero_qty(self, calc):
        """Zero quantity returns None for rates, no exceptions."""
        result = calc.calculate_labor_rate(
            budget_hours=100,
            actual_hours=90,
            budget_qty=0,        # Zero quantity — can't calculate rate
            actual_qty=0,
            budget_cost=5000,
            actual_cost=4500,
        )
        assert result["bgt_mh_per_unit"] is None
        assert result["act_mh_per_unit"] is None
        assert result["bgt_cost_per_unit"] is None
        assert result["act_cost_per_unit"] is None

    def test_all_none_inputs(self, calc):
        """All None inputs return all None results, no exceptions."""
        result = calc.calculate_labor_rate(
            budget_hours=None,
            actual_hours=None,
            budget_qty=None,
            actual_qty=None,
            budget_cost=None,
            actual_cost=None,
        )
        assert result["bgt_mh_per_unit"] is None
        assert result["act_mh_per_unit"] is None
        assert result["rec_rate"] is None
        assert result["rec_basis"] is None
