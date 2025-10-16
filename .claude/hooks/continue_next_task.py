#!/usr/bin/env python3
import json
import os
import sys

def load_queue(path):
    try:
        with open(path) as handle:
            return json.load(handle)
    except Exception:
        return {}

def update_queue(path, queue_data):
    try:
        with open(path, "w") as handle:
            json.dump(queue_data, handle)
    except Exception:
        pass

def main():
    root = os.environ.get("CLAUDE_PROJECT_DIR", "")
    queue_path = os.path.join(root, ".claude", "task_queue.json")
    try:
        _ = json.load(sys.stdin)
    except Exception:
        print(json.dumps({"decision": None}), end="")
        sys.exit(0)

    queue_data = load_queue(queue_path)
    queue = queue_data.get("queue", [])
    cursor = int(queue_data.get("cursor", 0))

    next_task = None
    if cursor < len(queue):
        next_task = queue[cursor]
        queue_data["cursor"] = cursor + 1
        update_queue(queue_path, queue_data)

    if next_task:
        reason = f"Continue with next task: {next_task}. Stay under 60% of context, then Stop again."
        print(json.dumps({"decision": "block", "reason": reason}), end="")
    else:
        print(json.dumps({"decision": None}), end="")

if __name__ == "__main__":
    main()
