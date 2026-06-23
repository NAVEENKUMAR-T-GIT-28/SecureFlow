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
