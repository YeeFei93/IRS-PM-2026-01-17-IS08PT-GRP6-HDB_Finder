"""
amenity_proximity_service/distances.py
=======================================
Query MySQL for the nearest amenity distance per estate.

Assumes this table/junction naming convention (same schema as hawker_centres):

  Amenity tables        Junction tables
  ─────────────────     ──────────────────────────────
  hawker_centres        resale_flats_hawker_centres
  mrt_stations          resale_flats_mrt_stations
  malls                 resale_flats_malls
  parks                 resale_flats_parks
  schools               resale_flats_schools
  hospitals             resale_flats_hospitals

Each junction table has:
  resale_flats_id   varchar(36)   FK → resale_flats.resale_flat_id
  <amenity>_id      varchar(36)   FK → amenity table PK  (unused in queries here)
  distance          float         kilometres

Public API
----------
nearest_amenities(estate: str) -> dict
    Returns one entry per amenity type:
    {
      "mrt":      {"dist_km": float, "walk_mins": int, "within_threshold": bool},
      "hawker":   {"dist_km": float, "walk_mins": int, "within_threshold": bool},
      "mall":     {"dist_km": float, "walk_mins": int, "within_threshold": bool},
      "park":     {"dist_km": float, "walk_mins": int, "within_threshold": bool},
      "school":   {"dist_km": float, "walk_mins": int, "within_threshold": bool},
      "hospital": {"dist_km": float, "walk_mins": int, "within_threshold": bool},
    }
"""

from __future__ import annotations

from amenity_proximity_service.db_connector import DbConnector

# ── Amenity config ──────────────────────────────────────────────────────────
# junction_table : the MySQL junction table name
# max_walk_mins  : threshold for within_threshold flag (from constants.js)
_AMENITY_CONFIG: dict[str, dict] = {
    "mrt":      {"junction_table": "resale_flats_mrt_stations",     "max_walk_mins": 6},
    "hawker":   {"junction_table": "resale_flats_hawker_centres",    "max_walk_mins": 12},
    "mall":     {"junction_table": "resale_flats_malls",             "max_walk_mins": 18},
    "park":     {"junction_table": "resale_flats_parks",             "max_walk_mins": 12},
    "school":   {"junction_table": "resale_flats_schools",           "max_walk_mins": 12},
    "hospital": {"junction_table": "resale_flats_hospitals",         "max_walk_mins": 36},
}

# Walking speed: 5 km/h with a 20% buffer → effective 4 km/h
# walk_mins = dist_km * 60 / 4 = dist_km * 15
_WALK_MINS_PER_KM = 15.0


def _dist_to_walk_mins(dist_km: float) -> int:
    return round(dist_km * _WALK_MINS_PER_KM)


def _query_min_distance(cursor, junction_table: str, estate: str) -> float | None:
    """Return the minimum amenity distance (km) across all flats in an estate."""
    query = f"""
        SELECT MIN(j.distance) AS dist_km
        FROM resale_flats rf
        JOIN `{junction_table}` j ON rf.resale_flat_id = j.resale_flats_id
        WHERE rf.estate = %s
    """
    cursor.execute(query, (estate,))
    row = cursor.fetchone()
    if row is None:
        return None
    dist = row.get("dist_km") if isinstance(row, dict) else row[0]
    return float(dist) if dist is not None else None


def nearest_amenities(estate: str) -> dict:
    """Return nearest amenity distances for every amenity type for an estate.

    Parameters
    ----------
    estate : str
        HDB estate/town name (uppercase), e.g. ``'WOODLANDS'``.

    Returns
    -------
    dict
        Keys: mrt, hawker, mall, park, school, hospital.
        Each value: ``{"dist_km": float, "walk_mins": int, "within_threshold": bool}``.
        If no data exists for an amenity, ``dist_km`` is ``None`` and
        ``within_threshold`` is ``False``.
    """
    db = DbConnector()
    cursor = db.cursor
    result: dict = {}

    try:
        for amenity_key, config in _AMENITY_CONFIG.items():
            dist_km = _query_min_distance(cursor, config["junction_table"], estate)

            if dist_km is not None:
                walk_mins = _dist_to_walk_mins(dist_km)
                within_threshold = walk_mins <= config["max_walk_mins"]
                result[amenity_key] = {
                    "dist_km": round(dist_km, 4),
                    "walk_mins": walk_mins,
                    "within_threshold": within_threshold,
                }
            else:
                result[amenity_key] = {
                    "dist_km": None,
                    "walk_mins": None,
                    "within_threshold": False,
                }
    finally:
        db.Close()

    return result
