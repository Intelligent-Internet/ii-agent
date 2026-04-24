"""E2E suite gating + shared fixtures.

End-to-end tests in this package exercise the live local stack
(http://localhost:8000 + Docker postgres). They are skipped by default
so the standard ``uv run pytest`` sweep stays hermetic.

Opt in by exporting ``II_AGENT_E2E=1`` before invocation::

    II_AGENT_E2E=1 uv run pytest src/tests/e2e/ -v

The stack must already be running and healthy. The suite makes no
attempt to bring it up — that's the operator's job and is gated through
``./scripts/stack_control.sh start`` per project conventions.
"""

from __future__ import annotations

import os

import pytest

E2E_ENV_FLAG = "II_AGENT_E2E"
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
POSTGRES_CONTAINER = os.environ.get("POSTGRES_CONTAINER", "ii-agent-local-postgres-1")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "iiagent")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "iiagentdev")


def pytest_collection_modifyitems(config, items):
    """Skip everything in src/tests/e2e/ unless II_AGENT_E2E=1."""
    if os.environ.get(E2E_ENV_FLAG) == "1":
        return
    skip = pytest.mark.skip(reason=f"e2e suite gated by {E2E_ENV_FLAG}=1")
    for item in items:
        if "tests/e2e" in str(item.fspath).replace("\\", "/"):
            item.add_marker(skip)
