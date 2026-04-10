import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(CURRENT_DIR, "shared")
BACKEND_ROOT = os.path.join(CURRENT_DIR, "..")

sys.path.append(SHARED_DIR)
sys.path.append(BACKEND_ROOT)

from adapter_runner import start_import_adapter
from estate_finder_service.queries import get_flats_for_estate


def handle_flat_lookup(payload: dict) -> dict:
    """
    Payload fields (all optional except estate):
      estate      str   — HDB town name (uppercase)
      ftype       str   — flat type, e.g. '4 ROOM' or 'any'
      floor_pref  str   — 'low' | 'mid' | 'high' | 'any'
      budget      float — buyer's effective budget for proximity sort
      min_lease   int   — minimum remaining lease years
      months      int   — lookback window (default 14)
      limit       int   — max records to return (default 20)
    """
    flats = get_flats_for_estate(
        estate     = payload.get("estate", ""),
        ftype      = payload.get("ftype", "any"),
        floor_pref = payload.get("floor_pref", "any"),
        budget     = float(payload.get("budget", 0)),
        min_lease  = int(payload.get("min_lease", 0)),
        months     = int(payload.get("months", 14)),
        limit      = int(payload.get("limit", 20)),
    )
    return {"estate": payload.get("estate", ""), "flats": flats}


start_import_adapter(
    queue_name="queue:flat_lookup",
    service_name="flat_lookup",
    handler=handle_flat_lookup,
)
