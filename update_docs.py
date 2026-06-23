import os
from pathlib import Path

# Files to include in the document
FILES = [
    ".gitignore",
    "README.md",
    "agent/ollama_agent.py",
    "agent/tools.json",
    "agent/tool_registry.py",
    "agent/sandbox/cli.py",
    "agent/sandbox/config.txt",
    "firewall/app.py",
    "firewall/guard.py",
    "firewall/secureflow_guard.py",
    "firewall/rules.json",
    "firewall/templates/index.html",
]

def generate_tree():
    return """naveen-agent-gaurd/
├── .gitignore
├── README.md
├── agent/
│   ├── ollama_agent.py
│   ├── tools.json
│   ├── tool_registry.py
│   └── sandbox/
│       ├── cli.py
│       └── config.txt
├── firewall/
│   ├── app.py
│   ├── guard.py
│   ├── secureflow_guard.py
│   ├── rules.json
│   └── templates/
│       └── index.html
└── docs/
    ├── api.md
    ├── architecture.md
    └── security-model.md"""

def get_language(filename):
    ext = Path(filename).suffix
    if ext == '.py': return 'python'
    if ext == '.json': return 'json'
    if ext == '.html': return 'html'
    if ext == '.md': return 'markdown'
    return 'text'

def main():
    root = Path(__file__).parent.resolve()
    out_lines = []
    out_lines.append("# SecureFlow Project Structure and Source Code\n")
    out_lines.append("This document contains the complete folder structure and full source code of the **SecureFlow** human-in-the-loop tool-call approval prototype.\n")
    out_lines.append("---\n")
    out_lines.append("## 1. Folder Structure\n")
    out_lines.append("```text\n" + generate_tree() + "\n```\n")
    out_lines.append("---\n")
    out_lines.append("## 2. Source Code Files\n")

    for file_rel in FILES:
        p = root / file_rel
        if not p.exists():
            continue
        
        # Format URI properly for clickable links
        file_uri = f"file:///{str(p).replace(chr(92), '/')}"
        out_lines.append(f"### [{file_rel}]({file_uri})")
        out_lines.append(f"```{get_language(file_rel)}")
        
        try:
            # Read exact file content
            content = p.read_text(encoding="utf-8").strip()
            out_lines.append(content)
        except Exception as e:
            out_lines.append(f"Error reading file: {e}")
            
        out_lines.append("```\n")
        out_lines.append("---\n")

    # Write to Seureflow.md
    target = root / "Seureflow.md"
    target.write_text("\n".join(out_lines), encoding="utf-8")
    print("Successfully updated Seureflow.md with the latest codebase!")

if __name__ == "__main__":
    main()
