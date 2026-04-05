"""
db/loader.py
============
Load raw data files (CSV + GeoJSON) into SQLite.
Called once at startup; also exposed as /api/refresh endpoint.

Supported file formats per dataset:
  - resale_prices.csv        (from data.gov.sg — required, ~50MB CSV)
  - hawker_centres.geojson   (from data.gov.sg)
  - mrt_stations.geojson     (from data.gov.sg)
  - hospitals.geojson        (pre-built, included in repo)
  - parks.geojson            (from data.gov.sg)
  - schools.csv              (MOE General Information of Schools CSV)
                              OR schools.geojson if you have a pre-geocoded version

Schools CSV note:
  The MOE schools CSV has school_name, address, postal_code but NO lat/lng.
  The loader geocodes each school via the OneMap Search API automatically.
  Geocoded results are stored in SQLite so this only runs once.
  If OneMap is unreachable, schools are skipped gracefully (non-fatal).
"""

import csv
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

from db.connection import get_conn, init_schema
from geo.distances import init_geo

DATA_DIR = Path(__file__).parent.parent / "data"


def init_db():
    """
    Full startup initialisation:
    1. Create schema
    2. Load CSV + GeoJSON if tables are empty
    3. Load GeoJSON features into memory for fast distance lookups
    """
    init_schema()
    _load_if_empty()
    init_geo()   # Load GeoJSON files into geo/distances.py memory cache


def _load_if_empty():
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM resale_transactions").fetchone()[0]
        if count == 0:
            print("[db] No resale data found — loading from CSV…")
            load_resale_csv()
        else:
            print(f"[db] Resale transactions: {count:,} rows already loaded.")

        hcount = conn.execute("SELECT COUNT(*) FROM hawker_centres").fetchone()[0]
        mcount = conn.execute("SELECT COUNT(*) FROM malls").fetchone()[0]
        if hcount == 0 or mcount == 0:
            load_all_geojson()
        else:
            print(f"[db] GeoJSON already loaded ({hcount} hawkers, {mcount} malls).")


# ── Resale CSV ────────────────────────────────────────────────────────────────

def load_resale_csv(months_window: int = 24) -> int:
    """
    Load resale_prices.csv into resale_transactions table.
    Keeps only the last `months_window` months of data.
    Performs basic data quality checks.
    Returns number of rows inserted.
    """
    csv_path = DATA_DIR / "resale_prices.csv"
    if not csv_path.exists():
        print(f"[loader] WARNING: {csv_path} not found. Run scripts/download_data.py first.")
        return 0

    # Calculate cutoff month
    cutoff = (datetime.now() - timedelta(days=months_window * 30.5)).strftime("%Y-%m")

    required_cols = {"town", "flat_type", "storey_range", "floor_area_sqm",
                     "resale_price", "month"}
    rows_inserted = 0
    skipped = 0

    with get_conn() as conn:
        conn.execute("DELETE FROM resale_transactions")   # Full reload

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cols = set(reader.fieldnames or [])

            if not required_cols.issubset(cols):
                missing = required_cols - cols
                raise ValueError(f"CSV missing required columns: {missing}")

            batch = []
            for row in reader:
                if row.get("month", "") < cutoff:
                    continue

                try:
                    price = float(row["resale_price"])
                    area  = float(row.get("floor_area_sqm", 0) or 0)
                except ValueError:
                    skipped += 1
                    continue

                if price <= 0 or area < 0:
                    skipped += 1
                    continue

                batch.append((
                    row["month"],
                    row["town"].strip().upper(),
                    row["flat_type"].strip().upper(),
                    row.get("block", "").strip(),
                    row.get("street_name", "").strip(),
                    row.get("storey_range", "").strip(),
                    area,
                    row.get("flat_model", "").strip(),
                    _safe_int(row.get("lease_commence_date")),
                    row.get("remaining_lease", "").strip(),
                    price,
                ))

                if len(batch) >= 1000:
                    conn.executemany("""
                        INSERT INTO resale_transactions
                        (month, town, flat_type, block, street_name, storey_range,
                         floor_area_sqm, flat_model, lease_commence_date,
                         remaining_lease, resale_price)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """, batch)
                    rows_inserted += len(batch)
                    batch = []

            if batch:
                conn.executemany("""
                    INSERT INTO resale_transactions
                    (month, town, flat_type, block, street_name, storey_range,
                     floor_area_sqm, flat_model, lease_commence_date,
                     remaining_lease, resale_price)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, batch)
                rows_inserted += len(batch)

        conn.execute(
            "INSERT INTO refresh_log (dataset, rows_loaded) VALUES (?, ?)",
            ("resale_transactions", rows_inserted)
        )

    print(f"[loader] Resale CSV: {rows_inserted:,} rows loaded, {skipped} skipped.")
    return rows_inserted


# ── GeoJSON files ─────────────────────────────────────────────────────────────

def load_all_geojson():
    """Load all amenity files into their respective SQLite tables."""
    _load_hawkers()
    _load_mrt()
    _load_hospitals()
    _load_parks()
    _load_schools()   # handles both schools.csv and schools.geojson
    _load_malls()     # malls.geojson (pre-built, 110 malls)


def _extract_point(feat: dict) -> tuple[float, float] | None:
    """Extract (lat, lng) from a GeoJSON feature. Returns None if not a point."""
    geom   = feat.get("geometry", {})
    coords = geom.get("coordinates", [])
    gtype  = geom.get("type", "")
    if gtype == "Point" and len(coords) >= 2:
        return float(coords[1]), float(coords[0])   # GeoJSON is [lng, lat]
    return None


def _load_hawkers():
    path = DATA_DIR / "hawker_centres.geojson"
    if not path.exists():
        print(f"[loader] hawker_centres.geojson not found — skipping.")
        return
    feats = json.loads(path.read_text()).get("features", [])
    rows  = []
    for f in feats:
        pt = _extract_point(f)
        if pt is None:
            continue
        p = f.get("properties", {})
        name = p.get("NAME") or p.get("name") or p.get("HAWKER_CENTRE_NO") or "Unknown"
        rows.append((name, p.get("ADDRESS_MYENV", ""), pt[0], pt[1]))
    with get_conn() as conn:
        conn.execute("DELETE FROM hawker_centres")
        conn.executemany(
            "INSERT INTO hawker_centres (name, address, lat, lng) VALUES (?,?,?,?)", rows)
    print(f"[loader] Hawker centres: {len(rows)} loaded.")


def _load_mrt():
    path = DATA_DIR / "mrt_stations.geojson"
    if not path.exists():
        print(f"[loader] mrt_stations.geojson not found — skipping.")
        return
    feats = json.loads(path.read_text()).get("features", [])
    rows  = []
    for f in feats:
        pt = _extract_point(f)
        if pt is None:
            continue
        p    = f.get("properties", {})
        name = p.get("STN_NAME") or p.get("name") or p.get("NAME") or "Unknown"
        code = p.get("STN_NO") or p.get("stn_code") or ""
        line = p.get("COLOR") or p.get("line") or ""
        rows.append((name, code, line, pt[0], pt[1]))
    with get_conn() as conn:
        conn.execute("DELETE FROM mrt_stations")
        conn.executemany(
            "INSERT INTO mrt_stations (name, code, line, lat, lng) VALUES (?,?,?,?,?)", rows)
    print(f"[loader] MRT stations: {len(rows)} loaded.")


def _load_hospitals():
    path = DATA_DIR / "hospitals.geojson"
    if not path.exists():
        print(f"[loader] hospitals.geojson not found — skipping.")
        return
    feats = json.loads(path.read_text()).get("features", [])
    rows  = []
    for f in feats:
        pt = _extract_point(f)
        if pt is None:
            continue
        p    = f.get("properties", {})
        name = p.get("name") or p.get("NAME") or "Unknown"
        rows.append((name, p.get("address", ""), pt[0], pt[1]))
    with get_conn() as conn:
        conn.execute("DELETE FROM hospitals")
        conn.executemany(
            "INSERT INTO hospitals (name, address, lat, lng) VALUES (?,?,?,?)", rows)
    print(f"[loader] Hospitals: {len(rows)} loaded.")


def _load_parks():
    path = DATA_DIR / "parks.geojson"
    if not path.exists():
        print(f"[loader] parks.geojson not found — skipping.")
        return
    feats = json.loads(path.read_text()).get("features", [])
    rows  = []
    for f in feats:
        pt = _extract_point(f)
        if pt is None:
            # For parks with polygon geometry, use first coordinate
            geom = f.get("geometry", {})
            try:
                if geom["type"] == "Polygon":
                    lng, lat = geom["coordinates"][0][0]
                    pt = (lat, lng)
                elif geom["type"] == "MultiPolygon":
                    lng, lat = geom["coordinates"][0][0][0]
                    pt = (lat, lng)
            except (KeyError, IndexError, TypeError):
                continue
        if pt is None:
            continue
        p    = f.get("properties", {})
        name = p.get("NAME") or p.get("name") or "Park"
        rows.append((name, pt[0], pt[1]))
    with get_conn() as conn:
        conn.execute("DELETE FROM parks")
        conn.executemany(
            "INSERT INTO parks (name, lat, lng) VALUES (?,?,?)", rows)
    print(f"[loader] Parks: {len(rows)} loaded.")


def _load_schools():
    """
    Load schools from either:
      a) schools.csv  — MOE General Information of Schools (no lat/lng, geocodes via OneMap)
      b) schools.geojson — pre-geocoded GeoJSON (used if CSV is absent)
    CSV takes priority when both are present.
    """
    csv_path  = DATA_DIR / "schools.csv"
    json_path = DATA_DIR / "schools.geojson"

    if csv_path.exists():
        _load_schools_from_csv(csv_path)
    elif json_path.exists():
        _load_schools_from_geojson(json_path)
    else:
        print("[loader] Neither schools.csv nor schools.geojson found — skipping.")


def _load_schools_from_csv(csv_path: Path):
    """
    Load MOE schools CSV.
    Expected columns (from data.gov.sg MOE dataset):
      school_name, address, postal_code, [optional: lat/lng or latitude/longitude]

    If lat/lng columns are absent, geocodes each school via OneMap Search API.
    Schools that fail geocoding are skipped.
    """
    rows = []
    geocoded = 0
    skipped  = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = [col.lower().strip() for col in (reader.fieldnames or [])]

        # Detect if lat/lng columns already exist in this CSV
        has_lat = any(col in fieldnames for col in ("latitude", "lat"))
        has_lng = any(col in fieldnames for col in ("longitude", "lng"))
        has_coords = has_lat and has_lng

        if has_coords:
            print("[loader] Schools CSV: lat/lng columns detected — skipping geocoding.")
        else:
            print("[loader] Schools CSV: no lat/lng — will geocode via OneMap.")

        for row in reader:
            # Normalise keys to lowercase
            row = {k.lower().strip(): v for k, v in row.items()}
            name    = (row.get("school_name") or row.get("name") or "").strip()
            address = (row.get("address") or "").strip()
            postal  = (row.get("postal_code") or row.get("postcode") or "").strip()

            if not name:
                skipped += 1
                continue

            if has_coords:
                try:
                    lat = float(row.get("latitude") or row.get("lat"))
                    lng = float(row.get("longitude") or row.get("lng"))
                    rows.append((name, address, lat, lng))
                except (TypeError, ValueError):
                    skipped += 1
            else:
                # Geocode via OneMap — use postal code for accuracy, fallback to address
                query = postal if postal else address
                coords = _onemap_geocode(query)
                if coords:
                    rows.append((name, address, coords[0], coords[1]))
                    geocoded += 1
                    # Polite delay to avoid rate limiting (OneMap allows ~250 req/min)
                    time.sleep(0.25)
                else:
                    skipped += 1

    with get_conn() as conn:
        conn.execute("DELETE FROM schools")
        conn.executemany(
            "INSERT INTO schools (name, address, lat, lng) VALUES (?,?,?,?)", rows)

    print(f"[loader] Schools (CSV): {len(rows)} loaded"
          + (f", {geocoded} geocoded via OneMap" if geocoded else "")
          + (f", {skipped} skipped" if skipped else "") + ".")


def _load_schools_from_geojson(json_path: Path):
    """Fallback: load a pre-geocoded schools.geojson file."""
    feats = json.loads(json_path.read_text()).get("features", [])
    rows  = []
    for feat in feats:
        pt = _extract_point(feat)
        if pt is None:
            continue
        p    = feat.get("properties", {})
        name = p.get("school_name") or p.get("NAME") or p.get("name") or "School"
        rows.append((name, p.get("address", ""), pt[0], pt[1]))
    with get_conn() as conn:
        conn.execute("DELETE FROM schools")
        conn.executemany(
            "INSERT INTO schools (name, address, lat, lng) VALUES (?,?,?,?)", rows)
    print(f"[loader] Schools (GeoJSON): {len(rows)} loaded.")


def _onemap_geocode(query: str) -> tuple[float, float] | None:
    """
    Geocode a Singapore address or postal code via OneMap Search API.
    Returns (lat, lng) or None if not found / API unavailable.
    No API key required for the public search endpoint.
    """
    try:
        encoded = urllib.parse.quote(query)
        url = (
            f"https://www.onemap.gov.sg/api/common/elastic/search"
            f"?searchVal={encoded}&returnGeom=Y&getAddrDetails=N"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "HDB-Recommender/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        results = data.get("results", [])
        if results:
            return float(results[0]["LATITUDE"]), float(results[0]["LONGITUDE"])
    except Exception:
        pass
    return None


def _load_malls():
    path = DATA_DIR / "malls.geojson"
    if not path.exists():
        print(f"[loader] malls.geojson not found — skipping.")
        return
    feats = json.loads(path.read_text()).get("features", [])
    rows  = []
    for f in feats:
        pt = _extract_point(f)
        if pt is None:
            continue
        p    = f.get("properties", {})
        name = p.get("name") or p.get("NAME") or "Mall"
        rows.append((name, pt[0], pt[1]))
    with get_conn() as conn:
        conn.execute("DELETE FROM malls")
        conn.executemany(
            "INSERT INTO malls (name, lat, lng) VALUES (?,?,?)", rows)
    print(f"[loader] Shopping malls: {len(rows)} loaded.")


def _safe_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
