"""
scripts/refresh_resale.py
=========================
Monthly resale price data refresh.
Run manually or schedule as a cron job.

Cron example (runs at 2am on the 1st of each month):
    0 2 1 * * cd /path/to/hdb-backend && python scripts/refresh_resale.py

What it does:
  1. Downloads the latest resale_prices.csv from data.gov.sg
  2. Replaces the existing file
  3. Reloads SQLite with fresh data (last 24 months only)
  4. Logs the refresh timestamp
"""

import sys
import json
import time
import urllib.request
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR   = Path(__file__).parent.parent / "data"
DATASET_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"


def refresh():
    print("[refresh] Starting monthly resale data refresh…")

    # ── Step 1: Poll for download URL ─────────────────────────────────────────
    poll_url = (
        f"https://api-open.data.gov.sg/v1/public/api/datasets/"
        f"{DATASET_ID}/poll-download"
    )
    url = None
    for attempt in range(10):
        try:
            req = urllib.request.Request(
                poll_url, headers={"User-Agent": "HDB-Recommender-Refresh/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            url = (data.get("data", {}).get("url")
                   or data.get("data", {}).get("downloadUrl"))
            if url:
                break
        except Exception as e:
            print(f"[refresh] Poll attempt {attempt+1} failed: {e}")
        time.sleep(3)

    if not url:
        print("[refresh] ✗ Could not retrieve download URL. Aborting.")
        sys.exit(1)

    # ── Step 2: Download to temp file ─────────────────────────────────────────
    tmp_path  = DATA_DIR / "resale_prices_new.csv"
    dest_path = DATA_DIR / "resale_prices.csv"

    print(f"[refresh] Downloading from {url[:80]}…")
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "HDB-Recommender-Refresh/1.0"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            content = resp.read()
        tmp_path.write_bytes(content)
        print(f"[refresh] Downloaded {len(content)/1024:.0f} KB")
    except Exception as e:
        print(f"[refresh] ✗ Download failed: {e}")
        sys.exit(1)

    # ── Step 3: Replace existing file ─────────────────────────────────────────
    if dest_path.exists():
        backup = DATA_DIR / "resale_prices_backup.csv"
        dest_path.rename(backup)
        print(f"[refresh] Previous file backed up to {backup.name}")

    tmp_path.rename(dest_path)
    print(f"[refresh] ✓ resale_prices.csv updated.")

    # ── Step 4: Reload SQLite ─────────────────────────────────────────────────
    from db.loader import load_resale_csv
    count = load_resale_csv()
    print(f"[refresh] ✓ SQLite reloaded with {count:,} rows.")
    print("[refresh] Refresh complete.")


if __name__ == "__main__":
    refresh()
