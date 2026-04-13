import math
from time import sleep

import requests
from typing import Any, Dict, Optional

ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"


class GeolocationConverter:
    def GetGeolocation(self, block: str, street_name: str,) -> Dict[str, Any]:
        timeout: int = 15
        # Build query string
        parts = [str(block).strip()]
        parts.append(str(street_name).strip())
        search_val = " ".join(parts)
        data = None
        params = {
            "searchVal": search_val,
            "returnGeom": "Y",
            "getAddrDetails": "Y",
            "pageNum": 1
        }

        def fetch_data():
            resp = requests.get(ONEMAP_SEARCH_URL, params=params, timeout=timeout)
            if resp.status_code != 200:
                print(f"Retrying block {block} street_name {street_name}...")
                sleep(0.5)
                fetch_data()

            if not resp.text.strip():
                print(f"Retrying block {block} street_name {street_name}...")
                sleep(0.5)
                fetch_data()

            content_type = resp.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                print(f"Retrying block {block} street_name {street_name}...")
                sleep(0.5)
                fetch_data()
            
            data = resp.json()
            results = data.get("results", [])
            if not results:
                print(f"No geocoding result found for address: {search_val}")
            return results
        try:
            data = fetch_data()
        except Exception as e:
            print(f"Retrying block {block} street_name {street_name}...")
            sleep(0.5)
            fetch_data()

        def to_feature(r: Dict[str, Any]) -> Dict[str, Any]:
            longitude = float(r["LONGITUDE"])
            latitude = float(r["LATITUDE"])

            return {
                "latitude": latitude,
                "longitude": longitude
            }

        if data:
            features = [to_feature(r) for r in data]
            return features[0] 
        else:
            return {}
        
    def CalculateDistance(self, lat1, lon1, lat2, lon2):
        """
        Calculate distance between two GPS coordinates using the Haversine formula.
        
        Parameters:
        lat1, lon1 : float  -> latitude and longitude of current location
        lat2, lon2 : float  -> latitude and longitude of target location
        
        Returns:
        distance in kilometers
        """

        # Earth radius in kilometers
        R = 6371.0

        # Convert degrees to radians
        lat1 = math.radians(lat1)
        lon1 = math.radians(lon1)
        lat2 = math.radians(lat2)
        lon2 = math.radians(lon2)

        # Differences
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        # Haversine formula
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        distance = R * c

        return distance
        