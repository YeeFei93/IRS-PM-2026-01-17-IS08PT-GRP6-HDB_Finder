"""
geo/centroids.py
================
Pre-coded lat/lng centroids for all HDB towns.
Used as fallback when planning area GeoJSON polygon centroid
computation is unavailable or as a fast lookup.

Coordinates represent the approximate centre of each HDB estate,
not any specific block. Derived from Singapore Master Plan 2019
planning area centroids.
"""

TOWN_CENTROIDS: dict[str, dict] = {
    "ANG MO KIO":      {"lat": 1.3691, "lng": 103.8454},
    "BEDOK":           {"lat": 1.3236, "lng": 103.9273},
    "BISHAN":          {"lat": 1.3526, "lng": 103.8352},
    "BUKIT BATOK":     {"lat": 1.3490, "lng": 103.7495},
    "BUKIT MERAH":     {"lat": 1.2819, "lng": 103.8239},
    "BUKIT PANJANG":   {"lat": 1.3774, "lng": 103.7719},
    "BUONA VISTA":     {"lat": 1.3072, "lng": 103.7902},
    "CENTRAL AREA":    {"lat": 1.2897, "lng": 103.8501},
    "CHOA CHU KANG":   {"lat": 1.3840, "lng": 103.7470},
    "CLEMENTI":        {"lat": 1.3162, "lng": 103.7649},
    "GEYLANG":         {"lat": 1.3201, "lng": 103.8918},
    "HOUGANG":         {"lat": 1.3719, "lng": 103.8929},
    "JURONG EAST":     {"lat": 1.3329, "lng": 103.7436},
    "JURONG WEST":     {"lat": 1.3404, "lng": 103.7090},
    "KALLANG":         {"lat": 1.3100, "lng": 103.8651},
    "MARINE PARADE":   {"lat": 1.3022, "lng": 103.9073},
    "PASIR RIS":       {"lat": 1.3721, "lng": 103.9474},
    "PUNGGOL":         {"lat": 1.4019, "lng": 103.9024},
    "QUEENSTOWN":      {"lat": 1.2942, "lng": 103.7861},
    "SEMBAWANG":       {"lat": 1.4491, "lng": 103.8185},
    "SENGKANG":        {"lat": 1.3868, "lng": 103.8914},
    "SERANGOON":       {"lat": 1.3554, "lng": 103.8679},
    "TAMPINES":        {"lat": 1.3530, "lng": 103.9449},
    "TOA PAYOH":       {"lat": 1.3343, "lng": 103.8563},
    "WOODLANDS":       {"lat": 1.4382, "lng": 103.7891},
    "YISHUN":          {"lat": 1.4304, "lng": 103.8354},
}


def get_centroid(town: str) -> dict | None:
    """
    Return {"lat": float, "lng": float} for a town name,
    or None if not found.
    """
    return TOWN_CENTROIDS.get(town.upper())


def all_towns() -> list[str]:
    return list(TOWN_CENTROIDS.keys())
