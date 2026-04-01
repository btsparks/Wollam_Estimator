"""Cost report importer — parse HeavyJob Cost Analysis exports and backfill actual costs.

Parses fixed-width CostAnalysis text files exported from HeavyJob.
Updates hj_costcode table with actual labor, equipment, and material/sub costs
that the HCSS API doesn't provide.

Also populates rpt_* ground truth columns (schema v2.4) which are used for
data quality assessment. The HCSS timecard API returns incomplete data for
large/old jobs — cost report values are the authoritative source.
"""

import re
import logging
from datetime import datetime
from pathlib import Path

from app.config import COST_REPORT_DIR
from app.database import get_connection

logger = logging.getLogger(__name__)

# Regex to match cost code data lines.
# Groups: 1=code, 2=description, 3=bgt_qty, 4=placed_qty, 5=unit, 6=pct_complete,
#         7=exp_labor, 8=act_labor, 9=exp_equip, 10=act_equip,
#         11=exp_matl, 12=act_matl, 13=bgt_total, 14=exp_total,
#         15=act_total, 16=difference
COST_LINE_RE = re.compile(
    r'^\s*(\d{4})\s+'           # 1: cost code (4 digits)
    r'(.+?)\s{2,}'              # 2: description (text, ends at 2+ spaces)
    r'([\d,]+)\s+'              # 3: budgeted qty
    r'([\d,]+)\s+'              # 4: placed qty
    r'(\w+)\s+'                 # 5: unit
    r'(\d+)\s+'                 # 6: % complete
    r'([\d,]+)\s+'              # 7: expected labor $
    r'([\d,]+)\s+'              # 8: actual labor $
    r'([\d,]+)\s+'              # 9: expected equipment $
    r'([\d,]+)\s+'              # 10: actual equipment $
    r'([\d,]+)\s+'              # 11: expected material/sub $
    r'([\d,]+)\s+'              # 12: actual material/sub $
    r'([\d,]+)\s+'              # 13: budgeted total $
    r'([\d,]+)\s+'              # 14: expected total $
    r'([\d,]+)\s+'              # 15: actual total $
    r'(-?[\d,]+)'               # 16: difference $
)

# Extract job number from filename like "CostAnalysis - 8582.txt"
FILENAME_RE = re.compile(r'CostAnalysis\s*-\s*(\d+)\.txt')


def _parse_number(s: str) -> float:
    """Convert a comma-formatted number string to float."""
    return float(s.replace(',', ''))


def parse_cost_report(filepath: str) -> list[dict]:
    """Parse a HeavyJob Cost Analysis file.

    Args:
        filepath: Path to the CostAnalysis .txt file.

    Returns:
        List of dicts with keys: code, description, placed_qty, unit,
        pct_complete, act_labor_cost, act_equip_cost, act_other_cost, act_total
    """
    results = []
    seen_codes = set()  # Track codes to skip duplicates from repeated page headers

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            m = COST_LINE_RE.match(line)
            if not m:
                continue

            code = m.group(1)

            # Skip duplicate lines (same cost code appears on every page after headers)
            if code in seen_codes:
                continue
            seen_codes.add(code)

            results.append({
                'code': code,
                'description': m.group(2).strip(),
                'placed_qty': _parse_number(m.group(4)),
                'unit': m.group(5),
                'pct_complete': _parse_number(m.group(6)),
                'act_labor_cost': _parse_number(m.group(8)),
                'act_equip_cost': _parse_number(m.group(10)),
                'act_other_cost': _parse_number(m.group(12)),
                'act_total': _parse_number(m.group(15)),
            })

    return results


def import_cost_report(filepath: str) -> dict:
    """Parse a cost analysis file and update hj_costcode table.

    For each cost code in the report, updates the matching row (by job_id + code)
    with actual labor, equipment, material, and total costs.

    Args:
        filepath: Path to the CostAnalysis .txt file.

    Returns:
        Dict with stats: job_number, job_id, codes_parsed, codes_updated,
        codes_not_found, total_cost_imported.
    """
    path = Path(filepath)
    filename_match = FILENAME_RE.match(path.name)
    if not filename_match:
        return {
            'error': f'Cannot extract job number from filename: {path.name}',
            'codes_updated': 0,
        }

    job_number = filename_match.group(1)
    records = parse_cost_report(filepath)

    conn = get_connection()
    try:
        # Look up job_id from job table
        job_row = conn.execute(
            "SELECT job_id FROM job WHERE job_number = ?",
            (job_number,)
        ).fetchone()

        if not job_row:
            return {
                'error': f'Job {job_number} not found in database',
                'job_number': job_number,
                'codes_parsed': len(records),
                'codes_updated': 0,
            }

        job_id = job_row['job_id']
        codes_updated = 0
        codes_not_found = []
        total_cost = 0.0

        for rec in records:
            # Check if this cost code exists for this job
            existing = conn.execute(
                "SELECT cc_id, act_qty FROM hj_costcode WHERE job_id = ? AND code = ?",
                (job_id, rec['code'])
            ).fetchone()

            if not existing:
                codes_not_found.append(rec['code'])
                continue

            now = datetime.now().isoformat()

            # Build the update — always overwrite cost columns + rpt_* ground truth
            update_fields = {
                'act_labor_cost': rec['act_labor_cost'],
                'act_equip_cost': rec['act_equip_cost'],
                'act_matl_cost': rec['act_other_cost'],
                'act_total': rec['act_total'],
                'pct_complete': rec['pct_complete'],
                'rpt_placed_qty': rec['placed_qty'],
                'rpt_labor_cost': rec['act_labor_cost'],
                'rpt_equip_cost': rec['act_equip_cost'],
                'rpt_pct_complete': rec['pct_complete'],
                'rpt_imported_at': now,
            }

            # Update act_qty from placed_qty if existing is NULL or 0
            existing_qty = existing['act_qty']
            if (existing_qty is None or existing_qty == 0) and rec['placed_qty'] > 0:
                update_fields['act_qty'] = rec['placed_qty']

            set_clause = ', '.join(f'{k} = ?' for k in update_fields)
            values = list(update_fields.values())
            values.append(job_id)
            values.append(rec['code'])

            conn.execute(
                f"UPDATE hj_costcode SET {set_clause} WHERE job_id = ? AND code = ?",
                values
            )

            codes_updated += 1
            total_cost += rec['act_total']

        conn.commit()

        return {
            'job_number': job_number,
            'job_id': job_id,
            'codes_parsed': len(records),
            'codes_updated': codes_updated,
            'codes_not_found': codes_not_found,
            'codes_not_found_count': len(codes_not_found),
            'total_cost_imported': round(total_cost, 2),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def import_all_cost_reports() -> dict:
    """Scan the cost report directory and import all CostAnalysis files.

    Returns:
        Dict with overall summary: files_found, files_imported, total_codes_updated,
        total_cost_imported, per_file results.
    """
    if not COST_REPORT_DIR.exists():
        return {
            'error': f'Cost report directory not found: {COST_REPORT_DIR}',
            'files_found': 0,
        }

    files = sorted(COST_REPORT_DIR.glob('CostAnalysis - *.txt'))

    if not files:
        return {
            'error': 'No CostAnalysis files found',
            'directory': str(COST_REPORT_DIR),
            'files_found': 0,
        }

    results = []
    total_updated = 0
    total_cost = 0.0
    errors = 0

    for filepath in files:
        logger.info(f"Importing cost report: {filepath.name}")
        result = import_cost_report(str(filepath))
        results.append(result)

        if 'error' in result:
            errors += 1
            logger.warning(f"  Error: {result['error']}")
        else:
            total_updated += result['codes_updated']
            total_cost += result['total_cost_imported']
            logger.info(
                f"  Job {result['job_number']}: "
                f"{result['codes_updated']} codes updated, "
                f"${result['total_cost_imported']:,.0f} total cost"
            )

    return {
        'files_found': len(files),
        'files_imported': len(files) - errors,
        'files_with_errors': errors,
        'total_codes_updated': total_updated,
        'total_cost_imported': round(total_cost, 2),
        'per_file': results,
    }


def get_data_quality(job_id: int) -> dict:
    """Return data quality assessment for a job.

    Checks whether cost report ground truth exists and how timecard
    coverage compares. Used by AI Chat to flag unreliable data.

    Returns:
        dict with keys: has_cost_report, quality, note, timecard_hours,
        estimated_total_hours, coverage_pct
    """
    conn = get_connection()
    try:
        rpt = conn.execute(
            """SELECT COUNT(*) as rpt_count,
                      COALESCE(SUM(rpt_labor_cost), 0) as total_rpt_labor
               FROM hj_costcode
               WHERE job_id = ? AND rpt_labor_cost IS NOT NULL AND rpt_labor_cost > 0""",
            (job_id,),
        ).fetchone()

        has_report = rpt["rpt_count"] > 0
        total_rpt_labor = rpt["total_rpt_labor"]

        tc = conn.execute(
            "SELECT COALESCE(SUM(hours), 0) as h FROM hj_timecard WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        tc_hrs = tc["h"]

        # Rough estimate: $46/hr blended average for Wollam crews
        est_hrs = total_rpt_labor / 46 if total_rpt_labor else 0
        coverage = (tc_hrs / est_hrs * 100) if est_hrs > 0 else None

        if not has_report:
            quality = "unknown"
            note = "No cost report available to verify timecard completeness"
        elif coverage is not None and coverage >= 85:
            quality = "good"
            note = f"Timecard data covers ~{coverage:.0f}% of cost report labor"
        elif coverage is not None and coverage >= 60:
            quality = "partial"
            note = (
                f"Timecard data covers only ~{coverage:.0f}% of cost report labor "
                "- some rates may be based on incomplete data"
            )
        else:
            quality = "incomplete"
            note = (
                f"Timecard data covers only ~{coverage:.0f}% of cost report labor "
                "- rates are unreliable for this job"
            )

        return {
            "has_cost_report": has_report,
            "quality": quality,
            "note": note,
            "timecard_hours": round(tc_hrs, 1),
            "estimated_total_hours": round(est_hrs, 0) if est_hrs else None,
            "coverage_pct": round(coverage, 1) if coverage is not None else None,
        }
    finally:
        conn.close()
