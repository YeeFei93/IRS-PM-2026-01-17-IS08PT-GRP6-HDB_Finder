import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(CURRENT_DIR, "shared")
BACKEND_ROOT = os.path.join(CURRENT_DIR, "..")

sys.path.append(SHARED_DIR)
sys.path.append(BACKEND_ROOT)

from adapter_runner import start_import_adapter
from recommendation_scorer_service.feedback_store import (
    get_model_evaluations,
    record_feedback,
)


def handle_recommendation_feedback(payload: dict) -> dict:
    action = str(payload.get("action", "record")).strip().lower()

    if action == "get_model_evaluations":
        return {"evaluations": get_model_evaluations()}

    resale_flat_id = str(payload.get("resale_flat_id", "")).strip()
    recommendation = str(payload.get("recommendation", "")).strip()
    event = str(payload.get("event", "")).strip().lower()

    return record_feedback(
        resale_flat_id=resale_flat_id,
        recommendation=recommendation,
        event=event,
    )


start_import_adapter(
    queue_name="queue:recommendation_feedback",
    service_name="recommendation_feedback",
    handler=handle_recommendation_feedback,
)
