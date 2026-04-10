import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(CURRENT_DIR, "shared")
BACKEND_ROOT = os.path.join(CURRENT_DIR, "..")

sys.path.append(SHARED_DIR)
sys.path.append(BACKEND_ROOT)

from adapter_runner import start_import_adapter
from recommendation_scorer_service.recommender import run_recommendation

start_import_adapter(
    queue_name="queue:recommendation",
    service_name="recommendation",
    handler=run_recommendation,
)