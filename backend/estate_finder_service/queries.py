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

from datetime import date, datetime, timedelta
import re
import statistics
from collections import defaultdict
from amenity_proximity_service.utils.db_connector import DbConnector

# --- Mapping Configuration ---

# Use the dictionary to map towns to regions, since the front-end allows region-based filtering but not town-based directly. This will help us filter towns based on selected regions.
TOWN_REGION_MAP = {
    'WOODLANDS': 'North', 'SEMBAWANG': 'North', 'YISHUN': 'North', 'ANG MO KIO': 'North', 'BISHAN': 'North',
    'SENGKANG': 'Northeast', 'PUNGGOL': 'Northeast', 'HOUGANG': 'Northeast', 'SERANGOON': 'Northeast', 'BUANGKOK': 'Northeast',
    'TAMPINES': 'East', 'BEDOK': 'East', 'PASIR RIS': 'East', 'GEYLANG': 'East', 'KALLANG/WHAMPOA': 'East',
    'JURONG WEST': 'West', 'JURONG EAST': 'West', 'BUKIT BATOK': 'West', 'CHOA CHU KANG': 'West', 'CLEMENTI': 'West', 'BUKIT PANJANG': 'West',
    'QUEENSTOWN': 'Central', 'BUKIT MERAH': 'Central', 'TOA PAYOH': 'Central', 'CENTRAL AREA': 'Central', 'MARINE PARADE': 'Central'
}

# Only show flats sold after this date (Oct 2025 onwards)
_MIN_SOLD_DATE = date(2025, 10, 1)

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


def _apply_flat_filters(query: str, params: list, ftype: str, floor_pref: str, min_lease: int, alias: str = "rf") -> tuple:
    """Append optional filter clauses to a flat query. Returns (query, params)."""
    if ftype and ftype.lower() != "any":
        query += f" AND {alias}.flat_type = %s"
        params.append(ftype)
    if floor_pref and floor_pref.lower() in _FLOOR_CLAUSES:
        clause = _FLOOR_CLAUSES[floor_pref.lower()].replace("storey_range_start", f"{alias}.storey_range_start")
        query += f" AND {clause}"
    if min_lease > 0:
        query += f" AND {alias}.remaining_lease_years >= %s"
        params.append(min_lease)
    return query, params


def _normalise_records(rows, budget: float, limit: int) -> list[dict]:
    """Shared post-processing: normalise dates, sort by budget proximity, slice."""
    if not rows:
        return []
    records = [dict(r) for r in rows]
    for r in records:
        if hasattr(r.get("sold_date"), "strftime"):
            r["sold_date"] = r["sold_date"].strftime("%Y-%m")
        if r.get("latitude") is not None:
            r["latitude"] = float(r["latitude"])
        if r.get("longitude") is not None:
            r["longitude"] = float(r["longitude"])
    if budget > 0:
        records.sort(key=lambda r: abs(r["resale_price"] - budget))
    return records[:limit]


def get_flats_for_estate(
    estate: str,
    ftype: str = "any",
    floor_pref: str = "any",
    budget: float = 0,
    min_lease: int = 0,
    months: int = 14,
    limit: int = 20,
) -> list[dict]:
    """Return flat transactions for a single estate, sorted by budget proximity."""
    cutoff = max((datetime.now() - timedelta(days=months * 30.5)).date(), _MIN_SOLD_DATE)
    query = """
        SELECT rf.estate, rf.block, rf.street_name, rf.flat_type, rf.flat_model,
               rf.storey_range_start, rf.storey_range_end,
               rf.floor_area_sqm,
               rf.remaining_lease_years, rf.remaining_lease_months,
               rf.resale_price, rf.sold_date,
               g.latitude, g.longitude
        FROM resale_flats rf
        LEFT JOIN resale_flats_geolocation g
               ON g.block = rf.block AND g.street_name = rf.street_name
        WHERE rf.estate = %s AND rf.sold_date >= %s
    """
    params = [estate, cutoff]
    query, params = _apply_flat_filters(query, params, ftype, floor_pref, min_lease)
    query += " ORDER BY rf.sold_date DESC"
    db = DbConnector()
    try:
        db.cursor.execute(query, tuple(params))
        rows = db.cursor.fetchall()
    finally:
        db.Close()
    return _normalise_records(rows, budget, limit)


def get_top_flats_across_estates(
    estates: list,
    ftype: str = "any",
    floor_pref: str = "any",
    budget: float = 0,
    min_lease: int = 0,
    months: int = 14,
    limit: int = 20,
) -> list[dict]:
    """Return top flats across all recommended estates, sorted by budget proximity.

    Fetches a larger pool (limit * 3 per estate) then re-sorts globally so the
    final Top-N is the best matches globally, not just the best per estate.
    """
    if not estates:
        return []
    cutoff = max((datetime.now() - timedelta(days=months * 30.5)).date(), _MIN_SOLD_DATE)
    placeholders = ", ".join(["%s"] * len(estates))
    query = f"""
        SELECT rf.estate, rf.block, rf.street_name, rf.flat_type, rf.flat_model,
               rf.storey_range_start, rf.storey_range_end,
               rf.floor_area_sqm,
               rf.remaining_lease_years, rf.remaining_lease_months,
               rf.resale_price, rf.sold_date,
               g.latitude, g.longitude
        FROM resale_flats rf
        LEFT JOIN resale_flats_geolocation g
               ON g.block = rf.block AND g.street_name = rf.street_name
        WHERE rf.estate IN ({placeholders}) AND rf.sold_date >= %s
    """
    params = list(estates) + [cutoff]
    query, params = _apply_flat_filters(query, params, ftype, floor_pref, min_lease)
    query += " ORDER BY rf.sold_date DESC"
    db = DbConnector()
    try:
        db.cursor.execute(query, tuple(params))
        rows = db.cursor.fetchall()
    finally:
        db.Close()
    return _normalise_records(rows, budget, limit)


def get_parks_for_flat(block: str, street_name: str) -> list[dict]:
    """Return non-playground parks within threshold of a flat block, with coordinates."""
    query = """
        SELECT p.park_name,
               p.latitude,
               p.longitude,
               rfp.distance
        FROM resale_flats_parks rfp
        JOIN parks p ON p.park_name = rfp.park_name
        WHERE rfp.block = %s AND rfp.street_name = %s
          AND p.latitude IS NOT NULL AND p.longitude IS NOT NULL
          AND p.park_name NOT REGEXP '( PG| OS| FC|PLAYGROUND)$'
        ORDER BY rfp.distance
    """
    db = DbConnector()
    try:
        db.cursor.execute(query, (block, street_name))
        rows = db.cursor.fetchall()
    except Exception:
        return []
    finally:
        db.Close()
    return [
        {
            "name":      r["park_name"],
            "latitude":  float(r["latitude"]),
            "longitude": float(r["longitude"]),
            "distance":  round(float(r["distance"]), 3),
        }
        for r in rows
    ]


def _get_amenity_for_flat(
    block: str, street_name: str,
    join_table: str, amenity_table: str, amenity_name_col: str,
) -> list[dict]:
    """
    Generic amenity query for name-based FK schema (-05).
    join_table has columns: block, street_name, <amenity_name_col>, distance.
    amenity_table has columns: <amenity_name_col>, latitude, longitude.
    Returns [] gracefully on any error (table not yet populated, etc.).
    """
    query = f"""
        SELECT a.`{amenity_name_col}` AS name,
               a.latitude,
               a.longitude,
               j.distance
        FROM `{join_table}` j
        JOIN `{amenity_table}` a ON a.`{amenity_name_col}` = j.`{amenity_name_col}`
        WHERE j.block = %s AND j.street_name = %s
          AND a.latitude IS NOT NULL AND a.longitude IS NOT NULL
        ORDER BY j.distance
    """
    db = DbConnector()
    try:
        db.cursor.execute(query, (block, street_name))
        rows = db.cursor.fetchall()
    except Exception:
        return []
    finally:
        try:
            db.Close()
        except Exception:
            pass
    return [
        {
            "name":      r["name"],
            "latitude":  float(r["latitude"]),
            "longitude": float(r["longitude"]),
            "distance":  round(float(r["distance"]), 3),
        }
        for r in rows
    ]


def get_all_amenities_for_flat(block: str, street_name: str) -> dict:
    """
    Return all proximity amenity types for a flat in a single call.
    Types not yet populated in the DB return empty lists.
    Distance thresholds are enforced at the DB population stage; all returned
    rows are already within threshold.
    """
    return {
        "parks":     get_parks_for_flat(block, street_name),
        "hawkers":   _get_amenity_for_flat(block, street_name,
                         "resale_flats_hawker_centres",   "hawker_centres",   "hawker_centre_name"),
        "mrts":      _get_amenity_for_flat(block, street_name,
                         "resale_flats_mrt_stations",     "mrt_stations",     "mrt_station_name"),
        "schools":   _get_amenity_for_flat(block, street_name,
                         "resale_flats_schools",          "schools",          "school_name"),
        "malls":     _get_amenity_for_flat(block, street_name,
                         "resale_flats_shopping_malls",   "shopping_malls",   "shopping_mall_name"),
        "hospitals": _get_amenity_for_flat(block, street_name,
                         "resale_flats_public_hospitals", "public_hospitals", "hospital_name"),
    }