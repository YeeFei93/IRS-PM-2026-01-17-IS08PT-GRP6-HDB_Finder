import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(CURRENT_DIR, "shared")
BACKEND_ROOT = os.path.join(CURRENT_DIR, "..")

sys.path.append(SHARED_DIR)
sys.path.append(BACKEND_ROOT)

from adapter_runner import start_import_adapter
from estate_finder_service.queries import get_flats_for_estate, get_top_flats_across_estates


def handle_flat_lookup(payload: dict) -> dict:
    """
    Payload fields (all optional except estate/estates):
      estate      str         — single HDB town (single-estate mode)
      estates     list[str]   — multiple HDB towns (cross-estate mode)
      ftype       str         — flat type, e.g. '4 ROOM' or 'any'
      floor_pref  str         — 'low' | 'mid' | 'high' | 'any'
      budget      float       — buyer's effective budget for proximity sort
      min_lease   int         — minimum remaining lease years
      months      int         — lookback window (default 14)
      limit       int         — max records to return (default 20)
    """
    ftype      = payload.get("ftype", "any")
    floor_pref = payload.get("floor_pref", "any")
    budget     = float(payload.get("budget", 0))
    min_lease  = int(payload.get("min_lease", 0))
    months     = int(payload.get("months", 14))
    limit      = int(payload.get("limit", 20))

    estates = payload.get("estates")
    if estates and isinstance(estates, list) and len(estates) > 0:
        flats = get_top_flats_across_estates(
            estates=estates, ftype=ftype, floor_pref=floor_pref,
            budget=budget, min_lease=min_lease, months=months, limit=limit,
        )
        return {"estates": estates, "flats": flats}
    else:
        estate = payload.get("estate", "")
        flats = get_flats_for_estate(
            estate=estate, ftype=ftype, floor_pref=floor_pref,
            budget=budget, min_lease=min_lease, months=months, limit=limit,
        )
        return {"estate": estate, "flats": flats}


start_import_adapter(
    queue_name="queue:flat_lookup",
    service_name="flat_lookup",
    handler=handle_flat_lookup,
)
