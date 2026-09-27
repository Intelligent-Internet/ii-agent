"""II-Agent A2A Adapter — main entry point and ASGI middleware helpers.

This module provides:

* ``A2AAuthMiddleware`` — lightweight ASGI middleware that enforces API-key
  authentication on all private endpoints while leaving public paths
  (``/.well-known/*``, OPTIONS pre-flight) open.

* ``A2AVersionMiddleware`` — validates the ``A2A-Version`` request header and
  rejects unsupported versions with a deterministic 400 JSON-RPC 2.0 error.
  All responses carry an ``A2A-Version`` header advertising the current profile.

* URL-building helpers used to produce a stable base URL for the A2A
  Agent Card regardless of the deployment topology (Docker, cloud, local).

* ``_resolve_protocol_version`` — returns the adapter's declared protocol
  version, defaulting to ``"0.3.0"`` if package metadata is unavailable.
"""

from __future__ import annotations

import os
import socket
from importlib import metadata
from typing import Any, Callable, Iterable, Optional, Set

# ---------------------------------------------------------------------------
# Protocol / package version
# ---------------------------------------------------------------------------

_DEFAULT_PROTOCOL_VERSION = "0.3.0"


def _resolve_protocol_version() -> str:
    """Return the adapter's protocol version string.

    Reads ``importlib.metadata.version("ii-agent")`` and falls back to the
    hard-coded default when the package is not installed in the environment
    (e.g. during tests or local development without a build step).
    """
    try:
        return metadata.version("ii-agent")
    except Exception:
        return _DEFAULT_PROTOCOL_VERSION


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

_DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443}


def _format_host_with_scheme(host: str, port: int, scheme: str) -> str:
    """Build ``scheme://host[:port]``, omitting the port for scheme defaults.

    IPv6 addresses are wrapped in square brackets::

        _format_host_with_scheme("2001:db8::1", 8443, "https")
        → "https://[2001:db8::1]:8443"
    """
    # Wrap IPv6 addresses.
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    if _DEFAULT_PORTS.get(scheme) == port:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def _fallback_hostname() -> str:
    """Return a best-effort hostname for the current process.

    Resolution order:
    1. ``HOSTNAME`` environment variable (set by Docker/Kubernetes).
    2. ``socket.gethostname()``.
    """
    env_hostname = os.environ.get("HOSTNAME", "")
    if env_hostname:
        return env_hostname
    try:
        return socket.gethostname()
    except OSError:
        return "localhost"


def _parse_allowed_keys(keys_csv: str) -> Set[str]:
    """Parse a comma-separated list of API keys, stripping whitespace and empties."""
    return {k.strip() for k in keys_csv.split(",") if k.strip()}


def resolve_agent_card_base_url(config: Any) -> str:
    """Compute the canonical public base URL for the A2A Agent Card.

    Resolution order:

    1. ``config.public_base_url`` — trailing slash stripped.
    2. Constructed from ``config.server_host`` / ``config.server_port``.
       Unresolvable bind addresses (``0.0.0.0``, ``::``)) are replaced
       with the result of ``_fallback_hostname()``.

    Parameters
    ----------
    config:
        Any configuration object (or duck-typed stub) with the optional
        attributes ``public_base_url``, ``server_host``, ``server_port``.
    """
    public_base_url: Optional[str] = getattr(config, "public_base_url", None)
    if public_base_url:
        return public_base_url.rstrip("/")

    host: str = str(getattr(config, "server_host", "0.0.0.0") or "0.0.0.0")
    port_raw = getattr(config, "server_port", "11002") or "11002"
    port = int(str(port_raw))

    # Unroutable bind addresses → resolve to actual hostname.
    if host in {"0.0.0.0", "::"}:
        host = _fallback_hostname()

    return _format_host_with_scheme(host, port, "http")


# ---------------------------------------------------------------------------
# ASGI Auth Middleware
# ---------------------------------------------------------------------------

# Paths that bypass authentication entirely.
_PUBLIC_PATH_PREFIXES = ("/.well-known/",)


class A2AAuthMiddleware:
    """Minimal ASGI middleware that enforces API-key Bearer authentication.

    Requests are allowed through without a token when:

    * The HTTP method is ``OPTIONS`` (CORS pre-flight).
    * The path starts with any ``_PUBLIC_PATH_PREFIXES`` entry.

    All other requests must carry an ``Authorization: Bearer <key>`` header
    where ``<key>`` is present in the ``allowed_keys`` set supplied at
    construction time.

    Rejected requests receive a ``401 Unauthorized`` response with a JSON body.
    """

    _REJECT_BODY = b'{"detail":"Unauthorized"}'

    def __init__(self, app: Callable, allowed_keys: Set[str]) -> None:
        self._app = app
        self._allowed_keys = allowed_keys

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable,
    ) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        method: str = scope.get("method", "")
        path: str = scope.get("path", "")

        # OPTIONS and public paths pass through.
        if method.upper() == "OPTIONS" or any(
            path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES
        ):
            await self._app(scope, receive, send)
            return

        # Extract Bearer token from headers.
        headers: Iterable[tuple[bytes, bytes]] = scope.get("headers", [])
        token: Optional[str] = None
        for name, value in headers:
            if name.lower() == b"authorization":
                raw = value.decode("latin-1", errors="replace").strip()
                if raw.lower().startswith("bearer "):
                    token = raw[7:].strip()
                break

        if token and token in self._allowed_keys:
            await self._app(scope, receive, send)
            return

        # Unauthorized.
        client = scope.get("client")
        if client:
            import logging

            logging.getLogger(__name__).warning(
                "A2A auth rejected request from %s:%s path=%s",
                client[0],
                client[1],
                path,
            )

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(self._REJECT_BODY)).encode()),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": self._REJECT_BODY,
                "more_body": False,
            }
        )


# ---------------------------------------------------------------------------
# ASGI Version Middleware
# ---------------------------------------------------------------------------

# Versions the adapter accepts from clients.  Both 0.3.x (internal SSE envelope)
# and 1.0.x (canonical StreamResponse wrapper) are accepted; the profile is
# stored in scope["a2a_requested_version"] for route handlers that care.
_SUPPORTED_VERSIONS: frozenset[str] = frozenset({"0.3", "0.3.0", "1.0", "1.0.0"})

# Version string advertised in every response.
_CURRENT_VERSION: str = "0.3.0"

_VERSION_ERROR_TEMPLATE = (
    '{{"jsonrpc":"2.0","id":null,"error":{{"code":-32600,'
    '"message":"Unsupported A2A-Version \\"{version}\\". '
    'Supported versions: {supported}"}}}}'
)


class A2AVersionMiddleware:
    """Validates the ``A2A-Version`` request header and annotates responses.

    Behaviour:

    * If ``A2A-Version`` is **absent** the request is treated as requesting
      the current compatibility profile (``0.3.0``).
    * If the header is **present** and the value is in ``_SUPPORTED_VERSIONS``
      the negotiated version is stored in ``scope["a2a_requested_version"]``
      so route handlers can adjust their serialisation format.
    * If the header is **present** and the value is NOT in
      ``_SUPPORTED_VERSIONS`` a ``400`` response is returned immediately with
      a JSON-RPC 2.0 error body.  No upstream handler is invoked.

    Every response that passes through this middleware receives an
    ``A2A-Version`` header advertising the implementation's current profile,
    regardless of whether the client sent the header.
    """

    def __init__(
        self,
        app: Callable,
        *,
        supported: frozenset[str] = _SUPPORTED_VERSIONS,
        current_version: str = _CURRENT_VERSION,
    ) -> None:
        self._app = app
        self._supported = supported
        self._current_version = current_version
        self._version_header: bytes = current_version.encode()

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable,
        send: Callable,
    ) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        # Extract A2A-Version request header (case-insensitive lookup).
        raw_version = ""
        for name, value in scope.get("headers", []):
            if name.lower() == b"a2a-version":
                raw_version = value.decode("utf-8", errors="replace").strip()
                break

        if raw_version and raw_version not in self._supported:
            supported_list = ", ".join(sorted(self._supported))
            body = _VERSION_ERROR_TEMPLATE.format(
                version=raw_version,
                supported=supported_list,
            ).encode()
            resp_headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"a2a-version", self._version_header),
            ]
            await send({"type": "http.response.start", "status": 400, "headers": resp_headers})
            await send({"type": "http.response.body", "body": body, "more_body": False})
            return

        # Store the negotiated version for downstream route handlers.
        scope["a2a_requested_version"] = raw_version or self._current_version

        # Inject A2A-Version into every response that flows back.
        version_header = self._version_header

        async def _send_with_version(event: dict[str, Any]) -> None:
            if event.get("type") == "http.response.start":
                hdrs = list(event.get("headers", []))
                hdrs.append((b"a2a-version", version_header))
                event = dict(event, headers=hdrs)
            await send(event)

        await self._app(scope, receive, _send_with_version)
