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
