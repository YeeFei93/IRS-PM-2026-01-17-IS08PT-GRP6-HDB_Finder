import requests
from typing import Any, Dict, Optional

ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"


def address_to_geojson(
    block: str,
    street_name: str,
    unit: Optional[str] = None,
    *,
    return_all: bool = False,
    timeout: int = 15
) -> Dict[str, Any]:
    """
    Convert a Singapore-style address (block + optional unit + street name)
    into coordinates and GeoJSON using OneMap.

    Returns:
        - If return_all=False: best matching GeoJSON Feature
        - If return_all=True: FeatureCollection of all matches
    """

    # Build query string
    parts = [str(block).strip()]
    if unit:
        parts.append(f"#{str(unit).strip().lstrip('#')}")
    parts.append(str(street_name).strip())
    search_val = " ".join(parts)

    params = {
        "searchVal": search_val,
        "returnGeom": "Y",
        "getAddrDetails": "Y",
        "pageNum": 1
    }

    resp = requests.get(ONEMAP_SEARCH_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    results = data.get("results", [])
    if not results:
        raise ValueError(f"No geocoding result found for address: {search_val}")

    def to_feature(r: Dict[str, Any]) -> Dict[str, Any]:
        longitude = float(r["LONGITUDE"])
        latitude = float(r["LATITUDE"])

        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                # GeoJSON expects [longitude, latitude]
                "coordinates": [longitude, latitude]
            },
            "properties": {
                "search_value": search_val,
                "matched_address": r.get("ADDRESS"),
                "block": r.get("BLK_NO"),
                "road_name": r.get("ROAD_NAME"),
                "postal": r.get("POSTAL"),
                "building": r.get("BUILDING"),
                "unit": unit,
                # OneMap projected coordinates
                "x": float(r["X"]) if r.get("X") else None,
                "y": float(r["Y"]) if r.get("Y") else None,
                "latitude": latitude,
                "longitude": longitude
            }
        }

    features = [to_feature(r) for r in results]

    if return_all:
        return {
            "type": "FeatureCollection",
            "features": features
        }

    # Return the first result as best match
    return features[0]


print(address_to_geojson(block="406", street_name="ANG MO KIO AVE 10"))