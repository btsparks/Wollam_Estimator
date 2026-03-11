"""Inspect a raw timecard detail to find all available fields."""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
import httpx
from app.hcss.auth import HCSSAuth
from app.database import get_connection

HJ = "https://api.hcssapps.com/heavyjob"
BU_ID = "319078ad-cbfe-49e7-a8b4-b62fe0be273d"

async def main():
    auth = HCSSAuth()
    auth._access_token = None
    auth._token_expires_at = 0
    token = await auth.get_token()
    h = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # Get a job with known timecards
    conn = get_connection()
    job = conn.execute(
        "SELECT hcss_job_id FROM job WHERE job_number = '8553'"
    ).fetchone()
    conn.close()

    async with httpx.AsyncClient() as http:
        # Get first timecard summary
        r = await http.get(f"{HJ}/api/v1/timeCardInfo",
                          params={"jobId": job["hcss_job_id"], "take": 1},
                          headers=h, timeout=15)
        summaries = r.json().get("results", [])
        if not summaries:
            print("No timecards found")
            return

        tc_id = summaries[0]["id"]
        print(f"Timecard ID: {tc_id}\n")

        # Get full detail
        r2 = await http.get(f"{HJ}/api/v1/timeCards/{tc_id}", headers=h, timeout=15)
        detail = r2.json()

        # Print top-level fields
        print("=== TOP-LEVEL FIELDS ===")
        for k, v in detail.items():
            if isinstance(v, (list, dict)):
                print(f"  {k}: [{type(v).__name__} with {len(v)} items]")
            else:
                print(f"  {k}: {v}")

        # Print employee fields
        print("\n=== EMPLOYEE FIELDS (first employee) ===")
        if detail.get("employees"):
            emp = detail["employees"][0]
            for k, v in emp.items():
                if isinstance(v, list):
                    print(f"  {k}: [{len(v)} items]")
                    if v:
                        print(f"    sample: {json.dumps(v[0], indent=4)}")
                else:
                    print(f"  {k}: {v}")

        # Print equipment fields
        print("\n=== EQUIPMENT FIELDS (first equipment) ===")
        if detail.get("equipment"):
            eq = detail["equipment"][0]
            for k, v in eq.items():
                if isinstance(v, list):
                    print(f"  {k}: [{len(v)} items]")
                    if v:
                        print(f"    sample: {json.dumps(v[0], indent=4)}")
                else:
                    print(f"  {k}: {v}")
        else:
            print("  No equipment on this timecard")

        # Print cost code fields
        print("\n=== COST CODE FIELDS (first) ===")
        if detail.get("costCodes"):
            cc = detail["costCodes"][0]
            for k, v in cc.items():
                print(f"  {k}: {v}")

asyncio.run(main())
