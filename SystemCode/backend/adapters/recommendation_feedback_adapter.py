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
    set_feedback_state,
    sync_recommendation_snapshot,
)


def _parse_optional_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value

    clean = str(value).strip().lower()
    if clean in {"1", "true", "yes", "y", "on"}:
        return True
    if clean in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError("boolean fields must be true/false")


def handle_recommendation_feedback(payload: dict) -> dict:
    action = str(payload.get("action", "record")).strip().lower()

    if action == "get_model_evaluations":
        return {"evaluations": get_model_evaluations()}

    resale_flat_id = str(payload.get("resale_flat_id", "")).strip()
    recommendation = str(payload.get("recommendation", "")).strip() or None
    event = str(payload.get("event", "")).strip().lower()
    viewed = _parse_optional_bool(payload.get("viewed"))
    favourite = _parse_optional_bool(
        payload["favourite"] if "favourite" in payload else payload.get("favorite")
    )
    session_id = str(payload.get("session_id", "")).strip() or None
    recommendation_snapshot = payload.get("recommendation_snapshot")

    if action == "sync_recommendation_snapshot":
        return sync_recommendation_snapshot(
            recommendation=recommendation,
            session_id=session_id,
            recommendation_snapshot=recommendation_snapshot,
        )

    if action == "set_state" or viewed is not None or favourite is not None:
        return set_feedback_state(
            resale_flat_id=resale_flat_id,
            recommendation=recommendation,
            viewed=viewed,
            favourite=favourite,
            session_id=session_id,
            recommendation_snapshot=recommendation_snapshot,
        )

    return record_feedback(
        resale_flat_id=resale_flat_id,
        recommendation=recommendation,
        event=event,
        session_id=session_id,
        recommendation_snapshot=recommendation_snapshot,
    )


start_import_adapter(
    queue_name="queue:recommendation_feedback",
    service_name="recommendation_feedback",
    handler=handle_recommendation_feedback,
)
