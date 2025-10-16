#!/usr/bin/env python3
import json
import os
import sys

def collect_candidates(tool_input):
    candidates = []
    for key in ("file_path", "paths"):
        value = tool_input.get(key)
        if isinstance(value, str):
            candidates.append(value)
        elif isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, str))
    return candidates

def main():
    root = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    candidates = collect_candidates(tool_input)
    violations = []

    for candidate in candidates:
        if not candidate:
            continue
        real_path = candidate if os.path.isabs(candidate) else os.path.join(root, candidate)
        real_path = os.path.realpath(real_path)
        if not real_path.startswith(root + os.sep):
            violations.append(candidate)

    if violations:
        message = f"Writes must stay inside project root {root}. Offending: {violations}"
        print(message, file=sys.stderr)
        sys.exit(2)

    reference_root = os.path.join(root, "reference") + os.sep
    for candidate in candidates:
        if not candidate:
            continue
        real_path = candidate if os.path.isabs(candidate) else os.path.join(root, candidate)
        real_path = os.path.realpath(real_path)
        if real_path.startswith(reference_root):
            print("Reference is read-only; copy into workspace/notes/ before editing.", file=sys.stderr)
            sys.exit(2)

    sys.exit(0)

if __name__ == "__main__":
    main()
