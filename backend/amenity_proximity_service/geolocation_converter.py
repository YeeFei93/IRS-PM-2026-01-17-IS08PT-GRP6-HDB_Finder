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
        