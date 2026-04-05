"""
estate_finder_service/queries.py
=============
All SQL queries in one place. No business logic here.
Returns Hard filters for recommendation scorer to apply on the candidate list of towns, and reduce solution space.
# 1. Filter the flat type (No.Room flat) else all
# 2. Filter the floor preference (low,mid,high) else all
# 3. Filter the regions else all

"""

from datetime import datetime, timedelta
import statistics
from collections import defaultdict
from db.connection import get_conn # Need to draw from data-service

# --- Mapping Configuration ---

# Use the dictionary to map towns to regions, since the front-end allows region-based filtering but not town-based directly. This will help us filter towns based on selected regions.
TOWN_REGION_MAP = {
    'WOODLANDS': 'North', 'SEMBAWANG': 'North', 'YISHUN': 'North', 'ANG MO KIO': 'North', 'BISHAN': 'North',
    'SENGKANG': 'Northeast', 'PUNGGOL': 'Northeast', 'HOUGANG': 'Northeast', 'SERANGOON': 'Northeast', 'BUANGKOK': 'Northeast',
    'TAMPINES': 'East', 'BEDOK': 'East', 'PASIR RIS': 'East', 'GEYLANG': 'East', 'KALLANG/WHAMPOA': 'East',
    'JURONG WEST': 'West', 'JURONG EAST': 'West', 'BUKIT BATOK': 'West', 'CHOA CHU KANG': 'West', 'CLEMENTI': 'West', 'BUKIT PANJANG': 'West',
    'QUEENSTOWN': 'Central', 'BUKIT MERAH': 'Central', 'TOA PAYOH': 'Central', 'CENTRAL AREA': 'Central', 'MARINE PARADE': 'Central'
}

# Standard HDB Storey Range mappings
FLOOR_MAP = {
    'low': ['01 TO 03', '04 TO 06'],
    'mid': ['07 TO 09', '10 TO 12','13 TO 15'],
    'high': ['16 TO 18', '19 TO 21', '22 TO 24', '25 TO 27', '28 TO 30', '31 TO 33', '34 TO 36', '37 TO 39', '40 TO 42', '43 TO 45', '46 TO 48', '49 TO 51']
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
    query = "SELECT DISTINCT town FROM resale_transactions"
    params = []
    
    with get_conn() as conn:
        rows = conn.execute(query).fetchall()
        all_towns = [r["town"] for r in rows]

    if regions:
        # Filter the list of towns based on our dictionary
        return [t for t in all_towns if TOWN_REGION_MAP.get(t) in regions]
    
    return sorted(all_towns)

def get_transactions_for_town(town: str, ftype: str = "any", floor_pref: str = "any", months: int = 14) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=months * 30.5)).strftime("%Y-%m")
    
    # Base Query
    query = "SELECT resale_price, floor_area_sqm, month, storey_range FROM resale_transactions WHERE town = ? AND month >= ?"
    params = [town, cutoff]

    # Dynamic Filtering for Flat Type
    if ftype and ftype.lower() != "any":
        query += " AND flat_type = ?"
        params.append(ftype)

    # Dynamic Filtering for Floor Preference
    if floor_pref and floor_pref.lower() in FLOOR_MAP:
        allowed_floors = FLOOR_MAP[floor_pref.lower()]
        placeholders = ', '.join(['?'] * len(allowed_floors))
        query += f" AND storey_range IN ({placeholders})"
        params.extend(allowed_floors)

    query += " ORDER BY month DESC"

    with get_conn() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    if not rows:
        return []

    records = [dict(r) for r in rows]

    # Outlier removal (±3 std dev from median)
    prices = [r["resale_price"] for r in records]
    if len(prices) >= 5:
        med = statistics.median(prices)
        std = statistics.stdev(prices)
        records = [r for r in records if abs(r["resale_price"] - med) <= 3 * std]

    return records

def get_price_trend(town: str, ftype: str = "any", floor_pref: str = "any") -> dict:
    cutoff = (datetime.now() - timedelta(days=24 * 30.5)).strftime("%Y-%m")
    
    query = "SELECT month, resale_price FROM resale_transactions WHERE town = ? AND month >= ?"
    params = [town, cutoff]

    if ftype and ftype.lower() != "any":
        query += " AND flat_type = ?"
        params.append(ftype)

    if floor_pref and floor_pref.lower() in FLOOR_MAP:
        allowed_floors = FLOOR_MAP[floor_pref.lower()]
        placeholders = ', '.join(['?'] * len(allowed_floors))
        query += f" AND storey_range IN ({placeholders})"
        params.extend(allowed_floors)

    query += " ORDER BY month"

    with get_conn() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    if not rows:
        return {"town": town, "ftype": ftype, "months": [], "medians": []}

    monthly = defaultdict(list)
    for r in rows:
        monthly[r["month"]].append(r["resale_price"])

    months = sorted(monthly.keys())
    medians = [int(statistics.median(monthly[m])) for m in months]

    return {
        "town": town,
        "ftype": ftype,
        "months": months,
        "medians": medians,
        "n": len(rows),
    }