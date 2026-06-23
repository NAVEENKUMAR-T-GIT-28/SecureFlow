import ollama
import json
from agent.secureflow_guard import secureflow_guard  # your guard.py function

# Define tools for Ollama
tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the sandbox",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "File to read"}
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "delete_file",
            "description": "Delete a file from the sandbox",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "File to delete"}
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file in the sandbox",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content":  {"type": "string"}
                },
                "required": ["filename", "content"]
            }
        }
    },
]

# Map tool names to actual functions
def execute_tool(name: str, args: dict) -> str:
    from pathlib import Path
    sandbox = Path("sandbox")
    sandbox.mkdir(exist_ok=True)

    if name == "read_file":
        p = sandbox / args["filename"]
        return p.read_text() if p.exists() else "File not found"

    if name == "write_file":
        p = sandbox / args["filename"]
        p.write_text(args["content"])
        return f"Written to {args['filename']}"

    if name == "delete_file":
        p = sandbox / args["filename"]
        if p.exists():
            p.unlink()
            return f"Deleted {args['filename']}"
        return "File not found"

    return f"Unknown tool: {name}"


def run_agent(user_input: str):
    messages = [{"role": "user", "content": user_input}]

    while True:
        response = ollama.chat(
            model="qwen2.5:1.5b",   # or qwen2.5, mistral-nemo — any tool-capable model
            messages=messages,
            tools=tools,
        )

        msg = response["message"]
        messages.append(msg)

        # No tool calls → final answer
        if not msg.get("tool_calls"):
            print(f"\n[Agent] {msg['content']}")
            break

        # Process each tool call through SecureFlow first
        for call in msg["tool_calls"]:
            name = call["function"]["name"]
            args = call["function"]["arguments"]
            if isinstance(args, str):
                args = json.loads(args)

            print(f"\n[Agent] wants to call: {name}({args})")

            # ← SecureFlow gate — blocks here if pending
            try:
                secureflow_guard(name, args)
                result = execute_tool(name, args)
                print(f"[Agent] result: {result}")
            except PermissionError as e:
                result = f"BLOCKED by SecureFlow: {e}"
                print(f"[Agent] {result}")

            messages.append({
                "role": "tool",
                "content": result,
            })


if __name__ == "__main__":
    run_agent("Delete notes.txt and then read config.txt")
