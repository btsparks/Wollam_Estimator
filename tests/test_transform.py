"""
Tests for the Transformation Layer

Tests the discipline mapper, field intelligence confidence assessment,
safe division, and rate card generation.

These tests validate the core business logic that transforms raw HCSS
timecard data into field intelligence for estimating.
"""

import pytest

from app.transform.mapper import DisciplineMapper
from app.transform.calculator import assess_confidence, safe_divide


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
# Safe Divide Tests
# ─────────────────────────────────────────────────────────────

class TestSafeDivide:
    """Test safe division utility used for MH/unit and $/unit calculations."""

    def test_basic_division(self):
        """Normal division returns rounded result."""
        assert safe_divide(1264, 5100) == pytest.approx(0.2478, abs=0.0001)

    def test_zero_denominator(self):
        """Zero denominator returns None instead of raising."""
        assert safe_divide(100, 0) is None

    def test_none_numerator(self):
        """None numerator returns None."""
        assert safe_divide(None, 100) is None

    def test_none_denominator(self):
        """None denominator returns None."""
        assert safe_divide(100, None) is None

    def test_both_none(self):
        """Both None returns None."""
        assert safe_divide(None, None) is None

    def test_zero_numerator(self):
        """Zero numerator returns 0.0, not None."""
        assert safe_divide(0, 100) == 0.0

    def test_large_values(self):
        """Handles large values without overflow."""
        result = safe_divide(69520, 5100)
        assert result == pytest.approx(13.6314, abs=0.001)

    def test_rounding(self):
        """Results are rounded to 4 decimal places."""
        result = safe_divide(1, 3)
        assert result == 0.3333


# ─────────────────────────────────────────────────────────────
# Confidence Assessment Tests
# ─────────────────────────────────────────────────────────────

class TestAssessConfidence:
    """Test confidence assessment based on timecard data richness."""

    def test_high_confidence(self):
        """HIGH: 20+ timecards across 10+ work days."""
        level, reason = assess_confidence(timecard_count=50, work_days=20)
        assert level == "high"
        assert "50 timecards" in reason

    def test_high_at_threshold(self):
        """HIGH: exactly at the threshold (20 tc, 10 days)."""
        level, reason = assess_confidence(timecard_count=20, work_days=10)
        assert level == "high"

    def test_high_tc_but_few_days(self):
        """MODERATE: enough timecards but not enough work days."""
        level, reason = assess_confidence(timecard_count=25, work_days=5)
        assert level == "moderate"

    def test_moderate_confidence(self):
        """MODERATE: 5-19 timecards."""
        level, reason = assess_confidence(timecard_count=10, work_days=5)
        assert level == "moderate"

    def test_moderate_at_threshold(self):
        """MODERATE: exactly at the lower threshold (5 tc)."""
        level, reason = assess_confidence(timecard_count=5, work_days=3)
        assert level == "moderate"

    def test_low_confidence(self):
        """LOW: 1-4 timecards — thin data."""
        level, reason = assess_confidence(timecard_count=3, work_days=2)
        assert level == "low"
        assert "thin data" in reason.lower() or "caution" in reason.lower()

    def test_low_single_timecard(self):
        """LOW: single timecard — could be a fluke."""
        level, reason = assess_confidence(timecard_count=1, work_days=1)
        assert level == "low"

    def test_none_confidence(self):
        """NONE: zero timecards — no field data at all."""
        level, reason = assess_confidence(timecard_count=0, work_days=0)
        assert level == "none"
        assert "no timecard" in reason.lower()
