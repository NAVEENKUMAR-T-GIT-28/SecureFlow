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
