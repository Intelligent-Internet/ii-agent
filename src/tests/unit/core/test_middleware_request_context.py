"""Unit tests for core/middleware/request_context.py."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from ii_agent.core.middleware.request_context import (
    SKIP_LOGGING_PATHS,
    request_tracing_middleware,
)

pytestmark = pytest.mark.unit


def _make_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(request_tracing_middleware)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/data")
    def data():
        return {"value": 42}

    return app


class TestRequestTracingMiddleware:
    def test_skips_health_path(self):
        client = TestClient(_make_app())
        resp = client.get("/health")
        assert resp.status_code == 200
        # Skipped path should NOT have tracing headers
        assert "X-Request-ID" not in resp.headers

    def test_adds_request_id_header(self):
        client = TestClient(_make_app())
        resp = client.get("/api/data")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers
        assert "X-Span-ID" in resp.headers

    def test_preserves_upstream_request_id(self):
        client = TestClient(_make_app())
        resp = client.get("/api/data", headers={"X-Request-ID": "upstream-id-123"})
        assert resp.headers["X-Request-ID"] == "upstream-id-123"

    def test_preserves_upstream_span_id(self):
        client = TestClient(_make_app())
        resp = client.get("/api/data", headers={"X-Span-ID": "span-456"})
        assert resp.headers["X-Request-ID"] == "span-456"

    def test_generates_uuid_when_no_upstream_id(self):
        client = TestClient(_make_app())
        resp = client.get("/api/data")
        request_id = resp.headers["X-Request-ID"]
        # Should look like a UUID (contains hyphens, 36 chars)
        assert len(request_id) == 36
        assert request_id.count("-") == 4


class TestSkipLoggingPaths:
    def test_health_is_in_skip_list(self):
        assert "/health" in SKIP_LOGGING_PATHS
