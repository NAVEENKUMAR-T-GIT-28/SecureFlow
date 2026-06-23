# SecureFlow Project Structure and Source Code

This document contains the complete folder structure and full source code of the **SecureFlow** human-in-the-loop tool-call approval prototype.

---

## 1. Folder Structure

```text
naveen-agent-gaurd/
├── .gitignore
├── README.md
├── update_docs.py
├── migrate.py
├── secureflow/
│   ├── sandbox/
│   │   ├── cli.py
│   │   └── config.txt
│   ├── agent/
│   │   ├── ollama_agent.py
│   │   ├── tools.json
│   │   └── tool_registry.py
│   └── firewall/
│       ├── app.py
│       ├── guard.py
│       ├── secureflow_guard.py
│       ├── rules.json
│       └── templates/
│           └── index.html
└── docs/
    ├── api.md
    ├── architecture.md
    └── security-model.md
```

---

## 2. Source Code Files

### [.gitignore](file:///C:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/.gitignore)
```text
# Python files
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# Environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Virtualenv
.venv/
venv/

# Sandbox directory containing transient agent files
sandbox/

# IDE files
.vscode/
.idea/
*.suo
*.ntvs*
*.njsproj
*.sln
*.swp
```

---

### [README.md](file:///C:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/README.md)
```markdown
# SecureFlow

A minimal prototype of the **agent firewall / human-in-the-loop approval** pattern.
Two processes talk over HTTP; a human can intercept and approve or deny tool calls
in real time.

---

## Install

```bash
pip install flask requests
```

---

## Run (three terminals)

### Terminal 1 — Gateway
```bash
python gateway/app.py
# → Gateway running on http://localhost:9000
# → Loaded rules.json: read_file=allow, write_file=allow, delete_file=pending
```

### Terminal 2 — Agent
```bash
python agent/main.py
# → Mini-AEGIS Agent ready. Type 'help' for commands.
```

### Terminal 3 — Human reviewer (curl or any HTTP client)
This terminal is only needed when an action is held for approval.

---

## Example session

**Terminal 2 (Agent):**
```
> write notes.txt Hello from Mini-AEGIS
[Agent] Checking with gateway...
Written 19 bytes to notes.txt.

> read notes.txt
[Agent] Checking with gateway...
Hello from Mini-AEGIS

> delete notes.txt
[Agent] Checking with gateway...
[Agent] PENDING — check_id=7f3a1b2c. Waiting for human decision
        (POST http://localhost:9000/decide/7f3a1b2c) ...
```
*(Agent is blocked here — nothing happens yet.)*

**Terminal 3 (Human — approve the deletion):**
```bash
curl -X POST http://localhost:9000/decide/7f3a1b2c \
     -H "Content-Type: application/json" \
     -d '{"decision": "allow"}'
```

**Terminal 2 (Agent, within ~2 seconds):**
```
[Agent] delete_file OK: notes.txt deleted.
Deleted notes.txt.
```

**To deny instead:**
```bash
curl -X POST http://localhost:9000/decide/7f3a1b2c \
     -H "Content-Type: application/json" \
     -d '{"decision": "block", "reason": "looks risky, denying"}'
```

---

## Audit log

```bash
curl http://localhost:9000/log
```
Returns every check ever made, in order, with its final decision.

---

## Changing the rules (no code edits needed)

Edit `gateway/rules.json` and restart the Gateway.

| `delete_file` rule | Effect                                              |
|--------------------|-----------------------------------------------------|
| `"pending"`        | Agent waits; human must approve or deny (default)  |
| `"block"`          | Every delete attempt fails immediately              |
| `"allow"`          | Deletes run without any approval check              |

> **Rule loading:** Rules are read **once at startup**. Restart the Gateway
> after editing `rules.json` to pick up changes.

---

## File layout

```
Agent-gaurd/
├── secureflow/
│   ├── sandbox/              # The only folder tools are allowed to touch
│   │   ├── cli.py
│   │   └── config.txt
│   ├── agent/
│   │   ├── ollama_agent.py   # Conversational LLM chat loop
│   │   ├── tool_registry.py  # Executes tools
│   │   └── tools.json        # Tool schemas loaded by the LLM
│   └── firewall/
│       ├── app.py            # Flask server — /check, /check/{id}, /decide/{id}, /log
│       ├── rules.json        # One rule per tool: allow | block | pending
│       └── secureflow_guard.py # Interceptor client that polls for approval
│
├── docs/
│   ├── architecture.md
│   ├── api.md
│   └── security-model.md
│
├── README.md
├── update_docs.py
├── migrate.py
└── .gitignore
```

---

## Gateway endpoints

| Method | Path                  | Called by | Purpose                              |
|--------|-----------------------|-----------|--------------------------------------|
| POST   | `/check`              | Agent     | Submit a tool call for approval      |
| GET    | `/check/{check_id}`   | Agent     | Poll for a pending decision          |
| POST   | `/decide/{check_id}`  | Human     | Approve or deny a held action        |
| GET    | `/log`                | Anyone    | View the full audit trail            |

---

## What this is NOT

This is a learning prototype. It intentionally omits:
authentication, a real database, a UI dashboard, ML/anomaly detection,
retry queues, HTTPS, and anything else that belongs in a production tool.
```

---

### [secureflow/agent/ollama_agent.py](file:///C:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/secureflow/agent/ollama_agent.py)
```python
import ollama
import json
import sys
from pathlib import Path

# Add project root to sys.path so the IDE linter and Python both resolve paths correctly
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from firewall.secureflow_guard import secureflow_guard
from agent.tool_registry import execute, REGISTRY

TOOLS_PATH = Path(__file__).parent / "tools.json"

# ── load tool schemas from tools.json ────────────────────────────────────────
def load_tools() -> list:
    data = json.loads(TOOLS_PATH.read_text())
    schemas = []
    for t in data["tools"]:
        schemas.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": {
                    "type": "object",
                    "properties": t["parameters"],
                    "required": t.get("required", [])
                }
            }
        })
    return schemas

# ── build system prompt dynamically from registry ────────────────────────────
def build_system_prompt() -> str:
    tool_names = ", ".join(REGISTRY.keys())
    return f"""You are a helpful assistant with access to a sandbox file system.
You have these tools available: {tool_names}.
Use them only when the user asks for something file-related.
For normal conversation or questions unrelated to files, reply directly without using any tools.
When you use a tool, briefly explain what you did and what you found."""

# ── single turn: handles all tool calls until LLM gives a text answer ────────
def chat_turn(messages: list, tools: list) -> str:
    while True:
        response = ollama.chat(
            model="qwen2.5:1.5b",
            messages=messages,
            tools=tools,
        )

        msg = response["message"]
        messages.append(msg)

        if not msg.get("tool_calls"):
            return msg["content"]

        for call in msg["tool_calls"]:
            name = call["function"]["name"]
            args = call["function"]["arguments"]
            if isinstance(args, str):
                args = json.loads(args)

            print(f"\n  🔧 Tool selected: {name}({args})")

            try:
                secureflow_guard(name, args)
                result = execute(name, args)       # ← dynamic, no if/else
                print(f"  ✓  {result}")
            except PermissionError as e:
                result = f"Action blocked by SecureFlow: {e}"
                print(f"  ✗  {result}")

            messages.append({
                "role": "tool",
                "content": result,
                "name": name,
            })

# ── main chat loop ────────────────────────────────────────────────────────────
def main():
    tools = load_tools()       # loaded fresh at startup from tools.json

    print("╔══════════════════════════════════════════════╗")
    print("║   SecureFlow Chat  (type 'exit' to quit)     ║")
    print(f"║   Tools loaded: {len(tools)} from tools.json            ║")
    print("╚══════════════════════════════════════════════╝\n")

    messages = [{"role": "system", "content": build_system_prompt()}]

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("Assistant: Goodbye!")
            break

        messages.append({"role": "user", "content": user_input})
        answer = chat_turn(messages, tools)
        print(f"\nAssistant: {answer}")

if __name__ == "__main__":
    main()
```

---

### [secureflow/agent/tools.json](file:///C:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/secureflow/agent/tools.json)
```json
{
  "tools": [
    {
      "name": "read_file",
      "description": "Read the contents of a file from the sandbox",
      "parameters": {
        "filename": {"type": "string", "description": "Name of the file to read"}
      },
      "required": ["filename"]
    },
    {
      "name": "write_file",
      "description": "Write or create a file in the sandbox with given content",
      "parameters": {
        "filename": {"type": "string"},
        "content":  {"type": "string", "description": "Content to write"}
      },
      "required": ["filename", "content"]
    },
    {
      "name": "delete_file",
      "description": "Permanently delete a file from the sandbox",
      "parameters": {
        "filename": {"type": "string", "description": "Name of the file to delete"}
      },
      "required": ["filename"]
    },
    {
      "name": "list_files",
      "description": "List all files currently in the sandbox",
      "parameters": {},
      "required": []
    }
  ]
}
```

---

### [secureflow/agent/tool_registry.py](file:///C:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/secureflow/agent/tool_registry.py)
```python
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
```

---

### [secureflow/sandbox/cli.py](file:///C:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/secureflow/sandbox/cli.py)
```python
"""
Mini-AEGIS Agent — Process A

A simple REPL that understands these commands:

  read   <filename>
  write  <filename> <content ...>
  delete <filename>
  help
  quit  (or exit, q)

Run this in one terminal after starting the Gateway in another:
  python gateway/app.py    ← Terminal 1
  python agent/main.py     ← Terminal 2
"""

import sys
from agent.tools import read_file, write_file, delete_file

HELP = """
Commands:
  read   <filename>              — read a file from sandbox/
  write  <filename> <content>    — write content to sandbox/<filename>
  delete <filename>              — delete sandbox/<filename>  (requires approval)
  help                           — show this message
  quit / exit / q                — exit
"""

def run():
    print("Mini-AEGIS Agent ready. Type 'help' for commands.")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Agent] Bye.")
            sys.exit(0)

        if not line:
            continue

        parts = line.split(maxsplit=2)
        cmd = parts[0].lower()

        if cmd in ("quit", "exit", "q"):
            print("[Agent] Bye.")
            sys.exit(0)

        elif cmd == "help":
            print(HELP)

        elif cmd == "read":
            if len(parts) < 2:
                print("[Agent] Usage: read <filename>")
                continue
            filename = parts[1]
            print(f"[Agent] Checking with gateway...")
            output = read_file(filename)
            print(output)

        elif cmd == "write":
            if len(parts) < 3:
                print("[Agent] Usage: write <filename> <content>")
                continue
            filename = parts[1]
            content = parts[2]
            print(f"[Agent] Checking with gateway...")
            output = write_file(filename, content)
            print(output)

        elif cmd == "delete":
            if len(parts) < 2:
                print("[Agent] Usage: delete <filename>")
                continue
            filename = parts[1]
            print(f"[Agent] Checking with gateway...")
            output = delete_file(filename)
            print(output)

        else:
            print(f"[Agent] Unknown command: {cmd!r}. Type 'help' for commands.")


if __name__ == "__main__":
    run()
```

---

### [secureflow/sandbox/config.txt](file:///C:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/secureflow/sandbox/config.txt)
```text
this file has configuration info
```

---

### [secureflow/firewall/app.py](file:///C:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/secureflow/firewall/app.py)
```python
"""
Mini-AEGIS Gateway — Process B
Runs as a standalone Flask server on localhost:9000.
The Agent (Process A) POSTs to /check before running any tool.
A human approves/denies via POST /decide/{check_id}.
Rules are loaded from rules.json at startup (restart to pick up changes).
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, request, jsonify, abort, render_template
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

RULES_PATH = Path(__file__).parent / "rules.json"

# ── In-memory state ──────────────────────────────────────────────────────────
# pending_checks: { check_id -> { tool, arguments, decision, reason, timestamp } }
pending_checks: dict = {}
# audit_log: list of every check ever made (grows forever, fine for a prototype)
audit_log: list = []

# ── Rule loading ─────────────────────────────────────────────────────────────
# Loaded once at startup; restart the gateway to pick up changes to rules.json.
def load_rules() -> dict:
    with open(RULES_PATH) as f:
        data = json.load(f)
    rules_map = {r["tool"]: r["decision"] for r in data.get("rules", [])}
    default = data.get("default_decision", "allow")
    return {"map": rules_map, "default": default}

RULES = load_rules()

def print_rules_summary():
    lines = [f"  {tool}={decision}" for tool, decision in RULES["map"].items()]
    lines.append(f"  default={RULES['default']}")
    print("Loaded rules.json:\n" + "\n".join(lines))

# ── Helpers ───────────────────────────────────────────────────────────────────
def make_check_id() -> str:
    return uuid.uuid4().hex[:8]

def log_entry(check_id: str, tool: str, arguments: dict, decision: str, reason: str = ""):
    audit_log.append({
        "check_id": check_id,
        "tool": tool,
        "arguments": arguments,
        "decision": decision,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
    })

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/check")
def check():
    """Called by the Agent before running any tool."""
    body = request.get_json(force=True)
    tool = body.get("tool", "")
    arguments = body.get("arguments", {})

    decision = RULES["map"].get(tool, RULES["default"])
    check_id = make_check_id()

    print(f"[Gateway] /check  tool={tool} args={arguments}  → {decision}  (id={check_id})")

    if decision == "allow":
        log_entry(check_id, tool, arguments, "allow")
        return jsonify({"decision": "allow"})

    if decision == "block":
        reason = f"{tool} is not permitted"
        log_entry(check_id, tool, arguments, "block", reason)
        return jsonify({"decision": "block", "reason": reason})

    if decision == "pending":
        pending_checks[check_id] = {
            "tool": tool,
            "arguments": arguments,
            "decision": "pending",
            "reason": "",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }
        # Add a pending entry to the log now; it will be updated when decided.
        log_entry(check_id, tool, arguments, "pending")
        socketio.emit("checks_updated", _get_pending_list())
        return jsonify({"decision": "pending", "check_id": check_id})

    # Shouldn't happen, but be safe
    return jsonify({"decision": "block", "reason": "unrecognised rule decision"}), 500


@app.get("/check/<check_id>")
def poll_check(check_id: str):
    """Polled by the Agent while waiting for a human decision."""
    entry = pending_checks.get(check_id)
    if entry is None:
        return jsonify({"error": "unknown check_id"}), 404

    resp: dict = {"decision": entry["decision"]}
    if entry["reason"]:
        resp["reason"] = entry["reason"]
    return jsonify(resp)


@app.post("/decide/<check_id>")
def decide(check_id: str):
    """Called manually by a human (curl/Postman) to approve or deny."""
    entry = pending_checks.get(check_id)
    if entry is None:
        return jsonify({"error": "unknown check_id"}), 404

    body = request.get_json(force=True)
    decision = body.get("decision", "")
    if decision not in ("allow", "block"):
        return jsonify({"error": "decision must be 'allow' or 'block'"}), 400

    reason = body.get("reason", "")
    entry["decision"] = decision
    entry["reason"] = reason

    # Update the audit log entry that was created as "pending"
    for rec in reversed(audit_log):
        if rec["check_id"] == check_id and rec["decision"] == "pending":
            rec["decision"] = decision
            rec["reason"] = reason
            break

    print(f"[Gateway] /decide  check_id={check_id}  → {decision}  reason={reason!r}")
    socketio.emit("checks_updated", _get_pending_list())
    return jsonify({"check_id": check_id, "decision": decision})


@app.get("/log")
def get_log():
    """Returns the full audit trail — every check ever made."""
    return jsonify(audit_log)


@app.get("/")
def dashboard():
    """Serves the web dashboard UI."""
    return render_template("index.html")


@app.get("/pending")
def get_pending():
    """Returns a list of all currently pending checks for the UI."""
    return jsonify(_get_pending_list())

def _get_pending_list():
    pending_list = []
    for cid, data in pending_checks.items():
        if data["decision"] == "pending":
            check_obj = data.copy()
            check_obj["check_id"] = cid
            pending_list.append(check_obj)
    
    # Sort by timestamp descending (newest first)
    pending_list.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return pending_list


if __name__ == "__main__":
    print("Mini-AEGIS Gateway running on http://localhost:9000")
    print_rules_summary()
    socketio.run(app, host="0.0.0.0", port=9000, debug=False, allow_unsafe_werkzeug=True)
```

---

### [secureflow/firewall/guard.py](file:///C:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/secureflow/firewall/guard.py)
```python
"""
Mini-AEGIS Guard — the require_approval() function.

Every tool calls this before touching the filesystem.
It either returns immediately (allow/block) or enters a polling loop
waiting for a human decision (pending).
"""

import time
import requests

GATEWAY_URL = "http://localhost:9000"
POLL_INTERVAL = 10       # seconds between polls
POLL_TIMEOUT  = 120     # seconds before we give up and block


class Allowed:
    pass

class Blocked:
    def __init__(self, reason: str):
        self.reason = reason


def require_approval(tool_name: str, arguments: dict) -> Allowed | Blocked:
    """
    Ask the Gateway whether this tool call is permitted.

    Returns Allowed() if the call may proceed, Blocked(reason) otherwise.
    Blocks the current thread if the Gateway returns 'pending', polling
    every POLL_INTERVAL seconds until a human decides or POLL_TIMEOUT elapses.
    """
    try:
        resp = requests.post(
            f"{GATEWAY_URL}/check",
            json={"tool": tool_name, "arguments": arguments},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return Blocked(f"Gateway unreachable: {exc}")

    decision = data.get("decision")

    if decision == "allow":
        return Allowed()

    if decision == "block":
        return Blocked(data.get("reason", "blocked by gateway"))

    if decision == "pending":
        check_id = data["check_id"]
        print(f"[Agent] PENDING — check_id={check_id}. Waiting for human decision "
              f"(POST http://localhost:9000/decide/{check_id}) ...")

        deadline = time.time() + POLL_TIMEOUT
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            try:
                poll = requests.get(
                    f"{GATEWAY_URL}/check/{check_id}",
                    timeout=10,
                )
                poll.raise_for_status()
                pdata = poll.json()
            except Exception as exc:
                return Blocked(f"Gateway unreachable during poll: {exc}")

            pdecision = pdata.get("decision")
            if pdecision == "allow":
                return Allowed()
            if pdecision == "block":
                return Blocked(pdata.get("reason", "denied by reviewer"))
            # still "pending" → keep looping

        return Blocked(f"approval timed out after {POLL_TIMEOUT}s")

    return Blocked(f"unexpected gateway decision: {decision!r}")
```

---

### [secureflow/firewall/secureflow_guard.py](file:///C:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/secureflow/firewall/secureflow_guard.py)
```python
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
```

---

### [secureflow/firewall/rules.json](file:///C:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/secureflow/firewall/rules.json)
```json
{
  "rules": [
    { "tool": "read_file",   "decision": "allow" },
    { "tool": "write_file",  "decision": "allow" },
    { "tool": "delete_file", "decision": "pending" }
  ],
  "default_decision": "allow"
}
```

---

### [secureflow/firewall/templates/index.html](file:///C:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/secureflow/firewall/templates/index.html)
```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>AEGIS Approval Center</title>

<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">

<style>
:root{
    --bg:#f5f7fa;
    --card:#ffffff;
    --border:#e5e7eb;

    --text:#111827;
    --muted:#6b7280;

    --success:#16a34a;
    --success-hover:#15803d;

    --danger:#dc2626;
    --danger-hover:#b91c1c;

    --warning-bg:#fef3c7;
    --warning-text:#92400e;

    --shadow:
        0 1px 3px rgba(0,0,0,.05),
        0 8px 24px rgba(0,0,0,.04);
}

*{
    margin:0;
    padding:0;
    box-sizing:border-box;
}

body{
    font-family:'Inter',sans-serif;
    background:var(--bg);
    color:var(--text);
    min-height:100vh;
    padding:40px 24px;
}

.container{
    max-width:1000px;
    margin:auto;
}

/* HEADER */

.header{
    margin-bottom:40px;
}

.header h1{
    font-size:2.2rem;
    font-weight:800;
    color:var(--text);
    margin-bottom:8px;
}

.header p{
    color:var(--muted);
    font-size:1rem;
}

/* EMPTY STATE */

.empty-state{
    background:var(--card);
    border:1px solid var(--border);
    border-radius:18px;
    padding:60px 40px;
    text-align:center;
    box-shadow:var(--shadow);
}

.empty-state svg{
    color:var(--success);
    margin-bottom:20px;
}

.empty-state h3{
    font-size:1.2rem;
    margin-bottom:8px;
}

.empty-state p{
    color:var(--muted);
}

/* LIST */

.requests-list{
    display:flex;
    flex-direction:column;
    gap:20px;
}

/* CARD */

.request-card{
    background:var(--card);
    border:1px solid var(--border);
    border-radius:18px;
    padding:24px;
    box-shadow:var(--shadow);
    transition:.2s ease;
}

.request-card:hover{
    transform:translateY(-2px);
}

.request-header{
    display:flex;
    justify-content:space-between;
    align-items:center;
    margin-bottom:18px;
}

.tool-name{
    display:flex;
    align-items:center;
    gap:10px;
    font-size:1.15rem;
    font-weight:700;
}

.tool-name svg{
    color:#374151;
}

/* BADGE */

.badge{
    padding:8px 14px;
    border-radius:999px;
    background:var(--warning-bg);
    color:var(--warning-text);
    font-size:.75rem;
    font-weight:700;
    letter-spacing:.05em;
    text-transform:uppercase;
}

/* ARGUMENT BOX */

.arguments-title{
    font-size:.9rem;
    font-weight:600;
    color:var(--muted);
    margin-bottom:10px;
}

.arguments-box{
    background:#f9fafb;
    border:1px solid #e5e7eb;
    border-radius:12px;
    padding:16px;
    font-family:monospace;
    font-size:.9rem;
    overflow-x:auto;
    white-space:pre-wrap;
    color:#374151;
    margin-bottom:18px;
}

.timestamp{
    font-size:.85rem;
    color:var(--muted);
    margin-bottom:20px;
}

/* ACTIONS */

.actions{
    display:flex;
    gap:12px;
}

.btn{
    flex:1;
    height:48px;
    border-radius:12px;
    cursor:pointer;
    font-size:.95rem;
    font-weight:600;
    display:flex;
    justify-content:center;
    align-items:center;
    gap:8px;
    transition:.2s ease;
}

/* REJECT */

.btn-block{
    background:white;
    color:var(--danger);
    border:1px solid var(--danger);
}

.btn-block:hover{
    background:#fef2f2;
}

/* APPROVE */

.btn-allow{
    background:var(--success);
    color:white;
    border:none;
}

.btn-allow:hover{
    background:var(--success-hover);
}

@media(max-width:700px){

    .request-header{
        flex-direction:column;
        align-items:flex-start;
        gap:12px;
    }

    .actions{
        flex-direction:column;
    }
}
</style>
</head>

<body>

<div class="container">

    <header class="header">
        <h1>AEGIS Approval Center</h1>
        <p>Human-in-the-loop security approvals</p>
    </header>

    <div id="requests-container" class="requests-list">

        <div class="empty-state">
            <svg width="50" height="50" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>

            <h3>No Pending Requests</h3>
            <p>All agent actions have been reviewed.</p>
        </div>

    </div>

</div>

<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>

<script>
const container = document.getElementById('requests-container');
let currentChecks = new Map();

function renderChecks(checks){

    const newKeys = checks.map(c => c.check_id).join(',');
    const oldKeys = Array.from(currentChecks.keys()).join(',');

    if(newKeys === oldKeys && checks.length === currentChecks.size){
        return;
    }

    if(checks.length === 0){

        container.innerHTML = `
        <div class="empty-state">
            <svg width="50" height="50" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
            </svg>

            <h3>No Pending Requests</h3>
            <p>All agent actions have been reviewed.</p>
        </div>
        `;

        currentChecks.clear();
        return;
    }

    currentChecks.clear();

    checks.forEach(c=>{
        currentChecks.set(c.check_id,c);
    });

    let html = '';

    checks.forEach(check=>{

        const timeStr =
            new Date(check.timestamp)
            .toLocaleTimeString();

        const argsStr =
            JSON.stringify(
                check.arguments,
                null,
                2
            );

        html += `
        <div class="request-card" id="check-${check.check_id}">

            <div class="request-header">

                <div class="tool-name">

                    <svg width="20" height="20" viewBox="0 0 24 24"
                    fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                    </svg>

                    ${check.tool}

                </div>

                <span class="badge">Pending</span>

            </div>

            <div class="arguments-title">
                Request Arguments
            </div>

            <div class="arguments-box">
${argsStr}
            </div>

            <div class="timestamp">
                Requested at ${timeStr} • ID: ${check.check_id}
            </div>

            <div class="actions">

                <button class="btn btn-block"
                    onclick="decide('${check.check_id}','block')">

                    Reject

                </button>

                <button class="btn btn-allow"
                    onclick="decide('${check.check_id}','allow')">

                    Approve

                </button>

            </div>

        </div>
        `;
    });

    container.innerHTML = html;
}

async function fetchPending(){

    try{

        const response =
            await fetch('/pending');

        const checks =
            await response.json();

        renderChecks(checks);

    }catch(error){

        console.error(error);

    }
}

async function decide(checkId, decision){

    const card =
        document.getElementById(
            `check-${checkId}`
        );

    if(card){

        card.style.opacity = '.5';
        card.style.pointerEvents = 'none';

    }

    try{

        await fetch(`/decide/${checkId}`,{

            method:'POST',

            headers:{
                'Content-Type':'application/json'
            },

            body:JSON.stringify({
                decision
            })

        });

        fetchPending();

    }catch(error){

        console.error(error);

    }
}

fetchPending();

const socket = io();

socket.on('checks_updated',(checks)=>{
    renderChecks(checks);
});
</script>

</body>
</html>
```

---
