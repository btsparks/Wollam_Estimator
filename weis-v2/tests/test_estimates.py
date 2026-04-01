"""Tests for the HeavyBid Estimates API endpoints."""

import re
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_connection
from app.hcss.models import (
    HBEstimate, HBEstimateFilters, HBEstimateTotals,
    HBBidItem, HBActivity, HBResource,
)
from app.hcss.storage import (
    upsert_hb_estimate, upsert_hb_biditems,
    upsert_hb_activities, upsert_hb_resources,
    get_all_hb_estimates, get_hb_estimate_detail,
    get_hb_biditems, get_hb_activities, get_hb_resources,
    get_hb_estimates_for_job,
)

client = TestClient(app)


# ── Fixtures ──

def _seed_estimate():
    """Insert a test estimate and return its local estimate_id."""
    est = HBEstimate(
        id="test-est-001",
        code="9999-TEST",
        name="Test Welding Estimate",
        processedStatus=2,
        estimateVersion="2021.2",
        businessUnitId="test-bu",
        filters=HBEstimateFilters(
            state="UT", estimator="Travis", bidDate="2026-03-01",
            createdDate="2026-02-01", modifiedDate="2026-03-15",
        ),
        totals=HBEstimateTotals(
            totalLabor_Total=5000.0, burden_Total=2500.0,
            permanentMaterial_Total=1000.0, constructionMaterial_Total=0.0,
            subcontract_Total=0.0,
            equipmentOperatingExpense_Total=500.0, companyEquipment_Total=300.0,
            rentedEquipment_Total=0.0, totalEqp_Total=800.0,
            totalEntryCost_Bid_Total=9300.0, bidTotal_Bid=10000.0,
            manhours_Total=100.0, balMarkup_Bid=700.0, actualMarkup_Bid=700.0,
            totalCost_Takeoff=9300.0, addonBondTotal=50.0, job_Duration=5.0,
        ),
    )
    return upsert_hb_estimate(est, "test-bu")


def _seed_biditems(estimate_id):
    items = [
        HBBidItem(id="bi-001", estimateId="test-est-001", biditemCode="10",
                   description="Fillet Weld", type="D", quantity=100.0,
                   units="IN", bidPrice=5000.0, labor=2000.0, burden=1000.0,
                   permanentMaterial=500.0, totalCost=4000.0, manhours=60.0),
        HBBidItem(id="bi-002", estimateId="test-est-001", biditemCode="20",
                   description="Full Pen Weld", type="D", quantity=50.0,
                   units="IN", bidPrice=5000.0, labor=3000.0, burden=1500.0,
                   permanentMaterial=500.0, totalCost=5300.0, manhours=40.0),
    ]
    return upsert_hb_biditems(items, estimate_id)


def _seed_activities(estimate_id):
    acts = [
        HBActivity(id="act-001", estimateId="test-est-001", biditemId="bi-001",
                    biditemCode="10", activityCode="A.10",
                    description="Fillet Stitch Weld", quantity=100.0, units="IN",
                    productionType="UH", productionRate=30.0, hoursPerDay=10.0,
                    crew="Z", crewHours=20.0, manHours=60.0, calculatedDuration=2.0,
                    labor=2000.0, burden=1000.0, permanentMaterial=500.0,
                    directTotal=4000.0, crewCost=3500.0,
                    notes="Test welding notes - 300 inch day is doable"),
        HBActivity(id="act-002", estimateId="test-est-001", biditemId="bi-002",
                    biditemCode="20", activityCode="A.10",
                    description="Full Pen Stitch Weld", quantity=50.0, units="IN",
                    productionType="UH", productionRate=12.0, hoursPerDay=10.0,
                    crew="Z", crewHours=50.0, manHours=40.0, calculatedDuration=5.0,
                    labor=3000.0, burden=1500.0, permanentMaterial=500.0,
                    directTotal=5300.0, notes="Full pen requires two passes"),
    ]
    return upsert_hb_activities(acts, estimate_id)


def _seed_resources(estimate_id):
    resources = [
        HBResource(id="res-001", estimateId="test-est-001", biditemId="bi-001",
                    activityId="act-001", activityCode="A.10", biditemCode="10",
                    resourceCode="WELD1", description="Welder",
                    typeCost="L", quantity=1.0, units="HR", unitPrice=45.0, total=900.0),
        HBResource(id="res-002", estimateId="test-est-001", biditemId="bi-001",
                    activityId="act-001", activityCode="A.10", biditemCode="10",
                    resourceCode="FIREWATCH", description="Fire Watch",
                    typeCost="L", quantity=1.0, units="HR", unitPrice=30.0, total=600.0),
    ]
    return upsert_hb_resources(resources, estimate_id)


# ── Job Number Parsing ──

class TestJobNumberParsing:
    def test_parse_standard_code(self):
        m = re.match(r'^(\d+)', '8553-CO-WEIR')
        assert m and m.group(1) == '8553'

    def test_parse_simple_number(self):
        m = re.match(r'^(\d+)', '8602')
        assert m and m.group(1) == '8602'

    def test_parse_no_number(self):
        m = re.match(r'^(\d+)', 'MISC-ESTIMATE')
        assert m is None

    def test_parse_leading_zeros(self):
        m = re.match(r'^(\d+)', '0042-JOB')
        assert m and m.group(1) == '0042'


# ── Storage Layer ──

class TestEstimateStorage:
    def test_upsert_estimate(self):
        est_id = _seed_estimate()
        assert est_id is not None
        assert isinstance(est_id, int)

    def test_upsert_biditems(self):
        est_id = _seed_estimate()
        count = _seed_biditems(est_id)
        assert count == 2

    def test_upsert_activities(self):
        est_id = _seed_estimate()
        count = _seed_activities(est_id)
        assert count == 2

    def test_upsert_resources(self):
        est_id = _seed_estimate()
        count = _seed_resources(est_id)
        assert count == 2

    def test_get_all_estimates(self):
        _seed_estimate()
        estimates = get_all_hb_estimates()
        assert len(estimates) > 0
        test_est = [e for e in estimates if e['code'] == '9999-TEST']
        assert len(test_est) > 0

    def test_get_estimate_detail(self):
        est_id = _seed_estimate()
        detail = get_hb_estimate_detail(est_id)
        assert detail is not None
        assert detail['code'] == '9999-TEST'
        assert detail['bid_total'] == 10000.0

    def test_get_biditems(self):
        est_id = _seed_estimate()
        _seed_biditems(est_id)
        items = get_hb_biditems(est_id)
        assert len(items) == 2
        assert items[0]['description'] in ('Fillet Weld', 'Full Pen Weld')

    def test_get_activities(self):
        est_id = _seed_estimate()
        _seed_activities(est_id)
        acts = get_hb_activities(est_id)
        assert len(acts) == 2

    def test_get_activities_filtered_by_biditem(self):
        est_id = _seed_estimate()
        _seed_activities(est_id)
        acts = get_hb_activities(est_id, biditem_id='bi-001')
        assert len(acts) == 1
        assert acts[0]['description'] == 'Fillet Stitch Weld'

    def test_get_resources(self):
        est_id = _seed_estimate()
        _seed_resources(est_id)
        res = get_hb_resources(est_id)
        assert len(res) == 2

    def test_get_resources_filtered_by_activity(self):
        est_id = _seed_estimate()
        _seed_resources(est_id)
        res = get_hb_resources(est_id, activity_id='act-001')
        assert len(res) == 2

    def test_resync_replaces_data(self):
        est_id = _seed_estimate()
        _seed_biditems(est_id)
        assert len(get_hb_biditems(est_id)) == 2
        # Re-seed should replace, not duplicate
        _seed_biditems(est_id)
        assert len(get_hb_biditems(est_id)) == 2

    def test_mapped_costcode_column_exists(self):
        est_id = _seed_estimate()
        _seed_activities(est_id)
        acts = get_hb_activities(est_id)
        assert 'mapped_costcode' in acts[0]
        assert acts[0]['mapped_costcode'] is None


# ── API Endpoints ──

class TestEstimateAPI:
    def test_list_estimates_returns_200(self):
        _seed_estimate()
        r = client.get("/api/estimates/")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_estimate_detail_returns_200(self):
        est_id = _seed_estimate()
        r = client.get(f"/api/estimates/{est_id}")
        assert r.status_code == 200
        data = r.json()
        assert data['code'] == '9999-TEST'
        assert data['bid_total'] == 10000.0

    def test_get_estimate_404(self):
        r = client.get("/api/estimates/99999")
        assert r.status_code == 404

    def test_get_biditems_returns_200(self):
        est_id = _seed_estimate()
        _seed_biditems(est_id)
        r = client.get(f"/api/estimates/{est_id}/biditems")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_get_activities_returns_200(self):
        est_id = _seed_estimate()
        _seed_activities(est_id)
        r = client.get(f"/api/estimates/{est_id}/activities")
        assert r.status_code == 200
        acts = r.json()
        assert len(acts) == 2
        # Verify notes are present (critical requirement)
        noted = [a for a in acts if a.get('notes')]
        assert len(noted) == 2

    def test_get_activities_filtered(self):
        est_id = _seed_estimate()
        _seed_activities(est_id)
        r = client.get(f"/api/estimates/{est_id}/activities?biditem_id=bi-001")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_get_resources_returns_200(self):
        est_id = _seed_estimate()
        _seed_resources(est_id)
        r = client.get(f"/api/estimates/{est_id}/resources")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_list_estimates_by_linked_job(self):
        _seed_estimate()  # code=9999-TEST, won't have a linked job
        r = client.get("/api/estimates/?linked_job_id=99999")
        assert r.status_code == 200
        # No match expected for fake job_id
        assert isinstance(r.json(), list)
