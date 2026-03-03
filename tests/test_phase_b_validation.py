"""
Phase B Validation Tests

Validates that the transformation pipeline produces rates matching
the manually-cataloged JCD data within defined tolerances.

Mock HCSS API response data in tests/mock_data/ mirrors what the real
API would return for Jobs 8553 and 8576. These tests prove that the
automated pipeline produces the same rates as hours of manual cataloging.

IMPORTANT DESIGN NOTE (per Travis, 2026-03-03):
    JCDs are NOT equivalent to raw HeavyJob/HeavyBid API output. A JCD is a
    curated intelligence product that synthesizes API data with PM interviews,
    crew observations, production context, and estimating judgment. The rates
    in a JCD (e.g., "recommended 0.28 MH/SF for wall F/S") reflect human
    analysis that goes beyond what any automated pipeline can replicate from
    raw API data alone.

    These Phase B tests validate that the pipeline MATH works correctly —
    given mock cost code data shaped like JCD values, the calculated rates
    land within tolerance. But when the real HCSS API is connected (Phase C+),
    the raw data may differ from JCD rates because:
      - JCDs include context the API doesn't (lessons learned, crew details)
      - JCDs apply PM judgment to normalize anomalies
      - Cost code meanings vary between projects (see discipline_map.yaml TODO)
      - "Recommended" rates in JCDs blend budget, actual, and experience

    Future validation should compare pipeline output to raw HeavyJob/HeavyBid
    data directly, not to JCD rates. JCDs remain the gold standard for the
    knowledge base but represent a higher-level product than API output.

Validation targets (from WEIS_CLAUDE_CODE_PROMPT_3-3.md):

| Activity                 | Job  | Expected Rate | Tolerance |
|--------------------------|------|---------------|-----------|
| Wall Form/Strip          | 8553 | 0.28 MH/SF    | ±0.02     |
| Wall Form/Strip          | 8576 | 0.20 MH/SF    | ±0.02     |
| Mat Pour                 | 8553 | 0.15 MH/CY    | ±0.02     |
| Pour Floor               | 8576 | 0.67 MH/CY    | ±0.05     |
| All-In Concrete          | 8553 | $867/CY       | ±$50      |
| All-In Concrete          | 8576 | $965/CY       | ±$50      |
| Flanged Joint 20-28"     | 8553 | 7 MH/JT       | ±0.5      |
| SS Pipe EX/BF            | 8576 | $3.08/CY      | ±$0.25    |
| SS Pipe All-In Install   | 8576 | $169/LF       | ±$10      |
| GC Percentage            | 8576 | 15.0%         | ±1.0%     |
"""

import json
from pathlib import Path

import pytest

from app.hcss.models import HJCostCode
from app.transform.rate_card import RateCardGenerator


MOCK_DATA_DIR = Path(__file__).parent / "mock_data"

# Concrete cost codes by job — includes labor (23xx), materials (33xx), subs (40xx)
CONCRETE_CODES_8553 = {
    "2300", "2301", "2302", "2304", "2306", "2308", "2310",
    "2314", "2316", "2324", "2330", "2332", "2334", "2340",
    "2342", "2343", "2344", "2350", "2352", "2360", "2362",
    "2364", "2366", "2368", "2370", "2372", "2374", "2376",
    "2380", "2382",
    "3300", "3302", "3304", "3310", "3360",
    "4025", "4050", "4075",
}

CONCRETE_CODES_8576 = {
    "2300", "2316", "2330", "2340", "2342", "2374",
    "3300", "3304",
    "4025", "4050",
}

SS_PIPE_CODES = {"2405", "2410", "2415"}

GC_CODES_8576 = {"1000", "1010", "1012", "1013", "2035"}


def load_mock_costcodes(job_number: str) -> list[HJCostCode]:
    """Load and validate mock cost codes from JSON."""
    path = MOCK_DATA_DIR / "heavyjob" / f"costcodes_{job_number}.json"
    with open(path) as f:
        data = json.load(f)
    return [HJCostCode.model_validate(r) for r in data]


def find_rate_item(rate_card, code: str):
    """Find a rate item by cost code in a rate card result."""
    for item in rate_card.items:
        if item.activity == code:
            return item
    raise ValueError(f"Code {code} not found in rate card")


def aggregate_actual_cost(cost_codes: list[HJCostCode], code_set: set[str]) -> float:
    """Sum actualTotalCost for codes in the given set."""
    total = 0.0
    for cc in cost_codes:
        if cc.code in code_set:
            total += cc.actualTotalCost or 0
    return total


class TestJob8553Rates:
    """Validate pipeline against Job 8553 JCD rates."""

    @pytest.fixture
    def cost_codes(self):
        return load_mock_costcodes("8553")

    @pytest.fixture
    def rate_card(self, cost_codes):
        gen = RateCardGenerator()
        return gen.generate_rate_card(
            job_number="8553",
            job_name="RTK SPD Pump Station",
            cost_codes=cost_codes,
        )

    def test_wall_form_strip(self, rate_card):
        """Wall Form/Strip: 0.28 MH/SF ±0.02 (code 2340)."""
        item = find_rate_item(rate_card, "2340")
        assert item.act_mh_per_unit is not None
        assert abs(item.act_mh_per_unit - 0.28) <= 0.02, (
            f"Wall F/S rate {item.act_mh_per_unit:.4f} outside 0.28 ± 0.02"
        )

    def test_mat_pour(self, rate_card):
        """Mat Pour: 0.15 MH/CY ±0.02 (code 2316)."""
        item = find_rate_item(rate_card, "2316")
        assert item.act_mh_per_unit is not None
        assert abs(item.act_mh_per_unit - 0.15) <= 0.02, (
            f"Mat Pour rate {item.act_mh_per_unit:.4f} outside 0.15 ± 0.02"
        )

    def test_all_in_concrete(self, cost_codes):
        """All-In Concrete: $867/CY ±$50."""
        total_cost = aggregate_actual_cost(cost_codes, CONCRETE_CODES_8553)

        # Total CY from concrete purchase code (3300)
        buy_concrete = next(cc for cc in cost_codes if cc.code == "3300")
        total_cy = buy_concrete.actualQuantity
        assert total_cy is not None and total_cy > 0

        all_in = total_cost / total_cy
        assert abs(all_in - 867) <= 50, (
            f"All-In Concrete ${all_in:.0f}/CY outside $867 ± $50"
        )

    def test_flanged_joint(self, rate_card):
        """Flanged Joint 20-28": 7 MH/JT ±0.5 (code 2716)."""
        item = find_rate_item(rate_card, "2716")
        assert item.act_mh_per_unit is not None
        assert abs(item.act_mh_per_unit - 7.0) <= 0.5, (
            f"Flanged Joint rate {item.act_mh_per_unit:.2f} outside 7.0 ± 0.5"
        )


class TestJob8576Rates:
    """Validate pipeline against Job 8576 JCD rates."""

    @pytest.fixture
    def cost_codes(self):
        return load_mock_costcodes("8576")

    @pytest.fixture
    def rate_card(self, cost_codes):
        gen = RateCardGenerator()
        return gen.generate_rate_card(
            job_number="8576",
            job_name="RTKC 5600 Pump Station",
            cost_codes=cost_codes,
        )

    def test_wall_form_strip(self, rate_card):
        """Wall Form/Strip: 0.20 MH/SF ±0.02 (code 2340)."""
        item = find_rate_item(rate_card, "2340")
        assert item.act_mh_per_unit is not None
        assert abs(item.act_mh_per_unit - 0.20) <= 0.02, (
            f"Wall F/S rate {item.act_mh_per_unit:.4f} outside 0.20 ± 0.02"
        )

    def test_pour_floor(self, rate_card):
        """Pour Floor: 0.67 MH/CY ±0.05 (code 2316)."""
        item = find_rate_item(rate_card, "2316")
        assert item.act_mh_per_unit is not None
        assert abs(item.act_mh_per_unit - 0.67) <= 0.05, (
            f"Pour Floor rate {item.act_mh_per_unit:.4f} outside 0.67 ± 0.05"
        )

    def test_all_in_concrete(self, cost_codes):
        """All-In Concrete: $965/CY ±$50."""
        total_cost = aggregate_actual_cost(cost_codes, CONCRETE_CODES_8576)

        buy_concrete = next(cc for cc in cost_codes if cc.code == "3300")
        total_cy = buy_concrete.actualQuantity
        assert total_cy is not None and total_cy > 0

        all_in = total_cost / total_cy
        assert abs(all_in - 965) <= 50, (
            f"All-In Concrete ${all_in:.0f}/CY outside $965 ± $50"
        )

    def test_ss_pipe_exbf(self, rate_card):
        """SS Pipe EX/BF: $3.08/CY ±$0.25 (code 2405)."""
        item = find_rate_item(rate_card, "2405")
        assert item.act_cost_per_unit is not None
        assert abs(item.act_cost_per_unit - 3.08) <= 0.25, (
            f"SS Pipe EX/BF ${item.act_cost_per_unit:.2f}/CY outside $3.08 ± $0.25"
        )

    def test_ss_pipe_all_in_install(self, cost_codes):
        """SS Pipe All-In Install: $169/LF ±$10."""
        total_cost = aggregate_actual_cost(cost_codes, SS_PIPE_CODES)

        # LF from the haul string code (2410) — represents pipe length
        haul_code = next(cc for cc in cost_codes if cc.code == "2410")
        total_lf = haul_code.actualQuantity
        assert total_lf is not None and total_lf > 0

        all_in = total_cost / total_lf
        assert abs(all_in - 169) <= 10, (
            f"SS Pipe All-In ${all_in:.0f}/LF outside $169 ± $10"
        )

    def test_gc_percentage(self, cost_codes):
        """GC%: 15.0% ±1.0%."""
        gc_cost = aggregate_actual_cost(cost_codes, GC_CODES_8576)
        total_cost = sum(
            (cc.actualTotalCost or 0) for cc in cost_codes if cc.code
        )
        assert total_cost > 0

        gc_pct = (gc_cost / total_cost) * 100
        assert abs(gc_pct - 15.0) <= 1.0, (
            f"GC% {gc_pct:.1f}% outside 15.0% ± 1.0%"
        )


class TestMockDataIntegrity:
    """Verify mock data loads correctly and models validate."""

    def test_8553_costcodes_load(self):
        """All 8553 cost codes parse into valid HJCostCode models."""
        codes = load_mock_costcodes("8553")
        assert len(codes) > 0
        for cc in codes:
            assert cc.code is not None
            assert cc.jobId == "job-8553"

    def test_8576_costcodes_load(self):
        """All 8576 cost codes parse into valid HJCostCode models."""
        codes = load_mock_costcodes("8576")
        assert len(codes) > 0
        for cc in codes:
            assert cc.code is not None
            assert cc.jobId == "job-8576"

    def test_8553_rate_card_generates(self):
        """Rate card generation completes without errors for 8553."""
        codes = load_mock_costcodes("8553")
        gen = RateCardGenerator()
        card = gen.generate_rate_card(
            job_number="8553",
            job_name="RTK SPD Pump Station",
            cost_codes=codes,
        )
        assert card.job_number == "8553"
        assert len(card.items) > 0

    def test_8576_rate_card_generates(self):
        """Rate card generation completes without errors for 8576."""
        codes = load_mock_costcodes("8576")
        gen = RateCardGenerator()
        card = gen.generate_rate_card(
            job_number="8576",
            job_name="RTKC 5600 Pump Station",
            cost_codes=codes,
        )
        assert card.job_number == "8576"
        assert len(card.items) > 0
