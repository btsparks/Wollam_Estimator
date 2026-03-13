"""Tests for rate settings and cost recalculation."""

import sqlite3
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_connection
from app.services.rate_import import parse_pay_class_file, parse_equipment_file

client = TestClient(app)

HJ_RATES_DIR = Path(__file__).parent.parent.parent / "HJ Rates"


class TestPayClassParser:
    """Test PayClass.txt parsing."""

    def test_parse_all_pay_classes(self):
        rates = parse_pay_class_file(HJ_RATES_DIR / "PayClass.txt")
        assert len(rates) == 34

    def test_carp_rate(self):
        rates = parse_pay_class_file(HJ_RATES_DIR / "PayClass.txt")
        carp = next(r for r in rates if r["pay_class_code"] == "CARP")
        assert carp["base_rate"] == 36.00
        assert carp["tax_pct"] == 15.45
        assert carp["fringe_non_ot"] == 10.50
        # loaded = 36 + (36 * 0.1545) + 10.50 = 52.062
        assert abs(carp["loaded_rate"] - 52.06) < 0.01

    def test_srpm_ot_factor(self):
        rates = parse_pay_class_file(HJ_RATES_DIR / "PayClass.txt")
        srpm = next(r for r in rates if r["pay_class_code"] == "SRPM")
        assert srpm["ot_factor"] == 1.00
        assert srpm["base_rate"] == 55.00

    def test_temp_zero_tax(self):
        rates = parse_pay_class_file(HJ_RATES_DIR / "PayClass.txt")
        templ = next(r for r in rates if r["pay_class_code"] == "TEMPL")
        assert templ["tax_pct"] == 0.0
        assert templ["fringe_non_ot"] == 0.0
        assert templ["loaded_rate"] == 44.00


class TestEquipmentParser:
    """Test EquipmentSetup.txt parsing."""

    def test_parse_equipment_count(self):
        items = parse_equipment_file(HJ_RATES_DIR / "EquipmentSetup.txt")
        assert len(items) > 1000

    def test_pickup_rate(self):
        items = parse_equipment_file(HJ_RATES_DIR / "EquipmentSetup.txt")
        pickup = next(i for i in items if i["equipment_code"] == "01-01")
        assert pickup["base_rate"] == 12.00
        assert pickup["group_name"] == "PICKUP"

    def test_no_duplicate_codes(self):
        items = parse_equipment_file(HJ_RATES_DIR / "EquipmentSetup.txt")
        codes = [i["equipment_code"] for i in items]
        assert len(codes) == len(set(codes))


class TestSettingsAPI:
    """Test settings API endpoints."""

    def test_labor_rates_list(self):
        res = client.get("/api/settings/labor-rates")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 34
        assert any(r["pay_class_code"] == "FORE" for r in data["rates"])

    def test_equipment_groups_list(self):
        res = client.get("/api/settings/equipment-groups")
        assert res.status_code == 200
        groups = res.json()["groups"]
        assert len(groups) >= 40
        names = [g["group_name"] for g in groups]
        assert "PICKUP" in names
        assert "CRANE" in names

    def test_equipment_rates_by_group(self):
        res = client.get("/api/settings/equipment-rates?group=PICKUP")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] > 20
        assert all(r["group_name"] == "PICKUP" for r in data["rates"])

    def test_rate_coverage(self):
        res = client.get("/api/settings/rate-coverage")
        assert res.status_code == 200
        data = res.json()
        assert data["labor"]["coverage_pct"] > 95
        assert data["equipment"]["coverage_pct"] > 95

    def test_recast_for_job(self):
        # Get first job
        conn = get_connection()
        job = conn.execute("SELECT job_id FROM job LIMIT 1").fetchone()
        conn.close()
        if not job:
            pytest.skip("No jobs in database")

        res = client.get(f"/api/settings/recast/{job['job_id']}")
        assert res.status_code == 200
        data = res.json()
        assert "job_totals" in data
        assert "cost_codes" in data
        assert data["job_totals"]["total_cost"] > 0

    def test_recast_404(self):
        res = client.get("/api/settings/recast/999999")
        assert res.status_code == 404
