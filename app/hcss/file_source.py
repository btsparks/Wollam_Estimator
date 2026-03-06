"""
File-Based HeavyJob Source — Reads real HeavyJob exported reports.

Implements the HeavyJobSource protocol so the sync orchestrator can ingest
data from manually exported report files (CstAlys.xlsx + LaborHoursReview.txt)
exactly the same way it would from the live API.

File naming convention:
    {job_number} - CstAlys.xlsx           Cost Analysis (costs, quantities)
    {job_number} - LaborHoursReview.txt   Labor Hours Review (labor hours)

Both files are merged by cost code to produce complete HJCostCode models.
CstAlys provides dollar costs; LaborHoursReview provides labor hours.

Usage:
    from app.hcss.file_source import FileHeavyJobSource, EmptyHeavyBidSource

    orchestrator = HCSSSyncOrchestrator(
        heavyjob_source=FileHeavyJobSource(Path("HJ Cost Reports")),
        heavybid_source=EmptyHeavyBidSource(),
    )
    result = await orchestrator.sync_all_closed_jobs()
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.hcss.models import HBEstimate, HJCostCode, HJJob

logger = logging.getLogger(__name__)


class FileHeavyJobSource:
    """
    Reads HeavyJob data from exported CstAlys.xlsx + LaborHoursReview.txt files.

    Discovers jobs by scanning the reports directory for CstAlys files.
    Merges cost data (from xlsx) with labor hours (from txt) by cost code.
    """

    def __init__(self, reports_dir: Path):
        self._dir = reports_dir

    async def get_jobs(self, status: str | None = None) -> list[HJJob]:
        """Discover jobs from CstAlys files in the reports directory."""
        jobs = []
        for path in sorted(self._dir.glob("* - CstAlys.xlsx")):
            job_number = path.name.split(" - ")[0].strip()
            job_name = self._extract_job_name(job_number)

            job = HJJob(
                id=f"file-{job_number}",
                jobNumber=job_number,
                description=job_name,
                status="Closed",  # Treat file-delivered reports as ready for analysis
            )
            if status is None or job.status == status:
                jobs.append(job)

        logger.info(f"FileHeavyJobSource: found {len(jobs)} jobs in {self._dir}")
        return jobs

    async def get_cost_codes(self, job_id: str) -> list[HJCostCode]:
        """Parse CstAlys.xlsx + LaborHoursReview.txt for a job."""
        job_number = job_id.replace("file-", "")

        cost_path = self._dir / f"{job_number} - CstAlys.xlsx"
        labor_path = self._dir / f"{job_number} - LaborHoursReview.txt"

        if not cost_path.exists():
            logger.warning(f"No CstAlys file for job {job_number}")
            return []

        # Parse cost data from Excel
        cost_data = self._parse_cost_analysis(cost_path)
        logger.info(f"  Parsed {len(cost_data)} cost codes from CstAlys for job {job_number}")

        # Parse labor hours from text file (if available)
        labor_data = {}
        if labor_path.exists():
            labor_data = self._parse_labor_hours(labor_path)
            logger.info(f"  Parsed {len(labor_data)} cost codes from LaborHoursReview for job {job_number}")

        # Merge into HJCostCode models
        return self._merge_cost_and_labor(job_id, cost_data, labor_data)

    def _extract_job_name(self, job_number: str) -> str:
        """Extract job name from LaborHoursReview.txt header, or use job number."""
        labor_path = self._dir / f"{job_number} - LaborHoursReview.txt"
        if labor_path.exists():
            try:
                with open(labor_path, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f):
                        if "Job Name:" in line:
                            name = line.split("Job Name:")[1].strip()
                            # Remove trailing "Job Code 8587" if on same line
                            name = re.split(r"\s{3,}|Job Code", name)[0].strip()
                            if name:
                                return name
                        if i > 10:
                            break
            except Exception:
                pass
        return f"Job {job_number}"

    def _parse_cost_analysis(self, path: Path) -> dict[str, dict[str, Any]]:
        """
        Parse CstAlys.xlsx into cost data keyed by cost code.

        Column layout (0-indexed):
            0: Cost Code (int)       1: Description
            2: Qty Budget            3: Qty Placed (actual)
            4: Unit                  5: % Complete
            6: Lab $ Expected*       7: Lab $ Actual
            8: Equip $ Expected*     9: Equip $ Actual
           10: Matl-Sub-Exp Exp*    11: Matl-Sub-Exp Actual
           12: Total $ Budget       13: Total $ Expected*
           14: Total $ Actual       15: Diff
           16: Flag

        * "Expected" = Budget × (%Complete / 100), NOT the raw budget.
          Raw category budget can be derived: budget = expected / (pct/100)
          when pct > 0.
        """
        import openpyxl

        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active
        result = {}

        for row in ws.iter_rows(min_row=3, values_only=True):
            # Skip summary/blank rows
            if row[0] is None or not isinstance(row[0], (int, float)):
                continue

            code = str(int(row[0]))
            pct = _num(row[5]) or 0

            # Derive budget costs from Expected / (pct/100) when possible
            lab_expected = _num(row[6])
            equip_expected = _num(row[8])
            matl_sub_expected = _num(row[10])

            lab_budget = None
            equip_budget = None
            matl_sub_budget = None
            if pct > 0:
                lab_budget = round(lab_expected / (pct / 100), 2) if lab_expected else None
                equip_budget = round(equip_expected / (pct / 100), 2) if equip_expected else None
                matl_sub_budget = round(matl_sub_expected / (pct / 100), 2) if matl_sub_expected else None

            result[code] = {
                "code": code,
                "description": str(row[1]).strip() if row[1] else None,
                "qty_budget": _num(row[2]),
                "qty_actual": _num(row[3]),
                "unit": str(row[4]).strip() if row[4] else None,
                "pct_complete": pct,
                "lab_cost_budget": lab_budget,
                "lab_cost_actual": _num(row[7]),
                "equip_cost_budget": equip_budget,
                "equip_cost_actual": _num(row[9]),
                "matl_sub_cost_budget": matl_sub_budget,
                "matl_sub_cost_actual": _num(row[11]),
                "total_budget": _num(row[12]),
                "total_actual": _num(row[14]),
                "flag": str(row[16]).strip() if row[16] else None,
            }

        wb.close()
        return result

    def _parse_labor_hours(self, path: Path) -> dict[str, dict[str, float | None]]:
        """
        Parse LaborHoursReview.txt into labor hours keyed by cost code.

        Fixed-width text format. Data rows start with 4-digit cost code.
        Extracts: Labor Hrs Budgeted, Expected, Actual, Difference.
        """
        pattern = re.compile(
            r"^\s+(\d{4})\s+"       # Cost code (4 digits)
            r"(.+?)\s{2,}"          # Description
            r"([\d,.]+)\s+"         # Qty Budgeted
            r"([\d,.]+)\s+"         # Qty Placed
            r"(\w+)\s+"            # Unit
            r"(\d+)\s+"            # % Comp
            r"([\d,.]+)\s+"        # Labor Hrs Budgeted
            r"([\d,.]+)\s+"        # Labor Hrs Expected
            r"([\d,.]+)\s+"        # Labor Hrs Actual
            r"(-?[\d,.]+)"         # Labor Hrs Difference
        )

        result = {}
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = pattern.match(line)
                    if not m:
                        continue

                    code = m.group(1)
                    hrs_budgeted = _parse_number(m.group(7))
                    hrs_actual = _parse_number(m.group(9))

                    result[code] = {
                        "labor_hrs_budgeted": hrs_budgeted,
                        "labor_hrs_actual": hrs_actual,
                    }
        except Exception as e:
            logger.error(f"Error parsing LaborHoursReview: {e}")

        return result

    def _merge_cost_and_labor(
        self,
        job_id: str,
        cost_data: dict[str, dict],
        labor_data: dict[str, dict],
    ) -> list[HJCostCode]:
        """Merge cost analysis data with labor hours by cost code."""
        cost_codes = []

        for code, cost in cost_data.items():
            labor = labor_data.get(code, {})

            cc = HJCostCode(
                id=f"{job_id}-cc-{code}",
                jobId=job_id,
                code=code,
                description=cost.get("description"),
                unit=cost.get("unit"),

                # Quantities
                budgetQuantity=cost.get("qty_budget"),
                actualQuantity=cost.get("qty_actual"),

                # Labor hours from LaborHoursReview
                budgetLaborHours=labor.get("labor_hrs_budgeted"),
                actualLaborHours=labor.get("labor_hrs_actual"),

                # Labor costs from CstAlys
                budgetLaborCost=cost.get("lab_cost_budget"),
                actualLaborCost=cost.get("lab_cost_actual"),

                # Equipment costs from CstAlys
                budgetEquipmentCost=cost.get("equip_cost_budget"),
                actualEquipmentCost=cost.get("equip_cost_actual"),

                # Material costs (combined with sub/exp in CstAlys)
                budgetMaterialCost=cost.get("matl_sub_cost_budget"),
                actualMaterialCost=cost.get("matl_sub_cost_actual"),

                # Total costs
                budgetTotalCost=cost.get("total_budget"),
                actualTotalCost=cost.get("total_actual"),

                # Progress
                percentComplete=cost.get("pct_complete"),
            )
            cost_codes.append(cc)

        return cost_codes


class EmptyHeavyBidSource:
    """Returns empty estimates — used when no HeavyBid data is available."""

    async def get_estimates(self) -> list[HBEstimate]:
        return []


def _num(val: Any) -> float | None:
    """Convert Excel cell value to float, handling None and strings."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_number(s: str) -> float | None:
    """Parse a formatted number string (e.g., '2,420.00', '-33.00')."""
    if not s:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None
