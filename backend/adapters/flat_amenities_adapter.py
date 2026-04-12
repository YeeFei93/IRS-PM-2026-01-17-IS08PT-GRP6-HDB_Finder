import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(CURRENT_DIR, "shared")
BACKEND_ROOT = os.path.join(CURRENT_DIR, "..")

sys.path.append(SHARED_DIR)
sys.path.append(BACKEND_ROOT)

from adapter_runner import start_import_adapter
from estate_finder_service.queries import get_all_amenities_for_flat


def handle_flat_parks(payload: dict) -> dict:
    """
    Payload fields:
      block        str  — HDB block number, e.g. '101B'
      street_name  str  — street name, e.g. 'PUNGGOL FIELD'
    Returns:
      { block, street_name, parks, hawkers, mrts, schools, malls, hospitals }
      Each list item: { name, latitude, longitude, distance }
      Types not yet populated in the DB return empty lists.
    """
    block       = payload.get("block", "").strip().upper()
    street_name = payload.get("street_name", "").strip().upper()
    amenities   = get_all_amenities_for_flat(block, street_name)
    return {"block": block, "street_name": street_name, **amenities}


start_import_adapter(
    queue_name="queue:flat_amenities",
    service_name="flat_amenities",
    handler=handle_flat_parks,
)
