import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(CURRENT_DIR, "shared")
SERVICE_ROOT = os.path.join(CURRENT_DIR, "..", "eligibility_checker_service")

sys.path.append(SHARED_DIR)
sys.path.append(SERVICE_ROOT)

from adapter_runner import start_import_adapter
from eligibility import check_eligibility

start_import_adapter(
    queue_name="queue:eligibility",
    service_name="eligibility",
    handler=check_eligibility,
)