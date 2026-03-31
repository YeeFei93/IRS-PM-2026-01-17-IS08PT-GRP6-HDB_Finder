"""
scripts/download_data.py
========================
First-time download of all data files into data/ directory.

Usage:
    python scripts/download_data.py

Downloads:
  - HDB Resale Prices CSV (data.gov.sg)
  - HDB Planning Area Boundaries GeoJSON (data.gov.sg)
  - Hawker Centres GeoJSON (data.gov.sg)
  - MRT Stations GeoJSON (data.gov.sg)

Hospitals GeoJSON is pre-built (hospitals.geojson already in data/).
Schools and Parks GeoJSON: download manually from data.gov.sg links below.
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── Dataset registry ──────────────────────────────────────────────────────────
# Format: (filename, dataset_id_or_url, description)
# data.gov.sg v2 download flow: poll endpoint → get download URL → fetch file

DATAGOV_DATASETS = {
    "resale_prices.csv": {
        "dataset_id": "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
        "description": "HDB Resale Flat Prices",
        "format": "csv",
    },
    "planning_areas.geojson": {
        "dataset_id": "d_4765db0e87b9c86336792efe8a1f7a66",
        "description": "Master Plan 2019 Planning Area Boundary",
        "format": "geojson",
    },
    "hawker_centres.geojson": {
        "dataset_id": "d_4a086da0a5553be1d89383cd90d07ebc",
        "description": "NEA Hawker Centres",
        "format": "geojson",
    },
    "mrt_stations.geojson": {
        "dataset_id": "d_5cb3563c5584bb533dfc3fbec97153e8",
        "description": "LTA MRT/LRT Stations",
        "format": "geojson",
    },
}


def poll_download_url(dataset_id: str, max_retries: int = 10) -> str | None:
    """
    data.gov.sg v2 API: poll the download endpoint until a URL is ready.
    Returns the file download URL or None on failure.
    """
    poll_url = (
        f"https://api-open.data.gov.sg/v1/public/api/datasets/"
        f"{dataset_id}/poll-download"
    )

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                poll_url,
                headers={"User-Agent": "HDB-Recommender/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())

            status = data.get("data", {}).get("status") or data.get("status")
            url    = (data.get("data", {}).get("url")
                      or data.get("url")
                      or data.get("data", {}).get("downloadUrl"))

            if url:
                return url

            if status in ("READY", "ready"):
                return url

            print(f"  Attempt {attempt+1}/{max_retries}: status={status}, waiting…")
            time.sleep(3)

        except Exception as e:
            print(f"  Poll error: {e}")
            time.sleep(3)

    return None


def download_file(url: str, dest_path: Path, description: str):
    """Download a file from URL to dest_path."""
    print(f"  Downloading {description}…")
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "HDB-Recommender/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read()
        dest_path.write_bytes(content)
        size_kb = len(content) / 1024
        print(f"  ✓ Saved to {dest_path} ({size_kb:.0f} KB)")
    except Exception as e:
        print(f"  ✗ Download failed: {e}")


def download_all():
    print("=" * 60)
    print("HDB Recommender — Data Downloader")
    print("=" * 60)

    for filename, meta in DATAGOV_DATASETS.items():
        dest = DATA_DIR / filename
        print(f"\n[{meta['description']}]")

        if dest.exists():
            size_kb = dest.stat().st_size / 1024
            print(f"  Already exists ({size_kb:.0f} KB). Delete to re-download.")
            continue

        print(f"  Polling data.gov.sg for dataset {meta['dataset_id']}…")
        url = poll_download_url(meta["dataset_id"])

        if url:
            download_file(url, dest, meta["description"])
        else:
            print(f"  ✗ Could not get download URL for {filename}.")
            print(f"    Manual download: https://data.gov.sg/datasets?resultId={meta['dataset_id']}")

    # ── Check for hospitals.geojson (manually built) ─────────────────────────
    hospitals_path = DATA_DIR / "hospitals.geojson"
    if hospitals_path.exists():
        print(f"\n[Hospitals GeoJSON] ✓ Already present.")
    else:
        print(f"\n[Hospitals GeoJSON] ✗ Not found.")
        print("  Run: python scripts/build_hospitals_geojson.py")

    print("\n" + "=" * 60)
    print("Download complete. Next steps:")
    print("  1. Verify files in data/ directory")
    print("  2. python main.py  (or uvicorn main:app)")
    print("  3. DB will be initialised automatically on first startup")
    print("=" * 60)


if __name__ == "__main__":
    download_all()
