#!/usr/bin/env python
"""Dropbox Document Intelligence CLI.

Usage:
    python scripts/scan_dropbox.py --discover              # Phase 1: find & catalog docs
    python scripts/scan_dropbox.py --extract-excel          # Phase 2: parse Excel files
    python scripts/scan_dropbox.py --extract-excel --job 8602  # Phase 2: single job
    python scripts/scan_dropbox.py --extract-specs --job 8602  # Phase 3: AI spec extraction
    python scripts/scan_dropbox.py --extract-specs --all    # Phase 3: all jobs
    python scripts/scan_dropbox.py --enrich                 # Push extractions -> cc_context
    python scripts/scan_dropbox.py --status                 # Show scan summary
    python scripts/scan_dropbox.py --full                   # Run all phases
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_db, get_connection
from app.services.dropbox_scanner import (
    discover_projects,
    discover_and_scan_all,
    extract_excel_documents,
    extract_specs,
    enrich_context,
    get_scan_summary,
)


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def resolve_job_id(job_number: str) -> int | None:
    """Look up job_id from a job number string."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT job_id FROM job WHERE job_number = ?",
            (job_number,),
        ).fetchone()
        return row["job_id"] if row else None
    finally:
        conn.close()


def cmd_discover(args):
    """Phase 1: Discover and catalog all Dropbox project documents."""
    print("\n=== Phase 1: Dropbox Discovery & Inventory ===\n")

    # First show what projects we find
    projects = discover_projects()
    print(f"Found {len(projects)} project folders in Dropbox:\n")

    matched = [p for p in projects if p["job_id"] is not None]
    unmatched = [p for p in projects if p["job_id"] is None]

    for p in matched:
        print(f"  [MATCHED] {p['folder_name']}  ->  job_id={p['job_id']}")
    for p in unmatched:
        print(f"  [NO MATCH] {p['folder_name']}")

    print(f"\n  Matched: {len(matched)} / {len(projects)} folders\n")

    # Now scan all matched projects
    print("Scanning documents...")
    result = discover_and_scan_all()

    print(f"\nResults:")
    print(f"  Projects scanned: {result['projects_matched']}")
    print(f"  Total documents cataloged: {result['total_documents']}")
    print(f"  New documents: {result['new_documents']}")
    print(f"  Updated documents: {result['updated_documents']}")

    if result["projects_unmatched"]:
        print(f"\n  Unmatched folders ({len(result['projects_unmatched'])}):")
        for name in result["projects_unmatched"]:
            print(f"    - {name}")

    print("\nDone. Run --extract-excel next for Phase 2.\n")


def cmd_extract_excel(args):
    """Phase 2: Parse Excel files (cost code logs, RFI logs, etc.)."""
    job_id = None
    if args.job:
        job_id = resolve_job_id(args.job)
        if job_id is None:
            print(f"Error: Job {args.job} not found in database.")
            return
        print(f"\n=== Phase 2: Excel Extraction (Job {args.job}) ===\n")
    else:
        print("\n=== Phase 2: Excel Extraction (All Jobs) ===\n")

    result = extract_excel_documents(job_id=job_id)

    print(f"Results:")
    print(f"  Documents found: {result['documents_found']}")
    print(f"  Documents extracted: {result['documents_extracted']}")

    if result["errors"]:
        print(f"\n  Errors ({len(result['errors'])}):")
        for err in result["errors"]:
            print(f"    - {err['file']}: {err['error']}")

    print("\nDone. Run --extract-specs next for Phase 3, or --enrich to push to context.\n")


def cmd_extract_specs(args):
    """Phase 3: AI-powered spec extraction from PDFs."""
    job_id = None
    all_jobs = args.all if hasattr(args, "all") else False

    if args.job:
        job_id = resolve_job_id(args.job)
        if job_id is None:
            print(f"Error: Job {args.job} not found in database.")
            return
        print(f"\n=== Phase 3: AI Spec Extraction (Job {args.job}) ===\n")
    elif all_jobs:
        print("\n=== Phase 3: AI Spec Extraction (All Jobs) ===\n")
    else:
        print("Error: Specify --job <number> or --all for spec extraction.")
        return

    result = extract_specs(job_id=job_id, all_jobs=all_jobs)

    print(f"Results:")
    print(f"  Spec PDFs found: {result['specs_found']}")
    print(f"  Specs extracted: {result['specs_extracted']}")

    if result["errors"]:
        print(f"\n  Errors ({len(result['errors'])}):")
        for err in result["errors"]:
            print(f"    - {err['file']}: {err['error']}")

    print("\nDone. Run --enrich to push extractions to cc_context/pm_context.\n")


def cmd_enrich(args):
    """Push Dropbox extractions into cc_context/pm_context."""
    print("\n=== Enrichment: Dropbox -> Context Tables ===\n")

    result = enrich_context()

    print(f"Results:")
    print(f"  cc_context rows added: {result['cc_context_added']}")
    print(f"  cc_context rows updated: {result['cc_context_updated']}")
    print(f"  pm_context rows updated: {result['pm_context_updated']}")
    print("\nDone. New context will appear in AI Estimating Chat.\n")


def cmd_status(args):
    """Show scan summary."""
    print("\n=== Dropbox Scan Status ===\n")

    summary = get_scan_summary()

    print(f"  Jobs with documents: {summary['jobs_with_documents']}")
    print(f"  Total documents: {summary['total_documents']}")
    print(f"  Extracted: {summary['documents_extracted']}")
    print(f"  Pending: {summary['documents_pending']}")

    if summary["by_category"]:
        print(f"\n  By category:")
        for cat, cnt in summary["by_category"].items():
            print(f"    {cat}: {cnt}")

    print(f"\n  Total extracts: {summary['total_extracts']}")
    if summary["by_extract_type"]:
        print(f"\n  By extract type:")
        for etype, cnt in summary["by_extract_type"].items():
            print(f"    {etype}: {cnt}")

    print()


def cmd_full(args):
    """Run all phases sequentially."""
    print("\n" + "=" * 60)
    print("  DROPBOX DOCUMENT INTELLIGENCE — FULL PIPELINE")
    print("=" * 60)

    cmd_discover(args)
    cmd_extract_excel(args)

    if args.job:
        cmd_extract_specs(args)
    else:
        print("\nSkipping Phase 3 (spec extraction) — use --job or --all for AI extraction.")

    cmd_enrich(args)
    cmd_status(args)


def main():
    parser = argparse.ArgumentParser(
        description="WEIS Dropbox Document Intelligence Scanner"
    )

    parser.add_argument("--discover", action="store_true",
                        help="Phase 1: Discover and catalog documents")
    parser.add_argument("--extract-excel", action="store_true",
                        help="Phase 2: Parse Excel files")
    parser.add_argument("--extract-specs", action="store_true",
                        help="Phase 3: AI-powered spec extraction")
    parser.add_argument("--enrich", action="store_true",
                        help="Push extractions to cc_context/pm_context")
    parser.add_argument("--status", action="store_true",
                        help="Show scan summary")
    parser.add_argument("--full", action="store_true",
                        help="Run all phases")
    parser.add_argument("--job", type=str, default=None,
                        help="Job number to process (e.g., 8602)")
    parser.add_argument("--all", action="store_true",
                        help="Process all jobs (for --extract-specs)")

    args = parser.parse_args()

    setup_logging()

    # Ensure DB is up to date
    init_db()

    if args.full:
        cmd_full(args)
    elif args.discover:
        cmd_discover(args)
    elif args.extract_excel:
        cmd_extract_excel(args)
    elif args.extract_specs:
        cmd_extract_specs(args)
    elif args.enrich:
        cmd_enrich(args)
    elif args.status:
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
