"""Discover ALL available HCSS API endpoints.

Probes every known endpoint across HeavyJob, HeavyBid, E360, and DIS/Setups
to find out exactly what data we can pull with our current credentials.

Run: PYTHONUNBUFFERED=1 python scripts/discover_all_endpoints.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

import httpx
from app.hcss.auth import HCSSAuth

BU_ID = "319078ad-cbfe-49e7-a8b4-b62fe0be273d"

# All known API base URLs
BASES = {
    "heavyjob": "https://api.hcssapps.com/heavyjob",
    "heavybid": "https://api.hcssapps.com/heavybid-estimate-insights",
    "e360": "https://api.hcssapps.com/e360",
    "setups": "https://api.hcssapps.com/setups",
}


async def probe(http, headers, label, url, params=None):
    """Probe a single endpoint and report what comes back."""
    try:
        resp = await http.get(url, params=params, headers=headers, timeout=15.0)
        status = resp.status_code
        if status == 200:
            data = resp.json()
            # Figure out record count
            if isinstance(data, list):
                count = len(data)
                sample = data[0] if data else {}
            elif isinstance(data, dict):
                results = data.get("results", data.get("data", data.get("items", data.get("value", None))))
                if results and isinstance(results, list):
                    count = len(results)
                    sample = results[0] if results else {}
                else:
                    count = "dict"
                    sample = data
            else:
                count = "?"
                sample = str(data)[:200]

            # Get field names from sample
            if isinstance(sample, dict):
                fields = list(sample.keys())[:15]
            else:
                fields = [str(sample)[:100]]

            print(f"  OK  {label}")
            print(f"       Records: {count}")
            print(f"       Fields: {fields}")
            return {"status": "ok", "count": count, "fields": fields, "sample": sample}
        elif status == 401:
            print(f"  401 {label} -- UNAUTHORIZED (missing scope?)")
            return {"status": "unauthorized"}
        elif status == 403:
            print(f"  403 {label} -- FORBIDDEN")
            return {"status": "forbidden"}
        elif status == 404:
            print(f"  404 {label} -- NOT FOUND")
            return {"status": "not_found"}
        elif status == 429:
            print(f"  429 {label} -- RATE LIMITED")
            return {"status": "rate_limited"}
        else:
            text = resp.text[:200]
            print(f"  {status} {label} -- {text}")
            return {"status": f"http_{status}"}
    except Exception as e:
        print(f"  ERR {label} -- {e}")
        return {"status": "error", "error": str(e)}


async def main():
    auth = HCSSAuth()
    if not auth.is_configured:
        print("HCSS not configured - set HCSS_CLIENT_ID and HCSS_CLIENT_SECRET")
        return

    auth._access_token = None
    auth._token_expires_at = 0
    token = await auth.get_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    print(f"Token obtained. Business Unit: {BU_ID}\n")

    # We need a sample job ID for job-specific endpoints
    # Grab one from the DB
    from app.database import get_connection
    conn = get_connection()
    sample = conn.execute(
        "SELECT hcss_job_id FROM job WHERE hcss_job_id IS NOT NULL LIMIT 1"
    ).fetchone()
    conn.close()
    sample_job_id = sample[0] if sample else None
    print(f"Sample HCSS job ID: {sample_job_id}\n")

    results = {}

    async with httpx.AsyncClient() as http:
        hj = BASES["heavyjob"]
        hb = BASES["heavybid"]
        e3 = BASES["e360"]
        su = BASES["setups"]

        print("=" * 70)
        print("HEAVYJOB ENDPOINTS")
        print("=" * 70)

        # Business units
        results["hj_businessUnits"] = await probe(
            http, headers, "HJ /api/v1/businessUnits",
            f"{hj}/api/v1/businessUnits")

        # Jobs
        results["hj_jobs"] = await probe(
            http, headers, "HJ /api/v1/jobs",
            f"{hj}/api/v1/jobs", {"businessUnitId": BU_ID, "take": 2})

        # Employees
        results["hj_employees"] = await probe(
            http, headers, "HJ /api/v1/employees",
            f"{hj}/api/v1/employees", {"businessUnitId": BU_ID, "take": 3})

        # Equipment (try several paths)
        for path in ["/api/v1/equipment", "/api/v1/equipments"]:
            results[f"hj_{path}"] = await probe(
                http, headers, f"HJ {path}",
                f"{hj}{path}", {"businessUnitId": BU_ID, "take": 3})

        # Pay classes
        for path in ["/api/v1/payClasses", "/api/v1/payclasses"]:
            results[f"hj_{path}"] = await probe(
                http, headers, f"HJ {path}",
                f"{hj}{path}", {"businessUnitId": BU_ID, "take": 3})

        # Pay items
        results["hj_payItems"] = await probe(
            http, headers, "HJ /api/v1/payItems",
            f"{hj}/api/v1/payItems", {"businessUnitId": BU_ID, "take": 3})

        # Cost codes (need jobId)
        if sample_job_id:
            results["hj_costCodes"] = await probe(
                http, headers, "HJ /api/v1/costCodes",
                f"{hj}/api/v1/costCodes", {"jobId": sample_job_id, "take": 2})

            # Cost code progress
            results["hj_costCodeProgress"] = await probe(
                http, headers, "HJ /api/v1/costCodeProgress",
                f"{hj}/api/v1/costCodeProgress", {"jobId": sample_job_id, "take": 2})

            # Timecard info (already known to work)
            results["hj_timeCardInfo"] = await probe(
                http, headers, "HJ /api/v1/timeCardInfo",
                f"{hj}/api/v1/timeCardInfo", {"jobId": sample_job_id, "take": 2})

        # Forecasts
        results["hj_forecasts"] = await probe(
            http, headers, "HJ /api/v1/forecasts",
            f"{hj}/api/v1/forecasts", {"businessUnitId": BU_ID, "take": 3})

        # Try job-level forecast
        if sample_job_id:
            results["hj_forecasts_job"] = await probe(
                http, headers, "HJ /api/v1/forecasts (jobId)",
                f"{hj}/api/v1/forecasts", {"jobId": sample_job_id, "take": 2})

        # Change orders
        for path in ["/api/v1/changeOrders", "/api/v1/changeorders"]:
            if sample_job_id:
                results[f"hj_{path}"] = await probe(
                    http, headers, f"HJ {path} (jobId)",
                    f"{hj}{path}", {"jobId": sample_job_id, "take": 3})
            results[f"hj_{path}_bu"] = await probe(
                http, headers, f"HJ {path} (buId)",
                f"{hj}{path}", {"businessUnitId": BU_ID, "take": 3})

        # Materials
        for path in ["/api/v1/materials", "/api/v1/materialEntries"]:
            if sample_job_id:
                results[f"hj_{path}_job"] = await probe(
                    http, headers, f"HJ {path} (jobId)",
                    f"{hj}{path}", {"jobId": sample_job_id, "take": 3})

        # Subcontracts
        for path in ["/api/v1/subcontracts", "/api/v1/subcontractors"]:
            if sample_job_id:
                results[f"hj_{path}_job"] = await probe(
                    http, headers, f"HJ {path} (jobId)",
                    f"{hj}{path}", {"jobId": sample_job_id, "take": 3})

        # Daily diaries / daily logs
        for path in ["/api/v1/dailyDiaries", "/api/v1/dailies", "/api/v1/diaries"]:
            if sample_job_id:
                results[f"hj_{path}"] = await probe(
                    http, headers, f"HJ {path} (jobId)",
                    f"{hj}{path}", {"jobId": sample_job_id, "take": 3})

        # Tags / notes
        for path in ["/api/v1/tags", "/api/v1/notes", "/api/v1/jobNotes"]:
            results[f"hj_{path}"] = await probe(
                http, headers, f"HJ {path}",
                f"{hj}{path}", {"businessUnitId": BU_ID, "take": 3})

        # Quantities (installed qty tracking)
        for path in ["/api/v1/quantities", "/api/v1/installedQuantities"]:
            if sample_job_id:
                results[f"hj_{path}"] = await probe(
                    http, headers, f"HJ {path} (jobId)",
                    f"{hj}{path}", {"jobId": sample_job_id, "take": 3})

        # Safety / incidents
        for path in ["/api/v1/safety", "/api/v1/incidents"]:
            results[f"hj_{path}"] = await probe(
                http, headers, f"HJ {path}",
                f"{hj}{path}", {"businessUnitId": BU_ID, "take": 3})

        await asyncio.sleep(1)  # brief pause before hitting different API

        print(f"\n{'=' * 70}")
        print("HEAVYBID ENDPOINTS")
        print("=" * 70)

        # HeavyBid business units
        results["hb_businessunits"] = await probe(
            http, headers, "HB /api/v2/integration/businessunits",
            f"{hb}/api/v2/integration/businessunits")

        # HeavyBid estimates
        results["hb_estimates"] = await probe(
            http, headers, "HB estimates",
            f"{hb}/api/v2/integration/businessunits/{BU_ID}/estimates", {"take": 3})

        # HeavyBid bid items (need estimate ID - try without filter first)
        results["hb_biditems"] = await probe(
            http, headers, "HB biditems",
            f"{hb}/api/v2/integration/businessunits/{BU_ID}/biditems", {"take": 3})

        # HeavyBid activities
        results["hb_activities"] = await probe(
            http, headers, "HB activities",
            f"{hb}/api/v2/integration/businessunits/{BU_ID}/activities", {"take": 3})

        # HeavyBid resources
        results["hb_resources"] = await probe(
            http, headers, "HB resources",
            f"{hb}/api/v2/integration/businessunits/{BU_ID}/resources", {"take": 3})

        # HeavyBid materials
        results["hb_materials"] = await probe(
            http, headers, "HB materials",
            f"{hb}/api/v2/integration/businessunits/{BU_ID}/materials", {"take": 3})

        # Codebooks
        results["hb_activityCodebook"] = await probe(
            http, headers, "HB activityCodebook",
            f"{hb}/api/v2/integration/activityCodebook", {"businessUnitId": BU_ID})

        results["hb_materialCodebook"] = await probe(
            http, headers, "HB materialCodebook",
            f"{hb}/api/v2/integration/materialCodebook", {"businessUnitId": BU_ID})

        await asyncio.sleep(1)

        print(f"\n{'=' * 70}")
        print("E360 ENDPOINTS")
        print("=" * 70)

        # E360 timecards
        results["e360_timecards"] = await probe(
            http, headers, "E360 /api/v2/timecards",
            f"{e3}/api/v2/timecards", {"businessUnitId": BU_ID, "take": 3})

        # E360 equipment
        for path in ["/api/v2/equipment", "/api/v1/equipment"]:
            results[f"e360_{path}"] = await probe(
                http, headers, f"E360 {path}",
                f"{e3}{path}", {"businessUnitId": BU_ID, "take": 3})

        # E360 work orders
        for path in ["/api/v2/workOrders", "/api/v2/workorders"]:
            results[f"e360_{path}"] = await probe(
                http, headers, f"E360 {path}",
                f"{e3}{path}", {"businessUnitId": BU_ID, "take": 3})

        await asyncio.sleep(1)

        print(f"\n{'=' * 70}")
        print("DIS / SETUPS ENDPOINTS")
        print("=" * 70)

        # DIS / Setups
        for path in [
            "/api/v1/businessUnits",
            "/api/v1/employees",
            "/api/v1/equipment",
            "/api/v1/costCodes",
            "/api/v1/payClasses",
            "/api/v1/tags",
        ]:
            results[f"setups_{path}"] = await probe(
                http, headers, f"Setups {path}",
                f"{su}{path}", {"businessUnitId": BU_ID, "take": 3})

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    ok = [k for k, v in results.items() if v.get("status") == "ok"]
    unauth = [k for k, v in results.items() if v.get("status") == "unauthorized"]
    notfound = [k for k, v in results.items() if v.get("status") == "not_found"]
    other = [k for k, v in results.items() if v.get("status") not in ("ok", "unauthorized", "not_found")]

    print(f"\n  WORKING ({len(ok)}):")
    for k in ok:
        count = results[k].get("count", "?")
        print(f"    {k}: {count} records")

    if unauth:
        print(f"\n  UNAUTHORIZED ({len(unauth)}) -- need additional scopes:")
        for k in unauth:
            print(f"    {k}")

    if notfound:
        print(f"\n  NOT FOUND ({len(notfound)}) -- endpoint doesn't exist:")
        for k in notfound:
            print(f"    {k}")

    if other:
        print(f"\n  OTHER ({len(other)}):")
        for k in other:
            print(f"    {k}: {results[k].get('status')}")

    # Save full results
    out_path = Path(__file__).parent.parent / "data" / "api_discovery_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert samples to strings for JSON serialization
    serializable = {}
    for k, v in results.items():
        sv = dict(v)
        if "sample" in sv:
            try:
                json.dumps(sv["sample"])
            except (TypeError, ValueError):
                sv["sample"] = str(sv["sample"])[:500]
        serializable[k] = sv

    with open(out_path, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\nFull results saved to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
