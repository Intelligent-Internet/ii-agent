"""Smoke test: verify all router imports resolve without ImportError."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_include_routers_does_not_raise():
    """include_routers() must import all router modules without errors."""
    from fastapi import FastAPI
    from ii_agent.app.routers import include_routers

    app = FastAPI()
    # If any router module is missing, this raises ImportError
    include_routers(app)

    # Verify at least some routes were registered
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/health" in routes
