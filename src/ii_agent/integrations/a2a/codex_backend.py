"""OpenAI Codex CLI subprocess backend for the A2A adapter.

This module provides :class:`CodexBackend`, which shells out to the
``codex`` CLI in full-auto headless mode (``--full-auto --no-sandbox``) and
maps its stdout (JSONL or plain text) to A2A Server-Sent Events.

The Codex CLI is cost-optimised for shell/file/code tasks using o4-mini
by default.  It is the lowest-cost API-call option of the three evaluated
backends — ~$0.56/session (cached) vs $0.70 for Claude Sonnet 4.6.

Design constraints
------------------
* **No nested Docker**: ``--no-sandbox`` is mandatory when running inside the
  ii-agent sandbox container to avoid the Docker-in-Docker overhead that
  Codex's built-in sandbox would otherwise impose.
* **Conversation continuation**: Codex supports ``--conversation-id ID``
  to splice back into a prior conversation.  This is less persistent than
  Claude Code's ``--resume SESSION_ID`` (the conversation history lives in
  process memory, not a local file), so continuation is best-effort.
* **Output format**: The adapter attempts to parse each stdout line as JSON
  first; non-JSON lines are treated as streaming assistant text.  This
  tolerates both ``--output json`` structured mode and default text output.

JSONL event mapping
-------------------
When ``codex`` emits structured JSON lines, each is mapped as follows:

* ``system`` / ``init`` — skipped; ``conversation_id`` extracted internally
* ``message`` (assistant role) — ``assistant.message_delta``
* ``reasoning`` — ``assistant.reasoning_delta`` (o3, if streamed)
* ``tool_call`` — ``assistant.tool_call``
* ``tool_result`` / ``tool_output`` — skipped (adapter-internal)
* ``done`` / ``completion`` — ``assistant.message`` + ``assistant.usage``
* ``error`` — ``session.error``
* Plain text (non-JSON) — ``assistant.message_delta``
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from ii_agent.integrations.a2a.extension_utils import (
    REASONING_EXTENSION_URI,
    TOOL_TELEMETRY_EXTENSION_URI,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CODEX_BIN = "codex"
_DEFAULT_TIMEOUT = 300.0  # seconds per turn
_DEFAULT_SESSION_IDLE_TTL = 1800.0  # seconds before an idle session is reaped (30 min)
_REAPER_INTERVAL = 60.0  # seconds between reaper sweeps

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sse(event_type: str, data: dict[str, Any]) -> str:
    """Format one A2A Server-Sent Event string."""
    payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=True)
    return f"data: {payload}\n\n"


def _try_parse_json(line: str) -> dict[str, Any] | None:
    """Return parsed JSON dict or None if parsing fails."""
    stripped = line.strip()
    if not stripped:
        return None
    try:
        obj = json.loads(stripped)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class CodexConfig:
    """Configuration for the OpenAI Codex CLI subprocess backend.

    Attributes
    ----------
    api_key:
        OpenAI API key injected as ``OPENAI_API_KEY`` into the subprocess
        environment.  Required.
    codex_bin:
        Path or name of the ``codex`` CLI binary.  Defaults to ``"codex"``
        (relies on ``PATH`` resolution).
    model:
        Model override passed via ``--model``.  Empty string (default) defers
        to ``OPENAI_MODEL`` env var or Codex's built-in default (o4-mini).
    timeout:
        Maximum per-turn wall-clock time in seconds.  The subprocess is killed
        and a ``session.error`` event is emitted on expiry.  Defaults to
        300 s.
    cwd:
        Working directory for the subprocess.  ``None`` inherits the parent
        process CWD.
    extra_env:
        Additional environment variables merged into the subprocess env after
        the parent environment and the API key.
    instructions:
        Optional system-level instructions injected via ``--instructions``.
        Empty string (default) omits this flag.
    session_idle_ttl:
        Maximum idle time (in seconds) before a session is eligible for
        reaping.  Defaults to 1800 (30 minutes).
    """

    api_key: str
    codex_bin: str = _DEFAULT_CODEX_BIN
    model: str = ""
    timeout: float = _DEFAULT_TIMEOUT
    cwd: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)
    instructions: str = ""
    session_idle_ttl: float = _DEFAULT_SESSION_IDLE_TTL


# ---------------------------------------------------------------------------
# JSONL / text → A2A SSE mapping (public for testing)
# ---------------------------------------------------------------------------


class CodexLineResult:
    """Structured result from :func:`parse_codex_line`.

    Attributes
    ----------
    sse_events:
        Zero or more A2A SSE strings to emit immediately.
    text_fragment:
        Plain text extracted from this line that should be accumulated by the
        caller and included in the final ``assistant.message`` event.  Empty
        string if no text was extracted.
    conversation_id:
        Conversation/session ID seen in this line (e.g. from a ``system``
        init event).  Empty string if not present.
    usage:
        Token-usage dict seen in this line (from a ``done``/``completion``
        event).  Empty dict if not present.
    is_error:
        ``True`` when this line signals an error termination.
    """

    __slots__ = ("sse_events", "text_fragment", "conversation_id", "usage", "is_error")

    def __init__(
        self,
        *,
        sse_events: list[str] | None = None,
        text_fragment: str = "",
        conversation_id: str = "",
        usage: dict[str, Any] | None = None,
        is_error: bool = False,
    ) -> None:
        self.sse_events: list[str] = sse_events or []
        self.text_fragment = text_fragment
        self.conversation_id = conversation_id
        self.usage: dict[str, Any] = usage or {}
        self.is_error = is_error


def parse_codex_line(line: str) -> CodexLineResult:
    """Parse one stdout line from ``codex --full-auto --no-sandbox``.

    This is public and side-effect-free for unit-testing purposes.

    The function tries JSON parsing first; non-JSON lines are treated as
    streaming plain-text assistant output and add to *text_fragment*.
    """
    stripped = line.strip()
    if not stripped:
        return CodexLineResult()

    obj = _try_parse_json(stripped)

    if obj is None:
        # Plain text streaming — treat as assistant text delta.
        return CodexLineResult(
            sse_events=[_sse("assistant.message_delta", {"delta": stripped})],
            text_fragment=stripped,
        )

    event_type: str = str(obj.get("type") or "")

    # ------------------------------------------------------------------
    # system / init — extract conversation_id; no SSE emitted.
    # ------------------------------------------------------------------
    if event_type in ("system", "init"):
        conv_id = str(obj.get("conversation_id") or obj.get("session_id") or "")
        return CodexLineResult(conversation_id=conv_id)

    # ------------------------------------------------------------------
    # message (assistant role) — emit message_delta.
    # ------------------------------------------------------------------
    if event_type == "message":
        role = str(obj.get("role") or "").lower()
        if role not in ("", "assistant"):
            # user / tool messages: skip
            return CodexLineResult()
        content = obj.get("content") or ""
        if isinstance(content, list):
            # OpenAI content-array format: [{type: "text", text: "..."}]
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif isinstance(item, str):
                    parts.append(item)
            content = "".join(parts)
        text: str = str(content)
        if not text:
            return CodexLineResult()
        return CodexLineResult(
            sse_events=[_sse("assistant.message_delta", {"delta": text})],
            text_fragment=text,
        )

    # ------------------------------------------------------------------
    # reasoning — emit reasoning_delta (o3 extended thinking).
    # ------------------------------------------------------------------
    if event_type == "reasoning":
        reasoning_text = str(obj.get("content") or obj.get("text") or "")
        if not reasoning_text:
            return CodexLineResult()
        return CodexLineResult(
            sse_events=[
                _sse(
                    "assistant.reasoning_delta",
                    {
                        "delta": reasoning_text,
                        "extensions": [{"uri": REASONING_EXTENSION_URI}],
                    },
                )
            ]
        )

    # ------------------------------------------------------------------
    # tool_call — emit assistant.tool_call.
    # ------------------------------------------------------------------
    if event_type == "tool_call":
        tool_id: str = str(obj.get("id") or obj.get("call_id") or "")
        tool_name: str = str(obj.get("name") or obj.get("function") or "")
        raw_args = obj.get("arguments") or obj.get("input") or {}
        if isinstance(raw_args, str):
            try:
                tool_input = json.loads(raw_args)
            except json.JSONDecodeError:
                tool_input = {"raw": raw_args}
        else:
            tool_input = raw_args
        return CodexLineResult(
            sse_events=[
                _sse(
                    "assistant.tool_call",
                    {
                        "id": tool_id,
                        "name": tool_name,
                        "input": tool_input,
                        "extensions": [
                            {
                                "uri": TOOL_TELEMETRY_EXTENSION_URI,
                                "data": {"tool_name": tool_name, "phase": "pre"},
                            }
                        ],
                    },
                )
            ]
        )

    # ------------------------------------------------------------------
    # tool_result / tool_output — skip (adapter-internal detail).
    # ------------------------------------------------------------------
    if event_type in ("tool_result", "tool_output", "function_call_output"):
        return CodexLineResult()

    # ------------------------------------------------------------------
    # done / completion — emit usage; optionally carry final text.
    # ------------------------------------------------------------------
    if event_type in ("done", "completion"):
        usage_raw: dict[str, Any] = obj.get("usage") or {}
        in_tok = int(usage_raw.get("input_tokens") or usage_raw.get("prompt_tokens") or 0)
        out_tok = int(usage_raw.get("output_tokens") or usage_raw.get("completion_tokens") or 0)
        reasoning_tok = int(
            usage_raw.get("reasoning_tokens")
            or (usage_raw.get("completion_tokens_details") or {}).get("reasoning_tokens")
            or 0
        )
        usage_data: dict[str, Any] = {
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "reasoning_tokens": reasoning_tok,
            "total_tokens": in_tok + out_tok,
            "backend": "codex",
        }
        conv_id = str(obj.get("conversation_id") or "")
        # Some Codex versions include final result text in the done event.
        final_text = str(obj.get("result") or obj.get("content") or "")
        return CodexLineResult(
            usage=usage_data,
            text_fragment=final_text,
            conversation_id=conv_id,
        )

    # ------------------------------------------------------------------
    # error — emit session.error.
    # ------------------------------------------------------------------
    if event_type == "error":
        raw_err = obj.get("message") or obj.get("error") or "Codex execution error"
        return CodexLineResult(
            sse_events=[_sse("session.error", {"message": str(raw_err)})],
            is_error=True,
        )

    # Anything else: try to extract text content and emit as delta.
    fallback_text = str(obj.get("content") or obj.get("text") or "")
    if fallback_text:
        return CodexLineResult(
            sse_events=[_sse("assistant.message_delta", {"delta": fallback_text})],
            text_fragment=fallback_text,
        )
    return CodexLineResult()


# ---------------------------------------------------------------------------
# Backend class
# ---------------------------------------------------------------------------


class CodexBackend:
    """A2A streaming backend backed by the ``codex`` CLI subprocess.

    Each call to :meth:`stream` spawns a new
    ``codex --full-auto --no-sandbox`` process and maps its stdout to A2A
    SSE strings.  Conversation IDs extracted from Codex output are stored per
    *context_id* and reused via ``--conversation-id`` on subsequent turns to
    maintain context continuity.

    .. note::

        ``--no-sandbox`` is mandatory inside the ii-agent sandbox container.
        Without it, Codex would attempt to start its own Docker micro-sandbox,
        causing a nested-container conflict.

    Thread safety
    -------------
    Not thread-safe.  Designed for single-threaded asyncio use within one
    adapter server process.
    """

    def __init__(self, config: CodexConfig) -> None:
        self._cfg = config
        # Maps context_id → codex conversation_id for --conversation-id
        self._conversations: dict[str, str] = {}
        self._session_last_used: dict[str, float] = {}  # context_id → monotonic timestamp
        self._reaper_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_cmd(self, prompt: str, context_id: str) -> list[str]:
        """Build the ``codex`` CLI argument list for one turn."""
        cmd: list[str] = [
            self._cfg.codex_bin,
            "--full-auto",
            "--no-sandbox",
        ]
        conv_id = self._conversations.get(context_id)
        if conv_id:
            cmd += ["--conversation-id", conv_id]
        if self._cfg.model:
            cmd += ["--model", self._cfg.model]
        if self._cfg.instructions:
            cmd += ["--instructions", self._cfg.instructions]
        cmd.append(prompt)
        return cmd

    def _build_env(self) -> dict[str, str]:
        """Build the subprocess environment, injecting the API key."""
        env = dict(os.environ)
        env["OPENAI_API_KEY"] = self._cfg.api_key
        env.update(self._cfg.extra_env)
        return env

    def _apply_line_result(self, result: CodexLineResult, context_id: str) -> None:
        """Persist side-effects from a parsed line (conversation_id update)."""
        if result.conversation_id:
            self._conversations[context_id] = result.conversation_id

    # ------------------------------------------------------------------
    # Public streaming interface
    # ------------------------------------------------------------------

    async def stream(
        self,
        prompt: str,
        context_id: str = "default",
        task_id: str | None = None,
        *,
        parts: list[Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Yield A2A SSE strings for one ``codex`` invocation.

        Emits a ``session.task_id`` event first when *task_id* is supplied.

        Text output from Codex is accumulated and emitted as a single
        ``assistant.message`` event at the end of the stream so that
        downstream handlers can surface the complete response body.  Individual
        text chunks are also emitted as ``assistant.message_delta`` events as
        they arrive.

        A wall-clock *timeout* is enforced per turn; on expiry the subprocess
        is killed and ``session.error`` + ``[DONE]`` are emitted.  Non-zero
        exit codes without a prior structured error event also produce
        ``session.error``.

        Parameters
        ----------
        parts:
            Optional list of A2A ``Part`` objects.  Codex CLI is text-only;
            any non-text parts are logged and skipped.

        Always terminates with ``data: [DONE]\\n\\n``.
        """
        if parts:
            from a2a.types import TextPart as _TextPart

            non_text = [p for p in parts if not isinstance(getattr(p, "root", p), _TextPart)]
            if non_text:
                logger.warning(
                    "CodexBackend: %d multimodal part(s) ignored — "
                    "Codex CLI does not support non-text input (context_id=%s)",
                    len(non_text),
                    context_id,
                )
        if task_id:
            yield _sse("session.task_id", {"task_id": task_id})
            await asyncio.sleep(0)

        self._touch_session(context_id)

        cmd = self._build_cmd(prompt, context_id)
        env = self._build_env()

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self._cfg.cwd,
        )

        loop = asyncio.get_event_loop()
        deadline = loop.time() + self._cfg.timeout

        accumulated_text: list[str] = []
        final_usage: dict[str, Any] = {}
        error_seen = False

        try:
            assert proc.stdout is not None
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    proc.kill()
                    await proc.wait()
                    yield _sse(
                        "session.error",
                        {"message": f"Codex timed out after {self._cfg.timeout}s"},
                    )
                    yield "data: [DONE]\n\n"
                    return

                try:
                    raw_line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    yield _sse(
                        "session.error",
                        {"message": f"Codex timed out after {self._cfg.timeout}s"},
                    )
                    yield "data: [DONE]\n\n"
                    return

                if not raw_line:
                    break  # EOF

                line = raw_line.decode("utf-8", errors="replace")
                result = parse_codex_line(line)

                self._apply_line_result(result, context_id)

                if result.is_error:
                    error_seen = True

                if result.text_fragment:
                    accumulated_text.append(result.text_fragment)

                if result.usage:
                    final_usage = result.usage

                for sse_chunk in result.sse_events:
                    yield sse_chunk
                    await asyncio.sleep(0)

        finally:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()

        # Non-zero exit without a structured error event → generic error.
        if proc.returncode != 0 and not error_seen:
            stderr_text = ""
            if proc.stderr is not None:
                try:
                    raw_err = await asyncio.wait_for(proc.stderr.read(), timeout=5.0)
                    stderr_text = raw_err.decode("utf-8", errors="replace").strip()
                except asyncio.TimeoutError:
                    stderr_text = "<stderr read timeout>"
            msg = f"Codex exited with code {proc.returncode}"
            if stderr_text:
                msg += f": {stderr_text[:500]}"
            yield _sse("session.error", {"message": msg})
            yield "data: [DONE]\n\n"
            return

        if not error_seen:
            # Emit the final assembled message.
            full_text = "\n".join(accumulated_text).strip()
            if full_text:
                yield _sse(
                    "assistant.message",
                    {
                        "content": full_text,
                        "tool_calls": [],
                        "extensions": [
                            {
                                "uri": TOOL_TELEMETRY_EXTENSION_URI,
                                "data": {"tool_count": 0},
                            }
                        ],
                    },
                )
                await asyncio.sleep(0)

            # Emit usage (zero-filled if Codex did not report it).
            usage_out: dict[str, Any] = (
                final_usage
                if final_usage
                else {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_tokens": 0,
                    "total_tokens": 0,
                }
            )
            usage_out.setdefault("backend", "codex")
            yield _sse("assistant.usage", usage_out)
            await asyncio.sleep(0)

        yield "data: [DONE]\n\n"

    # ------------------------------------------------------------------
    # Session reaper
    # ------------------------------------------------------------------

    def _touch_session(self, context_id: str) -> None:
        """Record the current time as the last-used timestamp for a session."""
        self._session_last_used[context_id] = time.monotonic()

    async def _reap_idle_sessions(self) -> int:
        """Remove conversations that have been idle longer than the configured TTL.

        Returns the number of conversations reaped.
        """
        ttl = self._cfg.session_idle_ttl
        now = time.monotonic()
        stale: list[str] = [ctx for ctx, ts in self._session_last_used.items() if (now - ts) > ttl]
        for ctx in stale:
            conv_id = self._conversations.pop(ctx, None)
            self._session_last_used.pop(ctx, None)
            logger.info("CodexBackend: reaped idle conversation %s (context=%s)", conv_id, ctx)
        return len(stale)

    async def _reaper_loop(self) -> None:
        """Background loop that periodically reaps idle sessions."""
        while True:
            try:
                await asyncio.sleep(_REAPER_INTERVAL)
                reaped = await self._reap_idle_sessions()
                if reaped:
                    logger.info("CodexBackend: reaper swept %d idle conversations", reaped)
            except asyncio.CancelledError:
                logger.info("CodexBackend: session reaper cancelled")
                break
            except Exception:
                logger.exception("CodexBackend: error in session reaper loop")

    def start_reaper(self) -> None:
        """Start the background session reaper task (idempotent)."""
        if self._reaper_task is None or self._reaper_task.done():
            self._reaper_task = asyncio.create_task(self._reaper_loop())
            logger.info(
                "CodexBackend: session reaper started (ttl=%.0fs, interval=%.0fs)",
                self._cfg.session_idle_ttl,
                _REAPER_INTERVAL,
            )

    def stop_reaper(self) -> None:
        """Cancel the background session reaper task."""
        if self._reaper_task is not None and not self._reaper_task.done():
            self._reaper_task.cancel()

    def evict_session(self, context_id: str) -> None:
        """Immediately remove a conversation by context_id (e.g. on session delete)."""
        conv_id = self._conversations.pop(context_id, None)
        self._session_last_used.pop(context_id, None)
        if conv_id:
            logger.info("CodexBackend: evicted conversation %s (context=%s)", conv_id, context_id)

    @property
    def session_count(self) -> int:
        """Return the number of active tracked conversations."""
        return len(self._conversations)
