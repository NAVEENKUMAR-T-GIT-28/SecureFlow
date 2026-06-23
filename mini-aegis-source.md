# Mini-AEGIS Project Structure and Source Code

This document contains the complete folder structure and full source code of the **Mini-AEGIS** human-in-the-loop tool-call approval prototype.

---

## 1. Folder Structure

```text
naveen-agent-gaurd/
├── README.md
├── agent/
│   ├── guard.py
│   ├── main.py
│   └── tools.py
├── gateway/
│   ├── app.py
│   ├── rules.json
│   └── templates/
│       └── index.html
└── sandbox/
    └── notes.txt (created during run)
```

---

## 2. Source Code Files

### [README.md](file:///c:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/README.md)
```markdown
# Agent-Gaurd

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
mini-aegis/
├── gateway/
│   ├── app.py        # Flask server — /check, /check/{id}, /decide/{id}, /log
│   └── rules.json    # One rule per tool: allow | block | pending
│
├── agent/
│   ├── main.py       # CLI loop
│   ├── guard.py      # require_approval() — the polling client
│   └── tools.py      # read_file / write_file / delete_file
│
├── sandbox/          # The only folder tools are allowed to touch
└── README.md
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

### [gateway/rules.json](file:///c:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/gateway/rules.json)
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

### [gateway/app.py](file:///c:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/gateway/app.py)
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

### [gateway/templates/index.html](file:///c:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/gateway/templates/index.html)
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mini-AEGIS Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0f172a;
            --glass-bg: rgba(30, 41, 59, 0.7);
            --glass-border: rgba(255, 255, 255, 0.1);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-green: #10b981;
            --accent-green-hover: #059669;
            --accent-red: #ef4444;
            --accent-red-hover: #dc2626;
        }

        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, rgba(37, 99, 235, 0.15) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(139, 92, 246, 0.15) 0px, transparent 50%);
            background-attachment: fixed;
            color: var(--text-primary);
            margin: 0;
            padding: 2rem;
            min-height: 100vh;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
        }

        .header {
            text-align: center;
            margin-bottom: 3rem;
        }

        .header h1 {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #60a5fa, #a78bfa);
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .header p {
            color: var(--text-secondary);
            font-size: 1.1rem;
        }

        .empty-state {
            text-align: center;
            padding: 4rem 2rem;
            background: var(--glass-bg);
            border: 1px solid var(--glass-border);
            border-radius: 1rem;
            backdrop-filter: blur(10px);
            color: var(--text-secondary);
            transition: all 0.3s ease;
        }

        .requests-list {
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        .request-card {
            background: var(--glass-bg);
            border: 1px solid var(--glass-border);
            border-radius: 1rem;
            padding: 1.5rem;
            backdrop-filter: blur(10px);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            animation: slideIn 0.4s ease-out forwards;
        }

        @keyframes slideIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .request-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        }

        .request-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 1rem;
        }

        .tool-name {
            font-size: 1.25rem;
            font-weight: 600;
            color: #e2e8f0;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .badge {
            font-size: 0.75rem;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            background: rgba(245, 158, 11, 0.2);
            color: #fcd34d;
            border: 1px solid rgba(245, 158, 11, 0.3);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 600;
        }

        .arguments-box {
            background: rgba(0, 0, 0, 0.2);
            border-radius: 0.5rem;
            padding: 1rem;
            margin-bottom: 1.5rem;
            font-family: monospace;
            font-size: 0.9rem;
            color: #cbd5e1;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }

        .actions {
            display: flex;
            gap: 1rem;
        }

        .btn {
            flex: 1;
            padding: 0.75rem 1.5rem;
            border-radius: 0.5rem;
            font-weight: 600;
            font-size: 1rem;
            border: none;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 0.5rem;
        }

        .btn-allow {
            background-color: var(--accent-green);
            color: white;
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.2);
        }

        .btn-allow:hover {
            background-color: var(--accent-green-hover);
            transform: translateY(-1px);
            box-shadow: 0 0 20px rgba(16, 185, 129, 0.4);
        }

        .btn-block {
            background-color: transparent;
            color: var(--accent-red);
            border: 1px solid var(--accent-red);
        }

        .btn-block:hover {
            background-color: rgba(239, 68, 68, 0.1);
        }
        
        .timestamp {
            font-size: 0.8rem;
            color: var(--text-secondary);
        }
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>Mini-AEGIS</h1>
            <p>Approval Dashboard</p>
        </header>

        <div id="requests-container" class="requests-list">
            <!-- Content populated by JS -->
            <div class="empty-state">
                <p>Loading pending requests...</p>
            </div>
        </div>
    </div>

    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <script>
        const container = document.getElementById('requests-container');
        let currentChecks = new Map(); // Store current state to avoid unnecessary re-renders

        function renderChecks(checks) {
            // Prevent blinking by checking if the data actually changed
            const newKeys = checks.map(c => c.check_id).join(',');
            const oldKeys = Array.from(currentChecks.keys()).join(',');
            
            if (newKeys === oldKeys && checks.length === currentChecks.size) {
                return; // Data hasn't changed, skip re-rendering
            }

            if (checks.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-bottom: 1rem; opacity: 0.5;">
                            <path d="M22 11.08V12a10 10 10 0 1 1-5.93-9.14"></path>
                            <polyline points="22 4 12 14.01 9 11.01"></polyline>
                        </svg>
                        <p>No pending requests right now.</p>
                        <p style="font-size: 0.9rem; margin-top: 0.5rem;">Agent is running smoothly.</p>
                    </div>
                `;
                currentChecks.clear();
                return;
            }

            currentChecks.clear();
            checks.forEach(c => currentChecks.set(c.check_id, c));

            let html = '';
            checks.forEach(check => {
                const timeStr = new Date(check.timestamp).toLocaleTimeString();
                const argsStr = JSON.stringify(check.arguments, null, 2);
                
                html += `
                    <div class="request-card" id="check-${check.check_id}">
                        <div class="request-header">
                            <div class="tool-name">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
                                </svg>
                                ${check.tool}
                            </div>
                            <span class="badge">PENDING</span>
                        </div>
                        
                        <div class="arguments-box">${argsStr}</div>
                        
                        <div class="request-header" style="margin-bottom: 1.5rem;">
                            <span class="timestamp">Requested at ${timeStr} • ID: ${check.check_id}</span>
                        </div>

                        <div class="actions">
                            <button class="btn btn-block" onclick="decide('${check.check_id}', 'block')">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                                Reject
                            </button>
                            <button class="btn btn-allow" onclick="decide('${check.check_id}', 'allow')">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
                                Allow Action
                            </button>
                        </div>
                    </div>
                `;
            });
            
            container.innerHTML = html;
        }

        async function fetchPending() {
            try {
                const response = await fetch('/pending');
                const checks = await response.json();
                renderChecks(checks);
            } catch (error) {
                console.error("Failed to fetch pending requests:", error);
            }
        }

        async function decide(checkId, decision) {
            // Optimistic UI update
            const card = document.getElementById(`check-${checkId}`);
            if (card) {
                card.style.opacity = '0.5';
                card.style.pointerEvents = 'none';
            }

            try {
                await fetch(`/decide/${checkId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        decision: decision,
                        reason: decision === 'block' ? 'Rejected via Dashboard UI' : ''
                    })
                });
                // Fetch immediately to update UI
                fetchPending();
            } catch (error) {
                console.error("Failed to submit decision:", error);
                if (card) {
                    card.style.opacity = '1';
                    card.style.pointerEvents = 'auto';
                }
                alert("Failed to submit decision. Check console.");
            }
        }

        // Initial fetch
        fetchPending();

        // Connect to Socket.IO for real-time updates
        const socket = io();
        socket.on('checks_updated', (checks) => {
            renderChecks(checks);
        });
    </script>
</body>
</html>
```

---

### [agent/main.py](file:///c:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/agent/main.py)
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
from tools import read_file, write_file, delete_file

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

### [agent/guard.py](file:///c:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/agent/guard.py)
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
POLL_INTERVAL = 2       # seconds between polls
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

### [agent/tools.py](file:///c:/Users/navee/Downloads/mini-aegis/naveen-agent-gaurd/agent/tools.py)
```python
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
```
