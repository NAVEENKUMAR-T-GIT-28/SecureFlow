import sys
from pathlib import Path

# Add project root to sys.path to resolve imports correctly
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from firewall.guard import require_approval, Allowed, Blocked

def secureflow_guard(tool_name: str, arguments: dict):
    """
    Wrapper for secureflow / mini-aegis guard.
    Raises PermissionError if the action is blocked by the gateway.
    """
    result = require_approval(tool_name, arguments)
    if isinstance(result, Blocked):
        raise PermissionError(result.reason)
