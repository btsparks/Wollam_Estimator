"""
WEIS JCD Ingestion Script
Parses JCD markdown files for Job 8553 and populates the SQLite database.

Strategy: Semi-structured extraction. Uses a generic markdown table parser
combined with discipline-specific extraction logic. Each discipline JCD has
its own handler that knows what tables/sections to extract.
"""

import sys
import re
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import get_connection, init_db, DB_PATH


# ---------------------------------------------------------------------------
# Generic Markdown Helpers
# ---------------------------------------------------------------------------

def parse_md_tables(text: str) -> list[list[dict]]:
    """Extract all pipe-delimited markdown tables from text.
    Returns a list of tables, each table is a list of row dicts keyed by header."""
    tables = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Detect table header row (has pipes and next line is separator)
        if "|" in line and i + 1 < len(lines) and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip()):
            headers = [h.strip().strip("*") for h in line.split("|")[1:-1]]
            i += 2  # skip header + separator
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|") and not re.match(r"^\|[\s\-:|]+\|$", lines[i].strip()):
                cells = [c.strip().strip("*") for c in lines[i].split("|")[1:-1]]
                if len(cells) == len(headers):
                    rows.append(dict(zip(headers, cells)))
                i += 1
            if rows:
                tables.append(rows)
        else:
            i += 1
    return tables


def clean_number(val: str) -> float | None:
    """Parse a number from a markdown cell. Handles $, commas, %, +/-, ~, parens."""
    if not val or val.strip() in ("—", "–", "N/A", "n/a", "", "—", "Varies", "Lump Sum", "Owner-furnished"):
        return None
    val = val.strip()
    # Remove markdown bold
    val = val.replace("**", "")
    # Remove emoji/symbols
    val = re.sub(r"[✓⚠️✅⭐]", "", val).strip()
    # Handle percentage ranges like "11-15%"
    if "%" in val and "-" in val:
        # Take the first number for ranges
        val = val.split("-")[0].strip()
    # Remove units at end (MH/SF, $/CY, etc.)
    val = re.sub(r"\s*(MH/\w+|MH|%|/\w+)\s*$", "", val).strip()
    # Remove leading symbols
    val = val.lstrip("~$+")
    # Remove commas
    val = val.replace(",", "")
    # Handle parenthetical negatives
    if val.startswith("(") and val.endswith(")"):
        val = "-" + val[1:-1]
    # Handle trailing %
    val = val.rstrip("%").strip()
    # Remove any remaining non-numeric except . and -
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def get_section(text: str, header_pattern: str, next_header_level: int = 2) -> str:
    """Extract text from a markdown section by header pattern."""
    pattern = rf"^{'#' * next_header_level}\s+{header_pattern}.*$"
    match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
    if not match:
        return ""
    start = match.end()
    # Find next header at same or higher level
    end_pattern = rf"^{'#' * next_header_level}\s+"
    end_match = re.search(end_pattern, text[start:], re.MULTILINE)
    if end_match:
        return text[start:start + end_match.start()]
    return text[start:]


# ---------------------------------------------------------------------------
# Project-Level Ingestion (from Master Summary)
# ---------------------------------------------------------------------------

def ingest_project(conn) -> int:
    """Insert the project record for Job 8553. Returns project_id."""
    conn.execute("""
        INSERT OR REPLACE INTO projects (
            job_number, job_name, owner, project_type, contract_type,
            location, start_date, end_date, duration_months,
            contract_value, total_actual_cost, total_budget_cost,
            total_actual_mh, total_budget_mh, building_sf,
            cpi, projected_margin, notes,
            cataloged_date, cataloged_by, data_quality
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "8553",
        "RTK SPD Pump Station",
        "Rio Tinto Kennecott",
        "pump_station",
        "sub_kiewit",
        "Bingham Canyon Mine, Utah",
        "2023-10-01",
        "2025-11-30",
        24.0,
        None,  # contract_value (bid price ~$59.4M but this is estimated)
        35571414.0,
        48694091.0,
        108889.0,
        147691.0,
        43560.0,
        1.37,
        40.1,
        "SPD (Solids Processing & Distribution) Pump Station. CPI of 1.37 indicates "
        "conservative estimating. 2:1 slope VE saved ~$2.4M in earthwork.",
        date.today().isoformat(),
        "Claude/Travis",
        "complete",
    ))
    conn.commit()
    row = conn.execute("SELECT id FROM projects WHERE job_number = '8553'").fetchone()
    return row["id"]


# ---------------------------------------------------------------------------
# Discipline Ingestion
# ---------------------------------------------------------------------------

DISCIPLINES = [
    ("EARTHWORK", "Earthwork", 4810455, 2364751, 20548, 9720),
    ("CONCRETE", "Concrete", 11634675, 9033158, 45932, 36923),
    ("STEEL", "Structural Steel", 7799628, 6058859, 8881, 9442),
    ("PIPING", "Piping", 6286424, 5226461, 17340, 8344),
    ("MECHANICAL", "Mechanical Equipment", 1434420, 1142430, 6321, 4796),
    ("ELECTRICAL", "Electrical", 6426441, 6194890, 2597, 2081),
    ("BUILDING", "Building Erection", 2695038, 2045313, None, None),
    ("GCONDITIONS", "General Conditions", 8355492, 3909710, 40520, 26990),
]


def ingest_disciplines(conn, project_id: int) -> dict:
    """Insert discipline records. Returns dict of discipline_code -> id."""
    disc_ids = {}
    for code, name, bud_cost, act_cost, bud_mh, act_mh in DISCIPLINES:
        var_cost = act_cost - bud_cost if act_cost and bud_cost else None
        var_pct = (var_cost / bud_cost * 100) if var_cost and bud_cost else None
        var_mh = (act_mh - bud_mh) if act_mh is not None and bud_mh is not None else None

        conn.execute("""
            INSERT INTO disciplines (
                project_id, discipline_code, discipline_name,
                budget_cost, actual_cost, variance_cost, variance_pct,
                budget_mh, actual_mh, variance_mh
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, code, name, bud_cost, act_cost, var_cost, var_pct,
              bud_mh, act_mh, var_mh))

    conn.commit()
    rows = conn.execute(
        "SELECT id, discipline_code FROM disciplines WHERE project_id = ?",
        (project_id,)
    ).fetchall()
    for r in rows:
        disc_ids[r["discipline_code"]] = r["id"]
    return disc_ids


# ---------------------------------------------------------------------------
# Cost Code Ingestion
# ---------------------------------------------------------------------------

def ingest_cost_codes(conn, project_id: int, disc_ids: dict):
    """Insert cost code records from all JCD discipline sections."""

    # Concrete cost codes (23xx self-perform labor)
    concrete_codes = [
        ("2300", "C_Site Equipment", "DAY", 185, None, 0, 0, 0, 0, 393116, 444504),
        ("2301", "C_Escort Conc Truck", "CY", 12582, None, 532, 1135, None, None, 33119, 73154),
        ("2302", "C_Cold Weather", "DAY", 66, None, 2178, 1508, None, None, 169835, 124560),
        ("2304", "C_Rebar Support", "LB", 2715200, None, 1942, 2632, None, None, 126254, 113352),
        ("2306", "C_Install Formsavers", "EA", 185, None, 185, 306, None, None, 11118, 11994),
        ("2308", "C_Install Grout", "BAG", 13, None, 33, 125, None, None, 1733, 5542),
        ("2310", "C_Install Bollards", "EA", 10, None, 80, 75, None, None, 8668, 3476),
        ("2314", "CMS_F/S Mat Slab", "SF", 12187, None, 4419, 2592, None, None, 259562, 99120),
        ("2316", "CMS_Pour Mat Slab", "CY", 6936, None, 2867, 941, None, None, 165624, 107686),
        ("2324", "CMS_Set Waterstop", "LF", 1383, None, 138, 328, None, None, 9043, 11627),
        ("2330", "CO_F/S Octagon", "SF", 20074, None, 7316, 7547, None, None, 423105, 296859),
        ("2332", "CO_Pour Octagon", "CY", 2304, None, 2388, 673, None, None, 141305, 25584),
        ("2334", "CO_Pipe Embeds", "EA", 6, None, 150, 263, None, None, 9128, 10486),
        ("2340", "CW_F/S Walls", "SF", 45853, None, 12827, 10110, None, None, 741824, 399668),
        ("2342", "CW_Pour Walls", "CY", 1656, None, 1312, 1321, None, None, 77641, 55789),
        ("2343", "CW_Wall & Stair Embeds", "EA", 10, None, 0, 53, None, None, 0, 1982),
        ("2344", "CW_Set Anchor Bolts", "EA", 108, None, 324, 199, None, None, 17276, 8033),
        ("2350", "CLD_F/S Dock", "SF", 342, None, 911, 344, None, None, 52676, 13231),
        ("2352", "CLD_Pour Dock", "CY", 169, None, 135, 40, None, None, 7999, 8772),
        ("2354", "CLD_Install Sealer", "LF", 1200, None, 36, 0, None, None, 1920, 0),
        ("2360", "CPS_EX/BF Supports", "CY", 276, None, 158, 279, None, None, 13581, 23836),
        ("2362", "CPS_F/S Supports", "SF", 8689, None, 2835, 1665, None, None, 163967, 65858),
        ("2364", "CPS_Pour Supports", "CY", 357, None, 808, 293, None, None, 47775, 13743),
        ("2366", "CPS_Set Anchor Bolts", "EA", 648, None, 662, 307, None, None, 35298, 12046),
        ("2368", "CPS_Set Embeds", "EA", 5, None, 25, 42, None, None, 1333, 1750),
        ("2370", "CEQ_EX/BF Pads", "CY", 204, None, 181, 119, None, None, 15592, 10827),
        ("2372", "CEQ_F/S Pads", "SF", 4503, None, 1304, 1870, None, None, 77085, 75699),
        ("2374", "CEQ_Pour Pads", "CY", 827, None, 664, 463, None, None, 39286, 26164),
        ("2376", "CEQ_Set Anchor Bolts", "EA", 144, None, 216, 458, None, None, 45517, 19603),
        ("2380", "F_Offload Foam", "EA", 689, None, 227, 157, None, None, 15411, 8448),
        ("2382", "F_Install Foam", "EA", 689, None, 1080, 991, None, None, 101528, 47698),
    ]

    disc_id = disc_ids["CONCRETE"]
    for code, desc, unit, bid_qty, act_qty, bud_mh, act_mh, bud_uc, act_uc, bud_cost, act_cost in concrete_codes:
        bud_mh_per = (bud_mh / bid_qty) if bud_mh and bid_qty else None
        act_mh_per = (act_mh / (act_qty or bid_qty)) if act_mh and (act_qty or bid_qty) else None
        over_flag = act_cost > bud_cost * 1.2 if act_cost and bud_cost and bud_cost > 0 else False
        conn.execute("""
            INSERT INTO cost_codes (
                project_id, discipline_id, cost_code, description, unit,
                budget_qty, actual_qty, budget_cost, actual_cost,
                budget_mh, actual_mh, budget_mh_per_unit, actual_mh_per_unit,
                over_budget_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, disc_id, code, desc, unit,
              bid_qty, act_qty, bud_cost, act_cost,
              bud_mh, act_mh, bud_mh_per, act_mh_per, over_flag))

    # Earthwork cost codes
    earthwork_codes = [
        ("2110", "EX_L/H Excavation", "CY", 170272, None, 1737, 1054, 310774, 153447),
        ("2112", "EX_Knockdn Stockpile", "CY", 147611, None, 251, 121, 54586, 10511),
        ("2114", "EX_Knockdn Overflow", "CY", 22661, None, 116, 99, 19825, 9957),
        ("2116", "EX_Road Maint Excavation", "CY", 220000, None, 290, 166, 88152, 19936),
        ("2118", "EX_L/H Offhaul", "CY", 68519, None, 2284, 555, 401332, 68703),
        ("2120", "EX_Knockdn Offhaul", "CY", 68519, None, 319, 106, 69308, 12006),
        ("2122", "EX_Road Maint Offhaul", "CY", 68519, None, 319, 68, 89252, 9303),
        ("2150", "EX_P/C Fine Filter", "TON", 1354, None, 116, 67, 12367, 5606),
        ("2152", "EX_P/C Drain Rock", "TON", 5413, None, 387, 365, 45681, 33498),
        ("2154", "EX_P/C Structural Fill", "TON", 77591, None, 3637, 2011, 340186, 195686),
        ("2156", "EX_L/H WT Backfill", "CY", 147611, None, 2400, 620, 412089, 99835),
        ("2158", "EX_P/C WT Backfill", "CY", 147611, None, 1000, 368, 168709, 37753),
        ("2160", "EX_Road Maint WT BF", "CY", 147611, None, 194, 71, 59041, 12495),
        ("2161", "OF_Cut to Fill Dozer", "CY", 24401, None, 678, 314, 103685, 39598),
        ("2162", "OF_Finish OF Ponds", "SF", 716733, None, 191, 67, 32271, 6274),
        ("2180", "SW_Cut to Fill Dozer", "CY", 21205, None, 589, 556, 90108, 73113),
        ("2182", "SW_Finish Grade", "SF", 1102368, None, 221, 89, 37231, 8145),
        ("2184", "SW_Fine Grade Subgrade", "SF", 518130, None, 345, 191, 47507, 21438),
        ("2188", "SW_P/C Roadbase", "TON", 18231, None, 486, 349, 67105, 41756),
    ]

    disc_id = disc_ids["EARTHWORK"]
    for code, desc, unit, bid_qty, act_qty, bud_mh, act_mh, bud_cost, act_cost in earthwork_codes:
        bud_mh_per = (bud_mh / bid_qty) if bud_mh and bid_qty else None
        act_mh_per = (act_mh / (act_qty or bid_qty)) if act_mh and (act_qty or bid_qty) else None
        over_flag = act_cost > bud_cost * 1.2 if act_cost and bud_cost and bud_cost > 0 else False
        conn.execute("""
            INSERT INTO cost_codes (
                project_id, discipline_id, cost_code, description, unit,
                budget_qty, actual_qty, budget_cost, actual_cost,
                budget_mh, actual_mh, budget_mh_per_unit, actual_mh_per_unit,
                over_budget_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, disc_id, code, desc, unit,
              bid_qty, act_qty, bud_cost, act_cost,
              bud_mh, act_mh, bud_mh_per, act_mh_per, over_flag))

    # Structural Steel cost codes
    steel_codes = [
        ("2414", "SS_Bridge Crane", "EA", 1, None, 270, 0, 15742, 0),
        ("2430", "S_Install Grout", "BAG", 341, None, 902.5, 1124.5, 48122, 48869),
        ("2432", "S_Touch-up Paint", "TON", 561, None, 570, 779.5, 43897, 30877),
        ("2440", "S_Stair Towers", "EA", 4, None, 810, 1630, 47224, 72451),
        ("2442", "S_Structural Steel", "TON", 57, None, 1425, 1259, 87517, 63426),
        ("2444", "S_Install Treads", "EA", 129, None, 387, 105.5, 23114, 5237),
        ("2446", "S_Install Grating", "SF", 7792, None, 1168.8, 1481.5, 69806, 71581),
        ("2448", "S_Install Handrail", "LF", 1980, None, 1434, 1079, 90016, 52068),
        ("2450", "S_Anchor Bolts", "EA", 96, None, 144, 5, 8076, 210),
        ("2452", "S_Ground Supports", "EA", 66, None, 214.5, 219, 12810, 9161),
        ("2454", "S_LG Ground Supports", "EA", 19, None, 95, 121.5, 5674, 4909),
        ("2456", "S_Wall Supports", "EA", 49, None, 284, 683, 16962, 29453),
        ("2460", "IS_Inlet Steel", "TON", 15.15, None, 530, 394, 30915, 21595),
        ("2462", "IS_Platform Steel", "TON", 13, None, 152, 230, 9170, 10037),
        ("2850", "E_Elec Support", "LS", 1, None, 197.5, 162.5, 13818, 11853),
    ]

    disc_id = disc_ids["STEEL"]
    for code, desc, unit, bid_qty, act_qty, bud_mh, act_mh, bud_cost, act_cost in steel_codes:
        bud_mh_per = (bud_mh / bid_qty) if bud_mh and bid_qty else None
        act_mh_per = (act_mh / (act_qty or bid_qty)) if act_mh and (act_qty or bid_qty) else None
        over_flag = act_cost > bud_cost * 1.2 if act_cost and bud_cost and bud_cost > 0 else False
        conn.execute("""
            INSERT INTO cost_codes (
                project_id, discipline_id, cost_code, description, unit,
                budget_qty, actual_qty, budget_cost, actual_cost,
                budget_mh, actual_mh, budget_mh_per_unit, actual_mh_per_unit,
                over_budget_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, disc_id, code, desc, unit,
              bid_qty, act_qty, bud_cost, act_cost,
              bud_mh, act_mh, bud_mh_per, act_mh_per, over_flag))

    # Piping cost codes (H/E pipe + bolt-ups + field welds + valves)
    piping_codes = [
        ("2710", "01_H/E Pipe", "LF", 1131, None, 2396, 1224, None, None),
        ("2712", "01_3-8in Bolt-up", "EA", 86, None, 258, 248, None, None),
        ("2714", "01_12-16in Bolt-up", "EA", 30, None, 150, 83, None, None),
        ("2716", "01_24-30in Bolt-up", "EA", 15, None, 120, 115, None, None),
        ("2718", "01_Field Welds", "EA", 25, None, 500, 416, None, None),
        ("2720", "20_H/E Pipe", "LF", 1179, None, 2358, 1239, None, None),
        ("2722", "20_2in Bolt-up", "EA", 24, None, 72, 19, None, None),
        ("2724", "20_6in Bolt-up", "EA", 19, None, 76, 56, None, None),
        ("2726", "20_Field Welds", "EA", 25, None, 250, 78, None, None),
        ("2730", "26_H/E Pipe", "LF", 1194, None, 3164, 1958, None, None),
        ("2732", "26_1.5-2in Bolt-up", "EA", 6, None, 18, 0, None, None),
        ("2734", "26_4-6in Bolt-up", "EA", 43, None, 172, 0, None, None),
        ("2736", "26_8-16in Bolt-up", "EA", 15, None, 82, 20, None, None),
        ("2738", "26_20-28in Bolt-up", "EA", 139, None, 1112, 330, None, None),
        ("2740", "50_H/E Pipe", "LF", 1171, None, 1756, 918, None, None),
        ("2742", "50_1-2.5in Bolt-up", "EA", 203, None, 304, 110, None, None),
        ("2744", "50_4-6in Bolt-up", "EA", 128, None, 256, 44, None, None),
        ("2746", "50_10-12in Bolt-up", "EA", 15, None, 60, 0, None, None),
        ("2748", "50_Field Welds", "EA", 30, None, 150, 208, None, None),
        ("2750", "TH_1.5in H/E Pipe", "LF", 500, None, 160, 114, None, None),
        ("2752", "TH_1.5in Fittings", "EA", 183, None, 92, 47, None, None),
        ("2780", "SP_H/E Pipe", "LF", 140, None, 350, 120, None, None),
        ("2782", "SP_1-8in Bolt-up", "EA", 22, None, 220, 4, None, None),
        ("2784", "SP_20-28in Bolt-up", "EA", 24, None, 600, 155, None, None),
        ("2790", "V_1-6in Valves", "EA", 166, None, 515, 321, None, None),
        ("2792", "V_8-16in Valves", "EA", 40, None, 394, 166, None, None),
        ("2794", "V_20-28in Valves", "EA", 68, None, 1754, 349, None, None),
    ]

    disc_id = disc_ids["PIPING"]
    for code, desc, unit, bid_qty, act_qty, bud_mh, act_mh, bud_cost, act_cost in piping_codes:
        bud_mh_per = (bud_mh / bid_qty) if bud_mh and bid_qty else None
        act_mh_per = (act_mh / (act_qty or bid_qty)) if act_mh and (act_qty or bid_qty) else None
        over_flag = False
        if act_cost and bud_cost and bud_cost > 0:
            over_flag = act_cost > bud_cost * 1.2
        conn.execute("""
            INSERT INTO cost_codes (
                project_id, discipline_id, cost_code, description, unit,
                budget_qty, actual_qty, budget_cost, actual_cost,
                budget_mh, actual_mh, budget_mh_per_unit, actual_mh_per_unit,
                over_budget_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, disc_id, code, desc, unit,
              bid_qty, act_qty, bud_cost, act_cost,
              bud_mh, act_mh, bud_mh_per, act_mh_per, over_flag))

    # Mechanical Equipment cost codes
    mech_codes = [
        ("2610", "M_Set SPD Pumps", "EA", 6, None, 900, 834, None, None),
        ("2612", "M_Grout SPD Pumps", "CY", 25, None, 360, 488, None, None),
        ("2614", "M_Set Sump Pumps", "EA", 4, None, 240, 105, None, None),
        ("2616", "M_Set Washdown Pumps", "EA", 4, None, 180, 149, None, None),
        ("2618", "M_Install Filters", "EA", 2, None, 20, 10, None, None),
        ("2620", "M_Install SW Tank", "EA", 1, None, 80, 15, None, None),
        ("2630", "M_Set Large AHU", "EA", 2, None, 200, 17, None, None),
        ("2632", "M_Set PDC", "LS", 1, None, 265, 193.5, None, None),
        ("2634", "M_Set HVAC", "EA", 2, None, 70, 65.5, None, None),
        ("2640", "M_Install Air Comp", "EA", 5, None, 150, 15, None, None),
        ("2642", "M_Install HPUs", "EA", 3, None, 180, 79, None, None),
        ("2644", "M_Install HPU Shed", "EA", 3, None, 120, 259, None, None),
    ]

    disc_id = disc_ids["MECHANICAL"]
    for code, desc, unit, bid_qty, act_qty, bud_mh, act_mh, bud_cost, act_cost in mech_codes:
        bud_mh_per = (bud_mh / bid_qty) if bud_mh and bid_qty else None
        act_mh_per = (act_mh / (act_qty or bid_qty)) if act_mh and (act_qty or bid_qty) else None
        over_flag = False
        conn.execute("""
            INSERT INTO cost_codes (
                project_id, discipline_id, cost_code, description, unit,
                budget_qty, actual_qty, budget_cost, actual_cost,
                budget_mh, actual_mh, budget_mh_per_unit, actual_mh_per_unit,
                over_budget_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, disc_id, code, desc, unit,
              bid_qty, act_qty, bud_cost, act_cost,
              bud_mh, act_mh, bud_mh_per, act_mh_per, over_flag))

    # Electrical cost codes
    elec_codes = [
        ("2852", "E_EX/BF Ductbank", "LF", 926, None, 111.1, 81.5, 9576, 7999),
        ("2854", "E_Pour Duct Bank", "CY", 92, None, 90.8, 28.5, 5274, 1103),
        ("2856", "E_EX/BF Pads", "CY", 35, None, 100.5, 63.5, 7336, 4830),
        ("2858", "E_F/S Pads", "SF", 120, None, 30, 30, 1742, 1308),
        ("2860", "E_Pour Pads", "CY", 21, None, 75, 4, 4421, 229),
        ("2862", "E_EX/BF Ground Grid", "LF", 6600, None, 302, 137, 26303, 11494),
    ]

    disc_id = disc_ids["ELECTRICAL"]
    for code, desc, unit, bid_qty, act_qty, bud_mh, act_mh, bud_cost, act_cost in elec_codes:
        bud_mh_per = (bud_mh / bid_qty) if bud_mh and bid_qty else None
        act_mh_per = (act_mh / (act_qty or bid_qty)) if act_mh and (act_qty or bid_qty) else None
        over_flag = act_cost > bud_cost * 1.2 if act_cost and bud_cost and bud_cost > 0 else False
        conn.execute("""
            INSERT INTO cost_codes (
                project_id, discipline_id, cost_code, description, unit,
                budget_qty, actual_qty, budget_cost, actual_cost,
                budget_mh, actual_mh, budget_mh_per_unit, actual_mh_per_unit,
                over_budget_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, disc_id, code, desc, unit,
              bid_qty, act_qty, bud_cost, act_cost,
              bud_mh, act_mh, bud_mh_per, act_mh_per, over_flag))

    # General Conditions cost codes
    gc_codes = [
        ("1000", "Management", "DAY", 528, None, 26800, 17050, 2191521, 948044),
        ("1005", "Safety Management", "DAY", 528, None, 5280, 54, 433653, 2959),
        ("1010", "Field Supervision", "DAY", 528, None, 5280, 5780, 496852, 382648),
        ("1017", "RTKC Training", "EA", 60, None, 360, 1283, 21044, 101032),
        ("1040", "Onsite Fuel & Maint", "DAY", 150, None, 2400, 792, 184783, 61201),
    ]

    disc_id = disc_ids["GCONDITIONS"]
    for code, desc, unit, bid_qty, act_qty, bud_mh, act_mh, bud_cost, act_cost in gc_codes:
        bud_mh_per = (bud_mh / bid_qty) if bud_mh and bid_qty else None
        act_mh_per = (act_mh / (act_qty or bid_qty)) if act_mh and (act_qty or bid_qty) else None
        over_flag = act_cost > bud_cost * 1.2 if act_cost and bud_cost and bud_cost > 0 else False
        conn.execute("""
            INSERT INTO cost_codes (
                project_id, discipline_id, cost_code, description, unit,
                budget_qty, actual_qty, budget_cost, actual_cost,
                budget_mh, actual_mh, budget_mh_per_unit, actual_mh_per_unit,
                over_budget_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, disc_id, code, desc, unit,
              bid_qty, act_qty, bud_cost, act_cost,
              bud_mh, act_mh, bud_mh_per, act_mh_per, over_flag))

    conn.commit()


# ---------------------------------------------------------------------------
# Unit Costs Ingestion (Recommended Rates from JCDs)
# ---------------------------------------------------------------------------

def ingest_unit_costs(conn, project_id: int, disc_ids: dict):
    """Insert unit cost records — the recommended estimating rates."""

    records = [
        # Concrete
        ("CONCRETE", "Wall Form/Strip", "MH/SF", 0.280, 0.276, 0.28, "actual", "Gold standard - validated", None, None, None, "HIGH"),
        ("CONCRETE", "Wall Pour", "MH/CY", 0.792, 0.798, 0.80, "actual", None, None, None, None, "HIGH"),
        ("CONCRETE", "Mat Pour (3-pump continuous)", "MH/CY", 0.413, 0.136, 0.15, "actual", "3-pump continuous pour strategy", None, None, None, "HIGH"),
        ("CONCRETE", "Octagon Form/Strip", "MH/SF", 0.364, 0.376, 0.38, "actual", "Complex octagonal geometry", None, None, None, "MEDIUM"),
        ("CONCRETE", "Equipment Pad F/S", "MH/SF", 0.290, 0.415, 0.43, "actual", "+50% for heavy embeds and anchor bolts", None, None, None, "HIGH"),
        ("CONCRETE", "Embed Installation", "MH/EA", None, 0.625, 0.60, "actual", "Range: 0.50-0.75 MH/EA", None, None, None, "MEDIUM"),
        ("CONCRETE", "Concrete Material (4500 PSI)", "$/CY", 202, 205, 210, "actual", "Altaview delivered", None, None, None, "HIGH"),
        ("CONCRETE", "Formwork Materials", "$/SF", 6.53, 3.46, 3.50, "actual", "Form rental + For-Shor panels", None, None, None, "HIGH"),
        ("CONCRETE", "Rebar (F&I sub)", "$/LB", 1.35, 1.30, 1.33, "actual", "Champion/Iron Mountain", None, None, None, "HIGH"),
        ("CONCRETE", "Concrete Pumping", "$/CY", 27.93, 12.13, 17.5, "adjusted", "Fewer pours = lower rate", None, None, None, "MEDIUM"),
        ("CONCRETE", "All-In Concrete", "$/CY", 896, 867, 867, "actual", "Includes rebar, labor, material, pumping", None, None, None, "HIGH"),
        ("CONCRETE", "Site Equipment (concrete)", "$/DAY", 2125, 2403, 2400, "actual", "Cranes, lifts, heaters, generators", None, None, None, "HIGH"),

        # Earthwork
        ("EARTHWORK", "L/H Excavation (tailings, short)", "$/CY", 1.83, 1.15, 1.38, "adjusted", "Conservative for tailings", None, None, None, "HIGH"),
        ("EARTHWORK", "L/H Offhaul (long haul 3+ mi)", "$/CY", 5.86, 2.54, 3.50, "adjusted", None, None, None, None, "HIGH"),
        ("EARTHWORK", "P/C Structural Fill", "$/TON", 4.38, 3.37, 3.50, "adjusted", None, None, None, None, "HIGH"),
        ("EARTHWORK", "L/H Whole Tailings", "$/CY", 2.79, 1.82, 2.00, "adjusted", None, None, None, None, "HIGH"),
        ("EARTHWORK", "P/C Whole Tailings", "$/CY", 1.14, 0.69, 1.00, "adjusted", None, None, None, None, "MEDIUM"),
        ("EARTHWORK", "P/C Roadbase", "$/TON", 3.68, 2.29, 2.50, "adjusted", None, None, None, None, "HIGH"),
        ("EARTHWORK", "Structural Fill (delivered)", "$/TON", 13.52, 10.64, 13.00, "adjusted", "Rhine Construction", None, None, None, "HIGH"),
        ("EARTHWORK", "Roadbase (delivered)", "$/TON", 17.14, 12.75, 14.00, "adjusted", "Geneva Rock", None, None, None, "HIGH"),
        ("EARTHWORK", "Drain Rock (delivered)", "$/TON", 38.69, 25.40, 27.50, "adjusted", None, None, None, None, "MEDIUM"),

        # Structural Steel
        ("STEEL", "Structural Steel Erection (misc)", "MH/TON", 25.0, 22.1, 25, "budget", "Budget rate validated", None, None, None, "HIGH"),
        ("STEEL", "Stair Tower Install (at-grade)", "MH/TON", 30.0, None, 30, "budget", "At-grade, good fab", None, None, None, "MEDIUM"),
        ("STEEL", "Stair Tower Install (below-grade)", "MH/TON", 30.0, 60.4, 57.5, "actual", "Confined access, fab issues", None, None, None, "HIGH"),
        ("STEEL", "Handrail Installation", "MH/LF", 0.72, 0.55, 0.58, "adjusted", "Galvanized/epoxy on good anchors", None, None, None, "HIGH"),
        ("STEEL", "Pipe Support - Ground (small)", "MH/EA", 3.25, 3.32, 3.50, "adjusted", None, None, None, None, "HIGH"),
        ("STEEL", "Pipe Support - Ground (large)", "MH/EA", 5.00, 6.39, 6.50, "adjusted", None, None, None, None, "HIGH"),
        ("STEEL", "Pipe Support - Wall", "MH/EA", 5.80, 13.94, 13.00, "actual", "2-2.5x ground supports due to access/anchoring", None, None, None, "HIGH"),
        ("STEEL", "Grating Installation", "MH/SF", 0.15, 0.19, 0.19, "actual", None, None, None, None, "HIGH"),
        ("STEEL", "Grout (cementitious, bags)", "MH/BAG", 2.65, 3.30, 3.25, "adjusted", None, None, None, None, "HIGH"),
        ("STEEL", "Structural Steel (delivered)", "$/TON", None, 5035, 5250, "adjusted", "Competitive bidding", None, None, None, "HIGH"),

        # Piping
        ("PIPING", "H/E Pipe - CS (shop fab spool)", "MH/LF", 2.00, 0.97, 1.10, "adjusted", "100% shop fabricated spools", None, None, None, "HIGH"),
        ("PIPING", "H/E Pipe - RLCS (shop fab spool)", "MH/LF", 2.65, 1.11, 1.13, "adjusted", "Large bore, heavier handling", None, None, None, "HIGH"),
        ("PIPING", "H/E Pipe - 316SS (shop fab)", "MH/LF", 1.50, 0.70, 0.73, "adjusted", "Small bore, lighter spools", None, None, None, "HIGH"),
        ("PIPING", "Flanged Bolt-up 1-3in", "MH/EA", 1.50, 1.50, 1.50, "actual", "On target", None, None, None, "HIGH"),
        ("PIPING", "Flanged Bolt-up 4-8in", "MH/EA", 3.00, 3.00, 3.00, "actual", "Wide variance in data", None, None, None, "MEDIUM"),
        ("PIPING", "Flanged Bolt-up 10-16in", "MH/EA", 5.25, 5.25, 5.50, "adjusted", "Consistent across specs", None, None, None, "HIGH"),
        ("PIPING", "Flanged Bolt-up 20-30in", "MH/EA", 8.00, 6.50, 7.00, "adjusted", "Crane assist required", None, None, None, "HIGH"),
        ("PIPING", "Field Weld - CS <12in", "MH/EA", 10.0, 9.69, 10.00, "budget", None, None, None, None, "MEDIUM"),
        ("PIPING", "Field Weld - CS 12-24in", "MH/EA", 20.0, 16.27, 16.00, "actual", "Large diameter, multi-pass", None, None, None, "HIGH"),
        ("PIPING", "Field Weld - SS", "MH/EA", 5.0, 6.12, 6.00, "actual", "TIG welding, purge requirements", None, None, None, "HIGH"),
        ("PIPING", "Valve Install 1-6in", "MH/EA", 3.10, 1.78, 2.00, "adjusted", "Hand carry, simple mount", None, None, None, "HIGH"),
        ("PIPING", "Valve Install 8-16in", "MH/EA", 9.85, 7.55, 7.50, "actual", "Rigging required", None, None, None, "HIGH"),
        ("PIPING", "Valve Install 20-28in", "MH/EA", 25.79, 13.31, 13.00, "actual", "Crane set, alignment critical", None, None, None, "HIGH"),
        ("PIPING", "63in HDPE D/L/B", "$/LF", 52.68, 31.98, 35.00, "adjusted", "Unit cost includes equipment", None, None, None, "HIGH"),
        ("PIPING", "Hydrotesting", "MH/LF", 0.250, 0.190, 0.20, "adjusted", "Standard hold time", None, None, None, "HIGH"),
        ("PIPING", "Material Handling (pipe)", "MH/LF", 0.117, 0.087, 0.09, "adjusted", "With bridge crane access", None, None, None, "HIGH"),

        # Mechanical Equipment
        ("MECHANICAL", "SPD Pump Set (large)", "MH/EA", 150, 139, 145, "adjusted", "Set only, grout separate", None, None, None, "HIGH"),
        ("MECHANICAL", "Sump Pump Set", "MH/EA", 60, 26.3, 30, "adjusted", "Simpler installation", None, None, None, "HIGH"),
        ("MECHANICAL", "Washdown Pump Set", "MH/EA", 45, 37.3, 40, "adjusted", None, None, None, None, "MEDIUM"),
        ("MECHANICAL", "Epoxy Grout (all-in with F/S)", "MH/CY", 14.4, 50.4, 50, "actual", "CRITICAL: includes placement + F/S. F/S was missed in bid.", None, None, None, "HIGH"),
        ("MECHANICAL", "Epoxy Grout Material", "$/CY", None, 5540, 7800, "adjusted", "For-Shor. Foundation may be missing ~$54K invoice.", None, None, None, "MEDIUM"),
        ("MECHANICAL", "Epoxy Grout All-In", "$/CY", None, 7656, 10000, "adjusted", "Material + labor. Add 10-15% for winter.", None, None, None, "HIGH"),
        ("MECHANICAL", "HPU Shed Install", "MH/EA", 40, 86.3, 85, "actual", "Includes structural, equipment mounting, weatherproofing", None, None, None, "HIGH"),

        # Electrical
        ("ELECTRICAL", "Heavy Industrial Electrical", "$/SF", 118, 136.44, 138, "adjusted", "All-in including Wollam support", None, None, None, "HIGH"),
        ("ELECTRICAL", "Duct Bank EX/BF", "$/LF", 10.34, 8.64, 10.00, "adjusted", "Includes equipment", None, None, None, "HIGH"),
        ("ELECTRICAL", "Duct Bank Pour", "$/CY", 57.33, 11.99, 40.00, "adjusted", "Conservative, includes equipment", None, None, None, "MEDIUM"),
        ("ELECTRICAL", "Ground Grid EX/BF", "$/LF", 3.99, 1.74, 2.50, "adjusted", "Includes equipment", None, None, None, "HIGH"),
        ("ELECTRICAL", "Equipment Pad EX/BF", "$/CY", 209.60, 138.00, 150.00, "adjusted", "Includes equipment", None, None, None, "HIGH"),

        # General Conditions
        ("GCONDITIONS", "Management (PM+Super+Admin)", "$/DAY", 4151, 2107, 2500, "adjusted", None, None, None, None, "HIGH"),
        ("GCONDITIONS", "Field Supervision", "$/DAY", 941, 850, 900, "adjusted", None, None, None, None, "HIGH"),
        ("GCONDITIONS", "Survey (active phases)", "$/MO", None, 18000, 18000, "actual", "Digital Earth LLC", None, None, None, "HIGH"),
        ("GCONDITIONS", "QC Testing (% of job)", "%", 1.31, 0.65, 0.75, "adjusted", "Terracon", None, None, None, "HIGH"),
        ("GCONDITIONS", "GL Insurance", "%", 0.70, 0.72, 0.72, "actual", "Consistent benchmark", None, None, None, "HIGH"),
        ("GCONDITIONS", "Total GC (% of job)", "%", 17.2, 11.0, 13.0, "adjusted", None, None, None, None, "HIGH"),
    ]

    for disc_code, activity, unit, bud, act, rec, basis, notes, mh_bud, mh_act, mh_rec, conf in records:
        disc_id = disc_ids[disc_code]
        conn.execute("""
            INSERT INTO unit_costs (
                project_id, discipline_id, activity, unit,
                budget_rate, actual_rate, recommended_rate,
                rate_basis, rate_notes,
                mh_per_unit_budget, mh_per_unit_actual, mh_per_unit_rec,
                confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, disc_id, activity, unit,
              bud, act, rec, basis, notes,
              mh_bud, mh_act, mh_rec, conf))

    conn.commit()


# ---------------------------------------------------------------------------
# Production Rates Ingestion
# ---------------------------------------------------------------------------

def ingest_production_rates(conn, project_id: int, disc_ids: dict):
    """Insert production rate records."""

    rates = [
        # Earthwork
        ("EARTHWORK", "Tailings Excavation (short haul)", "CY", "CY/hr", 588, 750, 700, 8, "PC650 Komatsu", "4x 40-ton Artic Trucks", "Tailings material, short haul <1500ft", None, "HIGH"),
        ("EARTHWORK", "Structural Fill P/C", "TON", "TON/hr", 160, 200, 180, 8, "D71i GPS Dozer", "84in Smooth Drum Roller", "Good material, Rhine pit", None, "HIGH"),
        ("EARTHWORK", "Whole Tailings L/H", "CY", "CY/hr", 369, 450, 400, 4, "PC360 Excavator", "2x 40-ton Artic", "Short haul from stockpile", None, "MEDIUM"),

        # Concrete
        ("CONCRETE", "Wall Formwork (gang forms)", "SF", "SF/shift", 400, 400, 400, 14, None, None, "Gang forms, 24-29ft walls with counterforts", None, "HIGH"),
        ("CONCRETE", "Mat Pour (3-pump continuous)", "CY", "CY/shift", 400, 500, 450, 22, None, None, "3-pump setup, 18hr continuous pour", None, "HIGH"),

        # Building Erection
        ("BUILDING", "Primary Steel Erection", "TON", "MH/TON", 13.5, 7.0, 9.0, 9, "RT Crane", None, "J&M achieved 5.4-8.0 MH/TON", None, "HIGH"),
        ("BUILDING", "Secondary Steel (girts/purlins)", "TON", "MH/TON", 30.9, 20.3, 22.5, 12, None, None, "Lighter pieces, more piece-count intensive", None, "HIGH"),
        ("BUILDING", "All-In Steel Erection", "TON", "MH/TON", 17.4, 19.1, 19.0, 11, "RT Crane", None, "Includes connections/welding time", None, "HIGH"),
        ("BUILDING", "IMP/Siding Installation", "SF", "MH/SF", None, 0.065, 0.07, None, None, None, "Wall + roof panels + trim", None, "MEDIUM"),
    ]

    for disc_code, activity, unit, prod_unit, bud, act, rec, crew, equip1, equip2, conditions, notes, conf in rates:
        disc_id = disc_ids[disc_code]
        conn.execute("""
            INSERT INTO production_rates (
                project_id, discipline_id, activity, unit, production_unit,
                budget_rate, actual_rate, recommended_rate,
                crew_size, equipment_primary, equipment_secondary,
                conditions, notes, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, disc_id, activity, unit, prod_unit,
              bud, act, rec, crew, equip1, equip2, conditions, notes, conf))

    conn.commit()


# ---------------------------------------------------------------------------
# Crew Configurations
# ---------------------------------------------------------------------------

def ingest_crews(conn, project_id: int, disc_ids: dict):
    """Insert crew configuration records."""

    crews = [
        # Earthwork - Excavation
        ("EARTHWORK", "Foundation Excavation (>100K CY)",
         "1 Foreman, 1 PC650 Excavator Op, 1-2 Floor Dozer Ops, 4 Haul Truck Drivers, 1 Backup Excavator Op",
         1, 0, 0, 0, 4, 0, 0, 0, None, 8,
         "PC650 Komatsu, 4x 40-ton Artics, D65i Dozer, PC490 (backup)", 10,
         "Peak production 7000-8000 CY/day. Full-time floor dozer essential."),

        # Earthwork - Structural Fill
        ("EARTHWORK", "Structural Fill P/C",
         "1 Foreman, 1 Dozer Op, 1 Roller Op, 1 Water Truck, 1 Skidsteer Op, 2 Laborers (plate compactors), 0.5 Grader Op",
         1, 0, 0, 2, 4, 0, 0, 0, None, 8,
         "D71i GPS Dozer, 84in Smooth Drum Roller, 8000gal Water Truck, JD 331G Skidsteer, Cat 16M Grader", 10,
         "1,600 TON/shift. Special compaction within 5ft of walls."),

        # Concrete - Wall Pours
        ("CONCRETE", "Wall Forming & Pour",
         "1 Foreman, 4-6 Carpenters, 4-6 Laborers, 2 Operators, 2-4 Finishers",
         1, 5, 0, 5, 2, 0, 0, 0, None, 15,
         "RT Crane, Manlift", 10,
         "0.28 MH/SF formwork. Gang forms built on-site, 325-425 SF panels."),

        # Concrete - Mat Pours
        ("CONCRETE", "Mat Pour (large continuous)",
         "2 Foremen (day/night), 10-12 Laborers, 4-6 Finishers, 3 Operators, 2-3 Pump Ops",
         2, 0, 0, 11, 3, 0, 0, 0, "Pump Operators: 3", 22,
         "3x Concrete Pumps (65m, 56m, 47m)", 18,
         "0.15 MH/CY (3-pump continuous). 18-hour continuous pour cycles."),

        # Piping
        ("PIPING", "Flanged Pipe Installation",
         "1 Foreman, 4-6 Pipefitters, 2-4 Welders, 2 Riggers, 1-2 Operators",
         1, 0, 0, 0, 2, 0, 5, 0, "Welders: 3", 12,
         "Bridge Crane (building), RT Crane, Forklift", 10,
         "7 MH/joint for 20-28in flanged. Bridge crane on temp power was critical success factor."),

        # Building Erection
        ("BUILDING", "Primary Steel Erection (J&M crew)",
         "9-man structural crew - ironworkers + crane operators",
         1, 0, 0, 0, 1, 6, 0, 0, None, 9,
         "RT Crane", 10,
         "J&M achieved 5.4-8.0 MH/TON primary steel."),
    ]

    for (disc_code, activity, desc, foreman, jman, apprentice, laborer, operator,
         ironworker, pipefitter, electrician, other, total, equip, shift, notes) in crews:
        disc_id = disc_ids[disc_code]
        conn.execute("""
            INSERT INTO crew_configurations (
                project_id, discipline_id, activity, crew_description,
                foreman, journeyman, apprentice, laborer, operator,
                ironworker, pipefitter, electrician, other_trades,
                total_crew_size, equipment_list, shift_hours, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, disc_id, activity, desc,
              foreman, jman, apprentice, laborer, operator,
              ironworker, pipefitter, electrician, other, total,
              equip, shift, notes))

    conn.commit()


# ---------------------------------------------------------------------------
# Material Costs
# ---------------------------------------------------------------------------

def ingest_material_costs(conn, project_id: int, disc_ids: dict):
    """Insert material cost records."""

    materials = [
        # Concrete
        ("CONCRETE", None, "Ready Mix Concrete", "4500 PSI delivered", "Altaview", "CY", 10040, 205, 2058274, None, None),
        ("CONCRETE", "3302", "Concrete Materials", "Misc concrete materials", None, "LS", None, None, 183886, None, None),
        ("CONCRETE", "3304", "Embeds", "Anchor bolts, sleeves, plates", None, "LS", None, None, 153186, None, None),
        ("CONCRETE", "3360", "Geofoam", "Loading dock void fill", None, "EA", 689, 710, 489457, None, None),
        ("CONCRETE", None, "Formwork Rental", "For-Shor Alisply panel system", "For-Shor", "SF", 91648, 1.96, 179403, None, None),

        # Earthwork
        ("EARTHWORK", "3116", "Structural Fill", "Delivered to site", "Rhine Construction", "TON", 58400, 14.14, 825362, None, None),
        ("EARTHWORK", "3108", "Roadbase", "Delivered to site", "Geneva Rock", "TON", 18231, 12.75, 232442, None, None),
        ("EARTHWORK", "3112", "Drain Rock", None, None, "TON", 5413, 25.40, 137511, None, None),
        ("EARTHWORK", "3114", "Fine Filter", None, None, "TON", 1354, 26.42, 35778, None, None),

        # Structural Steel
        ("STEEL", "3400", "Steel Building Package", "PEMB package", None, "LS", None, None, 3200516, None, None),
        ("STEEL", "3410", "Structural Steel (misc)", "Misc structural", None, "TON", 472, 4690, 2213365, None, None),
        ("STEEL", "3420", "Pipe Supports", "134 supports", None, "EA", 134, 830, 111189, None, None),

        # Piping
        ("PIPING", "3222", "RLCS Pipe Spools", "Rubber Lined CS, shop fab", "All Pipe Works", "LS", None, None, 2033778, None, None),
        ("PIPING", "3220", "CS Pipe Spools", "Carbon Steel, shop fab", "All Pipe Works", "LS", None, None, 611037, None, None),
        ("PIPING", "3224", "316SS Pipe Spools", "Stainless Steel, shop fab", "All Pipe Works", "LS", None, None, 478182, None, None),
        ("PIPING", "3226", "Valves", "All sizes", "Energy West Controls", "LS", 274, None, 803754, None, None),
        ("PIPING", "3210", "Bolts & Gaskets", "Hardware", "Monroe Avex LLC", "LS", None, None, 106590, None, None),

        # Mechanical
        ("MECHANICAL", "3260", "Pumps", "Weir Slurry + Tech-Flow", None, "EA", 14, None, 497826, None, None),
        ("MECHANICAL", "3312", "Epoxy Grout", "For-Shor epoxy grout", "For-Shor Co.", "CY", 24, 5540, 132955, None, None),
    ]

    for (disc_code, cc, mat_type, mat_desc, vendor, unit, qty, uc, total, po, delivery) in materials:
        disc_id = disc_ids[disc_code]
        conn.execute("""
            INSERT INTO material_costs (
                project_id, discipline_id, cost_code, material_type,
                material_description, vendor, unit, quantity,
                unit_cost, total_cost, po_number, delivery_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, disc_id, cc, mat_type,
              mat_desc, vendor, unit, qty, uc, total, po, delivery))

    conn.commit()


# ---------------------------------------------------------------------------
# Subcontractors
# ---------------------------------------------------------------------------

def ingest_subcontractors(conn, project_id: int, disc_ids: dict):
    """Insert subcontractor records."""

    subs = [
        # Concrete subs
        ("CONCRETE", "4025", "Champion/Iron Mountain", "Rebar furnish & install",
         "rebar", 3659718, 3539407, "LB", 2715200, 1.30, None, "good", True,
         "On budget. Pre-tied wall curtains crane-set into place."),
        ("CONCRETE", "4050", "Brundage Bone", "Concrete pumping",
         "concrete_pump", 342099, 148587, "CY", 12250, 12.13, None, "good", True,
         "57% under budget. Fewer pours = fewer mobilizations."),

        # Steel subs
        ("STEEL", "4400", "J&M Steel Solutions", "Building steel fabrication & erection",
         "building_erection", 1779855, 1776490, "TON", 472, 3766, None, "good", True,
         "On budget. Primary steel 5.4-8.0 MH/TON achieved."),

        # Electrical sub
        ("ELECTRICAL", "4100", "Hunt Electric (IES)", "Complete electrical systems",
         "electrical", 4122394, 4639686, "SF", 35000, 132.56, None, "acceptable", True,
         "12.5% over budget. Review change orders at closeout."),

        # Mechanical sub
        ("MECHANICAL", "4150", "HVAC Subcontractor", "Full HVAC system",
         "other", 1747455, 1315112, None, None, None, None, "good", True, None),

        # GC subs
        ("GCONDITIONS", None, "Digital Earth LLC", "Construction survey, layout, as-builts",
         "survey", 437680, 107375, "MO", 8, 18000, None, "good", True,
         "$18K/month during active earthwork/concrete phases."),
        ("GCONDITIONS", "4250", "Terracon", "QC testing - concrete, earthwork, steel, welds",
         "testing", 638000, 231564, None, None, None, 0.65, "good", True,
         "0.65% of job cost. Full-time inspector during pours and backfill."),
        ("GCONDITIONS", None, "Rhine Construction", "Structural fill delivery",
         "other", None, 825362, "TON", 58400, 14.14, None, "good", True,
         "Cheaper than Geneva at $15.25/TON."),
        ("GCONDITIONS", None, "Geneva Rock", "Roadbase delivery",
         "other", None, 232442, "TON", 18231, 12.75, None, "good", True, None),
    ]

    for (disc_code, cc, name, scope, category, contract, actual, unit, qty, uc,
         pct, rating, reuse, notes) in subs:
        disc_id = disc_ids[disc_code]
        conn.execute("""
            INSERT INTO subcontractors (
                project_id, discipline_id, cost_code, sub_name,
                scope_description, scope_category, contract_amount, actual_amount,
                unit, quantity, unit_cost, sub_pct_of_discipline,
                performance_rating, would_use_again, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, disc_id, cc, name, scope, category,
              contract, actual, unit, qty, uc, pct, rating, reuse, notes))

    conn.commit()


# ---------------------------------------------------------------------------
# Lessons Learned
# ---------------------------------------------------------------------------

def ingest_lessons_learned(conn, project_id: int, disc_ids: dict):
    """Insert lessons learned records."""

    lessons = [
        # Project-wide
        (None, "estimating", "HIGH", "2:1 Slope VE Saved ~$2.4M",
         "Hired Sunrise Engineering for geotechnical analysis. Site had been under surcharge 2+ years. Approved 2:1 slopes vs 4:1 bid assumption.",
         "Reduced offhaul by 60%, backfill by 63%. Single largest driver of earthwork profitability.",
         "Always request geotechnical analysis early for tailings work.", "pump_station"),

        (None, "estimating", "HIGH", "CPI of 1.37 Indicates Conservative Estimating",
         "Budget $48.7M vs actual $35.6M. 37% under budget overall.",
         "Projected gross margin of 40.1%.",
         "Validate historical rates against actual performance to calibrate estimates.", "all"),

        # Concrete
        ("CONCRETE", "production_variance", "HIGH", "Wall F/S Rate Validated at 0.28 MH/SF",
         "Wall forming tracked almost exactly on budget (0.276 vs 0.280 MH/SF) across 36,000+ SF of 24-29ft walls.",
         "Gold standard rate for estimating.",
         "Use 0.28 MH/SF for wall formwork with gang forms.", "pump_station"),

        ("CONCRETE", "production_variance", "HIGH", "3-Pour Strategy Saved ~$1.5M",
         "Executed 3 massive continuous pours instead of 5-7 smaller pours. 0.15 MH/CY vs 0.41 MH/CY budget.",
         "Pumping savings ~$193K, reduced forming, fewer mobilizations.",
         "For large mat foundations, evaluate continuous pour strategy. Requires 3-pump setup and 18-hr crew.", "pump_station"),

        ("CONCRETE", "scope_gap", "HIGH", "Equipment Pad Embeds Add 40-50% to F/S",
         "CEQ_F/S Pads ran 48% over budget (0.428 vs 0.290 MH/SF) due to heavy anchor bolt density and embed complexity.",
         "75,699 actual cost vs 77,085 budget - saved by quantity.",
         "Add 40-50% complexity factor to equipment pad forming rates for pump stations.", "pump_station"),

        ("CONCRETE", "scope_gap", "MEDIUM", "Mine Site Escort Costs 2.5x Over",
         "RTK required individual escorts for every concrete truck. Budget $33K, actual $73K.",
         "$40K overrun, offset by pumping savings.",
         "Budget $5-7/CY for mine site escort costs. Clarify requirements during bid.", "all"),

        # Piping
        ("PIPING", "estimating", "HIGH", "Budget Rates 40-70% Too High for Shop Fab Spools",
         "All piping specs came in 39-76% under MH budget. Shop fabricated spools with good fit-up.",
         "Total piping labor: 8,342 MH vs 17,339 budget (-52%).",
         "Reduce H/E pipe rates by 40-50% when using quality shop fabricator with good delivery sequence.", "pump_station"),

        ("PIPING", "material", "HIGH", "Bridge Crane on Temp Power Was Critical",
         "Building bridge crane installed on temp power early. Eliminated 95% of external crane needs.",
         "Equipment cost $792/day vs $2,186/day budget.",
         "If bridge crane available, reduce equipment budget by 50-60%.", "pump_station"),

        # Steel
        ("STEEL", "production_variance", "HIGH", "Wall Supports 140% Over Budget",
         "Wall-mounted pipe supports went 140% over budget (13.94 vs 5.80 MH/EA). Access, anchoring, alignment.",
         "683 MH vs 284 MH budget.",
         "Use 12-14 MH/EA for wall supports. 2-2.5x ground supports.", "all"),

        ("STEEL", "production_variance", "HIGH", "Stair Towers 101% Over Budget",
         "Fabrication quality issues (Alumasteel), poor field execution, critical path conflicts.",
         "1,630 MH vs 810 MH budget.",
         "Require shop inspection. Include field fit allowance. Dedicated crew.", "all"),

        # Mechanical
        ("MECHANICAL", "scope_gap", "HIGH", "Epoxy Grout F/S Missed in Bid - 721 MH",
         "Forming and stripping for epoxy grout was NOT included in original estimate. True rate is 50 MH/CY, not 14-20.",
         "721 MH unbudgeted. F/S adds ~30 MH/CY on top of placement.",
         "ALWAYS include F/S in epoxy grout estimates. Budget 50 MH/CY all-in.", "all"),

        ("MECHANICAL", "design", "HIGH", "Pump Rework Due to Design Issues - 584 MH",
         "Pumps removed and reset 2 times. Concrete modifications required.",
         "584 MH extra work, $41,689.",
         "Verify pump base dimensions against vendor drawings BEFORE concrete pour.", "pump_station"),

        # Electrical
        ("ELECTRICAL", "subcontractor", "MEDIUM", "Electrical Sub 12.5% Over Budget",
         "Hunt Electric went $517K over budget. Potential causes: change orders, scope growth, material escalation.",
         "+$517,292 variance.",
         "Include 10-15% contingency for electrical subs on complex industrial.", "all"),

        # GC
        ("GCONDITIONS", "estimating", "HIGH", "Mine Site Training 380% Over Budget",
         "RTKC training: 1,283 MH actual vs 360 MH budget. Extensive safety training required.",
         "$101K vs $21K budget.",
         "Budget 2-3x training hours for mine site work.", "all"),

        ("GCONDITIONS", "estimating", "MEDIUM", "Safety Staff Provided by Owner",
         "RTK provided site safety oversight. Wollam safety staffing minimal (54 MH vs 5,280 budget).",
         "$431K savings on safety management.",
         "Verify owner safety requirements before bidding dedicated safety staff.", "all"),
    ]

    for (disc_code, category, severity, title, description, impact, recommendation, applies_to) in lessons:
        disc_id = disc_ids.get(disc_code) if disc_code else None
        conn.execute("""
            INSERT INTO lessons_learned (
                project_id, discipline_id, category, severity,
                title, description, impact, recommendation, applies_to
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, disc_id, category, severity,
              title, description, impact, recommendation, applies_to))

    conn.commit()


# ---------------------------------------------------------------------------
# Benchmark Rates
# ---------------------------------------------------------------------------

def ingest_benchmarks(conn, project_id: int):
    """Insert benchmark rates compiled from 8553 data."""

    benchmarks = [
        ("CONCRETE", "Wall Form/Strip (gang forms)", "MH/SF", 0.25, 0.30, 0.28, "mh_per_unit", "8553", "pump_station", "Gold standard rate, validated", None),
        ("CONCRETE", "Mat Pour (continuous 3-pump)", "MH/CY", 0.13, 0.17, 0.15, "mh_per_unit", "8553", "pump_station", "Requires 3-pump setup", None),
        ("CONCRETE", "Equipment Pad F/S (heavy embeds)", "MH/SF", 0.40, 0.50, 0.43, "mh_per_unit", "8553", "pump_station", "Add 40-50% for heavy embeds", None),
        ("CONCRETE", "All-In Concrete", "$/CY", 800, 950, 867, "unit_cost", "8553", "pump_station", "Includes rebar, labor, material, pumping", None),

        ("EARTHWORK", "Tailings Excavation (short haul)", "$/CY", 1.00, 1.50, 1.25, "unit_cost", "8553", "pump_station", None, None),
        ("EARTHWORK", "Structural Fill P/C", "$/TON", 3.00, 4.00, 3.50, "unit_cost", "8553", "pump_station", None, None),
        ("EARTHWORK", "Structural Fill (delivered)", "$/TON", 12.00, 15.00, 14.00, "unit_cost", "8553", "pump_station", "Rhine Construction", None),
        ("EARTHWORK", "Excavation Production", "CY/hr", 600, 800, 700, "production_rate", "8553", "pump_station", "With PC650 + 4 artics", None),

        ("STEEL", "Pipe Support - Wall", "MH/EA", 12.0, 14.0, 13.0, "mh_per_unit", "8553", "all", "2-2.5x ground supports", None),
        ("STEEL", "Pipe Support - Ground", "MH/EA", 3.0, 6.5, 5.0, "mh_per_unit", "8553", "all", "Range: small 3.5, large 6.5", None),
        ("STEEL", "Handrail", "MH/LF", 0.50, 0.65, 0.58, "mh_per_unit", "8553", "all", None, None),

        ("PIPING", "Flanged Joint 20-28in", "MH/EA", 6.0, 8.0, 7.0, "mh_per_unit", "8553", "pump_station", "Crane assist required", None),
        ("PIPING", "H/E Pipe (shop fab, blended)", "MH/LF", 0.70, 1.20, 1.00, "mh_per_unit", "8553", "pump_station", "All specs blended", None),
        ("PIPING", "Hydrotesting", "MH/LF", 0.15, 0.25, 0.20, "mh_per_unit", "8553", "pump_station", "Standard hold time", None),

        ("MECHANICAL", "Epoxy Grout (all-in with F/S)", "MH/CY", 45, 55, 50, "mh_per_unit", "8553", "all", "CRITICAL: includes F/S. Do not estimate placement only.", None),
        ("MECHANICAL", "SPD Pump Set", "MH/EA", 130, 160, 145, "mh_per_unit", "8553", "pump_station", "Set only, grout separate", None),

        ("ELECTRICAL", "Heavy Industrial Pump Station", "$/SF", 125, 150, 138, "unit_cost", "8553", "pump_station", "All-in including GC support", None),

        ("GCONDITIONS", "Management Daily Rate", "$/DAY", 2000, 3000, 2500, "unit_cost", "8553", "all", "PM + Super + Admin", None),
        ("GCONDITIONS", "QC Testing (% of job)", "%", 0.50, 1.00, 0.65, "unit_cost", "8553", "all", "Contractor-provided", None),
        ("GCONDITIONS", "GL Insurance", "%", 0.70, 0.75, 0.72, "unit_cost", "8553", "all", "Consistent benchmark", None),
        ("GCONDITIONS", "Total GC (% of job)", "%", 11.0, 16.0, 13.0, "unit_cost", "8553", "all", None, None),
    ]

    for (disc, activity, unit, low, high, typical, rate_type, jobs, proj_type, notes, updated) in benchmarks:
        conn.execute("""
            INSERT INTO benchmark_rates (
                discipline_code, activity, unit, low_rate, high_rate,
                typical_rate, rate_type, source_jobs, project_type,
                notes, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (disc, activity, unit, low, high, typical, rate_type,
              jobs, proj_type, notes, date.today().isoformat()))

    conn.commit()


# ---------------------------------------------------------------------------
# General Conditions Breakdown
# ---------------------------------------------------------------------------

def ingest_gc_breakdown(conn, project_id: int):
    """Insert general conditions breakdown records."""

    gc_items = [
        ("management", "PM + Superintendent + Admin", "1000", 2191521, 948044, "$/DAY", 2107, 450, 2.67, None),
        ("safety", "Safety Management", "1005", 433653, 2959, "$/DAY", None, None, 0.008, "RTK provided safety oversight"),
        ("supervision", "Field Supervision", "1010", 496852, 382648, "$/DAY", 850, 450, 1.08, None),
        ("other", "Small Tools", "1012", 231364, 67616, "$/MO", 2817, 24, 0.19, None),
        ("other", "Consumables", "1013", 138586, 89572, "$/MO", 3732, 24, 0.25, None),
        ("other", "Safety Consumables", "1014", 149336, 54939, "$/MO", 2289, 24, 0.15, None),
        ("equipment", "Site Equipment", "1025", 121688, 68647, "$/DAY", 153, 450, 0.19, None),
        ("other", "Fuel & Maintenance", "1040", 184783, 61201, "$/DAY", 136, 450, 0.17, None),
        ("other", "RTKC Training", "1017", 21044, 101032, "EA", None, None, 0.28, "380% over budget - mine site training"),
        ("other", "Holidays", "1019", 137983, 64291, "$/MO", 2679, 24, 0.18, None),
        ("other", "Site Facilities", "1016", 192470, 133175, "$/MO", 5549, 24, 0.37, None),
        ("survey", "Survey (Digital Earth + Terracon + Sunrise)", "4000", 437680, 150073, "$/MO", 18000, 8, 0.42, "$18K/mo during active phases"),
        ("testing", "QC Testing (Terracon)", "4250", 638000, 231564, "% of job", 0.65, None, 0.65, "Full-time inspector during pours and backfill"),
        ("insurance", "GL Insurance", "8000", 342757, 257745, "% of job", 0.72, None, 0.72, "Consistent benchmark"),
        ("other", "Overhead Allocation", "9999", 1183086, 557894, "% of job", 1.57, None, 1.57, "Corporate overhead"),
    ]

    for (category, desc, cc, bud, act, unit, rate, duration, pct, notes) in gc_items:
        conn.execute("""
            INSERT INTO general_conditions_breakdown (
                project_id, category, description, cost_code,
                budget_cost, actual_cost, unit, rate, duration,
                pct_of_total_job, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, category, desc, cc, bud, act, unit, rate, duration, pct, notes))

    conn.commit()


# ---------------------------------------------------------------------------
# Main Ingestion Entry Point
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("WEIS JCD Ingestion — Job 8553 RTK SPD Pump Station")
    print("=" * 60)

    # Initialize database if needed
    init_db()

    conn = get_connection()
    try:
        # Check if data already exists
        existing = conn.execute("SELECT id FROM projects WHERE job_number = '8553'").fetchone()
        if existing:
            print("\nJob 8553 already exists in database. Clearing and re-ingesting...")
            pid = existing["id"]
            for table in ["general_conditions_breakdown", "benchmark_rates",
                          "lessons_learned", "subcontractors", "material_costs",
                          "crew_configurations", "production_rates", "unit_costs",
                          "cost_codes", "disciplines"]:
                conn.execute(f"DELETE FROM {table} WHERE project_id = ?", (pid,))
            conn.execute("DELETE FROM benchmark_rates")  # No project_id FK
            conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
            conn.commit()

        # 1. Project
        print("\n[1/9] Ingesting project record...")
        project_id = ingest_project(conn)
        print(f"  Project ID: {project_id}")

        # 2. Disciplines
        print("[2/9] Ingesting disciplines...")
        disc_ids = ingest_disciplines(conn, project_id)
        print(f"  {len(disc_ids)} disciplines created")

        # 3. Cost Codes
        print("[3/9] Ingesting cost codes...")
        ingest_cost_codes(conn, project_id, disc_ids)
        count = conn.execute("SELECT COUNT(*) as c FROM cost_codes WHERE project_id = ?", (project_id,)).fetchone()["c"]
        print(f"  {count} cost codes ingested")

        # 4. Unit Costs
        print("[4/9] Ingesting unit costs (recommended rates)...")
        ingest_unit_costs(conn, project_id, disc_ids)
        count = conn.execute("SELECT COUNT(*) as c FROM unit_costs WHERE project_id = ?", (project_id,)).fetchone()["c"]
        print(f"  {count} unit cost records ingested")

        # 5. Production Rates
        print("[5/9] Ingesting production rates...")
        ingest_production_rates(conn, project_id, disc_ids)
        count = conn.execute("SELECT COUNT(*) as c FROM production_rates WHERE project_id = ?", (project_id,)).fetchone()["c"]
        print(f"  {count} production rate records ingested")

        # 6. Crews
        print("[6/9] Ingesting crew configurations...")
        ingest_crews(conn, project_id, disc_ids)
        count = conn.execute("SELECT COUNT(*) as c FROM crew_configurations WHERE project_id = ?", (project_id,)).fetchone()["c"]
        print(f"  {count} crew configurations ingested")

        # 7. Materials
        print("[7/9] Ingesting material costs...")
        ingest_material_costs(conn, project_id, disc_ids)
        count = conn.execute("SELECT COUNT(*) as c FROM material_costs WHERE project_id = ?", (project_id,)).fetchone()["c"]
        print(f"  {count} material cost records ingested")

        # 8. Subcontractors
        print("[8/9] Ingesting subcontractors...")
        ingest_subcontractors(conn, project_id, disc_ids)
        count = conn.execute("SELECT COUNT(*) as c FROM subcontractors WHERE project_id = ?", (project_id,)).fetchone()["c"]
        print(f"  {count} subcontractor records ingested")

        # 9. Lessons Learned
        print("[9/9] Ingesting lessons learned...")
        ingest_lessons_learned(conn, project_id, disc_ids)
        count = conn.execute("SELECT COUNT(*) as c FROM lessons_learned WHERE project_id = ?", (project_id,)).fetchone()["c"]
        print(f"  {count} lessons learned ingested")

        # Bonus: Benchmarks and GC Breakdown
        print("\n[+] Ingesting benchmark rates...")
        ingest_benchmarks(conn, project_id)
        count = conn.execute("SELECT COUNT(*) as c FROM benchmark_rates").fetchone()["c"]
        print(f"  {count} benchmark rates ingested")

        print("[+] Ingesting general conditions breakdown...")
        ingest_gc_breakdown(conn, project_id)
        count = conn.execute("SELECT COUNT(*) as c FROM general_conditions_breakdown WHERE project_id = ?", (project_id,)).fetchone()["c"]
        print(f"  {count} GC breakdown items ingested")

        # Summary
        print("\n" + "=" * 60)
        print("INGESTION COMPLETE")
        print("=" * 60)
        from app.database import get_table_counts
        counts = get_table_counts()
        total = 0
        for table, count in counts.items():
            print(f"  {table}: {count}")
            total += count
        print(f"\n  TOTAL RECORDS: {total}")
        print(f"  Database: {DB_PATH}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
