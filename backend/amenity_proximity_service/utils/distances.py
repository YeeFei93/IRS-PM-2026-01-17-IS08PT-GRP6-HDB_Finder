"""
amenity_proximity_service/distances.py
=======================================
Query MySQL for amenity counts and nearest distances per estate.

Assumes this table/junction naming convention:

  Amenity tables        Junction tables
  ─────────────────     ──────────────────────────────
  hawker_centres        resale_flats_hawker_centres
  mrt_stations          resale_flats_mrt_stations
  malls                 resale_flats_malls
  parks                 resale_flats_parks
  schools               resale_flats_schools
  public_hospitals      resale_flats_public_hospitals

Each junction table has:
  resale_flats_id   varchar(36)   FK → resale_flats.resale_flat_id
  <amenity>_id      varchar(36)   FK → amenity table PK
  distance          float         kilometres

Public API
----------
nearest_amenities(estate: str) -> dict
    Returns one entry per amenity type:
    {
      "mrt": {
        "dist_km": float,           # nearest distance
        "walk_mins": int,            # walk time of nearest
        "within_threshold": bool,    # is nearest within threshold?
        "count_within": int,         # how many within threshold distance
        "avg_dist_km": float|None,   # avg distance of those within threshold
      },
      ...
    }
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from amenity_proximity_service.utils.db_connector import DbConnector

# ── In-memory cache (populated on first call per estate, warm on startup) ──
_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()

# ── Amenity config ──────────────────────────────────────────────────────────
# junction_table  : the MySQL junction table name
# amenity_fk      : the FK column in the junction table for the amenity PK
# max_walk_mins   : threshold for within_threshold flag (from constants.js)
# threshold_km    : distance equivalent (max_walk_mins / 15 min/km)
_AMENITY_CONFIG: dict[str, dict] = {
    "mrt":      {"junction_table": "resale_flats_mrt_stations",   "amenity_fk": "mrt_station_id",    "max_walk_mins": 12, "threshold_km": 1.0},
    "hawker":   {"junction_table": "resale_flats_hawker_centres", "amenity_fk": "hawker_centre_name",  "max_walk_mins": 12, "threshold_km": 1.0},
    "mall":     {"junction_table": "resale_flats_malls",          "amenity_fk": "mall_id",             "max_walk_mins": 18, "threshold_km": 1.5},
    "park":     {"junction_table": "resale_flats_parks",          "amenity_fk": "park_name",           "max_walk_mins": 12, "threshold_km": 1.0},
    "school":   {"junction_table": "resale_flats_schools",        "amenity_fk": "school_name",         "max_walk_mins": 12, "threshold_km": 1.0},
    "hospital": {"junction_table": "resale_flats_public_hospitals", "amenity_name_col": "hospital_name", "max_walk_mins": 36, "threshold_km": 3.0},
}

# Walking speed: 5 km/h → 12 min/km (matches frontend ≤1km/≤1.5km/≤3km labels)
# walk_mins = dist_km * 60 / 5 = dist_km * 12
_WALK_MINS_PER_KM = 12.0


def _dist_to_walk_mins(dist_km: float) -> int:
    return round(dist_km * _WALK_MINS_PER_KM)


def _query_amenity_stats(cursor, junction_table: str, amenity_fk: str,
                         estate: str, threshold_km: float) -> dict:
    """Return nearest distance, count of distinct amenities within threshold,
    and avg distance within threshold for an estate.

    Returns dict with keys: min_dist, count_within, avg_dist.
    All values may be None if the junction table doesn't exist or has no data.

    count_within uses COUNT(DISTINCT amenity_fk) to count unique amenities
    reachable from any flat in the estate, NOT the total number of
    flat-amenity pairs.
    """
    import mysql.connector
    query = f"""
        SELECT
            MIN(j.distance)                                                   AS min_dist,
            COUNT(DISTINCT CASE WHEN j.distance <= %s THEN j.`{amenity_fk}` END) AS count_within,
            AVG(CASE WHEN j.distance <= %s THEN j.distance END)               AS avg_dist
        FROM resale_flats rf
        JOIN `{junction_table}` j ON rf.resale_flat_id = j.resale_flat_id
        WHERE rf.estate = %s
    """
    try:
        cursor.execute(query, (threshold_km, threshold_km, estate))
        row = cursor.fetchone()
    except mysql.connector.Error:
        # Table does not exist yet
        return {"min_dist": None, "count_within": 0, "avg_dist": None}

    if row is None:
        return {"min_dist": None, "count_within": 0, "avg_dist": None}

    # Handle both dict and tuple cursor results
    if isinstance(row, dict):
        min_dist = row.get("min_dist")
        count_within = row.get("count_within") or 0
        avg_dist = row.get("avg_dist")
    else:
        min_dist = row[0]
        count_within = row[1] or 0
        avg_dist = row[2]

    return {
        "min_dist": float(min_dist) if min_dist is not None else None,
        "count_within": int(count_within),
        "avg_dist": float(avg_dist) if avg_dist is not None else None,
    }


def _query_named_amenity_stats(cursor, junction_table: str, amenity_name_col: str,
                               estate: str, threshold_km: float) -> dict:
    """Variant for junction tables keyed by block/street_name + amenity name."""
    import mysql.connector
    query = f"""
        SELECT
            MIN(j.distance) AS min_dist,
            COUNT(DISTINCT CASE WHEN j.distance <= %s THEN j.`{amenity_name_col}` END) AS count_within,
            AVG(CASE WHEN j.distance <= %s THEN j.distance END) AS avg_dist
        FROM (
            SELECT DISTINCT estate, block, street_name
            FROM resale_flats
            WHERE estate = %s
        ) rf
        JOIN `{junction_table}` j
          ON rf.block = j.block
         AND rf.street_name = j.street_name
    """
    try:
        cursor.execute(query, (threshold_km, threshold_km, estate))
        row = cursor.fetchone()
    except mysql.connector.Error:
        return {"min_dist": None, "count_within": 0, "avg_dist": None}

    if row is None:
        return {"min_dist": None, "count_within": 0, "avg_dist": None}

    if isinstance(row, dict):
        min_dist = row.get("min_dist")
        count_within = row.get("count_within") or 0
        avg_dist = row.get("avg_dist")
    else:
        min_dist = row[0]
        count_within = row[1] or 0
        avg_dist = row[2]

    return {
        "min_dist": float(min_dist) if min_dist is not None else None,
        "count_within": int(count_within),
        "avg_dist": float(avg_dist) if avg_dist is not None else None,
    }


def _fetch_one_amenity(amenity_key: str, config: dict, estate: str) -> tuple[str, dict, dict]:
    """Run one amenity query in its own DB connection (thread-safe)."""
    db = DbConnector()
    try:
        if "amenity_fk" in config:
            stats = _query_amenity_stats(
                db.cursor, config["junction_table"], config["amenity_fk"],
                estate, config["threshold_km"]
            )
        else:
            stats = _query_named_amenity_stats(
                db.cursor, config["junction_table"], config["amenity_name_col"],
                estate, config["threshold_km"]
            )
    finally:
        db.Close()
    return amenity_key, config, stats


def nearest_amenities(estate: str) -> dict:
    """Return amenity stats for every amenity type for an estate.

    Results are cached in memory so repeated lookups are O(1).

    Parameters
    ----------
    estate : str
        HDB estate/town name (uppercase), e.g. ``'WOODLANDS'``.

    Returns
    -------
    dict
        Keys: mrt, hawker, mall, park, school, hospital.
        Each value: ``{"dist_km": float, "walk_mins": int,
        "within_threshold": bool, "count_within": int, "avg_dist_km": float|None}``.
        If no data exists for an amenity, ``dist_km`` is ``None`` and
        ``within_threshold`` is ``False``.
    """
    # Fast path: return cached result
    if estate in _cache:
        return _cache[estate]

    result: dict = {}

    # Run all 6 amenity queries in parallel (each with its own DB connection)
    with ThreadPoolExecutor(max_workers=len(_AMENITY_CONFIG)) as executor:
        futures = {
            executor.submit(_fetch_one_amenity, k, v, estate): k
            for k, v in _AMENITY_CONFIG.items()
        }
        for future in as_completed(futures):
            amenity_key, config, stats = future.result()
            dist_km = stats["min_dist"]
            if dist_km is not None:
                walk_mins = _dist_to_walk_mins(dist_km)
                within_threshold = walk_mins <= config["max_walk_mins"]
                result[amenity_key] = {
                    "dist_km": round(dist_km, 4),
                    "walk_mins": walk_mins,
                    "within_threshold": within_threshold,
                    "count_within": stats["count_within"],
                    "avg_dist_km": round(stats["avg_dist"], 4) if stats["avg_dist"] is not None else None,
                }
            else:
                result[amenity_key] = {
                    "dist_km": None,
                    "walk_mins": None,
                    "within_threshold": False,
                    "count_within": 0,
                    "avg_dist_km": None,
                }

    with _cache_lock:
        _cache[estate] = result
    return result


def warm_all_estates() -> None:
    """Pre-populate the in-memory cache for every estate in the DB.

    Called once in a background thread when the recommendation adapter
    starts so the first user request gets cached results.
    """
    try:
        db = DbConnector()
        try:
            db.cursor.execute("SELECT DISTINCT estate FROM resale_flats ORDER BY estate")
            rows = db.cursor.fetchall()
        finally:
            db.Close()
        estates = [r["estate"] if isinstance(r, dict) else r[0] for r in rows]
        # Fetch estates in parallel to finish warm-up quickly
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(nearest_amenities, e): e for e in estates}
            for future in as_completed(futures):
                future.result()  # surface any exceptions to logs
    except Exception:
        pass  # warm-up failure must never crash the adapter
