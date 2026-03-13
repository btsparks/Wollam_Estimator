"""Parse and import labor/equipment rates from HeavyJob export files."""

import re
import sqlite3
from pathlib import Path


def parse_pay_class_file(filepath: Path) -> list[dict]:
    """Parse PayClass.txt fixed-width file into rate records.

    Returns list of dicts with keys:
        pay_class_code, description, base_rate, ot_factor, ot2_factor,
        tm_rate, tm_ot_rate, tax_pct, fringe_non_ot, fringe_with_ot, loaded_rate
    """
    rates = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        for line in f:
            stripped = line.rstrip()
            if not stripped or stripped.startswith("_"):
                continue
            # Skip headers
            if any(kw in stripped for kw in [
                "Wollam Construction", "Job Name", "Pay Class Listing",
                "Pay Class    Description", "2nd", "OT Factor"
            ]):
                continue
            # Data lines: code starts at col 1
            code = stripped[0:13].strip()
            if not code or not code[0].isalpha():
                continue

            desc = stripped[13:34].strip()

            # Use regex to extract all decimal numbers — more reliable than fixed-width
            nums = re.findall(r"(\d+\.\d+)", stripped[34:])
            if len(nums) < 9:
                continue

            base_rate = float(nums[0])
            ot_factor = float(nums[1])
            ot2_factor = float(nums[2])
            tm_rate = float(nums[3])
            tm_ot_rate = float(nums[4])
            # nums[5] = tm_ot2_rate (skip)
            tax_pct = float(nums[6])
            fringe_non_ot = float(nums[7])
            fringe_with_ot = float(nums[8])

            # Loaded rate = base + (base × tax%) + fringe
            loaded = base_rate + (base_rate * tax_pct / 100) + fringe_non_ot

            rates.append({
                "pay_class_code": code,
                "description": desc,
                "base_rate": base_rate,
                "ot_factor": ot_factor,
                "ot2_factor": ot2_factor,
                "tm_rate": tm_rate,
                "tm_ot_rate": tm_ot_rate,
                "tax_pct": tax_pct,
                "fringe_non_ot": fringe_non_ot,
                "fringe_with_ot": fringe_with_ot,
                "loaded_rate": round(loaded, 2),
            })
    return rates


def parse_equipment_file(filepath: Path) -> list[dict]:
    """Parse EquipmentSetup.txt fixed-width file into equipment rate records.

    Returns list of dicts with keys:
        equipment_code, description, base_rate, second_rate, group_name
    """
    items = []
    seen_codes = set()
    with open(filepath, "r", encoding="utf-8-sig") as f:
        for line in f:
            stripped = line.rstrip()
            if not stripped or stripped.startswith("_"):
                continue
            if any(kw in stripped for kw in [
                "Wollam Construction", "Job Name", "Equipment Listing",
                "Code           Description", "Alt. Code"
            ]):
                continue
            code = stripped[0:15].strip()
            if not code or not code[0].isdigit():
                continue
            if code in seen_codes:
                continue
            seen_codes.add(code)

            desc = stripped[15:39].strip()

            def _float(s):
                try:
                    return float(s.strip())
                except (ValueError, IndexError):
                    return 0.0

            base_rate = _float(stripped[56:72])
            second_rate = _float(stripped[72:87])
            group_name = stripped[145:].strip() if len(stripped) > 145 else ""

            items.append({
                "equipment_code": code,
                "description": desc,
                "base_rate": base_rate,
                "second_rate": second_rate,
                "group_name": group_name,
            })
    return items


def import_labor_rates(conn: sqlite3.Connection, rates: list[dict]) -> int:
    """Insert/update labor rates into the database. Returns count imported."""
    count = 0
    for r in rates:
        conn.execute("""
            INSERT INTO labor_rate (
                pay_class_code, description, base_rate, ot_factor, ot2_factor,
                tm_rate, tm_ot_rate, tax_pct, fringe_non_ot, fringe_with_ot,
                loaded_rate, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'imported')
            ON CONFLICT(pay_class_code) DO UPDATE SET
                description = excluded.description,
                base_rate = excluded.base_rate,
                ot_factor = excluded.ot_factor,
                ot2_factor = excluded.ot2_factor,
                tm_rate = excluded.tm_rate,
                tm_ot_rate = excluded.tm_ot_rate,
                tax_pct = excluded.tax_pct,
                fringe_non_ot = excluded.fringe_non_ot,
                fringe_with_ot = excluded.fringe_with_ot,
                loaded_rate = excluded.loaded_rate,
                source = 'imported',
                updated_at = CURRENT_TIMESTAMP
        """, (
            r["pay_class_code"], r["description"], r["base_rate"],
            r["ot_factor"], r["ot2_factor"], r["tm_rate"], r["tm_ot_rate"],
            r["tax_pct"], r["fringe_non_ot"], r["fringe_with_ot"],
            r["loaded_rate"],
        ))
        count += 1
    conn.commit()
    return count


def import_equipment_rates(conn: sqlite3.Connection, items: list[dict]) -> int:
    """Insert/update equipment rates into the database. Returns count imported."""
    count = 0
    for item in items:
        conn.execute("""
            INSERT INTO equipment_rate (
                equipment_code, description, base_rate, second_rate,
                group_name, source
            ) VALUES (?, ?, ?, ?, ?, 'imported')
            ON CONFLICT(equipment_code) DO UPDATE SET
                description = excluded.description,
                base_rate = excluded.base_rate,
                second_rate = excluded.second_rate,
                group_name = excluded.group_name,
                source = 'imported',
                updated_at = CURRENT_TIMESTAMP
        """, (
            item["equipment_code"], item["description"],
            item["base_rate"], item["second_rate"], item["group_name"],
        ))
        count += 1
    conn.commit()
    return count
