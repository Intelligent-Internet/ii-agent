from __future__ import annotations

import io
import os
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Any

import pytest

# Ensure modules with import-time model resolution have a default model config.
os.environ.setdefault("LLM_CONFIGS__default__model", "gpt-4o")
os.environ.setdefault("LLM_CONFIGS__default__provider", "OpenAI")
os.environ.setdefault("LLM_CONFIGS__default__api_key", "test-key")
os.environ.setdefault("COMPOSIO_CACHE_DIR", "/tmp/.composio")
os.environ.setdefault("II_AGENT_SKIP_MIGRATIONS", "1")

from ii_agent.core.config.settings import get_settings
from ii_agent_tools.storage.base import BaseStorage
from ii_agent.workers.celery.model_imports import import_model_modules

_REQUIRED_SUITE_MARKERS = {"unit", "integration", "smoke"}
_ALL_SUITE_MARKERS = _REQUIRED_SUITE_MARKERS | {"external"}
_UNEXPECTED_SKIPS_ATTR = "_ii_agent_unexpected_skips"


def pytest_addoption(parser):
    parser.addoption(
        "--fail-on-unexpected-skip",
        action="store_true",
        default=False,
        help="Fail the run when required suites contain unclassified skipped tests.",
    )


def pytest_configure(config):
    setattr(config, _UNEXPECTED_SKIPS_ATTR, [])


def _has_suite_marker(item: pytest.Item) -> bool:
    return any(item.get_closest_marker(marker) for marker in _ALL_SUITE_MARKERS)


def _suite_markers_for_item(item: pytest.Item) -> set[str]:
    return {marker for marker in _ALL_SUITE_MARKERS if item.get_closest_marker(marker)}


def pytest_collection_modifyitems(config, items: list[pytest.Item]):
    for item in items:
        nodeid = item.nodeid

        # Keep suite marker policy stable regardless of runner invocation style.
        if not _has_suite_marker(item):
            if "src/tests/unit/" in nodeid:
                item.add_marker(pytest.mark.unit)
            elif "src/tests/integration/" in nodeid:
                item.add_marker(pytest.mark.integration)
            elif "src/tests/smoke/" in nodeid:
                item.add_marker(pytest.mark.smoke)
            elif "src/tests/a2a/" in nodeid:
                item.add_marker(pytest.mark.external)

        suite_markers = _suite_markers_for_item(item) & _REQUIRED_SUITE_MARKERS
        if len(suite_markers) > 1:
            raise pytest.UsageError(
                f"{item.nodeid} has multiple required suite markers: {sorted(suite_markers)}"
            )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    outcome = yield
    report: pytest.TestReport = outcome.get_result()

    if report.when != "setup" or report.outcome != "skipped":
        return

    markers = {marker.name for marker in item.iter_markers()}

    # Only enforce skip policy on required suites. External tests are opt-in.
    if not (markers & _REQUIRED_SUITE_MARKERS):
        return
    if "external" in markers or "allowed_skip" in markers:
        return

    reason = str(report.longrepr)
    getattr(item.config, _UNEXPECTED_SKIPS_ATTR).append((item.nodeid, reason))


def pytest_sessionfinish(session: pytest.Session, exitstatus: int):
    should_fail_on_skip = session.config.getoption("--fail-on-unexpected-skip") or (
        os.getenv("II_AGENT_FAIL_ON_SKIP", "").lower() in {"1", "true", "yes"}
    )

    unexpected_skips: list[tuple[str, str]] = getattr(session.config, _UNEXPECTED_SKIPS_ATTR, [])

    if not should_fail_on_skip or not unexpected_skips:
        return

    terminal_reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminal_reporter:
        terminal_reporter.write_sep(
            "=",
            f"{len(unexpected_skips)} unexpected skip(s) in required suites",
        )
        for nodeid, reason in unexpected_skips:
            reason_line = reason.splitlines()[-1] if reason else "no reason provided"
            terminal_reporter.write_line(f"{nodeid} -> {reason_line}")

    session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Keep settings singleton isolated across tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_orm_model_registry():
    """Import the ORM model graph once so mapper resolution is stable in tests."""
    import_model_modules()


class InMemoryStorage(BaseStorage):
    """Simple in-memory storage used in tests."""

    def __init__(self):
        self._objects: dict[str, bytes] = {}

    def write(self, content, path: str, content_type: str | None = None):
        if hasattr(content, "read"):
            payload = content.read()
        else:
            payload = content
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        self._objects[path] = payload

    def write_from_url(self, url: str, path: str, content_type: str | None = None) -> str:
        self._objects[path] = f"from:{url}".encode("utf-8")
        return path

    def read(self, path: str):
        return io.BytesIO(self._objects[path])

    def get_download_signed_url(self, path: str, expiration_seconds: int = 3600) -> str | None:
        return f"https://signed.local/{path}"

    def get_download_signed_urls_batch(
        self, paths: list[str], expiration_seconds: int = 3600
    ) -> list[str | None]:
        return [f"https://signed.local/{p}" for p in paths]

    def get_upload_signed_url(
        self, path: str, content_type: str, expiration_seconds: int = 3600
    ) -> str:
        return f"https://upload.local/{path}"

    def is_exists(self, path: str) -> bool:
        return path in self._objects

    def get_file_size(self, path: str) -> int:
        return len(self._objects[path])

    def get_public_url(self, path: str) -> str:
        return f"https://public.local/{path}"

    def get_permanent_url(self, path: str) -> str:
        return f"https://permanent.local/{path}"

    def upload_and_get_permanent_url(
        self, content, path: str, content_type: str | None = None
    ) -> str:
        self.write(content, path, content_type)
        return self.get_permanent_url(path)


@pytest.fixture
def in_memory_storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def settings_factory(tmp_path):
    """Return a factory for lightweight Settings-like objects."""

    class AttrDict(dict):
        def __getattr__(self, name):
            try:
                return self[name]
            except KeyError as exc:
                raise AttributeError(name) from exc

        def __setattr__(self, name, value):
            self[name] = value

    base = {
        "environment": "dev",
        "workspace_path": str(tmp_path / "workspace"),
        "workspace_upload_subpath": "uploads",
        "use_container_workspace": False,
        "tool_server_url": "http://tool-server",
        "stripe_return_url": "https://app.local",
        "stripe_success_url": None,
        "stripe_cancel_url": None,
        "jwt_secret_key": "test-secret",
        "access_token_expire_minutes": 15,
        "refresh_token_expire_days": 7,
        "database": {
            "url": "postgresql+asyncpg://postgres:postgres@localhost:5432/ii_agent",
            "pool_size": 10,
            "max_overflow": 20,
            "pool_timeout": 30,
        },
        "redis": {
            "session_url": "redis://localhost:6379/0",
            "session_enabled": False,
        },
        "storage": {
            "provider": "gcs",
            "project_id": "test-project",
            "file_upload_bucket_name": "uploads-bucket",
            "media_bucket_name": "media-bucket",
            "file_store_path": str(tmp_path / "storage"),
            "serve_base_url": None,
        },
        "oauth": {
            "session_secret_key": "session-secret",
            "ii_auth_base": "https://auth.ii.inc",
        },
        "credits": {
            "default_user_credits": 10.0,
            "default_subscription_plan": "free",
            "default_plans_credits": {
                "free": 10.0,
                "plus": 100.0,
                "pro": 250.0,
            },
            "waitlist_enabled": False,
        },
        "stripe": {
            "secret_key": "sk_test_123",
            "webhook_secret": "whsec_123",
            "price_plus_monthly": "price_plus_m",
            "price_plus_annually": "price_plus_a",
            "price_pro_monthly": "price_pro_m",
            "price_pro_annually": "price_pro_a",
            "stripe_portal_return_url": "https://app.local/billing",
        },
        "llm_configs": {},
        "sandbox": {"time_til_clean_up": 3600},
        "agent": {
            "inner_loop_mode": "native",
            "chat_inner_loop_mode": "direct",
            "a2a_backend": "copilot",
        },
        "mcp": {
            "anthropic_oauth_token_url": "https://mcp.local/oauth/token",
            "anthropic_oauth_client_id": "client-id",
            "anthropic_oauth_redirect_uri": "https://mcp.local/callback",
        },
    }

    def _to_ns(value: Any):
        if isinstance(value, dict):
            return AttrDict({k: _to_ns(v) for k, v in value.items()})
        return value

    def _merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
        for key, value in src.items():
            if isinstance(value, dict) and isinstance(dst.get(key), dict):
                _merge(dst[key], value)
            else:
                dst[key] = value
        return dst

    def _factory(**overrides):
        merged = _merge(deepcopy(base), overrides)
        return _to_ns(merged)

    return _factory


@pytest.fixture
def async_session_cm_factory():
    """Create async context managers yielding arbitrary objects."""

    def _factory(value):
        @asynccontextmanager
        async def _cm():
            yield value

        return _cm

    return _factory
