from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import logging
import os
import threading
import time as _time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse
import uvicorn

from ii_agent.integrations.a2a.__main__ import (
    A2AAuthMiddleware,
    A2AVersionMiddleware,
    _parse_allowed_keys,
    _resolve_protocol_version,
)
from ii_agent.integrations.a2a.extension_utils import (
    REASONING_EXTENSION_URI,
    TOOL_TELEMETRY_EXTENSION_URI,
)
from ii_agent.integrations.a2a.multimodal import (
    build_conversation_context,
    extract_historical_image_parts,
    extract_user_content,
    has_multimodal_parts,
)
from ii_agent.integrations.a2a.registry import AgentCard, AgentRegistry
from ii_agent.integrations.a2a.router import AgentRouter
from ii_agent.integrations.a2a.task_store import TaskStore
from ii_agent.integrations.a2a._logger import logger


class A2AStreamRequest(BaseModel):
    """Request payload for local A2A stream testing."""

    context_id: str = Field(default="default")
    messages: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplyRequest(BaseModel):
    """Payload for submitting user input to a task in ``input_required`` state."""

    text: str = Field(default="", description="User's text response to the INPUT_REQUIRED prompt.")


class ToolResultBody(BaseModel):
    """Payload for delivering a bridged tool execution result."""

    result: str = Field(default="", description="Tool execution result text.")
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# URL validation for SSRF protection
# ---------------------------------------------------------------------------
_PRIVATE_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]


def _is_safe_url(url: str) -> tuple[bool, str]:
    """Validate URL to prevent SSRF attacks.

    Returns (is_safe, error_message). If is_safe is True, error_message is empty.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL format"

    # Only allow http/https schemes
    if parsed.scheme not in ("http", "https"):
        return False, f"Invalid scheme '{parsed.scheme}': only http/https allowed"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must have a hostname"

    # Block known dangerous hostnames
    dangerous_hosts = {"metadata.google.internal", "169.254.169.254"}
    if hostname.lower() in dangerous_hosts:
        return False, f"Blocked hostname: {hostname}"

    # Try to resolve as IP address and check against private ranges
    try:
        ip = ipaddress.ip_address(hostname)
        for network in _PRIVATE_IP_RANGES:
            if ip in network:
                return False, f"Private/internal IP addresses are not allowed: {hostname}"
    except ValueError:
        # Not an IP address (it's a hostname) - allow it
        # DNS rebinding attacks are harder to prevent here without async resolution
        pass

    return True, ""


# A2ASendRequest is identical in shape; kept as a named alias for clarity.
A2ASendRequest = A2AStreamRequest

# ---------------------------------------------------------------------------
# Module-level singletons (one per server process)
# ---------------------------------------------------------------------------

_STREAM_HEARTBEAT_INTERVAL = 15.0  # seconds
_HEARTBEAT_SSE = 'data: {"type": "heartbeat", "data": {"status": "waiting"}}\n\n'

# ---------------------------------------------------------------------------
# Active-stream tracker for /debug/streams inspection
# ---------------------------------------------------------------------------
_active_streams: dict[str, dict[str, Any]] = {}
_active_streams_lock = threading.Lock()


def _track_stream(task_id: str, **kw: Any) -> None:
    with _active_streams_lock:
        _active_streams.setdefault(task_id, {}).update(kw, _updated=_time.time())


def _untrack_stream(task_id: str) -> None:
    with _active_streams_lock:
        _active_streams.pop(task_id, None)


# ---------------------------------------------------------------------------
# Event-loop watchdog — a daemon thread that verifies the asyncio loop is
# responsive.  If the loop fails to schedule a callback within 5 s we emit
# an ERROR-level log visible even when everything else is frozen.
# ---------------------------------------------------------------------------
_watchdog_logger = logging.getLogger(__name__ + ".watchdog")


def _start_event_loop_watchdog(
    loop: asyncio.AbstractEventLoop,
    interval: float = 10.0,
    timeout: float = 5.0,
) -> threading.Thread:
    """Start a daemon thread that periodically pings the event loop."""

    def _run() -> None:
        while True:
            _time.sleep(interval)
            responded = threading.Event()

            def _ping() -> None:
                responded.set()

            try:
                loop.call_soon_threadsafe(_ping)
            except RuntimeError:
                _watchdog_logger.warning("Event loop closed — watchdog exiting")
                break

            if not responded.wait(timeout=timeout):
                _watchdog_logger.error(
                    "EVENT LOOP BLOCKED: no response for %.0fs — asyncio heartbeats cannot fire!",
                    timeout,
                )
            else:
                # Only log at DEBUG to avoid noise when things are healthy.
                _watchdog_logger.debug("Event loop responsive")

    t = threading.Thread(target=_run, daemon=True, name="a2a-el-watchdog")
    t.start()
    _watchdog_logger.info(
        "Event-loop watchdog started (interval=%.0fs, timeout=%.0fs)", interval, timeout
    )
    return t


async def _with_heartbeats(
    gen: AsyncIterator[str],
    interval: float = _STREAM_HEARTBEAT_INTERVAL,
    *,
    stream_id: str = "",
) -> AsyncIterator[str]:
    """Wrap an async generator with independent heartbeat injection.

    Drains *gen* via a background task into an asyncio.Queue.  The consumer
    loop pulls from the queue with a timeout; on timeout a heartbeat SSE
    chunk is yielded regardless of whether the underlying generator is
    producing output.

    This guarantees heartbeats reach the HTTP client even when the backend
    generator's own heartbeat mechanism is stalled (e.g. because the
    Copilot SDK blocks the generator's await point).
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    _sid = stream_id or "?"
    _hb_count = 0
    _chunk_count = 0
    _t0 = _time.monotonic()

    logger.info(f"[stream:{_sid}] _with_heartbeats started (interval={interval:.1f}s)")

    async def _drain() -> None:
        nonlocal _chunk_count
        _drain_t0 = _time.monotonic()
        logger.info(f"[stream:{_sid}] drain task started")
        try:
            async for chunk in gen:
                _chunk_count += 1
                _elapsed = _time.monotonic() - _drain_t0
                # Log every 10th chunk or first 5 to avoid flooding.
                if _chunk_count <= 5 or _chunk_count % 10 == 0:
                    _preview = chunk[:80].replace("\n", "\\n") if chunk else ""
                    logger.info(
                        f"[stream:{_sid}] drain: chunk #{_chunk_count}"
                        f" at {_elapsed:.1f}s ({_preview})"
                    )
                await queue.put(chunk)
        except Exception:
            logger.opt(exception=True).warning(f"[stream:{_sid}] drain: generator raised")
        finally:
            _elapsed = _time.monotonic() - _drain_t0
            logger.info(
                f"[stream:{_sid}] drain: ended"
                f" (chunks={_chunk_count}, elapsed={_elapsed:.1f}s) — sending sentinel"
            )
            await queue.put(None)  # sentinel

    task = asyncio.create_task(_drain())
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                _hb_count += 1
                _elapsed = _time.monotonic() - _t0
                logger.info(
                    f"[stream:{_sid}] heartbeat #{_hb_count}"
                    f" at {_elapsed:.1f}s (chunks_so_far={_chunk_count})"
                )
                _track_stream(_sid, heartbeats=_hb_count, last_heartbeat=_time.time())
                yield _HEARTBEAT_SSE
                continue
            if chunk is None:
                _elapsed = _time.monotonic() - _t0
                logger.info(
                    f"[stream:{_sid}] stream complete"
                    f" (chunks={_chunk_count}, heartbeats={_hb_count}, elapsed={_elapsed:.1f}s)"
                )
                break
            yield chunk
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        _untrack_stream(_sid)


# Task store: TTL-bounded (1 h), capped at 10 000 entries.
# Replaces the unbounded plain dict from Phase 3.
_TASK_STORE: TaskStore = TaskStore(ttl_seconds=3600.0, maxsize=10_000)

# Agent registry and router (populated at startup or via /agents endpoints).
_AGENT_REGISTRY: AgentRegistry = AgentRegistry()
_AGENT_ROUTER: AgentRouter = AgentRouter(_AGENT_REGISTRY, fallback_name=None)

# Per-task reply queues for INPUT_REQUIRED round-trips.
# A task in "input_required" state blocks on its queue; the :reply endpoint
# puts the user's response into the queue to resume execution.
_TASK_INPUT_QUEUES: dict[str, asyncio.Queue[dict[str, Any]]] = {}

# Timeout (seconds) to wait for user input before failing the task.
_INPUT_REQUIRED_TIMEOUT: float = 300.0


def _backend_timeout_from_env(var_name: str, default: float) -> float:
    """Read a per-turn timeout (seconds) for a CLI backend from an env var.

    Falls back to *default* when the env var is unset, empty, non-numeric,
    or non-positive.  The hard-coded 300 s default baked into the
    Copilot/Claude-Code/Codex backends tripped long deep-research turns
    (multi-step tool chains routinely exceed 5 minutes); this helper lets
    operators tune the budget per backend without patching the image.
    """
    raw = os.environ.get(var_name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logging.getLogger(__name__).warning(
            "Ignoring invalid %s=%r (expected float seconds); using %.0fs",
            var_name,
            raw,
            default,
        )
        return default
    if value <= 0:
        logging.getLogger(__name__).warning(
            "Ignoring non-positive %s=%r; using %.0fs", var_name, raw, default
        )
        return default
    return value


def _extract_last_user_text(messages: list[dict[str, Any]]) -> str:
    """Extract a plain-text prompt from the latest user message payload."""

    for msg in reversed(messages):
        role = str(msg.get("role") or "").lower()
        if role != "user":
            continue

        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                elif isinstance(item, str) and item.strip():
                    parts.append(item.strip())
            if parts:
                return "\n".join(parts)

    return ""


def _sse(event_type: str, data: dict[str, Any]) -> str:
    payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=True)
    return f"data: {payload}\n\n"


async def _event_stream(
    req: A2AStreamRequest,
    *,
    task_id: Optional[str] = None,
) -> AsyncIterator[str]:
    """Emit the canonical A2A SSE event sequence for one turn.

    A2A Extension metadata is embedded in reasoning and tool events so that
    callers that support ``urn:ii-agent:extensions:reasoning/v1`` and
    ``urn:ii-agent:extensions:tool-telemetry/v1`` can surface rich telemetry.

    When *task_id* is provided, the stream first emits a ``session.task_id``
    event so the client can associate replies with a paused task.

    **INPUT_REQUIRED simulation**: If the prompt ends with ``?``, the stream
    pauses and emits ``session.input_required``, then blocks until the client
    POSTs to ``/tasks/{task_id}:reply``.  This exercises the full round-trip
    without requiring a real Copilot CLI backend.
    """
    prompt = _extract_last_user_text(req.messages)

    # Emit task_id first so the client can associate replies.
    if task_id:
        yield _sse("session.task_id", {"task_id": task_id})
        await asyncio.sleep(0)

    # Reasoning delta — with A2A Extension metadata.
    yield _sse(
        "assistant.reasoning_delta",
        {
            "delta": "Analyzing request...",
            "extensions": [{"uri": REASONING_EXTENSION_URI}],
        },
    )
    await asyncio.sleep(0)

    # --- INPUT_REQUIRED simulation ---
    # If the prompt ends with "?" we pause and wait for the client to reply.
    # This exercises the full INPUT_REQUIRED round-trip in the MVP.
    user_reply: str = ""
    if prompt.endswith("?") and task_id is not None:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        _TASK_INPUT_QUEUES[task_id] = queue

        # Signal that we need input.
        yield _sse(
            "session.input_required",
            {
                "message": "Please provide additional context to proceed.",
                "schema": {"type": "string"},
            },
        )
        await asyncio.sleep(0)

        # Block until reply arrives or timeout.
        try:
            reply = await asyncio.wait_for(queue.get(), timeout=_INPUT_REQUIRED_TIMEOUT)
            user_reply = str(reply.get("text") or "")
        except asyncio.TimeoutError:
            yield _sse(
                "session.error", {"message": "INPUT_REQUIRED timed out waiting for user reply"}
            )
            yield "data: [DONE]\n\n"
            return
        finally:
            _TASK_INPUT_QUEUES.pop(task_id, None)

    # Build the response body incorporating any user reply.
    base = (
        f"[A2A adapter MVP] Received context '{req.context_id}'. "
        f"Prompt summary: {prompt[:240] if prompt else 'no user message provided'}"
    )
    if user_reply:
        base = f"{base} | User replied: {user_reply}"

    response_text = base
    midpoint = max(1, len(response_text) // 2)

    yield _sse("assistant.message_delta", {"delta": response_text[:midpoint]})
    await asyncio.sleep(0)
    yield _sse("assistant.message_delta", {"delta": response_text[midpoint:]})
    await asyncio.sleep(0)

    # Final message — with A2A tool-telemetry Extension metadata.
    yield _sse(
        "assistant.message",
        {
            "content": response_text,
            "tool_calls": [],
            "extensions": [{"uri": TOOL_TELEMETRY_EXTENSION_URI, "data": {"tool_count": 0}}],
        },
    )
    await asyncio.sleep(0)

    usage = {
        "input_tokens": max(1, len(prompt.split())),
        "output_tokens": max(1, len(response_text.split())),
        "total_tokens": max(2, len(prompt.split()) + len(response_text.split())),
        "duration": 0.05,
    }
    yield _sse("assistant.usage", usage)
    yield "data: [DONE]\n\n"


async def _collect_task(
    req: A2AStreamRequest,
    task_id: str,
    *,
    stream_callable: Optional[Any] = None,
) -> dict[str, Any]:
    """Drain an event stream and build a completed Task dict.

    *stream_callable*, when provided, is called as
    ``stream_callable(req, task_id=task_id)`` and must return an async
    iterable of A2A SSE strings.  Defaults to the module-level
    ``_event_stream`` (simulated backend).

    Handles the ``session.input_required`` event by updating the task status
    in ``_TASK_STORE`` so that concurrent ``GET /tasks/{task_id}`` calls will
    return the correct ``input_required`` state while the stream is paused.

    States flow: ``submitted`` → ``working`` → ``input_required`` (optional) →
    ``working`` (resumed) → ``completed`` | ``failed``.
    """
    context_id = req.context_id or "default"
    artifacts: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    status_state: str = "working"
    error_message: str | None = None

    try:
        active_stream = stream_callable if stream_callable is not None else _event_stream
        async for raw_chunk in active_stream(req, task_id=task_id):
            chunk = raw_chunk.strip()
            if not chunk.startswith("data:"):
                continue
            raw = chunk[5:].strip()
            if raw == "[DONE]":
                break
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event_type: str = event.get("type", "")
            data: dict[str, Any] = event.get("data", {})

            if event_type == "session.input_required":
                # Persist the paused state so callers can observe it.
                if task_id in _TASK_STORE:
                    _TASK_STORE[task_id]["status"]["state"] = "input_required"

            elif event_type == "session.error":
                status_state = "failed"
                error_message = data.get("message", "Unknown stream error")
                break

            elif event_type == "assistant.message":
                text = data.get("content", "")
                if text:
                    artifacts.append(
                        {
                            "artifactId": str(uuid.uuid4()),
                            "mimeType": "text/plain",
                            "parts": [{"kind": "text", "text": text}],
                            "index": len(artifacts),
                        }
                    )
                    history.append({"role": "assistant", "content": text})

        if not error_message:
            status_state = "completed"
    except Exception as exc:
        status_state = "failed"
        error_message = str(exc)

    task: dict[str, Any] = {
        "id": task_id,
        "contextId": context_id,
        "status": {"state": status_state},
        "artifacts": artifacts,
        "history": history,
    }
    if error_message:
        task["error"] = {"message": error_message}
    return task


def create_app(
    *,
    registry: Optional[AgentRegistry] = None,
    router: Optional[AgentRouter] = None,
    backend: Optional[Any] = None,
    allowed_keys: Optional[frozenset[str]] = None,
) -> FastAPI:
    """Create the FastAPI application.

    Parameters
    ----------
    registry:
        Agent registry to use.  Defaults to the module-level singleton
        ``_AGENT_REGISTRY``.  Pass a fresh instance in tests for isolation.
    router:
        Agent router to use.  Defaults to the module-level singleton
        ``_AGENT_ROUTER`` (which wraps the module-level registry).  When a
        custom *registry* is provided without a custom *router*, a new router
        wrapping the custom registry is created automatically.
    backend:
        Optional A2A streaming backend.  Must expose a ``stream(prompt,
        context_id, task_id)`` async generator interface returning A2A SSE
        strings.  When ``None`` (the default) the built-in simulated
        ``_event_stream`` is used.  Typical value: a
        :class:`~ii_agent.integrations.a2a.claude_code_backend.ClaudeCodeBackend`
        instance.
    allowed_keys:
        Optional frozenset of API key strings that are accepted by
        :class:`A2AAuthMiddleware`.  When ``None`` (the default) auth is
        **not** enforced — all requests are permitted (open mode, suitable
        for local development or CI).  Pass a non-empty frozenset to
        activate bearer-token enforcement on all private endpoints.
    """
    _registry = registry if registry is not None else _AGENT_REGISTRY
    if router is not None:
        _router = router
    elif registry is not None:
        _router = AgentRouter(_registry)
    else:
        _router = _AGENT_ROUTER

    # ---------------------------------------------------------------------------
    # Unified event source — routes to the real backend or the simulated stream.
    # ---------------------------------------------------------------------------

    async def _event_source(req: A2AStreamRequest, *, task_id: Optional[str] = None):
        """Yield A2A SSE strings from the active backend or the simulated stream."""
        if backend is not None:
            prompt, parts = extract_user_content(req.messages)
            # Include images from earlier user turns so the LLM retains
            # visibility of previously uploaded images on follow-up questions.
            historical_images = extract_historical_image_parts(req.messages)
            if historical_images:
                parts.extend(historical_images)
            # Prepend prior conversation turns so the Copilot SDK LLM
            # retains context across runs (each run creates a fresh SDK
            # session with no built-in history).
            history_prefix = build_conversation_context(req.messages)
            if history_prefix:
                prompt = history_prefix + prompt
                logger.info(
                    f"[a2a:event_source] Conversation history prepended "
                    f"(messages={len(req.messages)}, history_chars={len(history_prefix)}, "
                    f"prompt_chars={len(prompt)}, multimodal_parts={len(parts)}, "
                    f"context_id={req.context_id}, task_id={(task_id or '')[:8]})"
                )
            else:
                logger.info(
                    f"[a2a:event_source] No prior history "
                    f"(messages={len(req.messages)}, prompt_chars={len(prompt)}, "
                    f"multimodal_parts={len(parts)}, context_id={req.context_id}, "
                    f"task_id={(task_id or '')[:8]})"
                )
            # Extract native tool schemas from A2A metadata for bridging.
            tool_schemas = (req.metadata or {}).get("native_tool_schemas") or None
            # Forward the agent's system message so the CLI LLM receives
            # the same directives as the native inner loop.
            system_message = (req.metadata or {}).get("system_message") or None
            # Forward the user-selected model so the backend can steer the
            # LLM used for this specific request rather than always using
            # the startup-configured default.
            model_id: str = (req.metadata or {}).get("model") or ""
            logger.debug(
                "[a2a:stream] model_id=%r backend_default=%r context_id=%s",
                model_id,
                getattr(getattr(backend, "config", None), "model", ""),
                req.context_id,
            )
            # Pass multimodal parts, tool schemas, system message, and model to backends.
            if has_multimodal_parts(parts):
                async for chunk in backend.stream(
                    prompt,
                    req.context_id or "default",
                    task_id,
                    parts=parts,
                    tool_schemas=tool_schemas,
                    system_message=system_message,
                    model=model_id,
                ):
                    yield chunk
            else:
                async for chunk in backend.stream(
                    prompt,
                    req.context_id or "default",
                    task_id,
                    tool_schemas=tool_schemas,
                    system_message=system_message,
                    model=model_id,
                ):
                    yield chunk
        else:
            async for chunk in _event_stream(req, task_id=task_id):
                yield chunk

    app = FastAPI(title="II-Agent A2A Adapter MVP", version="0.1.0")

    # --- Start event-loop watchdog on first request ---
    _watchdog_started = False

    @app.middleware("http")
    async def _ensure_watchdog(request: Any, call_next: Any) -> Any:
        nonlocal _watchdog_started
        if not _watchdog_started:
            _watchdog_started = True
            _start_event_loop_watchdog(asyncio.get_running_loop())
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/debug/streams")
    async def debug_streams() -> dict[str, Any]:
        """Return active stream state for live inspection."""
        with _active_streams_lock:
            return {
                "active_streams": dict(_active_streams),
                "stream_count": len(_active_streams),
                "server_uptime": _time.monotonic(),
            }

    # --- Tool bridge: result delivery endpoint ---

    @app.post("/tools/{tool_call_id}/result")
    async def tool_result(tool_call_id: str, body: ToolResultBody = Body()) -> dict[str, Any]:
        """Receive the result of a bridged native tool execution.

        The ii-agent inner loop calls this endpoint after executing a tool
        locally.  The result is delivered to the SDK handler that is
        blocking inside the Copilot CLI session.
        """
        if backend is None:
            return {"status": "error", "message": "no backend configured"}
        delivered = backend.receive_tool_result(tool_call_id, body.result)
        return {"status": "ok" if delivered else "not_found", "tool_call_id": tool_call_id}

    @app.get("/.well-known/agent-card.json", include_in_schema=False)
    async def agent_card() -> JSONResponse:
        # Capabilities reflect the *internal compatibility profile* implemented
        # today.  Wire-level A2A 1.0 StreamResponse interop mode is not yet
        # active; see Track A in a2a-implementation-handoff.md.
        card = {
            "name": "ii-agent",
            "description": (
                "II-Agent A2A adapter — provides access to the II-Agent inner loop "
                "via the Agent2Agent protocol."
            ),
            "version": _resolve_protocol_version(),
            "url": "",  # Resolved at runtime by callers via expose_port()
            "capabilities": {
                "streaming": True,
                "pushNotifications": False,
                "stateTransitionHistory": False,
                # Supported operations for this profile.
                "supportedOperations": [
                    "message/stream",
                    "message/send",
                    "tasks/get",
                    "tasks/cancel",
                    "tasks/reply",
                ],
                # Interop profile declaration — internal compatibility profile
                # (type/data SSE envelope).  Not yet strict A2A 1.0 wire-level.
                "a2aProfile": "internal-compat",
                "a2aProfileVersion": _resolve_protocol_version(),
            },
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain", "text/event-stream"],
            "skills": [
                {
                    "id": "general",
                    "name": "General Agent",
                    "description": "Handles general queries using the configured LLM backend.",
                    "tags": ["general", "code", "research"],
                    "examples": ["Write a Python script that …", "Explain how … works"],
                }
            ],
            "extensions": [
                {
                    "uri": REASONING_EXTENSION_URI,
                    "description": "Streaming reasoning deltas (chain-of-thought).",
                    "required": False,
                },
                {
                    "uri": TOOL_TELEMETRY_EXTENSION_URI,
                    "description": "Structured tool call and tool result telemetry.",
                    "required": False,
                },
            ],
        }
        return JSONResponse(content=card)

    @app.post("/message:stream")
    async def message_stream(req: A2AStreamRequest) -> StreamingResponse:
        """SSE streaming endpoint.

        Generates a task_id and embeds it as the first ``session.task_id``
        event so clients can use it for ``/tasks/{task_id}:reply`` calls.
        """
        task_id = str(uuid.uuid4())
        _prompt_preview = ""
        for msg in req.messages or []:
            if isinstance(msg.get("content"), str):
                _prompt_preview = msg["content"][:100]
                break
        # Compute per-role message breakdown for observability.
        _role_counts: dict[str, int] = {}
        for msg in req.messages or []:
            _r = str(msg.get("role") or "unknown").lower()
            _role_counts[_r] = _role_counts.get(_r, 0) + 1
        logger.info(
            f"[stream:{task_id[:8]}] /message:stream request "
            f"(context_id={req.context_id}, messages={len(req.messages or [])}, "
            f"roles={_role_counts}, prompt={_prompt_preview!r})"
        )
        _TASK_STORE[task_id] = {
            "id": task_id,
            "contextId": req.context_id or "default",
            "status": {"state": "working"},
            "artifacts": [],
            "history": [],
        }
        _track_stream(task_id[:8], state="started", context_id=req.context_id)
        return StreamingResponse(
            _with_heartbeats(
                _event_source(req, task_id=task_id),
                stream_id=task_id[:8],
            ),
            media_type="text/event-stream",
        )

    @app.post("/message:send")
    async def message_send(req: A2ASendRequest) -> JSONResponse:
        """Synchronous A2A task execution.

        Collects the full event stream and returns a completed Task object
        conforming to the A2A protocol task schema.
        """
        task_id = str(uuid.uuid4())
        task_stub: dict[str, Any] = {
            "id": task_id,
            "contextId": req.context_id or "default",
            "status": {"state": "submitted"},
            "artifacts": [],
            "history": [],
        }
        _TASK_STORE[task_id] = task_stub

        task = await _collect_task(req, task_id, stream_callable=_event_source)
        _TASK_STORE[task_id] = task
        return JSONResponse(content=task)

    @app.get("/tasks/{task_id}")
    async def get_task(task_id: str) -> JSONResponse:
        """Return a previously submitted task by ID."""
        task = _TASK_STORE.get(task_id)
        if task is None:
            return JSONResponse(status_code=404, content={"detail": "Task not found"})
        return JSONResponse(content=task)

    @app.post("/tasks/{task_id}:cancel")
    async def cancel_task(task_id: str) -> JSONResponse:
        """Cancel a task that is in a cancellable state (submitted, working, or input_required)."""
        task = _TASK_STORE.get(task_id)
        if task is None:
            return JSONResponse(status_code=404, content={"detail": "Task not found"})
        state = task.get("status", {}).get("state", "")
        if state in ("completed", "failed", "canceled"):
            return JSONResponse(
                status_code=409,
                content={"detail": f"Task is already {state}"},
            )
        # If there is a waiting reply queue, unblock it with a cancel signal.
        queue = _TASK_INPUT_QUEUES.pop(task_id, None)
        if queue is not None:
            await queue.put({"_cancelled": True})
        task["status"]["state"] = "canceled"
        return JSONResponse(content=task)

    @app.post("/tasks/{task_id}:reply")
    async def reply_task(task_id: str, reply: ReplyRequest = Body()) -> JSONResponse:
        """Submit user input for a task that is in ``input_required`` state.

        The waiting ``_event_stream`` generator receives the reply through an
        ``asyncio.Queue`` and resumes producing events.
        """
        task = _TASK_STORE.get(task_id)
        if task is None:
            return JSONResponse(status_code=404, content={"detail": "Task not found"})
        state = task.get("status", {}).get("state", "")
        if state != "input_required":
            return JSONResponse(
                status_code=409,
                content={"detail": f"Task is not awaiting input (current state: '{state}')"},
            )
        queue = _TASK_INPUT_QUEUES.get(task_id)
        if queue is None:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Task input queue is not available; the task may have timed out"
                },
            )
        await queue.put({"text": reply.text, "metadata": reply.metadata})
        task["status"]["state"] = "working"
        return JSONResponse(content=task)

    # ------------------------------------------------------------------
    # Agent registry endpoints (Phase 4)
    # ------------------------------------------------------------------

    @app.get("/agents")
    async def list_agents() -> JSONResponse:
        """Return all registered agent cards."""
        return JSONResponse(content=[card.to_dict() for card in _registry.list_all()])

    @app.post("/agents:discover")
    async def discover_agent(body: dict[str, Any]) -> JSONResponse:
        """Discover an agent by crawling its ``/.well-known/agent-card.json``.

        Body: ``{"url": "<agent-base-url>"}``
        """
        base_url = str(body.get("url") or "").strip()
        if not base_url:
            return JSONResponse(status_code=422, content={"detail": "'url' is required"})

        # SSRF protection: validate URL before making external request
        is_safe, error_msg = _is_safe_url(base_url)
        if not is_safe:
            return JSONResponse(status_code=422, content={"detail": error_msg})

        try:
            card = await _registry.discover(base_url)
        except Exception as exc:
            # Don't leak internal error details to client
            logger.warning("Agent discovery failed for %s: %s", base_url, exc, exc_info=True)
            return JSONResponse(
                status_code=502,
                content={"detail": "Discovery failed: unable to fetch agent card"},
            )
        return JSONResponse(content=card.to_dict())

    @app.post("/agents:register")
    async def register_agent(body: dict[str, Any]) -> JSONResponse:
        """Manually register an agent card.

        Body is a partial or full A2A agent card JSON.  ``name`` and ``url``
        are required.
        """
        name = str(body.get("name") or "").strip()
        url = str(body.get("url") or "").strip()
        if not name or not url:
            return JSONResponse(
                status_code=422,
                content={"detail": "'name' and 'url' are required"},
            )
        card = AgentCard.from_dict(body)
        await _registry.register(card)
        return JSONResponse(content=card.to_dict())

    @app.delete("/agents/{agent_name}")
    async def unregister_agent(agent_name: str) -> JSONResponse:
        """Remove a registered agent by name."""
        existed = await _registry.unregister(agent_name)
        if not existed:
            return JSONResponse(status_code=404, content={"detail": "Agent not found"})
        return JSONResponse(content={"detail": f"Agent '{agent_name}' unregistered"})

    @app.post("/agents:route")
    async def route_task(body: dict[str, Any]) -> JSONResponse:
        """Ask the router which agent would handle a given prompt.

        Body: ``{"prompt": "...", "hint_tags": ["code", "python"]}``  (tags optional)
        """
        prompt = str(body.get("prompt") or "")
        hint_tags = list(body.get("hint_tags") or [])
        card = _router.route(prompt, hint_tags=hint_tags)
        if card is None:
            return JSONResponse(
                status_code=503,
                content={"detail": "No agents registered; cannot route task"},
            )
        return JSONResponse(content=card.to_dict())

    # ------------------------------------------------------------------
    # Middleware wiring — Starlette applies add_middleware() in LIFO order
    # (last added = outermost).  We want:
    #   outermost: auth (protects everything below)
    #   innermost: version (annotates every response with A2A-Version header)
    # So we add version first, then auth.
    # ------------------------------------------------------------------
    app.add_middleware(A2AVersionMiddleware)
    if allowed_keys:
        app.add_middleware(A2AAuthMiddleware, allowed_keys=frozenset(allowed_keys))

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local A2A adapter MVP server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18100)
    parser.add_argument(
        "--backend",
        choices=["simulate", "claude-code", "codex", "copilot"],
        default="simulate",
        help=(
            "Event source backend.  'simulate' uses the built-in mock stream; "
            "'claude-code' delegates to the claude CLI subprocess "
            "(requires ANTHROPIC_API_KEY in the environment); "
            "'codex' delegates to the OpenAI codex CLI subprocess "
            "(requires OPENAI_API_KEY in the environment); "
            "'copilot' delegates to the Copilot CLI via github-copilot-sdk "
            "(uses GITHUB_TOKEN or GH_TOKEN, falls back to 'gh auth' login)."
        ),
    )
    args = parser.parse_args()

    # Configure logging so INFO-level diagnostics from the adapter and
    # backend modules are visible in the sandbox process output.
    _log_fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    logging.basicConfig(level=logging.INFO, format=_log_fmt)

    # Also write to a persistent file for post-mortem inspection via
    # docker exec <sandbox> cat /tmp/adapter.log
    try:
        _fh = logging.FileHandler("/tmp/adapter.log")
        _fh.setLevel(logging.INFO)
        _fh.setFormatter(logging.Formatter(_log_fmt))
        logging.getLogger().addHandler(_fh)
        logging.getLogger(__name__).info("File logging enabled at /tmp/adapter.log")
    except OSError:
        logging.getLogger(__name__).warning("Could not open /tmp/adapter.log for file logging")

    api_keys_csv = os.environ.get("II_AGENT_A2A_API_KEYS", "").strip()
    allowed_keys: Optional[frozenset[str]] = (
        frozenset(_parse_allowed_keys(api_keys_csv)) if api_keys_csv else None
    )

    def _timeout_from_env(var_name: str, default: float) -> float:
        return _backend_timeout_from_env(var_name, default)

    if args.backend == "claude-code":
        from ii_agent.integrations.a2a.claude_code_backend import (
            ClaudeCodeBackend,
            ClaudeCodeConfig,
        )

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            parser.error("--backend claude-code requires ANTHROPIC_API_KEY to be set")
        cc_timeout = _timeout_from_env("A2A_CLAUDE_CODE_TIMEOUT", 900.0)
        _backend = ClaudeCodeBackend(ClaudeCodeConfig(api_key=api_key, timeout=cc_timeout))
        logging.getLogger(__name__).info(
            "claude-code backend configured with per-turn timeout=%.0fs", cc_timeout
        )
        _app = create_app(backend=_backend, allowed_keys=allowed_keys)
    elif args.backend == "codex":
        from ii_agent.integrations.a2a.codex_backend import CodexBackend, CodexConfig

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            parser.error("--backend codex requires OPENAI_API_KEY to be set")
        cx_timeout = _timeout_from_env("A2A_CODEX_TIMEOUT", 900.0)
        _backend = CodexBackend(CodexConfig(api_key=api_key, timeout=cx_timeout))
        logging.getLogger(__name__).info(
            "codex backend configured with per-turn timeout=%.0fs", cx_timeout
        )
        _app = create_app(backend=_backend, allowed_keys=allowed_keys)
    elif args.backend == "copilot":
        from ii_agent.integrations.a2a.copilot_backend import CopilotBackend, CopilotConfig

        github_token = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
        # Empty token is acceptable — CopilotBackend falls back to 'gh auth' login.
        cp_timeout = _timeout_from_env("A2A_COPILOT_TIMEOUT", 900.0)
        _backend = CopilotBackend(CopilotConfig(github_token=github_token, timeout=cp_timeout))
        logging.getLogger(__name__).info(
            "copilot backend configured with per-turn timeout=%.0fs", cp_timeout
        )
        _app = create_app(backend=_backend, allowed_keys=allowed_keys)
    else:
        _app = create_app(allowed_keys=allowed_keys)

    uvicorn.run(_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
