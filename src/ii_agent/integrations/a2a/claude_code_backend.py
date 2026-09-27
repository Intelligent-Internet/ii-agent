"""Claude Code subprocess backend for the A2A adapter.

This module provides :class:`ClaudeCodeBackend`, which shells out to the
``claude`` CLI in streaming mode (``--output-format stream-json``) and maps
its JSONL event stream to A2A Server-Sent Events.

Session IDs returned by Claude Code are tracked per *context_id* to enable
``--resume`` across conversation turns within the same context.

Event mapping
-------------
Claude Code ``--output-format stream-json`` emits JSONL lines.  Each line is
mapped to zero or more A2A SSE strings:

* ``system`` (init) — **skipped** (``session_id`` is extracted internally)
* ``assistant`` / ``thinking`` block → ``assistant.reasoning_delta``
* ``assistant`` / ``text`` block → ``assistant.message_delta``
* ``assistant`` / ``tool_use`` block → ``assistant.tool_call``
* ``user`` (tool results) — **skipped** (adapter-internal implementation detail)
* ``result`` / success → ``assistant.message`` + ``assistant.usage``
* ``result`` / error → ``session.error``
* Malformed JSON or empty lines — **skipped**
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import tempfile
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

_DEFAULT_CLAUDE_BIN = "claude"
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


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ClaudeCodeConfig:
    """Configuration for the Claude Code subprocess backend.

    Attributes
    ----------
    api_key:
        Anthropic API key injected as ``ANTHROPIC_API_KEY`` into the
        subprocess environment.  Required.
    claude_bin:
        Path or name of the ``claude`` CLI binary.  Defaults to ``"claude"``
        (relies on ``PATH`` resolution).
    model:
        Model override passed via ``--model``.  Empty string (default) defers
        to the ``ANTHROPIC_MODEL`` environment variable or Claude's built-in
        default (Sonnet 4).
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
    session_idle_ttl:
        Maximum idle time (in seconds) before a session is eligible for
        reaping.  Defaults to 1800 (30 minutes).
    """

    api_key: str
    claude_bin: str = _DEFAULT_CLAUDE_BIN
    model: str = ""
    timeout: float = _DEFAULT_TIMEOUT
    cwd: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)
    session_idle_ttl: float = _DEFAULT_SESSION_IDLE_TTL


# ---------------------------------------------------------------------------
# JSONL → A2A SSE mapping (public for testing)
# ---------------------------------------------------------------------------


def parse_claude_event_line(line: str) -> list[str]:
    """Parse one JSONL line from ``claude --output-format stream-json``.

    Returns a list (possibly empty) of A2A SSE strings.

    This function is intentionally a pure transformation with no side effects
    so it can be unit-tested without any subprocess machinery.
    """
    stripped = line.strip()
    if not stripped:
        return []

    try:
        event: dict[str, Any] = json.loads(stripped)
    except json.JSONDecodeError:
        return []

    event_type: str = event.get("type", "")
    results: list[str] = []

    if event_type == "assistant":
        message = event.get("message") or {}
        content = message.get("content") or []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")

            if block_type == "thinking":
                thinking_text = block.get("thinking", "")
                if thinking_text:
                    results.append(
                        _sse(
                            "assistant.reasoning_delta",
                            {
                                "delta": thinking_text,
                                "extensions": [{"uri": REASONING_EXTENSION_URI}],
                            },
                        )
                    )

            elif block_type == "text":
                text = block.get("text", "")
                if text:
                    results.append(_sse("assistant.message_delta", {"delta": text}))

            elif block_type == "tool_use":
                tool_name = block.get("name", "")
                results.append(
                    _sse(
                        "assistant.tool_call",
                        {
                            "id": block.get("id", ""),
                            "name": tool_name,
                            "input": block.get("input") or {},
                            "extensions": [
                                {
                                    "uri": TOOL_TELEMETRY_EXTENSION_URI,
                                    "data": {"tool_name": tool_name, "phase": "pre"},
                                }
                            ],
                        },
                    )
                )

    elif event_type == "result":
        is_error: bool = bool(event.get("is_error"))
        subtype: str = event.get("subtype", "")

        if is_error or subtype == "error_during_execution":
            raw_err = event.get("error")
            if isinstance(raw_err, dict):
                error_msg: str = str(raw_err.get("message") or "Claude Code execution error")
            else:
                error_msg = str(raw_err) if raw_err else "Claude Code execution error"
            results.append(_sse("session.error", {"message": error_msg}))

        else:
            # success path
            final_result: str = event.get("result") or ""
            usage_raw: dict[str, Any] = event.get("usage") or {}
            in_tok = int(usage_raw.get("input_tokens") or 0)
            out_tok = int(usage_raw.get("output_tokens") or 0)
            usage: dict[str, Any] = {
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cache_read_input_tokens": int(usage_raw.get("cache_read_input_tokens") or 0),
                "cache_creation_input_tokens": int(
                    usage_raw.get("cache_creation_input_tokens") or 0
                ),
                "total_tokens": in_tok + out_tok,
                "backend": "claude-code",
            }
            if final_result:
                results.append(
                    _sse(
                        "assistant.message",
                        {
                            "content": final_result,
                            "tool_calls": [],
                            "extensions": [
                                {
                                    "uri": TOOL_TELEMETRY_EXTENSION_URI,
                                    "data": {"tool_count": 0},
                                }
                            ],
                        },
                    )
                )
            results.append(_sse("assistant.usage", usage))

    # "system", "user", and unknown types → no A2A events emitted
    return results


# ---------------------------------------------------------------------------
# Backend class
# ---------------------------------------------------------------------------

# Image MIME prefixes recognised for ``--image`` flag forwarding.
_IMAGE_MIME_PREFIXES = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/")


def _extract_image_paths_from_parts(
    parts: list[Any] | None,
) -> tuple[list[str], list[str]]:
    """Extract local file paths for image Parts from an A2A Part list.

    For ``FilePart`` objects with image MIME types:
    * ``FileWithUri`` with ``file://`` scheme → use path directly.
    * ``FileWithBytes`` → write base64 bytes to a temporary file.
    * ``FileWithUri`` with remote URL → logged and skipped (no download).

    Returns ``(image_paths, temp_files)`` where *temp_files* lists paths
    that should be cleaned up after the subprocess finishes.
    """
    if not parts:
        return [], []

    image_paths: list[str] = []
    temp_files: list[str] = []

    for part in parts:
        root = getattr(part, "root", part)
        # Only process FilePart with image MIME
        kind = getattr(root, "kind", "")
        if kind != "file":
            continue
        file_obj = getattr(root, "file", None)
        if file_obj is None:
            continue
        mime = getattr(file_obj, "mime_type", None) or ""
        if not mime.startswith(_IMAGE_MIME_PREFIXES):
            logger.info(
                "ClaudeCodeBackend: skipping non-image FilePart (mime=%s)",
                mime,
            )
            continue

        # FileWithUri
        uri = getattr(file_obj, "uri", None)
        if uri:
            if uri.startswith("file://"):
                image_paths.append(uri[7:])  # strip file:// prefix
            else:
                logger.warning(
                    "ClaudeCodeBackend: skipping remote image URI %s "
                    "(download not supported — use file:// or inline bytes)",
                    uri[:120],
                )
            continue

        # FileWithBytes
        b64_bytes = getattr(file_obj, "bytes", None)
        if b64_bytes:
            try:
                raw = base64.b64decode(b64_bytes)
                # Determine extension from MIME
                ext = ".png"
                if "jpeg" in mime or "jpg" in mime:
                    ext = ".jpg"
                elif "gif" in mime:
                    ext = ".gif"
                elif "webp" in mime:
                    ext = ".webp"
                fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="a2a_img_")
                os.write(fd, raw)
                os.close(fd)
                image_paths.append(tmp_path)
                temp_files.append(tmp_path)
            except Exception:
                logger.warning(
                    "ClaudeCodeBackend: failed to decode image bytes for %s",
                    getattr(file_obj, "name", "unknown"),
                    exc_info=True,
                )

    return image_paths, temp_files


def _cleanup_temp_files(paths: list[str]) -> None:
    """Remove temporary files, ignoring errors."""
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


class ClaudeCodeBackend:
    """A2A streaming backend backed by the ``claude`` CLI subprocess.

    Each call to :meth:`stream` spawns a new
    ``claude --print --output-format stream-json`` process and maps its JSONL
    output to A2A SSE strings.  The ``session_id`` emitted by Claude Code is
    stored per *context_id* and reused via ``--resume`` on subsequent turns,
    enabling persistent multi-turn conversations at the CLI level.

    Thread safety
    -------------
    Not thread-safe.  Designed for single-threaded asyncio use within one
    adapter server process.
    """

    def __init__(self, config: ClaudeCodeConfig) -> None:
        self._cfg = config
        # Maps context_id → claude session_id for --resume
        self._sessions: dict[str, str] = {}
        self._session_last_used: dict[str, float] = {}  # context_id → monotonic timestamp
        self._reaper_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_cmd(
        self, prompt: str, context_id: str, *, image_paths: list[str] | None = None, model: str = ""
    ) -> list[str]:
        """Build the ``claude`` CLI argument list for one turn.

        Parameters
        ----------
        image_paths:
            Optional list of local file paths to images.  Each path is
            passed via ``--image <path>`` to the Claude CLI which supports
            multimodal input natively.
        model:
            User-selected model ID.  When non-empty overrides
            ``ClaudeCodeConfig.model`` for this invocation.
        """
        cmd: list[str] = [
            self._cfg.claude_bin,
            "--print",
            "--output-format",
            "stream-json",
        ]
        session_id = self._sessions.get(context_id)
        if session_id:
            cmd += ["--resume", session_id]
        effective_model = model or self._cfg.model
        if effective_model:
            cmd += ["--model", effective_model]
        for img_path in image_paths or []:
            cmd += ["--image", img_path]
        cmd.append(prompt)
        return cmd

    def _build_env(self) -> dict[str, str]:
        """Build the subprocess environment, injecting the API key."""
        env = dict(os.environ)
        env["ANTHROPIC_API_KEY"] = self._cfg.api_key
        env.update(self._cfg.extra_env)
        return env

    def _update_session_id(self, line: str, context_id: str) -> None:
        """Extract a ``session_id`` from a JSONL event line and store it.

        Claude Code sets ``session_id`` on both the ``system/init`` event and
        the final ``result`` event.  Either suffices for ``--resume``.
        """
        stripped = line.strip()
        if not stripped:
            return
        try:
            event: dict[str, Any] = json.loads(stripped)
        except json.JSONDecodeError:
            return
        sid = event.get("session_id")
        if sid:
            self._sessions[context_id] = str(sid)

    def _is_error_event(self, line: str) -> bool:
        """Return ``True`` if *line* is a ``result`` event with ``is_error``."""
        stripped = line.strip()
        if not stripped:
            return False
        try:
            event: dict[str, Any] = json.loads(stripped)
        except json.JSONDecodeError:
            return False
        return bool(event.get("type") == "result" and event.get("is_error")) or (
            event.get("type") == "result" and event.get("subtype") == "error_during_execution"
        )

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
        model: str = "",
    ) -> AsyncGenerator[str, None]:
        """Yield A2A SSE strings for one ``claude`` invocation.

        Emits a ``session.task_id`` event first when *task_id* is supplied so
        that clients can associate :ref:`INPUT_REQUIRED` replies with this
        task.

        A wall-clock *timeout* is enforced per turn; the subprocess is killed
        and a ``session.error`` event is emitted on expiry.  Non-zero exit
        codes not already covered by a structured error event also emit
        ``session.error``.

        Parameters
        ----------
        parts:
            Optional list of A2A ``Part`` objects.  ``FilePart`` objects
            with image MIME types are written to temporary files and passed
            via ``--image`` to the Claude CLI.  Non-image file parts are
            logged and skipped.

        Always terminates with a ``data: [DONE]\\n\\n`` sentinel.
        """
        if task_id:
            yield _sse("session.task_id", {"task_id": task_id})
            await asyncio.sleep(0)

        self._touch_session(context_id)

        # Extract image paths from multimodal parts (write to temp files).
        image_paths, temp_files = _extract_image_paths_from_parts(parts)

        try:
            cmd = self._build_cmd(prompt, context_id, image_paths=image_paths or None, model=model)
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
                            {"message": f"Claude Code timed out after {self._cfg.timeout}s"},
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
                            {"message": f"Claude Code timed out after {self._cfg.timeout}s"},
                        )
                        yield "data: [DONE]\n\n"
                        return

                    if not raw_line:
                        break  # EOF — subprocess finished writing

                    line = raw_line.decode("utf-8", errors="replace")

                    # Track session_id before emitting SSE so --resume is set up
                    # in time for the next call to stream() on this context.
                    self._update_session_id(line, context_id)

                    # Note whether Claude itself reported an error so we don't
                    # emit a duplicate on non-zero exit code below.
                    if self._is_error_event(line):
                        error_seen = True

                    for sse_chunk in parse_claude_event_line(line):
                        yield sse_chunk
                        await asyncio.sleep(0)

            finally:
                # Always reap the subprocess to avoid zombie processes.
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()

            # Emit a generic error only when the subprocess failed and Claude did
            # not already emit a structured error event via stream-json.
            if proc.returncode != 0 and not error_seen:
                stderr_text = ""
                if proc.stderr is not None:
                    try:
                        raw_err = await asyncio.wait_for(proc.stderr.read(), timeout=5.0)
                        stderr_text = raw_err.decode("utf-8", errors="replace").strip()
                    except asyncio.TimeoutError:
                        stderr_text = "<stderr read timeout>"
                msg = f"Claude Code exited with code {proc.returncode}"
                if stderr_text:
                    msg += f": {stderr_text[:500]}"
                yield _sse("session.error", {"message": msg})

            yield "data: [DONE]\n\n"
        finally:
            # Clean up any temporary image files we wrote for --image flags.
            _cleanup_temp_files(temp_files)

    # ------------------------------------------------------------------
    # Session reaper
    # ------------------------------------------------------------------

    def _touch_session(self, context_id: str) -> None:
        """Record the current time as the last-used timestamp for a session."""
        self._session_last_used[context_id] = time.monotonic()

    async def _reap_idle_sessions(self) -> int:
        """Remove sessions that have been idle longer than the configured TTL.

        Returns the number of sessions reaped.
        """
        ttl = self._cfg.session_idle_ttl
        now = time.monotonic()
        stale: list[str] = [ctx for ctx, ts in self._session_last_used.items() if (now - ts) > ttl]
        for ctx in stale:
            sid = self._sessions.pop(ctx, None)
            self._session_last_used.pop(ctx, None)
            logger.info("ClaudeCodeBackend: reaped idle session %s (context=%s)", sid, ctx)
        return len(stale)

    async def _reaper_loop(self) -> None:
        """Background loop that periodically reaps idle sessions."""
        while True:
            try:
                await asyncio.sleep(_REAPER_INTERVAL)
                reaped = await self._reap_idle_sessions()
                if reaped:
                    logger.info("ClaudeCodeBackend: reaper swept %d idle sessions", reaped)
            except asyncio.CancelledError:
                logger.info("ClaudeCodeBackend: session reaper cancelled")
                break
            except Exception:
                logger.exception("ClaudeCodeBackend: error in session reaper loop")

    def start_reaper(self) -> None:
        """Start the background session reaper task (idempotent)."""
        if self._reaper_task is None or self._reaper_task.done():
            self._reaper_task = asyncio.create_task(self._reaper_loop())
            logger.info(
                "ClaudeCodeBackend: session reaper started (ttl=%.0fs, interval=%.0fs)",
                self._cfg.session_idle_ttl,
                _REAPER_INTERVAL,
            )

    def stop_reaper(self) -> None:
        """Cancel the background session reaper task."""
        if self._reaper_task is not None and not self._reaper_task.done():
            self._reaper_task.cancel()

    def evict_session(self, context_id: str) -> None:
        """Immediately remove a session by context_id (e.g. on session delete)."""
        sid = self._sessions.pop(context_id, None)
        self._session_last_used.pop(context_id, None)
        if sid:
            logger.info("ClaudeCodeBackend: evicted session %s (context=%s)", sid, context_id)

    @property
    def session_count(self) -> int:
        """Return the number of active tracked sessions."""
        return len(self._sessions)
