"""
geo/distances.py
================
Spatial distance computation using Haversine + 20% walking buffer.

Walking buffer rationale:
  Straight-line distance × 1.20 ≈ actual walking path distance
  for Singapore's dense HDB grid layout.
  Walking speed: 4.8 km/h (Singapore average).

OneMap Routing API will be a drop-in replacement in onemap.py.
To switch, change the import in this file only.
"""

import math
import json
from pathlib import Path

# ── Data paths ────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data-service"

# Loaded once at module import (called during app startup via db/loader.py)
_HAWKERS   = []
_MRT       = []
_PARKS     = []
_HOSPITALS = []
_SCHOOLS   = []
_MALLS     = []


def load_geojson_features(path: Path) -> list:
    if not path.exists():
        print(f"[geo] WARNING: {path} not found — skipping.")
        return []
    with open(path) as f:
        data = json.load(f)
    return data.get("features", [])


def _db_to_features(table: str) -> list:
    """
    Load rows from a SQLite amenity table into a GeoJSON-compatible
    feature list so the rest of the distance code stays unchanged.
    Schools come from the DB (geocoded from CSV); all others from GeoJSON files.
    """
    try:
        from db.connection import get_conn
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT name, address, lat, lng FROM {table}"
            ).fetchall()
        return [
            {
                "geometry":   {"type": "Point", "coordinates": [r["lng"], r["lat"]]},
                "properties": {"NAME": r["name"], "address": r["address"] or ""},
            }
            for r in rows if r["lat"] and r["lng"]
        ]
    except Exception as e:
        print(f"[geo] Could not load {table} from DB: {e}")
        return []


def init_geo():
    """Called once at startup to load all amenity data into memory."""
    global _HAWKERS, _MRT, _PARKS, _HOSPITALS, _SCHOOLS, _MALLS
    _HAWKERS   = load_geojson_features(DATA_DIR / "hawker_centres.geojson")
    _MRT       = load_geojson_features(DATA_DIR / "mrt_stations.geojson")
    _PARKS     = load_geojson_features(DATA_DIR / "parks.geojson")
    _HOSPITALS = load_geojson_features(DATA_DIR / "hospitals.geojson")
    # Schools come from SQLite (geocoded from CSV) — not a GeoJSON file
    json_path  = DATA_DIR / "schools.geojson"
    if json_path.exists():
        _SCHOOLS = load_geojson_features(json_path)
    else:
        _SCHOOLS = _db_to_features("schools")
    _MALLS = load_geojson_features(DATA_DIR / "malls.geojson")
    print(f"[geo] Loaded: {len(_HAWKERS)} hawkers, {len(_MRT)} MRT, "
          f"{len(_PARKS)} parks, {len(_HOSPITALS)} hospitals, "
          f"{len(_SCHOOLS)} schools, {len(_MALLS)} malls")


# ── Core maths ────────────────────────────────────────────────────────────────

WALKING_BUFFER = 1.20   # 20% overhead vs straight-line
WALKING_SPEED  = 4.8    # km/h


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line great-circle distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def km_to_walk_mins(km: float) -> int:
    """Convert km (with walking buffer) to walk time in minutes."""
    return round((km * WALKING_BUFFER) / WALKING_SPEED * 60)


def _nearest(lat: float, lng: float, features: list) -> dict:
    """
    Return the nearest feature from a GeoJSON feature list.
    GeoJSON coordinates are [longitude, latitude].
    """
    best_km   = float("inf")
    best_name = "Unknown"

    for feat in features:
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates", [])

        # Handle Point geometry
        if geom.get("type") == "Point" and len(coords) >= 2:
            f_lng, f_lat = coords[0], coords[1]
        # Handle Polygon/MultiPolygon — use first coordinate as proxy centroid
        elif geom.get("type") in ("Polygon", "MultiPolygon"):
            try:
                if geom["type"] == "Polygon":
                    f_lng, f_lat = coords[0][0][0], coords[0][0][1]
                else:
                    f_lng, f_lat = coords[0][0][0][0], coords[0][0][0][1]
            except (IndexError, TypeError):
                continue
        else:
            continue

        km = haversine_km(lat, lng, f_lat, f_lng)
        if km < best_km:
            best_km   = km
            props     = feat.get("properties", {})
            best_name = (props.get("NAME")
                         or props.get("name")
                         or props.get("STN_NAME")
                         or props.get("HOSPITAL_N")
                         or "Unknown")

    return {
        "name":      best_name,
        "walk_mins": km_to_walk_mins(best_km) if best_km < float("inf") else 999,
        "dist_km":   round(best_km * WALKING_BUFFER, 2) if best_km < float("inf") else None,
    }


# ── Public API ────────────────────────────────────────────────────────────────

# ── Amenity thresholds (panel-linked) ────────────────────────────────────────
# These match the front-end must-have labels exactly.
# Used by the recommender to flag threshold compliance per amenity.
THRESHOLDS = {
    "mrt":      {"km": 0.50,  "label": "≤500m"},   # MRT ≤ 500m
    "hawker":   {"km": 1.00,  "label": "≤1km"},    # Hawker ≤ 1km
    "school":   {"km": 1.00,  "label": "≤1km"},    # Pri School ≤ 1km
    "park":     {"km": 1.00,  "label": "≤1km"},    # Park ≤ 1km
    "mall":     {"km": 1.50,  "label": "≤1.5km"},  # Mall ≤ 1.5km
    "hospital": {"km": 3.00,  "label": "≤3km"},    # Hospital ≤ 3km
}


def nearest_amenities(lat: float, lng: float) -> dict:
    """
    Return nearest amenity in each category for a given coordinate.
    Each result includes: name, walk_mins, dist_km, within_threshold (bool).
    Used by the recommender for each town centroid.
    """
    results = {}
    for key, features in [
        ("hawker",   _HAWKERS),
        ("mrt",      _MRT),
        ("park",     _PARKS),
        ("hospital", _HOSPITALS),
        ("school",   _SCHOOLS),
        ("mall",     _MALLS),
    ]:
        r = _nearest(lat, lng, features)
        threshold_km = THRESHOLDS.get(key, {}).get("km", 999)
        r["within_threshold"] = (r["dist_km"] or 999) <= threshold_km
        r["threshold_label"]  = THRESHOLDS.get(key, {}).get("label", "")
        results[key] = r
    return results
