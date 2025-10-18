#!/usr/bin/env python3
import json
import os
import re
import sys

def main():
    root = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    command = tool_input.get("command", "")

    if re.search(r"\bsudo\b", command):
        print("Dangerous command blocked (sudo).", file=sys.stderr)
        sys.exit(2)

    if re.search(r"\brm\s+-rf\s+/", command):
        print("Dangerous command blocked (rm -rf /).", file=sys.stderr)
        sys.exit(2)

    if re.search(r"\bchmod\s+777\b", command):
        print("Dangerous command blocked (chmod 777).", file=sys.stderr)
        sys.exit(2)

    if "src/ii_agent/" in command:
        print("II-Agent is read-only; implement in /scribe/**", file=sys.stderr)
        sys.exit(2)

    for abs_path in re.findall(r"\s(/[^ \t;]+)", command):
        real_path = os.path.realpath(abs_path)
        if not real_path.startswith(root + os.sep):
            print(f"Path {abs_path} escapes project root {root}.", file=sys.stderr)
            sys.exit(2)

    cd_match = re.search(r"\bcd\s+([^\s;]+)", command)
    if cd_match:
        target = cd_match.group(1)
        real_target = target if target.startswith("/") else os.path.join(root, target)
        real_target = os.path.realpath(real_target)
        if not real_target.startswith(root + os.sep):
            print(f"'cd {target}' would leave project root {root}.", file=sys.stderr)
            sys.exit(2)

    sys.exit(0)

if __name__ == "__main__":
    main()
