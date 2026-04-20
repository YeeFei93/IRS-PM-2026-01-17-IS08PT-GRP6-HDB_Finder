import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(CURRENT_DIR, "shared")
BACKEND_ROOT = os.path.join(CURRENT_DIR, "..")

sys.path.append(SHARED_DIR)
sys.path.append(BACKEND_ROOT)

from adapter_runner import start_import_adapter
from estate_finder_service.favourites_store import (
    list_favourites,
    remove_favourite,
    toggle_favourite,
)


def handle_favourites(payload: dict) -> dict:
    action = str(payload.get("action", "list")).strip().lower()
    resale_flat_id = str(payload.get("resale_flat_id", "")).strip()

    if action == "toggle":
        return toggle_favourite(resale_flat_id)
    if action == "remove":
        return remove_favourite(resale_flat_id)
    return list_favourites()


start_import_adapter(
    queue_name="queue:favourites",
    service_name="favourites",
    handler=handle_favourites,
)
