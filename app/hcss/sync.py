"""
HCSS Sync Orchestrator — Stub for Phase D

Manages the data sync workflow between HCSS systems and the WEIS database.
This module will be the entry point for:
    - Full sync (all closed jobs)
    - Incremental sync (jobs modified since last sync)
    - Job-to-estimate matching (linking HeavyJob actuals to HeavyBid estimates)

Currently a stub — only match_estimate_to_job is implemented because
it's pure logic (no API calls needed). All other methods raise
NotImplementedError until Phase D when API credentials are available.

Sync workflow (Phase D):
    1. Authenticate to HCSS (OAuth client credentials)
    2. Pull all closed jobs from HeavyJob
    3. For each job: pull cost codes, timecards, COs, materials, subs
    4. Match each job to its HeavyBid estimate (by job number)
    5. Pull estimate details (bid items, activities, resources)
    6. Store everything in raw data layer
    7. Trigger transformation pipeline (rate card generation)
    8. Mark rate cards as pending_review for PM interview
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.hcss.models import HBEstimate


class HCSSSyncOrchestrator:
    """
    Orchestrates data sync between HCSS APIs and WEIS database.

    Phase D will implement the full sync workflow. Currently only
    match_estimate_to_job is implemented.

    Usage (Phase D):
        orchestrator = HCSSSyncOrchestrator(heavyjob_api, heavybid_api, db)
        result = await orchestrator.sync_all_closed_jobs()
        print(f"Synced {result['jobs_processed']} jobs")
    """

    def __init__(self, heavyjob_api: Any = None, heavybid_api: Any = None, db: Any = None):
        """
        Args:
            heavyjob_api: HeavyJobAPI instance (Phase D).
            heavybid_api: HeavyBidAPI instance (Phase D).
            db: Database connection or session (Phase D).
        """
        self._hj = heavyjob_api
        self._hb = heavybid_api
        self._db = db

    async def sync_all_closed_jobs(self) -> dict[str, Any]:
        """
        Full sync — pull all closed jobs and their data from HCSS.

        Workflow:
            1. Get all closed jobs from HeavyJob
            2. For each job, pull cost codes, timecards, COs, materials, subs
            3. Match to HeavyBid estimate and pull bid data
            4. Store in raw data layer
            5. Generate rate cards

        Returns:
            Dict with jobs_processed, jobs_failed, errors.
        """
        raise NotImplementedError("Phase D — requires HCSS API credentials")

    async def sync_job(self, job_id: str) -> dict[str, Any]:
        """
        Sync a single job by its HCSS UUID.

        Pulls all data for one job (cost codes, timecards, COs, materials,
        subs) plus its matched estimate from HeavyBid.

        Args:
            job_id: HCSS job UUID.

        Returns:
            Dict with job details and sync status.
        """
        raise NotImplementedError("Phase D — requires HCSS API credentials")

    async def sync_incremental(self, since: datetime) -> dict[str, Any]:
        """
        Incremental sync — only jobs modified since a given timestamp.

        More efficient than full sync for regular updates. Checks the
        sync_metadata table for last successful sync and only pulls
        jobs modified after that point.

        Args:
            since: Datetime to sync from (typically last successful sync time).

        Returns:
            Dict with jobs_processed, jobs_skipped, jobs_failed.
        """
        raise NotImplementedError("Phase D — requires HCSS API credentials")

    def match_estimate_to_job(
        self,
        job_number: str,
        estimates: list[HBEstimate],
    ) -> HBEstimate | None:
        """
        Match a HeavyBid estimate to a job by job number.

        Searches estimate names for the job number. HCSS convention is
        to include the job number in the estimate name (e.g., "8553 RTK
        SPD Pump Station" or "Job 8553 - SPD Pump Station").

        This is the one method implemented in Phase A because it's pure
        matching logic — no API calls needed.

        Args:
            job_number: Wollam job number (e.g., '8553').
            estimates: List of HBEstimate models to search.

        Returns:
            Matching HBEstimate, or None if no match found.
        """
        job_num = str(job_number).strip()

        for estimate in estimates:
            est_name = (estimate.name or "").strip()

            # Check if the job number appears in the estimate name
            # Common patterns: "8553 RTK SPD", "Job 8553", "8553-RTK"
            if job_num in est_name:
                return estimate

        return None
