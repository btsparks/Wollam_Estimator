"""Backfill ChromaDB vector index from existing SQLite bid_document_chunks.

Usage:
    python scripts/backfill_vector_index.py                   # Rebuild all bids + institutional
    python scripts/backfill_vector_index.py --bid-id 918      # Rebuild single bid
    python scripts/backfill_vector_index.py --institutional    # Rebuild institutional memory only
"""

import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.vector_store import rebuild_bid_index, rebuild_institutional_index
from app.database import get_connection


def main():
    parser = argparse.ArgumentParser(description="Backfill ChromaDB vector index")
    parser.add_argument("--bid-id", type=int, help="Rebuild a single bid's index")
    parser.add_argument("--institutional", action="store_true", help="Rebuild institutional memory only")
    args = parser.parse_args()

    if args.bid_id:
        print(f"Rebuilding index for bid {args.bid_id}...")
        result = rebuild_bid_index(args.bid_id)
        print(f"  -> {result['chunks_embedded']} chunks in {result['duration_seconds']}s")

    elif args.institutional:
        print("Rebuilding institutional memory...")
        result = rebuild_institutional_index()
        print(f"  -> PM context: {result['pm_context']}")
        print(f"  -> CC context: {result['cc_context']}")
        print(f"  -> Diary: {result['diary']}")
        print(f"  -> Job documents: {result['job_document']}")
        print(f"  -> Duration: {result['duration_seconds']}s")

    else:
        # Rebuild all bids
        conn = get_connection()
        try:
            bids = conn.execute(
                "SELECT id, bid_name FROM active_bids ORDER BY id"
            ).fetchall()
        finally:
            conn.close()

        print(f"Rebuilding {len(bids)} bid(s)...")
        for bid in bids:
            print(f"  Bid {bid['id']} ({bid['bid_name']})...", end=" ")
            result = rebuild_bid_index(bid["id"])
            print(f"{result['chunks_embedded']} chunks in {result['duration_seconds']}s")

        print("\nRebuilding institutional memory...")
        result = rebuild_institutional_index()
        print(f"  -> PM context: {result['pm_context']}")
        print(f"  -> CC context: {result['cc_context']}")
        print(f"  -> Diary: {result['diary']}")
        print(f"  -> Job documents: {result['job_document']}")
        print(f"  -> Duration: {result['duration_seconds']}s")

    print("Done.")


if __name__ == "__main__":
    main()
