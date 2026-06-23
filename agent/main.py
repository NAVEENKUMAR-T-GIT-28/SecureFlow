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
