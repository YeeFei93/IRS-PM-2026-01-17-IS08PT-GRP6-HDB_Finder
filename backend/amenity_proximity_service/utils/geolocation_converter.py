import math
import json
from time import sleep

from typing import Any, Dict, Optional
from urllib.parse import urlencode
from urllib.request import urlopen
import requests

ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
OPENSTREETMAP_SEARCH_URL = "https://nominatim.openstreetmap.org/search?q={{address}}&format=jsonv2"


class GeolocationConverter:

    def OSM_Connect(self):
        try:
            home = "https://nominatim.openstreetmap.org/ui/search.html"
            session = requests.session()
            session.get(home, timeout=15)
        except requests.exceptions.RequestException as e:
            self.OSM_Connect()

    def GetOSMGeolocation(self, block, street_name):
        request_url = OPENSTREETMAP_SEARCH_URL.replace("{{address}}", f"{block} {street_name}")
        # print(request_url)
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
            response = requests.get(request_url, headers=headers, timeout=15)

            # Raise error for bad status codes (4xx, 5xx)
            response.raise_for_status()
            res = response.json()
            out = None

            for item in res: 
                if item.get("type") == "residential":
                    out = []
                    out.append(item.get("lat"))
                    out.append(item.get("lon"))
                    break
           
            if out == None:
                if len(res) == 0:
                    return None
                if res[0]:
                    out = []
                    out.append(res[0].get("lat"))
                    out.append(item.get("lon"))


            # print(out)
            return out 

            

        except Exception as e:
            print(request_url)
            print(f"Error occurred: {e}")
        
        self.GetOSMGeolocation(block, street_name)

    def GetOnemapGeolocation(self, block: str, street_name: str,) -> Dict[str, Any]:
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
        request_url = f"{ONEMAP_SEARCH_URL}?{urlencode(params)}"

        def fetch_data():
            while True:
                try:
                    print(request_url)
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
                        print(f"No geocoding result found for address: {search_val}")
                    return results
                except Exception:
                    print(f"Retrying block {block} street_name {street_name}...")
                    sleep(0.5)
        try:
            data = fetch_data()
        except Exception:
            print(f"Retrying block {block} street_name {street_name}...")
            sleep(0.5)
            data = fetch_data()

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
        

    def euclidean_distance(self, lat1, lon1, lat2, lon2):
        """
        Calculate Euclidean distance between two points
        given their latitude and longitude.
        """
        return math.sqrt((lat2 - lat1)**2 + (lon2 - lon1)**2)
    
