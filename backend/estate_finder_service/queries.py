"""
estate_finder_service/queries.py
=============
All SQL queries in one place. No business logic here.
Returns Hard filters for recommendation scorer to apply on the candidate list of towns, and reduce solution space.
# 1. Filter the flat type (No.Room flat) else all
# 2. Filter the floor preference (low,mid,high) else all
# 3. Filter the regions else all

MySQL migration notes:
  - Table: resale_flats (replaces resale_transactions)
  - estate         varchar(64)  replaces  town
  - sold_date      date         replaces  month (YYYY-MM string)
  - storey_range_start / storey_range_end  int  replace  storey_range varchar
  - remaining_lease_years / remaining_lease_months  int  replace  remaining_lease varchar
  - Placeholders: %s (MySQL) instead of ? (SQLite)
"""

from datetime import datetime, timedelta
import statistics
from collections import defaultdict
from amenity_proximity_service.db_connector import DbConnector

# --- Mapping Configuration ---

# Use the dictionary to map towns to regions, since the front-end allows region-based filtering but not town-based directly. This will help us filter towns based on selected regions.
TOWN_REGION_MAP = {
    'WOODLANDS': 'North', 'SEMBAWANG': 'North', 'YISHUN': 'North', 'ANG MO KIO': 'North', 'BISHAN': 'North',
    'SENGKANG': 'Northeast', 'PUNGGOL': 'Northeast', 'HOUGANG': 'Northeast', 'SERANGOON': 'Northeast', 'BUANGKOK': 'Northeast',
    'TAMPINES': 'East', 'BEDOK': 'East', 'PASIR RIS': 'East', 'GEYLANG': 'East', 'KALLANG/WHAMPOA': 'East',
    'JURONG WEST': 'West', 'JURONG EAST': 'West', 'BUKIT BATOK': 'West', 'CHOA CHU KANG': 'West', 'CLEMENTI': 'West', 'BUKIT PANJANG': 'West',
    'QUEENSTOWN': 'Central', 'BUKIT MERAH': 'Central', 'TOA PAYOH': 'Central', 'CENTRAL AREA': 'Central', 'MARINE PARADE': 'Central'
}

# Floor preference → storey_range_start SQL clause (MySQL int columns replace storey_range strings)
_FLOOR_CLAUSES = {
    'low':  'storey_range_start <= 6',
    'mid':  'storey_range_start BETWEEN 7 AND 15',
    'high': 'storey_range_start >= 16',
}

# --- Logic Functions ---

def detect_active_criteria(ftype: str, floor_pref: str, regions: list) -> list:
    active = []
    if ftype and ftype.lower() != "any":
        active.append("flat")
    if regions and len(regions) > 0:
        active.append("region")
    if floor_pref and floor_pref.lower() != "any":
        active.append("floor_pref")
    return active

def get_all_towns(regions: list = None) -> list[str]:
    """Returns towns, optionally filtered by selected regions."""
    db = DbConnector()
    try:
        db.cursor.execute("SELECT estate FROM estates ORDER BY estate")
        all_towns = [r["estate"] for r in db.cursor.fetchall()]
    finally:
        db.Close()

    if regions:
        # Normalise to title-case so 'north' / 'North' / 'NORTH' all match the map
        regions_title = [r.title() for r in regions]
        return [t for t in all_towns if TOWN_REGION_MAP.get(t) in regions_title]

    return all_towns

def get_transactions_for_town(town: str, ftype: str = "any", floor_pref: str = "any", months: int = 14) -> list[dict]:
    # 30.5 = average days per month (365 / 12), avoids calendar-aware month arithmetic
    cutoff = (datetime.now() - timedelta(days=months * 30.5)).date()

    query = """
        SELECT resale_price, floor_area_sqm, sold_date,
               storey_range_start, storey_range_end,
               remaining_lease_years, remaining_lease_months
        FROM resale_flats
        WHERE estate = %s AND sold_date >= %s
    """
    params = [town, cutoff]

    # Dynamic Filtering for Flat Type
    if ftype and ftype.lower() != "any":
        query += " AND flat_type = %s"
        params.append(ftype)

    # Dynamic Filtering for Floor Preference (int column comparisons)
    if floor_pref and floor_pref.lower() in _FLOOR_CLAUSES:
        query += f" AND {_FLOOR_CLAUSES[floor_pref.lower()]}"

    query += " ORDER BY sold_date DESC"

    db = DbConnector()
    try:
        db.cursor.execute(query, tuple(params))
        rows = db.cursor.fetchall()
    finally:
        db.Close()

    if not rows:
        return []

    records = [dict(r) for r in rows]

    # Normalise sold_date (date object) to YYYY-MM string for downstream grouping
    for r in records:
        if hasattr(r.get("sold_date"), "strftime"):
            r["sold_date"] = r["sold_date"].strftime("%Y-%m")

    # Outlier removal (±3 std dev from median)
    prices = [r["resale_price"] for r in records]
    if len(prices) >= 5:
        med = statistics.median(prices)
        std = statistics.stdev(prices)
        records = [r for r in records if abs(r["resale_price"] - med) <= 3 * std]

    return records

def get_price_trend(town: str, ftype: str = "any", floor_pref: str = "any") -> dict:
    # 30.5 = average days per month (365 / 12), avoids calendar-aware month arithmetic
    cutoff = (datetime.now() - timedelta(days=24 * 30.5)).date()

    query = """
        SELECT sold_date, resale_price
        FROM resale_flats
        WHERE estate = %s AND sold_date >= %s
    """
    params = [town, cutoff]

    if ftype and ftype.lower() != "any":
        query += " AND flat_type = %s"
        params.append(ftype)

    if floor_pref and floor_pref.lower() in _FLOOR_CLAUSES:
        query += f" AND {_FLOOR_CLAUSES[floor_pref.lower()]}"

    query += " ORDER BY sold_date"

    db = DbConnector()
    try:
        db.cursor.execute(query, tuple(params))
        rows = db.cursor.fetchall()
    finally:
        db.Close()

    if not rows:
        return {"town": town, "ftype": ftype, "months": [], "medians": []}

    monthly = defaultdict(list)
    for r in rows:
        month_key = r["sold_date"].strftime("%Y-%m") if hasattr(r.get("sold_date"), "strftime") else r["sold_date"]
        monthly[month_key].append(r["resale_price"])

    months_sorted = sorted(monthly.keys())
    medians = [int(statistics.median(monthly[m])) for m in months_sorted]

    return {
        "town": town,
        "ftype": ftype,
        "months": months_sorted,
        "medians": medians,
        "n": len(rows),
    }