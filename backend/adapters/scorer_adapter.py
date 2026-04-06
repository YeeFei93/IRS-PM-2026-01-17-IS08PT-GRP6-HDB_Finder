import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(CURRENT_DIR, "shared")
SERVICE_ROOT = os.path.join(CURRENT_DIR, "..", "recommendation_scorer_service")

sys.path.append(SHARED_DIR)
sys.path.append(SERVICE_ROOT)

from adapter_runner import start_import_adapter
from scorer import score_payload

start_import_adapter(
    queue_name="queue:scorer",
    service_name="scorer",
    handler=score_payload,
)
