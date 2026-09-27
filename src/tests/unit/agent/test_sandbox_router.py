"""Unit tests for sandbox router helpers + endpoint guards.

The endpoint itself is small but it is the only place users access
sandbox files from the browser, and the path-validation helpers are
security-critical: a bug here would let a session owner read arbitrary
host paths if the sandbox base were ever changed.
"""

from __future__ import annotations

import pytest

from ii_agent.agents.sandboxes.router import (
    _is_path_within_root,
    _normalize_sandbox_path,
)


pytestmark = pytest.mark.unit


class TestNormalizeSandboxPath:
    @pytest.mark.parametrize(
        ("inp", "expected"),
        [
            ("/workspace/foo.txt", "/workspace/foo.txt"),
            ("workspace/foo.txt", "/workspace/foo.txt"),
            ("/workspace/./foo.txt", "/workspace/foo.txt"),
            ("/workspace//foo.txt", "/workspace/foo.txt"),
            ("/workspace/sub/../foo.txt", "/workspace/foo.txt"),
            (" /workspace/foo.txt ", "/workspace/foo.txt"),
            ("/", "/"),
            ("foo", "/foo"),
        ],
    )
    def test_normalises_inputs(self, inp: str, expected: str):
        assert _normalize_sandbox_path(inp) == expected

    def test_collapses_traversal_attempts(self):
        # After normpath, traversal beyond root collapses to the root
        # segments — used as defence-in-depth alongside _is_path_within_root.
        assert _normalize_sandbox_path("/workspace/../../etc/passwd") == "/etc/passwd"


class TestIsPathWithinRoot:
    def test_exact_match_is_within(self):
        assert _is_path_within_root("/workspace", "/workspace") is True

    def test_subpath_is_within(self):
        assert _is_path_within_root("/workspace/sub/file.txt", "/workspace") is True

    def test_sibling_directory_is_not_within(self):
        # Naive prefix-match would say True; our implementation must not.
        assert _is_path_within_root("/workspace2/file", "/workspace") is False

    def test_traversal_attack_is_blocked(self):
        # Even though the normaliser collapses ../, attackers who
        # *succeed* in escaping the workspace must be rejected here.
        assert _is_path_within_root("/etc/passwd", "/workspace") is False

    def test_non_absolute_inputs_normalised(self):
        assert _is_path_within_root("workspace/file.txt", "workspace") is True

    def test_trailing_slash_in_root_is_handled(self):
        assert _is_path_within_root("/workspace/file", "/workspace/") is True

    def test_root_at_filesystem_root(self):
        # Edge case: workspace_root="/" should match everything.
        assert _is_path_within_root("/anything/x", "/") is True
