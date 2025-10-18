#!/usr/bin/env bash
set -euo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
NEXT_TASK="${1:-}"
# You can override the command with env CLAUDE_CMD
CLAUDE_CMD=${CLAUDE_CMD:-"claude --dangerously-skip-permission"}

if [ -n "$NEXT_TASK" ]; then
  echo "Starting new Claude session for next task: $NEXT_TASK" >&2
fi

# Start detached; adapt if your CLI supports session IDs or initial prompts
( cd "$ROOT" && eval "$CLAUDE_CMD" ) >/dev/null 2>&1 &
disown || true
