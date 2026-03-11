"""Check re-sync status."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.database import get_connection

c = get_connection()

for jn in ['8400', '8401', '8402']:
    total = c.execute(
        "SELECT COUNT(*) FROM hj_timecard t JOIN job j ON t.job_id = j.job_id WHERE j.job_number = ?",
        (jn,)).fetchone()[0]
    with_code = c.execute(
        "SELECT COUNT(*) FROM hj_timecard t JOIN job j ON t.job_id = j.job_id WHERE j.job_number = ? AND t.employee_code IS NOT NULL AND t.employee_code != ''",
        (jn,)).fetchone()[0]
    equip = c.execute(
        "SELECT COUNT(*) FROM hj_equipment_entry e JOIN job j ON e.job_id = j.job_id WHERE j.job_number = ?",
        (jn,)).fetchone()[0]
    codes = c.execute(
        "SELECT DISTINCT employee_code FROM hj_timecard t JOIN job j ON t.job_id = j.job_id WHERE j.job_number = ? AND t.employee_code IS NOT NULL AND t.employee_code != ''",
        (jn,)).fetchall()
    code_list = [r[0] for r in codes]
    print(f"Job {jn}: {total} tc, {with_code} with code, {equip} equip | Trades: {code_list[:8]}")

resynced = c.execute(
    "SELECT COUNT(DISTINCT j.job_number) FROM hj_timecard t JOIN job j ON t.job_id = j.job_id "
    "WHERE t.employee_code IS NOT NULL AND t.employee_code != ''"
).fetchone()[0]
total_jobs = c.execute("SELECT COUNT(*) FROM job WHERE CAST(job_number AS INTEGER) >= 8400").fetchone()[0]

# Total stats
total_tc = c.execute("SELECT COUNT(*) FROM hj_timecard").fetchone()[0]
with_code_all = c.execute("SELECT COUNT(*) FROM hj_timecard WHERE employee_code IS NOT NULL AND employee_code != ''").fetchone()[0]
total_equip = c.execute("SELECT COUNT(*) FROM hj_equipment_entry").fetchone()[0]

print(f"\nOverall: {resynced}/{total_jobs} jobs re-synced")
print(f"Timecard rows: {total_tc} | With employee_code: {with_code_all} ({with_code_all/max(total_tc,1)*100:.1f}%)")
print(f"Equipment entries: {total_equip}")

# New data
print(f"\nNew bulk data:")
print(f"  Pay items: {c.execute('SELECT COUNT(*) FROM hj_pay_item').fetchone()[0]}")
print(f"  Forecasts: {c.execute('SELECT COUNT(*) FROM hj_forecast').fetchone()[0]}")
print(f"  Employees: {c.execute('SELECT COUNT(*) FROM hj_employee').fetchone()[0]}")
print(f"  E360 entries: {c.execute('SELECT COUNT(*) FROM e360_timecard').fetchone()[0]}")

c.close()
