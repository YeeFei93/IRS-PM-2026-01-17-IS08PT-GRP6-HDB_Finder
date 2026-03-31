"""
geo/onemap.py
=============
OneMap Routing API integration.
Currently a stub — drop-in replacement for geo/distances.py
Haversine calculations when more accurate routing is needed.

To activate: replace `nearest_amenities` import in geo/distances.py
with the function from this file.

OneMap API docs: https://www.onemap.gov.sg/apidocs/
"""

import os
import urllib.request
import json


ONEMAP_API_KEY = os.getenv("ONEMAP_API_KEY", "")


def get_route_walk_mins(origin_lat: float, origin_lng: float,
                        dest_lat: float, dest_lng: float) -> int | None:
    """
    Query OneMap Routing API for walking time between two coordinates.
    Returns walk time in minutes, or None if API call fails.

    Requires ONEMAP_API_KEY environment variable to be set.
    """
    if not ONEMAP_API_KEY:
        return None

    url = (
        f"https://www.onemap.gov.sg/api/public/routingsvc/route"
        f"?start={origin_lat},{origin_lng}"
        f"&end={dest_lat},{dest_lng}"
        f"&routeType=walk"
        f"&token={ONEMAP_API_KEY}"
    )

    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        # Extract total time in seconds from route summary
        duration_secs = data["route_summary"]["total_time"]
        return round(duration_secs / 60)
    except Exception as e:
        print(f"[onemap] Routing API error: {e}")
        return None


def geocode_address(address: str) -> dict | None:
    """
    Geocode a Singapore address string to lat/lng using OneMap Search API.
    Returns {"lat": float, "lng": float} or None.
    """
    encoded = urllib.parse.quote(address)
    url = f"https://www.onemap.gov.sg/api/common/elastic/search?searchVal={encoded}&returnGeom=Y&getAddrDetails=Y"

    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
        results = data.get("results", [])
        if not results:
            return None
        first = results[0]
        return {
            "lat": float(first["LATITUDE"]),
            "lng": float(first["LONGITUDE"]),
            "address": first.get("ADDRESS", ""),
        }
    except Exception as e:
        print(f"[onemap] Geocode error: {e}")
        return None


import urllib.parse  # noqa: E402 (needed for geocode_address above)
