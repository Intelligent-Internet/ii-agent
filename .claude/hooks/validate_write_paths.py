#!/usr/bin/env python3
"""
Path validation hook used by the Codex pipeline.

The hook receives Claude tool invocation metadata on stdin and blocks write
actions that would touch forbidden locations.  We extend the default guard to
explicitly deny any attempt to recreate the legacy `src/ii_agent` tree now that
the project has pivoted fully to the Scribe architecture.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Iterable, List


def _normalize_paths(raw: object) -> List[str]:
    """Return a list of filesystem paths encoded in the tool input payload."""
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return [p for p in raw if isinstance(p, str)]
    return []


def _is_within_root(root: str, candidate: str) -> bool:
    """Check whether *candidate* resolves to a location under *root*."""
    try:
        resolved = os.path.realpath(candidate)
    except (FileNotFoundError, OSError):
        # If the path does not exist yet, resolve its parent directory.
        resolved = os.path.realpath(os.path.join(os.path.dirname(candidate), "."))
    root_resolved = os.path.realpath(root)
    return resolved == root_resolved or resolved.startswith(root_resolved + os.sep)


def _fails_guard(root: str, paths: Iterable[str]) -> List[str]:
    """Collect all forbidden paths among *paths*."""
    violations: List[str] = []
    for path in paths:
        if not path:
            continue
        if not _is_within_root(root, path):
            violations.append(path)
            continue
        # Special guard: prevent recreation of the legacy ii-agent tree.
        guard_prefix = os.path.join(root, "src", "ii_agent") + os.sep
        bridge_prefix = os.path.join(root, "adapters", "ii_bridge") + os.sep
        real = os.path.realpath(path)
        if real.startswith(os.path.realpath(guard_prefix)) or real.startswith(os.path.realpath(bridge_prefix)):
            violations.append(path)
    return violations


def main() -> int:
    payload = json.load(sys.stdin)
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    project_root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    # Only gate write-like operations.
    write_tools = {"Write", "Edit", "MultiEdit"}
    if tool not in write_tools:
        return 0

    candidates = _normalize_paths(
        tool_input.get("file_path") or tool_input.get("paths")
    )
    violations = _fails_guard(project_root, candidates)
    if not violations:
        return 0

    message = (
        "Legacy agent namespace is removed. Implement under scribe_core/ or scribe_agents/. "
        f"Blocked paths: {', '.join(sorted(set(violations)))}"
    )
    print(message, file=sys.stderr)
    return 2  # Signal to Claude Code to deny the write.


if __name__ == "__main__":
    sys.exit(main())
