import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(CURRENT_DIR, "shared")
BACKEND_ROOT = os.path.join(CURRENT_DIR, "..")

sys.path.append(SHARED_DIR)
sys.path.append(BACKEND_ROOT)

from adapter_runner import start_import_adapter
import recommendation_scorer_service.MCDM.recommender as recommender_module
from recommendation_scorer_service.MCDM.recommender import run_recommendation

# Safety patch:
# recommender.py imports compute_scores but later calls compute_score(...)
# This avoids modifying the original recommender file.
if hasattr(recommender_module, "compute_scores") and not hasattr(recommender_module, "compute_score"):
    recommender_module.compute_score = recommender_module.compute_scores

start_import_adapter(
    queue_name="queue:recommendation",
    service_name="recommendation",
    handler=run_recommendation,
)