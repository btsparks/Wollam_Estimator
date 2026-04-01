"""
Sync HeavyBid Estimate Insights -> WEIS SQLite

Lightweight CLI for initial sync and debugging.
Primary sync interface is the web UI (POST /api/estimates/sync).

Usage:
    python scripts/sync_heavybid.py              # Interactive: list + select
    python scripts/sync_heavybid.py --all        # Sync all available estimates
    python scripts/sync_heavybid.py --list       # List available estimates only
"""

import asyncio
import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db
from app.hcss.auth import HCSSAuth
from app.hcss.heavybid import HeavyBidAPI
from app.hcss.storage import (
    upsert_hb_estimate,
    upsert_hb_biditems,
    upsert_hb_activities,
    upsert_hb_resources,
    get_all_hb_estimates,
)

BU_ID = "319078ad-cbfe-49e7-a8b4-b62fe0be273d"


async def list_available(api: HeavyBidAPI) -> list:
    """Fetch and display available estimates from HCSS."""
    print("\nFetching estimates from HeavyBid API...")
    estimates = await api.get_estimates()
    print(f"Found {len(estimates)} estimates:\n")

    # Check which are already synced
    synced = {e["code"] for e in get_all_hb_estimates()}

    for i, est in enumerate(estimates):
        t = est.totals
        bid_total = t.bidTotal_Bid if t else 0
        manhours = t.manhours_Total if t else 0
        status = "[SYNCED]" if est.code in synced else "[NEW]   "
        print(
            f"  {i+1:3d}. {status} {est.code or '?':20s} "
            f"{est.name or '':30s} "
            f"${bid_total or 0:>12,.0f}  "
            f"{manhours or 0:>8,.0f} MH"
        )

    return estimates


async def sync_estimate(api: HeavyBidAPI, estimate, bu_id: str):
    """Sync a single estimate with all child data."""
    code = estimate.code or estimate.id
    print(f"\n--- Syncing: {code} ({estimate.name}) ---")

    # 1. Upsert estimate
    est_id = upsert_hb_estimate(estimate, bu_id)
    print(f"  Estimate -> ID {est_id}")

    # 2. Bid items
    biditems = await api.get_biditems(estimate.id)
    bi_count = upsert_hb_biditems(biditems, est_id)
    print(f"  Bid Items -> {bi_count}")

    # 3. Activities
    activities = await api.get_activities(estimate.id)
    act_count = upsert_hb_activities(activities, est_id)
    print(f"  Activities -> {act_count}")

    # 4. Resources
    resources = await api.get_resources(estimate.id)
    res_count = upsert_hb_resources(resources, est_id)
    print(f"  Resources -> {res_count}")

    return {"biditems": bi_count, "activities": act_count, "resources": res_count}


async def main():
    parser = argparse.ArgumentParser(description="Sync HeavyBid estimates to WEIS")
    parser.add_argument("--all", action="store_true", help="Sync all available estimates")
    parser.add_argument("--list", action="store_true", help="List available estimates only")
    args = parser.parse_args()

    # Init DB (runs migration if needed)
    init_db()

    auth = HCSSAuth()
    if not auth.is_configured:
        print("ERROR: HCSS credentials not configured. Set HCSS_CLIENT_ID and HCSS_CLIENT_SECRET.")
        sys.exit(1)

    api = HeavyBidAPI(auth, BU_ID)
    estimates = await list_available(api)

    if not estimates:
        print("No estimates found.")
        return

    if args.list:
        return

    if args.all:
        selected = estimates
    else:
        print("\nEnter estimate numbers to sync (comma-separated, e.g. '1,3,5' or 'all'):")
        choice = input("> ").strip().lower()
        if choice == "all":
            selected = estimates
        elif choice in ("q", "quit", "exit", ""):
            print("Cancelled.")
            return
        else:
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(",")]
                selected = [estimates[i] for i in indices if 0 <= i < len(estimates)]
            except (ValueError, IndexError):
                print("Invalid selection.")
                return

    print(f"\nSyncing {len(selected)} estimate(s)...")
    totals = {"biditems": 0, "activities": 0, "resources": 0}
    for est in selected:
        result = await sync_estimate(api, est, BU_ID)
        for k in totals:
            totals[k] += result[k]

    print(f"\n{'='*50}")
    print(f"DONE: {len(selected)} estimates synced")
    print(f"  Bid Items:  {totals['biditems']}")
    print(f"  Activities: {totals['activities']}")
    print(f"  Resources:  {totals['resources']}")


if __name__ == "__main__":
    asyncio.run(main())
