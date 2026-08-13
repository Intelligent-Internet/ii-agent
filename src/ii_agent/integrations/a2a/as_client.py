from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, Union

import httpx

from ii_agent.agents.models.message import Message
from ii_agent.integrations.a2a._logger import logger


@dataclass
class A2AStreamEvent:
    """Normalized event shape consumed by the A2A inner-loop strategy."""

    event_type: str
    data: Dict[str, Any]


class IIAgentA2AClient:
    """Minimal HTTP client for A2A adapter streaming endpoints.

    The adapter is expected to expose a ``/message:stream`` endpoint that
    returns line-delimited JSON or SSE data frames.

    URL resolution is lazy: supply either a static ``agent_url`` (for external
    agents and tests) or a ``url_factory`` coroutine (for per-sandbox adapters
    whose host-mapped port isn't known until first use).  The resolved URL is
    cached after the first call.
    """

    # The adapter sends heartbeats every 15s during tool execution.  A read
    # timeout of 120s tolerates multiple missed heartbeats before giving up,
    # while connect/write/pool timeouts stay short.
    _DEFAULT_STREAM_TIMEOUT = httpx.Timeout(
        connect=30.0,
        read=120.0,
        write=30.0,
        pool=30.0,
    )

    def __init__(
        self,
        agent_url: Optional[str] = None,
        *,
        url_factory: Optional[Callable[[], Awaitable[str]]] = None,
        timeout: Union[float, httpx.Timeout, None] = None,
        httpx_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if agent_url is None and url_factory is None:
            raise ValueError("Either agent_url or url_factory must be provided")
        self._static_url: Optional[str] = agent_url.rstrip("/") if agent_url else None
        self._url_factory = url_factory
        self._resolved_url: Optional[str] = None
        # A bare float (e.g. from config) is treated as the *connect* timeout;
        # read stays long to survive tool-execution pauses between heartbeats.
        if isinstance(timeout, (int, float)):
            self._timeout = httpx.Timeout(
                connect=float(timeout),
                read=self._DEFAULT_STREAM_TIMEOUT.read,
                write=self._DEFAULT_STREAM_TIMEOUT.write,
                pool=self._DEFAULT_STREAM_TIMEOUT.pool,
            )
        elif isinstance(timeout, httpx.Timeout):
            self._timeout = timeout
        else:
            self._timeout = self._DEFAULT_STREAM_TIMEOUT
        self._httpx_client = httpx_client

    # Keep a simple property for inspection/tests using only the static URL.
    @property
    def agent_url(self) -> Optional[str]:
        return self._resolved_url or self._static_url

    async def _resolve_url(self) -> str:
        """Return the base adapter URL, resolving lazily if a factory was given."""
        if self._resolved_url is not None:
            return self._resolved_url
        if self._static_url is not None:
            return self._static_url
        assert self._url_factory is not None
        resolved = await self._url_factory()
        self._resolved_url = resolved.rstrip("/")
        return self._resolved_url

    async def astream(
        self,
        *,
        messages: List[Message],
        context_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[A2AStreamEvent]:
        import time as _time

        base_url = await self._resolve_url()
        payload = {
            "context_id": context_id,
            "messages": [m.to_dict() for m in messages],
            "metadata": metadata or {},
        }

        # Compute per-role message breakdown for observability.
        _role_counts: Dict[str, int] = {}
        for m in messages:
            _r = str(getattr(m, "role", "unknown")).lower()
            _role_counts[_r] = _role_counts.get(_r, 0) + 1
        _payload_size = len(json.dumps(payload, default=str))
        logger.info(
            f"[a2a:client] Sending {len(messages)} messages to adapter "
            f"(roles={_role_counts}, payload_bytes={_payload_size}, "
            f"context_id={context_id})"
        )

        client = self._httpx_client or httpx.AsyncClient(timeout=self._timeout)
        owns_client = self._httpx_client is None
        _stream_t0 = _time.monotonic()
        _line_count = 0
        _event_count = 0
        _max_gap = 0.0
        _last_line_time = _stream_t0
        logger.info(
            f"A2A client: opening stream to {base_url}/message:stream "
            f"(context_id={context_id}, timeout={self._timeout})"
        )
        try:
            async with client.stream("POST", f"{base_url}/message:stream", json=payload) as resp:
                resp.raise_for_status()
                _connect_elapsed = _time.monotonic() - _stream_t0
                logger.info(
                    f"A2A client: stream connected "
                    f"(status={resp.status_code}, elapsed={_connect_elapsed:.2f}s, "
                    f"context_id={context_id})"
                )
                async for line in resp.aiter_lines():
                    _now = _time.monotonic()
                    _gap = _now - _last_line_time
                    _last_line_time = _now
                    _line_count += 1
                    if _gap > _max_gap:
                        _max_gap = _gap
                    _preview = line[:120] if line else ""
                    # Log all lines at INFO; warn if gap approaches read timeout
                    if _gap > 30.0:
                        logger.warning(
                            f"A2A SSE LONG GAP {_gap:.1f}s "
                            f"(line #{_line_count}, elapsed={_now - _stream_t0:.1f}s): {_preview}"
                        )
                    else:
                        logger.info(
                            f"A2A SSE line #{_line_count} "
                            f"(gap={_gap:.1f}s, elapsed={_now - _stream_t0:.1f}s): {_preview}"
                        )
                    event = self._parse_stream_line(line)
                    if event is not None:
                        _event_count += 1
                        yield event
        except Exception as exc:
            _elapsed = _time.monotonic() - _stream_t0
            logger.error(
                f"A2A client: stream error after {_elapsed:.1f}s "
                f"(lines={_line_count}, events={_event_count}, "
                f"max_gap={_max_gap:.1f}s, context_id={context_id}): {exc}"
            )
            raise
        finally:
            _elapsed = _time.monotonic() - _stream_t0
            logger.info(
                f"A2A client: stream closed "
                f"(elapsed={_elapsed:.1f}s, lines={_line_count}, events={_event_count}, "
                f"max_gap={_max_gap:.1f}s, context_id={context_id})"
            )
            if owns_client:
                await client.aclose()

    async def post_tool_result(
        self,
        *,
        tool_call_id: str,
        result: str,
    ) -> bool:
        """Deliver a bridged tool execution result to the adapter.

        The adapter's ``/tools/{tool_call_id}/result`` endpoint unblocks
        the SDK tool handler that is waiting for this result.

        Returns *True* on successful delivery.
        """
        base_url = await self._resolve_url()
        client = self._httpx_client or httpx.AsyncClient(timeout=30.0)
        owns_client = self._httpx_client is None
        try:
            resp = await client.post(
                f"{base_url}/tools/{tool_call_id}/result",
                json={"result": result},
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning(
                f"A2A client: post_tool_result failed for call {tool_call_id} to {base_url}: {exc}"
            )
            return False
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _parse_stream_line(line: str) -> Optional[A2AStreamEvent]:
        if not line:
            return None

        stripped = line.strip()
        if not stripped:
            return None

        if stripped.startswith("data:"):
            stripped = stripped[5:].strip()

        # Ignore SSE control frames and non-JSON payloads.
        if stripped in {"[DONE]", "done"}:
            return None

        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return None

        if not isinstance(payload, dict):
            return None

        event_type = str(payload.get("type") or payload.get("event") or "")
        if not event_type:
            return None

        data = payload.get("data")
        if isinstance(data, dict):
            event_data = data
        else:
            event_data = {"value": data}

        return A2AStreamEvent(event_type=event_type, data=event_data)

    async def get_agent_card(self) -> Any:
        """Fetch the agent card from ``/.well-known/agent-card.json``.

        Returns the parsed JSON response object (usually a dict or a Pydantic model
        depending on the server implementation).  The caller is responsible for
        interpreting the response.
        """
        base_url = await self._resolve_url()
        url = f"{base_url}/.well-known/agent-card.json"
        client = self._httpx_client
        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(timeout=self._timeout)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            # Return a simple namespace-like object so callers can access
            # .description and .extensions as attributes, mirroring SDK behaviour.
            payload = resp.json()

            class _Card:
                def __init__(self, data: Dict[str, Any]) -> None:
                    self._data = data
                    self.description: Optional[str] = data.get("description")
                    self.extensions: List[Any] = data.get("extensions") or []

                def __getitem__(self, key: str) -> Any:
                    return self._data[key]

                def get(self, key: str, default: Any = None) -> Any:
                    return self._data.get(key, default)

            return _Card(payload) if isinstance(payload, dict) else payload
        finally:
            if owns_client:
                await client.aclose()

    async def call_agent(
        self,
        *,
        messages: List[Message],
        context_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Send messages and collect the full SSE stream into a result dict.

        Returns a dict with keys ``success`` (bool), ``content`` (str), and
        ``user_display_content`` (str).  On error, ``success`` is ``False``.
        """
        parts: List[str] = []
        try:
            async for event in self.astream(
                messages=messages, context_id=context_id, metadata=metadata
            ):
                et = event.event_type
                if et in ("assistant.message", "message_complete", "content_done"):
                    content = event.data.get("content", "")
                    if content:
                        parts.append(str(content))
                elif et in ("assistant.message_delta", "text_delta", "message_delta"):
                    delta = event.data.get("delta", "")
                    if delta:
                        parts.append(str(delta))
                elif et in ("session.error", "error"):
                    msg = event.data.get("message", "Agent returned an error")
                    return {
                        "success": False,
                        "content": msg,
                        "user_display_content": "Agent returned an error",
                    }
            joined = "".join(parts)
            return {"success": True, "content": joined, "user_display_content": joined}
        except Exception as exc:
            return {"success": False, "content": str(exc), "user_display_content": str(exc)}

    async def close(self) -> None:
        """Close the underlying HTTP client if it was provided externally.

        After calling this the client should not be used again.
        """
        if self._httpx_client is not None:
            await self._httpx_client.aclose()

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel an in-progress adapter task.

        Sends ``POST /tasks/{task_id}:cancel`` to the adapter which sets the
        task state to ``canceled`` and unblocks any waiting tool-bridge
        handlers.  Returns *True* on successful cancellation.
        """
        base_url = await self._resolve_url()
        client = self._httpx_client or httpx.AsyncClient(timeout=10.0)
        owns_client = self._httpx_client is None
        try:
            resp = await client.post(f"{base_url}/tasks/{task_id}:cancel")
            return resp.status_code == 200
        except Exception:
            return False
        finally:
            if owns_client:
                await client.aclose()
