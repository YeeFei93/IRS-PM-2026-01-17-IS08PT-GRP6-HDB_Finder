# pip install requests folium
# python your_script.py

import json
import requests
import time
import math
import folium
from folium.plugins import MarkerCluster
from difflib import SequenceMatcher

INPUT_FILE = "malls.geojson"
OUTPUT_FILE = "malls_cleaned.geojson"
MAP_OUTPUT = "map_verification.html"

# -----------------------------
# Haversine distance (km)
# -----------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)

    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))


# -----------------------------
# Name similarity check
# -----------------------------
def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# -----------------------------
# Geocode using Nominatim
# -----------------------------
def geocode(place):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{place} Singapore",
        "format": "json",
        "limit": 1
    }

    headers = {
        "User-Agent": "geojson-validator"
    }

    response = requests.get(url, params=params, headers=headers)
    data = response.json()

    if len(data) == 0:
        return None

    return {
        "lat": float(data[0]["lat"]),
        "lon": float(data[0]["lon"]),
        "display_name": data[0]["display_name"]
    }


# -----------------------------
# Load GeoJSON
# -----------------------------
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    geojson = json.load(f)

features = geojson["features"]

# -----------------------------
# Initialize Map
# -----------------------------
m = folium.Map(location=[1.35, 103.82], zoom_start=12)
marker_cluster = MarkerCluster().add_to(m)

results = []

# -----------------------------
# Process each mall
# -----------------------------
for feature in features:
    name = feature["properties"].get("name")

    lon, lat = feature["geometry"]["coordinates"]  # GeoJSON format

    print(f"\nChecking: {name}")

    # Save original
    original_lat = lat
    original_lon = lon

    # Quick sanity check (Singapore bounds)
    if not (1.1 <= lat <= 1.5 and 103.6 <= lon <= 104.1):
        print("  ⚠️ Out of Singapore bounds")

    # Geocode
    api_result = geocode(name)

    if api_result is None:
        print("  ❌ No API result")
        continue

    api_lat = api_result["lat"]
    api_lon = api_result["lon"]
    api_name = api_result["display_name"]

    # Distance
    dist = haversine(lat, lon, api_lat, api_lon)

    # Name similarity
    sim_score = similarity(name, api_name)

    # Status logic
    if dist < 0.2 and sim_score > 0.7:
        status = "OK"
    elif dist < 1 and sim_score > 0.5:
        status = "SUSPICIOUS"
    else:
        status = "WRONG"

    print(f"  Distance: {dist:.3f} km")
    print(f"  Name similarity: {sim_score:.2f}")
    print(f"  Status: {status}")

    # -----------------------------
    # Auto-correct WRONG entries
    # -----------------------------
    if status == "WRONG":
        print("  🔧 Updating coordinates")
        feature["geometry"]["coordinates"] = [api_lon, api_lat]

    # -----------------------------
    # Visualization
    # -----------------------------
    if status == "OK":
        color = "green"
    elif status == "SUSPICIOUS":
        color = "orange"
    else:
        color = "red"

    # Original point (blue)
    folium.Marker(
        location=[original_lat, original_lon],
        popup=f"{name} (Original)\n{dist:.2f} km",
        tooltip=name,
        icon=folium.Icon(color="blue")
    ).add_to(marker_cluster)

    # Corrected/API point
    folium.Marker(
        location=[api_lat, api_lon],
        popup=f"{name} (Corrected)\n{dist:.2f} km\n{status}",
        tooltip=name,
        icon=folium.Icon(color=color)
    ).add_to(marker_cluster)

    # Draw line if mismatch
    if dist > 0.2:
        folium.PolyLine(
            locations=[
                [original_lat, original_lon],
                [api_lat, api_lon]
            ],
            color="red",
            weight=2
        ).add_to(m)

    results.append({
        "name": name,
        "original": (original_lat, original_lon),
        "api": (api_lat, api_lon),
        "distance_km": dist,
        "similarity": sim_score,
        "status": status
    })

    # Respect API rate limits
    time.sleep(1)


# -----------------------------
# Save cleaned GeoJSON
# -----------------------------
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(geojson, f, indent=2)

print("\n✅ Cleaned GeoJSON saved:", OUTPUT_FILE)


# -----------------------------
# Save map
# -----------------------------
m.save(MAP_OUTPUT)
print("🗺️ Map saved:", MAP_OUTPUT)


# -----------------------------
# Summary
# -----------------------------
ok = sum(1 for r in results if r["status"] == "OK")
sus = sum(1 for r in results if r["status"] == "SUSPICIOUS")
wrong = sum(1 for r in results if r["status"] == "WRONG")

print("\n📊 Summary:")
print(f"OK: {ok}")
print(f"SUSPICIOUS: {sus}")
print(f"WRONG (corrected): {wrong}")