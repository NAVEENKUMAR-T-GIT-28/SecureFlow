"""
Mini-AEGIS Agent tools.

Each tool:
  1. Calls guard.require_approval() first — always.
  2. Only touches the filesystem if the result is Allowed.
  3. All filesystem access is confined to the sandbox/ directory.
"""

from pathlib import Path
from guard import require_approval, Allowed

# All tools are sandboxed to this directory. Attempts to escape via '../' etc.
# are rejected.
SANDBOX = Path(__file__).parent.parent / "sandbox"
SANDBOX.mkdir(exist_ok=True)


def _resolve_safe(filename: str) -> Path | None:
    """Return an absolute path inside SANDBOX, or None if the filename escapes."""
    target = (SANDBOX / filename).resolve()
    try:
        target.relative_to(SANDBOX.resolve())
        return target
    except ValueError:
        return None


def read_file(filename: str) -> str:
    result = require_approval("read_file", {"filename": filename})
    if not isinstance(result, Allowed):
        return f"[BLOCKED] {result.reason}"

    path = _resolve_safe(filename)
    if path is None:
        return "[ERROR] Path escapes sandbox."
    if not path.exists():
        return f"[ERROR] File not found: {filename}"

    content = path.read_text()
    print(f"[Agent] read_file OK: {filename} ({len(content)} bytes)")
    return content


def write_file(filename: str, content: str) -> str:
    result = require_approval("write_file", {"filename": filename})
    if not isinstance(result, Allowed):
        return f"[BLOCKED] {result.reason}"

    path = _resolve_safe(filename)
    if path is None:
        return "[ERROR] Path escapes sandbox."

    path.write_text(content)
    print(f"[Agent] write_file OK: {filename} ({len(content)} bytes written)")
    return f"Written {len(content)} bytes to {filename}."


def delete_file(filename: str) -> str:
    result = require_approval("delete_file", {"filename": filename})
    if not isinstance(result, Allowed):
        return f"[BLOCKED] {result.reason}"

    path = _resolve_safe(filename)
    if path is None:
        return "[ERROR] Path escapes sandbox."
    if not path.exists():
        return f"[ERROR] File not found: {filename}"

    path.unlink()
    print(f"[Agent] delete_file OK: {filename} deleted.")
    return f"Deleted {filename}."
