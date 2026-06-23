from pathlib import Path

SANDBOX = Path(__file__).parent.parent / "sandbox"
SANDBOX.mkdir(exist_ok=True)

# Each function name must match the "name" field in tools.json exactly
def read_file(filename: str, **_) -> str:
    p = SANDBOX / filename
    return p.read_text(encoding="utf-8") if p.exists() else f"[ERROR] File not found: {filename}"

def write_file(filename: str, content: str, **_) -> str:
    p = SANDBOX / filename
    p.write_text(content, encoding="utf-8")
    return f"Written {len(content)} bytes to {filename}"

def delete_file(filename: str, **_) -> str:
    p = SANDBOX / filename
    if p.exists():
        p.unlink()
        return f"Successfully deleted {filename}"
    return f"[ERROR] File not found: {filename}"

def list_files(**_) -> str:
    files = list(SANDBOX.iterdir())
    if not files:
        return "Sandbox is empty — no files."
    return "Files in sandbox:\n" + "\n".join(f"  • {f.name}" for f in files)

# Registry maps name → function
REGISTRY = {
    "read_file":   read_file,
    "write_file":  write_file,
    "delete_file": delete_file,
    "list_files":  list_files,
}

def execute(name: str, args: dict) -> str:
    fn = REGISTRY.get(name)
    if fn is None:
        return f"[ERROR] Unknown tool: {name}"
    return fn(**args)
