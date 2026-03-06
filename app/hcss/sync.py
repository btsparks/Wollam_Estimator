"""
HCSS Sync Orchestrator — Protocol-Based Data Pipeline

Manages the data sync workflow between HCSS systems (or mock sources)
and the WEIS database. Uses Protocol-based dependency injection so the
orchestrator never knows whether it's talking to real APIs or mock files.

When credentials arrive, the only change is:
    orchestrator = HCSSSyncOrchestrator(
        heavyjob_source=HeavyJobAPI(client, bu_id),
        heavybid_source=HeavyBidAPI(client, bu_id),
    )
No code changes required.

Sync workflow:
    1. Pull all closed jobs from source
    2. For each job: pull cost codes (timecards/COs/materials/subs optional)
    3. Match each job to its HeavyBid estimate (by job number)
    4. Store everything in raw data layer (Tier 1)
    5. Generate rate cards via RateCardGenerator (Tier 2)
    6. Store rate cards in DB
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.hcss.models import (
    HBEstimate,
    HJCostCode,
    HJJob,
)
from app.hcss import storage
from app.transform.mapper import DisciplineMapper
from app.transform.rate_card import RateCardGenerator

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Source Protocols — any object matching these interfaces works
# ─────────────────────────────────────────────────────────────

@runtime_checkable
class HeavyJobSource(Protocol):
    """Interface for fetching HeavyJob data."""

    async def get_jobs(self, status: str | None = None) -> list[HJJob]: ...
    async def get_cost_codes(self, job_id: str) -> list[HJCostCode]: ...


@runtime_checkable
class HeavyBidSource(Protocol):
    """Interface for fetching HeavyBid data."""

    async def get_estimates(self) -> list[HBEstimate]: ...


# ─────────────────────────────────────────────────────────────
# Mock Sources — Read from Phase B JSON files
# ─────────────────────────────────────────────────────────────

MOCK_DATA_DIR = Path(__file__).parent.parent.parent / "tests" / "mock_data"


class MockHeavyJobSource:
    """Reads job and cost code data from tests/mock_data/heavyjob/*.json."""

    def __init__(self, data_dir: Path | None = None):
        self._dir = (data_dir or MOCK_DATA_DIR) / "heavyjob"

    async def get_jobs(self, status: str | None = None) -> list[HJJob]:
        jobs = []
        for path in sorted(self._dir.glob("job_*.json")):
            with open(path) as f:
                data = json.load(f)
            job = HJJob.model_validate(data)
            if status is None or job.status == status:
                jobs.append(job)
        return jobs

    async def get_cost_codes(self, job_id: str) -> list[HJCostCode]:
        # Extract job number from job_id (e.g., "job-8553" -> "8553")
        job_num = job_id.replace("job-", "")
        path = self._dir / f"costcodes_{job_num}.json"
        if not path.exists():
            return []
        with open(path) as f:
            data = json.load(f)
        return [HJCostCode.model_validate(cc) for cc in data]


class MockHeavyBidSource:
    """Reads estimate data from tests/mock_data/heavybid/*.json."""

    def __init__(self, data_dir: Path | None = None):
        self._dir = (data_dir or MOCK_DATA_DIR) / "heavybid"

    async def get_estimates(self) -> list[HBEstimate]:
        estimates = []
        for path in sorted(self._dir.glob("estimate_*.json")):
            with open(path) as f:
                data = json.load(f)
            estimates.append(HBEstimate.model_validate(data))
        return estimates


# ─────────────────────────────────────────────────────────────
# Sync Orchestrator
# ─────────────────────────────────────────────────────────────

class HCSSSyncOrchestrator:
    """
    Orchestrates data sync between HCSS sources and WEIS database.

    Accepts any object matching HeavyJobSource/HeavyBidSource protocols.
    The real HeavyJobAPI/HeavyBidAPI implement the same interface.

    Usage:
        # Mock (Phase C testing):
        orchestrator = HCSSSyncOrchestrator(
            heavyjob_source=MockHeavyJobSource(),
            heavybid_source=MockHeavyBidSource(),
        )
        result = await orchestrator.sync_all_closed_jobs()

        # Live (when credentials arrive):
        orchestrator = HCSSSyncOrchestrator(
            heavyjob_source=HeavyJobAPI(client, bu_id),
            heavybid_source=HeavyBidAPI(client, bu_id),
        )
        result = await orchestrator.sync_all_closed_jobs()
    """

    def __init__(
        self,
        heavyjob_source: Any = None,
        heavybid_source: Any = None,
        bu_name: str = "Wollam Construction",
        bu_hcss_id: str = "bu-wollam-001",
    ):
        self._hj = heavyjob_source
        self._hb = heavybid_source
        self._bu_name = bu_name
        self._bu_hcss_id = bu_hcss_id
        self._mapper = DisciplineMapper()
        self._generator = RateCardGenerator(mapper=self._mapper)

    async def sync_all_closed_jobs(self) -> dict[str, Any]:
        """
        Full sync — pull all closed jobs and their data from source.

        Workflow:
            1. Create sync_metadata record
            2. Ensure business unit exists
            3. Get all closed jobs from HeavyJob source
            4. Get all estimates from HeavyBid source
            5. For each job: store raw data, match estimate, generate rate card
            6. Update sync_metadata with results

        Returns:
            Dict with jobs_processed, jobs_failed, errors, sync_id.
        """
        if not self._hj or not self._hb:
            raise RuntimeError("No data sources configured. Set heavyjob_source and heavybid_source.")

        sync_id = storage.create_sync_record(
            source="hcss_api", sync_type="full",
            notes="Full sync of all closed jobs",
        )

        jobs_processed = 0
        jobs_failed = 0
        errors = []

        try:
            # Ensure business unit exists
            bu_id = storage.upsert_business_unit(self._bu_hcss_id, self._bu_name)

            # Pull all closed jobs
            jobs = await self._hj.get_jobs(status="Closed")
            logger.info(f"Found {len(jobs)} closed jobs to sync")

            # Pull all estimates for matching
            estimates = await self._hb.get_estimates()
            logger.info(f"Found {len(estimates)} estimates for matching")

            for job in jobs:
                try:
                    await self._sync_single_job(job, bu_id, estimates)
                    jobs_processed += 1
                except Exception as e:
                    jobs_failed += 1
                    errors.append(f"Job {job.jobNumber}: {e}")
                    logger.error(f"Failed to sync job {job.jobNumber}: {e}")

            storage.update_sync_record(
                sync_id, status="completed",
                jobs_processed=jobs_processed,
                jobs_failed=jobs_failed,
                error_log="\n".join(errors) if errors else None,
            )

        except Exception as e:
            storage.update_sync_record(
                sync_id, status="failed",
                jobs_processed=jobs_processed,
                jobs_failed=jobs_failed,
                error_log=str(e),
            )
            raise

        return {
            "sync_id": sync_id,
            "jobs_processed": jobs_processed,
            "jobs_failed": jobs_failed,
            "errors": errors,
        }

    async def sync_job(self, job_id: str) -> dict[str, Any]:
        """
        Sync a single job by its HCSS UUID.

        Args:
            job_id: HCSS job UUID (e.g., "job-8553").

        Returns:
            Dict with job details and sync status.
        """
        if not self._hj or not self._hb:
            raise RuntimeError("No data sources configured.")

        sync_id = storage.create_sync_record(
            source="hcss_api", sync_type="single",
            notes=f"Single job sync: {job_id}",
        )

        try:
            bu_id = storage.upsert_business_unit(self._bu_hcss_id, self._bu_name)

            # Find the job in the source
            all_jobs = await self._hj.get_jobs()
            job = next((j for j in all_jobs if j.id == job_id), None)
            if not job:
                raise ValueError(f"Job {job_id} not found in source")

            estimates = await self._hb.get_estimates()
            await self._sync_single_job(job, bu_id, estimates)

            storage.update_sync_record(
                sync_id, status="completed", jobs_processed=1,
            )
            return {"sync_id": sync_id, "job_id": job_id, "status": "completed"}

        except Exception as e:
            storage.update_sync_record(
                sync_id, status="failed", error_log=str(e),
            )
            raise

    async def sync_incremental(self, since: datetime) -> dict[str, Any]:
        """
        Incremental sync — delegates to full sync for now.

        A true incremental sync would only pull jobs modified since `since`,
        but the mock sources don't support modification timestamps.
        When live API is connected, this can filter by lastModified.

        Args:
            since: Datetime to sync from.

        Returns:
            Dict with sync results.
        """
        return await self.sync_all_closed_jobs()

    async def _sync_single_job(
        self,
        job: HJJob,
        bu_id: int,
        estimates: list[HBEstimate],
    ) -> None:
        """
        Per-job pipeline: store raw → match estimate → transform → store rate card.

        Args:
            job: HJJob model from source.
            bu_id: Database business_unit ID.
            estimates: All available estimates for matching.
        """
        logger.info(f"Syncing job {job.jobNumber}: {job.description}")

        # 1. Store job record
        job_id = storage.upsert_job(job, bu_id, data_source="hcss_api")

        # 2. Pull and store cost codes
        cost_codes = await self._hj.get_cost_codes(job.id)
        storage.upsert_cost_codes(cost_codes, job_id, mapper=self._mapper)
        logger.info(f"  Stored {len(cost_codes)} cost codes for job {job.jobNumber}")

        # 3. Match to HeavyBid estimate
        estimate = self.match_estimate_to_job(job.jobNumber, estimates)
        if estimate:
            est_id = storage.upsert_estimate(estimate, bu_id)
            storage.link_job_to_estimate(job_id, est_id)
            logger.info(f"  Matched estimate: {estimate.name}")

        # 4. Generate rate card
        card = self._generator.generate_rate_card(
            job_number=job.jobNumber,
            job_name=job.description or "",
            cost_codes=cost_codes,
            estimate=estimate,
        )

        # 5. Store rate card and items
        card_id = storage.upsert_rate_card(card, job_id)
        storage.upsert_rate_items(card.items, card_id)
        logger.info(
            f"  Rate card: {len(card.items)} items, "
            f"{len(card.flagged_items)} flagged"
        )

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

        Args:
            job_number: Wollam job number (e.g., '8553').
            estimates: List of HBEstimate models to search.

        Returns:
            Matching HBEstimate, or None if no match found.
        """
        job_num = str(job_number).strip()

        for estimate in estimates:
            est_name = (estimate.name or "").strip()
            if job_num in est_name:
                return estimate

        return None
