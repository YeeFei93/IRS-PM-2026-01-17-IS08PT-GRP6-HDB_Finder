import json
from time import sleep
from typing import Any, Dict, List
from urllib.parse import urlencode
from urllib.request import urlopen

ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"


class GeolocationConverter:
    def SearchGeolocations(self, search_val: str) -> List[Dict[str, Any]]:
        timeout: int = 15
        cleaned_search_val = " ".join(str(search_val).split())
        params = {
            "searchVal": cleaned_search_val,
            "returnGeom": "Y",
            "getAddrDetails": "Y",
            "pageNum": 1,
        }
        request_url = f"{ONEMAP_SEARCH_URL}?{urlencode(params)}"

        def fetch_data():
            while True:
                try:
                    with urlopen(request_url, timeout=timeout) as resp:
                        status_code = getattr(resp, "status", 200)
                        if status_code != 200:
                            raise ValueError(f"Unexpected status code: {status_code}")

                        payload = resp.read().decode("utf-8").strip()
                        if not payload:
                            raise ValueError("Empty response body")

                    data = json.loads(payload)
                    results = data.get("results", [])
                    if not results:
                        print(f"No geocoding result found for search: {cleaned_search_val}")
                    return results
                except Exception:
                    print(f"Retrying geolocation lookup for {cleaned_search_val}...")
                    sleep(0.5)

        try:
            data = fetch_data()
        except Exception:
            print(f"Retrying geolocation lookup for {cleaned_search_val}...")
            sleep(0.5)
            data = fetch_data()

        return data or []

    def ToGeolocation(self, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "latitude": float(result["LATITUDE"]),
            "longitude": float(result["LONGITUDE"]),
        }

    def GetGeolocation(self, search_val: str) -> Dict[str, Any]:
        data = self.SearchGeolocations(search_val)
        if not data:
            return {}

        return self.ToGeolocation(data[0])
