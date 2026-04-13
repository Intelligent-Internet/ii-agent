"""Targeted coverage for A2A main module helpers and middleware."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import ii_agent.integrations.a2a as a2a_package

if not hasattr(a2a_package, "__version__"):
    a2a_package.__version__ = ""

from ii_agent.integrations.a2a.__main__ import (
    A2AAuthMiddleware,
    _fallback_hostname,
    _format_host_with_scheme,
    _parse_allowed_keys,
    _resolve_protocol_version,
    resolve_agent_card_base_url,
)


def test_parse_allowed_keys_handles_whitespace_and_empty():
    assert _parse_allowed_keys("") == set()
    assert _parse_allowed_keys("a,b, c ,") == {"a", "b", "c"}


def test_format_host_with_scheme_handles_default_ports():
    assert _format_host_with_scheme("example.com", 443, "https") == "https://example.com"
    assert _format_host_with_scheme("example.com", 80, "http") == "http://example.com"
    assert _format_host_with_scheme("example.com", 9000, "http") == "http://example.com:9000"
    assert _format_host_with_scheme("127.0.0.1", 9000, "http") == "http://127.0.0.1:9000"


def test_format_host_with_scheme_ipv6_host():
    assert _format_host_with_scheme("2001:db8::1", 8443, "https") == "https://[2001:db8::1]:8443"


def test_fallback_hostname_uses_environment(monkeypatch):
    monkeypatch.setenv("HOSTNAME", "env-host")
    assert _fallback_hostname() == "env-host"


def test_resolve_agent_card_base_url_uses_public_base_url():
    config = SimpleNamespace(
        public_base_url="https://example.com/path/",
        server_host="10.0.0.1",
        server_port="11002",
    )
    assert resolve_agent_card_base_url(config) == "https://example.com/path"


def test_resolve_agent_card_base_url_fallback_for_local_host(monkeypatch):
    monkeypatch.delenv("HOSTNAME", raising=False)
    config = SimpleNamespace(
        public_base_url=None,
        server_host="0.0.0.0",
        server_port="11002",
    )
    monkeypatch.setattr(
        "ii_agent.integrations.a2a.__main__._fallback_hostname",
        lambda: "fallback-host",
    )
    assert resolve_agent_card_base_url(config) == "http://fallback-host:11002"


def test_resolve_protocol_version_fallback(monkeypatch):
    monkeypatch.setattr(
        "ii_agent.integrations.a2a.__main__.metadata.version",
        lambda _: (_ for _ in ()).throw(RuntimeError("missing")),
    )
    assert _resolve_protocol_version() == "0.3.0"


@pytest.mark.asyncio
async def test_a2a_auth_middleware_allows_public_and_options_without_token():
    sent = []

    async def app(scope, receive, send):
        sent.append(("called", scope["path"]))

    middleware = A2AAuthMiddleware(app, {"abc"})
    receive = AsyncMock()
    send = AsyncMock()

    await middleware(
        {"type": "http", "path": "/.well-known/agent.json", "method": "GET", "headers": []},
        receive,
        send,
    )
    await middleware(
        {
            "type": "http",
            "path": "/any",
            "method": "OPTIONS",
            "headers": [],
        },
        receive,
        send,
    )

    assert len(sent) == 2


@pytest.mark.asyncio
async def test_a2a_auth_middleware_allows_authorized_and_rejects_unauthorized():
    calls = []
    unauthorized = []

    async def app(scope, receive, send):
        calls.append(scope)

    async def fake_send(message):
        unauthorized.append(message)

    middleware = A2AAuthMiddleware(app, {"secret"})

    await middleware(
        {
            "type": "http",
            "path": "/private",
            "method": "GET",
            "headers": [(b"authorization", b"Bearer secret")],
            "client": ("127.0.0.1", 1234),
        },
        AsyncMock(),
        AsyncMock(),
    )
    assert calls
    calls.clear()

    await middleware(
        {
            "type": "http",
            "path": "/private",
            "method": "GET",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        },
        AsyncMock(),
        fake_send,
    )

    assert not calls
    assert any(chunk.get("type") == "http.response.start" for chunk in unauthorized)
