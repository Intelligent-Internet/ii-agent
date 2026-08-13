"""Unit tests for core/middleware/exception_handler.py."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.testclient import TestClient
from fastapi import FastAPI

from ii_agent.core.middleware.exception_handler import (
    exception_logging_middleware,
    ii_agent_error_handler,
    not_found_exception_handler,
    permission_exception_handler,
)
from ii_agent.core.exceptions import (
    IIAgentError,
    NotFoundError,
    NotFoundException,
    PermissionDeniedError,
    PermissionException,
    ValidationError,
)

pytestmark = pytest.mark.unit


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with the exception middleware + handlers."""
    app = FastAPI()
    app.middleware("http")(exception_logging_middleware)
    app.add_exception_handler(PermissionException, permission_exception_handler)
    app.add_exception_handler(NotFoundException, not_found_exception_handler)
    app.add_exception_handler(IIAgentError, ii_agent_error_handler)
    return app


# ---------------------------------------------------------------------------
# exception_logging_middleware
# ---------------------------------------------------------------------------


class TestExceptionLoggingMiddleware:
    def test_passes_through_normal_response(self):
        app = _make_app()

        @app.get("/ok")
        def ok():
            return {"status": "ok"}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_catches_http_exception(self):
        app = _make_app()

        @app.get("/bad")
        def bad():
            raise HTTPException(status_code=418, detail="I'm a teapot")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/bad")
        assert resp.status_code == 418
        body = resp.json()
        # Middleware returns {"error": ...}, but FastAPI's default handler
        # may intercept first with {"detail": ...}. Accept either key.
        assert body.get("error") == "I'm a teapot" or body.get("detail") == "I'm a teapot"

    def test_catches_unhandled_exception_as_500(self):
        app = _make_app()

        @app.get("/crash")
        def crash():
            raise RuntimeError("boom")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/crash")
        assert resp.status_code == 500
        assert "Internal Server Error" in resp.json()["detail"]

    def test_cannot_connect_now_returns_503_with_retry_after(self):
        """Postgres crash-recovery should surface as 503, not 500.

        See docs/runtime-docs/postgres-recovery-mode-failures.md — when
        PG is in startup recovery (e.g. after a WSL2 hard kill) asyncpg
        raises ``CannotConnectNowError``.  Middleware must convert that
        into a retryable 503 with ``Retry-After`` so frontends and
        smoke-tests can distinguish "wait a moment" from "real bug".
        """
        from asyncpg.exceptions import CannotConnectNowError

        app = _make_app()

        @app.get("/db")
        def db_endpoint():
            raise CannotConnectNowError("the database system is in recovery mode")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/db")
        assert resp.status_code == 503
        assert resp.headers.get("Retry-After") == "5"
        body = resp.json()
        assert body["error_code"] == "db_unavailable"
        assert "temporarily unavailable" in body["detail"].lower()

    def test_wrapped_cannot_connect_now_returns_503(self):
        """When SQLAlchemy wraps CannotConnectNowError in an
        OperationalError/DBAPIError, we still classify it correctly via
        the ``__cause__`` / ``__context__`` chain walk.
        """
        from asyncpg.exceptions import CannotConnectNowError

        app = _make_app()

        @app.get("/wrapped")
        def wrapped():
            try:
                raise CannotConnectNowError("recovery")
            except CannotConnectNowError as inner:
                raise RuntimeError("sqlalchemy wrapper") from inner

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/wrapped")
        assert resp.status_code == 503
        assert resp.headers.get("Retry-After") == "5"

    def test_unrelated_runtime_error_still_500(self):
        """Sanity check: only asyncpg's CannotConnectNowError downgrades
        to 503.  Other RuntimeErrors must remain opaque 500s.
        """
        app = _make_app()

        @app.get("/other")
        def other():
            raise RuntimeError("not a db problem")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/other")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Named exception handlers
# ---------------------------------------------------------------------------


class TestPermissionExceptionHandler:
    def test_returns_403(self):
        app = _make_app()

        @app.get("/forbidden")
        def forbidden():
            raise PermissionDeniedError("not allowed")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/forbidden")
        assert resp.status_code == 403
        assert "not allowed" in resp.json()["detail"]


class TestNotFoundExceptionHandler:
    def test_returns_404(self):
        app = _make_app()

        @app.get("/missing")
        def missing():
            raise NotFoundError("gone")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/missing")
        assert resp.status_code == 404
        assert "gone" in resp.json()["detail"]


class TestIIAgentErrorHandler:
    def test_returns_custom_status_and_error_code(self):
        app = _make_app()

        @app.get("/validate")
        def validate():
            raise ValidationError("bad input")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/validate")
        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"] == "bad input"
        assert body["error_code"] == "validation"

    def test_includes_custom_headers(self):
        app = _make_app()

        @app.get("/headers")
        def custom_headers():
            raise IIAgentError("err", headers={"X-Custom": "val"})

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/headers")
        assert resp.status_code == 500
        assert resp.headers.get("X-Custom") == "val"
