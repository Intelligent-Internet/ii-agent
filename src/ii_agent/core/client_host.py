"""Per-request client host context variable.

Tracks the hostname used by the browser that initiated the current
Socket.IO request. Used by IISandbox.expose_port() to rewrite
localhost URLs so they're reachable from the client's machine.
"""

from contextvars import ContextVar

# Set once per incoming WebSocket message before calling any handler.
# Defaults to 'localhost' so non-WebSocket code paths are unaffected.
client_host_var: ContextVar[str] = ContextVar("client_host", default="localhost")
