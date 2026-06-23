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