"""Exception types for the A2A integration layer."""

from __future__ import annotations

from ii_agent.core.exceptions import ServiceUnavailableError


class A2AAdapterUnavailableError(ServiceUnavailableError):
    """No A2A adapter URL could be resolved for the current request.

    Raised by the chat A2A wiring when ``AGENT_A2A_CHAT_STRICT=true``
    and ``_resolve_chat_a2a_url()`` returns ``None``. Surfaces the
    misconfiguration to the caller as HTTP 503 instead of silently
    falling back to the native LLM and incurring direct provider
    charges.
    """
