"""GitHub Copilot CLI A2A adapter backend.

This module provides :class:`CopilotBackend`, which uses the
``github-copilot-sdk`` (``copilot`` Python package) to connect to a running
Copilot CLI process via JSON-RPC and maps its event stream to A2A
Server-Sent Events.

This is the **primary** inner-loop replacement backend.  The architecture
follows the design specified in
``docs/design-docs/a2a-copilot-cli-inner-loop-strategy.md`` §B.5:

    ii-agent ──A2A SSE──▶ adapter_server.py ──SDK JSON-RPC──▶ Copilot CLI
                                   │
                           [CopilotBackend here]

The Copilot SDK lives *inside* this adapter process.  ii-agent's codebase
has no direct SDK dependency; it only sees the A2A HTTP interface served by
``adapter_server.py``.

Session lifecycle
-----------------
* A single :class:`CopilotClient` is lazily started on the first call and
  shared for the lifetime of the backend instance.
* Sessions are keyed by ``context_id`` so multi-turn conversations reuse the
  same CLI session, preserving Copilot's in-process conversation history.
* On the first call for a ``context_id`` a new CLI session is created.
* On subsequent calls the session is resumed via ``session_id``.

SDK event → A2A SSE mapping
----------------------------
=====================================================  ==========================================
SDK ``SessionEventType``                               A2A SSE event type
=====================================================  ==========================================
``ASSISTANT_MESSAGE_DELTA``                            ``assistant.message_delta``
``ASSISTANT_REASONING_DELTA``                          ``assistant.reasoning_delta``
``ASSISTANT_REASONING``                                ``assistant.reasoning``
``ASSISTANT_MESSAGE``                                  ``assistant.message``
``ASSISTANT_USAGE``                                    ``assistant.usage``
``SESSION_ERROR``                                      ``session.error``
``SESSION_IDLE`` / ``ASSISTANT_TURN_END`` / ``ABORT``  *(end-of-turn sentinel — triggers [DONE])*
all others                                             *(skipped)*
=====================================================  ==========================================

Tool-call events (``TOOL_EXECUTION_START``, ``TOOL_EXECUTION_COMPLETE``, etc.)
are skipped at the A2A level; Copilot handles tool execution autonomously
inside the CLI session.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
import uuid as _uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from ii_agent.integrations.a2a.extension_utils import (
    REASONING_EXTENSION_URI,
    TOOL_TELEMETRY_EXTENSION_URI,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CLI_PATH = "gh"  # GitHub CLI; Copilot CLI runs as `gh copilot agent`
_DEFAULT_TIMEOUT = 300.0  # seconds per turn
_DEFAULT_SESSION_IDLE_TTL = 1800.0  # seconds before an idle session is reaped (30 min)
_REAPER_INTERVAL = 60.0  # seconds between reaper sweeps
_HEARTBEAT_INTERVAL = 15.0  # seconds between heartbeat SSE events during tool execution


@dataclass
class _ToolExecutionRequest:
    """Sentinel injected into the event queue by SDK tool handlers.

    When the Copilot CLI invokes a bridged native tool the SDK handler puts
    one of these into the main event queue.  :meth:`CopilotBackend._run_turn`
    detects it, yields a ``tool.execution_request`` SSE event, and the
    ii-agent inner loop on the other side of the HTTP stream executes the
    tool and POSTs the result back.
    """

    data: dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sse(event_type: str, data: dict[str, Any]) -> str:
    """Format one A2A Server-Sent Event string."""
    payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=True)
    return f"data: {payload}\n\n"


# Image MIME prefixes for attachment conversion.
_IMAGE_MIME_PREFIXES = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/")


def _parts_to_attachments(
    parts: list[Any] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Convert A2A ``Part`` objects to Copilot SDK attachment dicts.

    The Copilot SDK ``Attachment`` union supports ``FileAttachment``,
    ``DirectoryAttachment``, and ``SelectionAttachment``.  All require a
    local file path — there is no inline/blob type.

    For ``FileWithUri`` with ``file://`` scheme we use ``file`` attachments.
    For ``FileWithBytes`` we decode the base64 data, write it to a temp file,
    and create a ``file`` attachment pointing at that path.  The caller is
    responsible for cleaning up *temp_files* after the SDK call completes.

    Returns ``(attachments, temp_files)`` where *temp_files* lists paths
    that should be cleaned up after the SDK call completes.
    """
    if not parts:
        return [], []

    import base64
    import tempfile

    attachments: list[dict[str, Any]] = []
    temp_files: list[str] = []

    # Map MIME type to file extension for temp file creation.
    _MIME_EXT: dict[str, str] = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }

    for part in parts:
        root = getattr(part, "root", part)
        kind = getattr(root, "kind", "")
        if kind != "file":
            continue
        file_obj = getattr(root, "file", None)
        if file_obj is None:
            continue
        mime = getattr(file_obj, "mime_type", None) or ""
        if not mime.startswith(_IMAGE_MIME_PREFIXES):
            logger.info(
                "CopilotBackend: skipping non-image FilePart (mime=%s)",
                mime,
            )
            continue

        # FileWithUri
        uri = getattr(file_obj, "uri", None)
        if uri:
            if uri.startswith("file://"):
                attachments.append({"type": "file", "path": uri[7:]})
            else:
                # Remote URL — download to temp file so the SDK can attach it.
                ext = _MIME_EXT.get(mime, ".bin")
                try:
                    import httpx as _httpx

                    resp = _httpx.get(uri, timeout=30.0, follow_redirects=True)
                    resp.raise_for_status()
                    fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="copilot_attach_")
                    os.write(fd, resp.content)
                    os.close(fd)
                    attachments.append({"type": "file", "path": tmp_path})
                    temp_files.append(tmp_path)
                    logger.info(
                        "CopilotBackend: downloaded remote image %s to %s (%d bytes)",
                        uri[:120],
                        tmp_path,
                        len(resp.content),
                    )
                except Exception as dl_exc:
                    logger.warning(
                        "CopilotBackend: failed to download remote image URI %s: %s",
                        uri[:120],
                        dl_exc,
                    )
            continue

        # FileWithBytes — SDK has no blob/inline type; write to temp file.
        b64_bytes = getattr(file_obj, "bytes", None)
        if b64_bytes:
            ext = _MIME_EXT.get(mime, ".bin")
            try:
                raw_data = base64.b64decode(b64_bytes)
                fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="copilot_attach_")
                os.write(fd, raw_data)
                os.close(fd)
                attachments.append({"type": "file", "path": tmp_path})
                temp_files.append(tmp_path)
            except Exception as write_exc:
                logger.warning(
                    "CopilotBackend: failed to write base64 attachment to temp file: %s",
                    write_exc,
                )
            continue

    return attachments, temp_files


def _cleanup_temp_files(paths: list[str]) -> None:
    """Remove temporary files, ignoring errors."""
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class CopilotConfig:
    """Configuration for the Copilot CLI A2A adapter backend.

    Attributes
    ----------
    github_token:
        GitHub personal access token with Copilot scope.  When empty the SDK
        falls back to the token from the ``gh`` CLI login (i.e. the already
        authenticated ``gh`` user).  Most sandbox deployments should leave
        this empty and rely on the host ``gh auth`` state.
    cli_path:
        Path or name of the GitHub CLI binary.  Defaults to ``"gh"`` (relies
        on ``PATH`` resolution, Copilot CLI is the ``gh copilot`` extension).
    model:
        Model override forwarded as ``SessionConfig.model``.  Empty string
        (default) lets Copilot use its own model selection policy.
    timeout:
        Maximum per-turn wall-clock time in seconds.  The per-event wait
        inside the stream is bounded by this value.
    working_directory:
        Working directory for the Copilot CLI process.  ``None`` defaults to
        ``/workspace`` (the standard ii-agent sandbox workspace path).
    extra_env:
        Additional environment variables merged into the subprocess environment.
    session_idle_ttl:
        Maximum idle time (in seconds) before a session is eligible for
        reaping.  Defaults to 1800 (30 minutes).
    """

    github_token: str = ""
    cli_path: str = _DEFAULT_CLI_PATH
    model: str = ""
    timeout: float = _DEFAULT_TIMEOUT
    working_directory: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)
    session_idle_ttl: float = _DEFAULT_SESSION_IDLE_TTL
    # Copilot infinite-session compaction controls.
    # background_compaction_threshold: context-utilisation ratio (0.0–1.0)
    # at which the SDK begins async compaction.  ``None`` uses the SDK
    # default (0.80).  Set to ``1.0`` to effectively disable background
    # compaction so that ii-agent retains sole compaction authority.
    background_compaction_threshold: float | None = None
    # buffer_exhaustion_threshold: context-utilisation ratio (0.0–1.0) at
    # which the SDK blocks until compaction completes.  ``None`` uses the
    # SDK default (0.95).
    buffer_exhaustion_threshold: float | None = None


# ---------------------------------------------------------------------------
# Event parser
# ---------------------------------------------------------------------------


def parse_copilot_event(event: Any) -> list[str]:
    """Map one Copilot SDK ``SessionEvent`` to zero or more A2A SSE strings.

    Parameters
    ----------
    event:
        A :class:`copilot.types.SessionEvent` (or compatible object with
        ``.type`` and ``.data`` attributes).

    Returns
    -------
    list[str]
        Zero or more A2A SSE-formatted strings ready to yield to the HTTP
        client.  An empty list means the event is skipped.

    Notes
    -----
    This function is intentionally a pure function (no side-effects) so it
    can be unit-tested without SDK or network access.
    """
    from copilot.generated.session_events import SessionEventType  # local import for testability

    sse_events: list[str] = []
    data = event.data
    event_type = event.type

    if event_type == SessionEventType.ASSISTANT_MESSAGE_DELTA:
        delta = getattr(data, "delta_content", None) or ""
        if delta:
            sse_events.append(_sse("assistant.message_delta", {"delta": delta}))

    elif event_type == SessionEventType.ASSISTANT_REASONING_DELTA:
        delta = getattr(data, "delta_content", None) or ""
        if delta:
            sse_events.append(
                _sse(
                    "assistant.reasoning_delta",
                    {
                        "delta": delta,
                        "extensions": [{"uri": REASONING_EXTENSION_URI}],
                    },
                )
            )

    elif event_type == SessionEventType.ASSISTANT_REASONING:
        content = (
            getattr(data, "reasoning_text", None) or getattr(data, "reasoning_opaque", None) or ""
        )
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        if content:
            sse_events.append(
                _sse(
                    "assistant.reasoning",
                    {
                        "content": content,
                        "extensions": [{"uri": REASONING_EXTENSION_URI}],
                    },
                )
            )

    elif event_type == SessionEventType.ASSISTANT_MESSAGE:
        content = getattr(data, "content", None) or ""
        tool_requests = getattr(data, "tool_requests", None) or []
        tool_calls = [
            {
                "id": getattr(tr, "tool_call_id", ""),
                "name": getattr(tr, "name", ""),
                "arguments": getattr(tr, "arguments", None) or {},
                "extensions": [{"uri": TOOL_TELEMETRY_EXTENSION_URI}],
            }
            for tr in tool_requests
        ]
        sse_events.append(
            _sse(
                "assistant.message",
                {"content": content, "tool_calls": tool_calls},
            )
        )

    elif event_type == SessionEventType.ASSISTANT_USAGE:
        input_tokens = int(getattr(data, "input_tokens", None) or 0)
        output_tokens = int(getattr(data, "output_tokens", None) or 0)
        cache_read = int(getattr(data, "cache_read_tokens", None) or 0)
        cache_write = int(getattr(data, "cache_write_tokens", None) or 0)
        cost = float(getattr(data, "cost", None) or 0.0)
        duration = float(getattr(data, "duration", None) or 0.0)
        premium_requests = int(getattr(data, "total_premium_requests", None) or 0)
        total_tokens = input_tokens + output_tokens
        sse_events.append(
            _sse(
                "assistant.usage",
                {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "cache_read_tokens": cache_read,
                    "cache_write_tokens": cache_write,
                    "cost": cost,
                    "duration": duration,
                    "premium_requests": premium_requests,
                    "backend": "copilot",
                    "extensions": [{"uri": TOOL_TELEMETRY_EXTENSION_URI}],
                },
            )
        )

    elif event_type == SessionEventType.SESSION_ERROR:
        message = getattr(data, "message", None) or "Copilot CLI reported an error"
        error_type = getattr(data, "error_type", None)
        payload: dict[str, Any] = {"message": message}
        if error_type:
            payload["error_type"] = error_type
        sse_events.append(_sse("session.error", payload))

    # All other event types are skipped (tool execution, session lifecycle, etc.)
    return sse_events


# ---------------------------------------------------------------------------
# Tool system message builder
# ---------------------------------------------------------------------------


def _build_tool_system_message(tool_schemas: list[dict[str, Any]]) -> str:
    """Build a system message addendum describing bridged tools.

    The Copilot CLI's underlying LLM needs explicit instructions that
    custom tools are available and what capabilities they provide.
    Without this, the LLM may refuse tasks it could accomplish using the
    bridged tools (e.g. browser automation, web search).

    Returns an empty string if there are no schemas.
    """
    if not tool_schemas:
        return ""

    # Categorize tools for a concise description.
    browser_tools: list[str] = []
    web_tools: list[str] = []
    dev_tools: list[str] = []
    other_tools: list[str] = []

    for schema in tool_schemas:
        name = schema.get("name", "")
        desc = schema.get("description", "")
        entry = f"- **{name}**: {desc}" if desc else f"- **{name}**"

        if name.startswith("browser_"):
            browser_tools.append(entry)
        elif "web" in name.lower() or "search" in name.lower() or "image_search" in name.lower():
            web_tools.append(entry)
        elif name in (
            "fullstack_project_init",
            "register_deployment",
            "add_user_env",
            "ask_user_env",
            "ask_user_select",
            "get_database_connection",
        ):
            dev_tools.append(entry)
        else:
            other_tools.append(entry)

    sections: list[str] = []
    sections.append(
        "# Custom Tools Available\n\n"
        "You have access to custom tools that extend your capabilities beyond "
        "the built-in file and shell tools. These tools are executed by the host "
        "system on your behalf — you MUST use them when the task requires their "
        "capabilities. Do NOT refuse tasks by claiming you lack these capabilities."
    )

    if browser_tools:
        sections.append(
            "\n\n## Browser Automation Tools\n\n"
            "You have a **real Chromium browser** running in your environment. "
            "You can navigate to any URL, click elements, fill forms, scroll, "
            "take screenshots, and interact with web pages. Use these tools "
            "to accomplish any web browsing task the user requests.\n\n"
            "### Workflow\n\n"
            "1. Before activating browser automation, try the `web_visit` tool "
            "to extract text-only content from a page.\n"
            "   - If the extracted content is sufficient, no further browser work "
            "is needed.\n"
            "   - If the page requires interaction, screenshots, authentication, "
            "or end-to-end UI testing, use the `Skill` tool with "
            '`{"skill":"agent-browser"}` (if available) to activate the browser.\n'
            "2. Use `agent-browser open <url>` to navigate, then "
            "`agent-browser snapshot -i` to collect element refs before interacting.\n"
            "3. Re-snapshot after navigation or DOM changes before reusing refs.\n\n"
            "### CAPTCHA / Anti-Bot / Manual User Handoff\n\n"
            "The browser runs in **headed mode** on a virtual display "
            "(AGENT_BROWSER_HEADED=1, DISPLAY=:99). If the site shows a CAPTCHA, "
            "bot-detection page, or requires manual human interaction:\n\n"
            "1. Navigate to the target URL with `agent-browser open <url>`.\n"
            "2. Use the `register_port` tool to expose port **6080**.\n"
            "3. Share the returned URL with the user **exactly as returned** "
            "— for port 6080 the tool already produces a ready-to-click "
            "noVNC viewer URL (`/vnc.html?autoconnect=true&password=…` "
            "baked in). Do NOT append any path or query params yourself; "
            "do NOT show the password separately. Render it as a Markdown "
            "link: `[Open noVNC viewer](<url-from-tool>)`.\n"
            "4. Tell the user to complete the CAPTCHA / manual step and let you "
            "know when done.  This is a hand-off indication to the user.\n"
            "5. Once the user confirms, consider this a hand-back indication "
            "from the user and continue the task with `agent-browser` "
            "commands (snapshot, click, fill, etc.).\n\n"
            "**You MUST use this workflow for any site that blocks automated "
            "access.** \n\n" + "\n".join(browser_tools)
        )

    if web_tools:
        sections.append(
            "\n\n## Web Search & Research Tools\n\n"
            "You can search the web and visit web pages to gather information.\n\n"
            + "\n".join(web_tools)
        )

    if dev_tools:
        sections.append("\n\n## Development Tools\n\n" + "\n".join(dev_tools))

    # Dedicated Skill tool section -— the LLM MUST know the invocation format
    skill_schema = next(
        (s for s in tool_schemas if s.get("name") == "Skill"),
        None,
    )
    if skill_schema:
        # Extract available skill names from the parameters schema description
        # or fall back to a generic example.
        sections.append(
            "\n\n## Skill Tool (CRITICAL)\n\n"
            "The `Skill` tool activates specialised skill modules. "
            "**You MUST pass a JSON argument** when calling this tool:\n\n"
            "```json\n"
            '{"skill": "<skill-name>"}\n'
            "```\n\n"
            "Examples:\n"
            '- `{"skill": "agent-browser"}` — activates browser automation\n'
            '- `{"skill": "pdf"}` — activates the PDF skill\n'
            '- `{"skill": "xlsx"}` — activates the Excel skill\n\n'
            "**Calling `Skill` without the `skill` argument will fail.** "
            'Always include `{"skill": "<name>"}` in the tool call arguments.'
        )

    if other_tools:
        # Filter out Skill from "other" since it now has its own section.
        other_tools_filtered = [t for t in other_tools if not t.startswith("- **Skill**")]
        if other_tools_filtered:
            sections.append("\n\n## Additional Tools\n\n" + "\n".join(other_tools_filtered))

    return "".join(sections)


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

# Sentinel object placed in the queue when the turn is finished.
_TURN_END = object()


class CopilotBackend:
    """A2A streaming backend backed by the GitHub Copilot CLI via the SDK.

    This class implements the duck-typed backend interface required by
    :func:`~ii_agent.integrations.a2a.adapter_server.create_app`:

    .. code-block:: python

        async def stream(
            self, prompt: str, context_id: str, task_id: str | None
        ) -> AsyncGenerator[str, None]: ...

    A single :class:`copilot.CopilotClient` is started on first use and
    shared across all streaming calls.  One Copilot CLI session is created
    per ``context_id`` and reused for subsequent turns so Copilot's
    conversation history and context window are preserved.

    Parameters
    ----------
    config:
        :class:`CopilotConfig` instance with CLI path, auth, and tuning.
    """

    # Maximum number of cached Copilot sessions.  Once the cap is reached the
    # oldest (least-recently-used) session is evicted.  This prevents unbounded
    # memory growth in long-running adapter processes with high session churn.
    _MAX_SESSIONS = 1000

    def __init__(self, config: CopilotConfig) -> None:
        self.config = config
        self._client: Any | None = None  # copilot.CopilotClient
        self._sessions: dict[str, str] = {}  # context_id → session_id
        self._session_last_used: dict[str, float] = {}  # context_id → monotonic timestamp
        self._client_lock = asyncio.Lock()
        self._reaper_task: asyncio.Task[None] | None = None
        # --- Tool bridge state ---
        # Per-turn event queue reference so SDK tool handlers can inject events.
        self._tool_stream_queue: asyncio.Queue[Any] | None = None
        self._tool_stream_loop: asyncio.AbstractEventLoop | None = None
        # Per-tool-call result delivery: tool_call_id → (asyncio.Event, [result], loop)
        self._tool_result_slots: dict[
            str, tuple[asyncio.Event, list[Any], asyncio.AbstractEventLoop]
        ] = {}
        # Track which tool schemas were used to create each session so we can
        # re-create when the tool set changes (unlikely mid-conversation).
        self._session_tool_count: dict[str, int] = {}  # context_id → len(tool_schemas)
        # Set to True by _run_turn when a bridged tool was executed.
        # Checked by stream() to decide if a continuation turn is needed.
        self._last_turn_had_bridged_tools: bool = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def stream(
        self,
        prompt: str,
        context_id: str,
        task_id: str | None = None,
        *,
        parts: list[Any] | None = None,
        tool_schemas: list[dict[str, Any]] | None = None,
        system_message: str | None = None,
        model: str = "",
    ) -> AsyncGenerator[str, None]:
        """Yield A2A SSE strings for a conversation turn.

        When bridged native tools are executed, the Copilot SDK
        automatically starts a continuation turn after
        ``ASSISTANT_TURN_END``.  :meth:`_run_turn` detects this and
        keeps draining rather than terminating the stream, so the
        full agentic loop completes within a single HTTP response.

        Parameters
        ----------
        model:
            Optional user-selected model ID to use for this turn.  When
            non-empty it overrides the backend startup-configured model
            so the request steers the LLM at runtime.  If empty the
            backend default (``CopilotConfig.model``) is used.
        """
        attachments, temp_files = _parts_to_attachments(parts)
        if attachments:
            logger.info(
                "CopilotBackend: forwarding %d image attachment(s) to Copilot SDK (context_id=%s)",
                len(attachments),
                context_id,
            )
        if task_id:
            yield _sse("session.task_id", {"task_id": task_id})

        self._touch_session(context_id)

        try:
            async for chunk in self._run_turn(
                prompt,
                context_id,
                attachments=attachments or None,
                tool_schemas=tool_schemas,
                system_message=system_message,
                model=model,
            ):
                yield chunk
        except Exception as exc:
            logger.error(
                "CopilotBackend: unhandled exception during turn (context_id=%s): %s",
                context_id,
                exc,
                exc_info=True,
            )
            yield _sse("session.error", {"message": f"Copilot adapter error: {exc}"})

        finally:
            if temp_files:
                _cleanup_temp_files(temp_files)

        yield "data: [DONE]\n\n"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_client(self) -> Any:
        """Return the shared :class:`copilot.CopilotClient`, starting it on first use."""
        if self._client is not None:
            return self._client

        async with self._client_lock:
            if self._client is not None:
                return self._client

            from copilot import CopilotClient  # local import — SDK not in main deps

            options: dict[str, Any] = {
                "auto_start": True,
                "auto_restart": True,
            }

            # Only override cli_path if explicitly configured to a non-default
            # value.  The SDK ships a bundled Copilot CLI binary and will use
            # it automatically when cli_path is omitted.
            if self.config.cli_path and self.config.cli_path != _DEFAULT_CLI_PATH:
                cli_path = self.config.cli_path
                if not os.path.isabs(cli_path):
                    cli_path = shutil.which(cli_path) or cli_path
                options["cli_path"] = cli_path

            if self.config.working_directory:
                options["cwd"] = self.config.working_directory
            else:
                options["cwd"] = "/workspace"

            if self.config.github_token:
                options["github_token"] = self.config.github_token
            else:
                # Use the gh auth login state already present in the sandbox.
                options["use_logged_in_user"] = True

            if self.config.extra_env:
                options["env"] = self.config.extra_env

            client = CopilotClient(options)
            # auto_start=True means create_session() will call start() lazily,
            # but we call it explicitly here so errors surface immediately.
            await client.start()
            self._client = client
            logger.info(
                "CopilotBackend: Copilot CLI client started (cli_path=%s)", self.config.cli_path
            )
            return client

    async def _get_or_create_session(
        self,
        context_id: str,
        tool_schemas: list[dict[str, Any]] | None = None,
        system_message: str | None = None,
        model: str = "",
    ) -> Any:
        """Create a fresh Copilot SDK session for each run.

        A new session is created every time to ensure the LLM always
        receives the current system message, tool definitions, and a
        clean context.  The ii-agent backend manages conversation history
        externally (the prompt already contains prior turns), so we do
        not need the SDK's internal session history.

        Stale session caching caused bridged tools (e.g. ``register_port``)
        to become invisible to the LLM on resumed sessions — the SDK does
        not re-inject tool definitions or system messages on resume.

        Parameters
        ----------
        model:
            User-selected model ID forwarded from A2A metadata.  When
            non-empty this overrides ``CopilotConfig.model`` for this
            session so the request steers the backend LLM at runtime.
        """
        client = await self._get_client()

        # Discard any cached session for this context — always start fresh.
        self._sessions.pop(context_id, None)
        self._session_tool_count.pop(context_id, None)

        def _handle_permission_request(req: Any, _ctx: Any) -> dict[str, Any]:
            """Log and auto-approve permission requests from the Copilot CLI."""
            # Extract tool info for audit logging
            tool_name = getattr(req, "name", None) or getattr(req, "tool", "unknown")
            args = getattr(req, "arguments", None) or getattr(req, "input", {})
            logger.info(
                "CopilotBackend: permission request approved — tool=%r args=%r context=%s",
                tool_name,
                args,
                context_id,
            )
            return {"kind": "approved", "rules": []}

        session_kwargs: dict[str, Any] = {
            "on_permission_request": _handle_permission_request,
            "streaming": True,
            "working_directory": self.config.working_directory or "/workspace",
        }
        # Prefer per-request model override; fall back to startup-configured default.
        effective_model = model or self.config.model
        if effective_model:
            session_kwargs["model"] = effective_model
            if model and model != self.config.model:
                logger.info(
                    "CopilotBackend: runtime model override model=%r (config default=%r) context=%s",
                    model,
                    self.config.model,
                    context_id,
                )

        # Wire infinite-session compaction controls if configured.
        infinite_cfg: dict[str, Any] = {"enabled": True}
        if self.config.background_compaction_threshold is not None:
            infinite_cfg["background_compaction_threshold"] = (
                self.config.background_compaction_threshold
            )
        if self.config.buffer_exhaustion_threshold is not None:
            infinite_cfg["buffer_exhaustion_threshold"] = self.config.buffer_exhaustion_threshold
        session_kwargs["infinite_sessions"] = infinite_cfg

        # Register bridged native tools if schemas are provided.
        if tool_schemas:
            sdk_tools = self._create_sdk_tools(tool_schemas)
            if sdk_tools:
                session_kwargs["tools"] = sdk_tools
                logger.info(
                    "CopilotBackend: registering %d bridged native tools for context %s",
                    len(sdk_tools),
                    context_id,
                )

        # Build the composite system message:
        #   1. Agent's full system prompt (personality, BROWSER_RULES, etc.)
        #   2. Tool instruction addendum (describes bridged tool capabilities)
        # This gives the CLI LLM the same directives the native loop receives.
        combined_parts: list[str] = []
        if system_message:
            combined_parts.append(system_message)
        if tool_schemas:
            tool_instruction = _build_tool_system_message(tool_schemas)
            if tool_instruction:
                combined_parts.append(tool_instruction)
        if combined_parts:
            session_kwargs["system_message"] = {
                "content": "\n\n".join(combined_parts),
            }

        session = await client.create_session(session_kwargs)
        self._sessions[context_id] = session.session_id
        self._session_tool_count[context_id] = len(tool_schemas) if tool_schemas else 0

        # Enforce LRU cap: evict the oldest session(s) if we exceeded the limit.
        while len(self._sessions) > self._MAX_SESSIONS:
            oldest_ctx = min(
                self._session_last_used,
                key=self._session_last_used.get,  # type: ignore[arg-type]
                default=None,
            )
            if oldest_ctx is None:
                break
            self._sessions.pop(oldest_ctx, None)
            self._session_last_used.pop(oldest_ctx, None)
            self._session_tool_count.pop(oldest_ctx, None)
            logger.debug("CopilotBackend: evicted LRU session for context %s", oldest_ctx)

        logger.info(
            "CopilotBackend: created session %s for context %s (tools=%d)",
            session.session_id,
            context_id,
            len(tool_schemas or []),
        )
        return session

    async def _run_turn(
        self,
        prompt: str,
        context_id: str,
        *,
        attachments: list[dict[str, Any]] | None = None,
        tool_schemas: list[dict[str, Any]] | None = None,
        system_message: str | None = None,
        model: str = "",
    ) -> AsyncGenerator[str, None]:
        """Run one conversation turn, yielding A2A SSE strings."""
        from copilot.generated.session_events import SessionEventType

        session = await self._get_or_create_session(
            context_id, tool_schemas=tool_schemas, system_message=system_message, model=model
        )

        # Queue-based bridge: the synchronous on() callback puts events into
        # an asyncio.Queue that our async generator drains.  The SDK fires
        # callbacks from a background thread, so we must use
        # call_soon_threadsafe to safely enqueue into the asyncio world.
        queue: asyncio.Queue[Any] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        # Store references so SDK tool handlers can inject events.
        self._tool_stream_queue = queue
        self._tool_stream_loop = loop

        # End-of-turn event types — when seen, we stop draining.
        _TERMINAL = {
            SessionEventType.SESSION_IDLE,
            SessionEventType.ASSISTANT_TURN_END,
            SessionEventType.ABORT,
            SessionEventType.SESSION_ERROR,
            SessionEventType.SESSION_SHUTDOWN,
        }

        # Maximum number of continuation turns when tools are called.
        # The Copilot SDK automatically starts a new turn after
        # ASSISTANT_TURN_END when tools were executed.  We skip that
        # TURN_END and keep draining so the continuation events flow
        # through the same SSE stream.  After skipping, we probe for
        # ASSISTANT_TURN_START with a short timeout to confirm the SDK
        # is actually continuing.
        _MAX_CONTINUATION_TURNS = 50
        _continuation_count = 0
        _turn_had_tools = False
        # Short timeout (seconds) to wait for ASSISTANT_TURN_START after
        # we skip a TURN_END.  If nothing arrives, the SDK is done.
        _CONTINUATION_PROBE_TIMEOUT = 3.0
        _awaiting_continuation = False

        def _on_event(event: Any) -> None:
            _etype = getattr(event, "type", type(event).__name__)
            if _etype == SessionEventType.SESSION_ERROR:
                _edata = getattr(event, "data", None)
                logger.warning(
                    "CopilotBackend._on_event: received SDK session error "
                    "type=%s message=%r error_type=%r",
                    _etype,
                    getattr(_edata, "message", None),
                    getattr(_edata, "error_type", None),
                )
            else:
                logger.info("CopilotBackend._on_event: received SDK event type=%s", _etype)
            loop.call_soon_threadsafe(queue.put_nowait, event)

        unsubscribe = session.on(_on_event)
        error_occurred = False
        turn_start = time.monotonic()

        # Deduplication: the Copilot SDK may fire the event callback more
        # than once for resumed sessions.  Track fingerprints to skip
        # duplicate events within a short window.
        _seen_fingerprints: dict[str, float] = {}
        _DEDUP_WINDOW = 2.0  # seconds

        try:
            send_opts: dict[str, Any] = {"prompt": prompt}
            if attachments:
                send_opts["attachments"] = attachments
            _send_t0 = time.monotonic()
            logger.info(
                "CopilotBackend._run_turn: calling session.send (context_id=%s)",
                context_id,
            )
            await session.send(send_opts)
            _send_elapsed = time.monotonic() - _send_t0
            logger.info(
                "CopilotBackend._run_turn: session.send returned in %.2fs (context_id=%s)",
                _send_elapsed,
                context_id,
            )
            if _send_elapsed > 5.0:
                logger.warning(
                    "CopilotBackend._run_turn: session.send took %.1fs — potential event-loop block!",
                    _send_elapsed,
                )

            while True:
                # Use a short timeout when probing for SDK continuation
                # after a skipped TURN_END, normal heartbeat interval otherwise.
                _get_timeout = (
                    _CONTINUATION_PROBE_TIMEOUT if _awaiting_continuation else _HEARTBEAT_INTERVAL
                )
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_get_timeout)
                except asyncio.TimeoutError:
                    # If we were probing for a continuation and none came,
                    # the SDK is done — break out cleanly.
                    if _awaiting_continuation:
                        logger.info(
                            "CopilotBackend._run_turn: no continuation after %.1fs, "
                            "ending stream (context_id=%s, elapsed=%.1fs)",
                            _CONTINUATION_PROBE_TIMEOUT,
                            context_id,
                            time.monotonic() - turn_start,
                        )
                        break
                    # Check overall turn timeout
                    elapsed = time.monotonic() - turn_start
                    if elapsed > self.config.timeout:
                        yield _sse(
                            "session.error",
                            {"message": f"Copilot CLI timed out after {self.config.timeout}s"},
                        )
                        error_occurred = True
                        break
                    # Send heartbeat to keep HTTP connection alive during
                    # long-running tool executions.
                    logger.info(
                        "CopilotBackend._run_turn: yielding heartbeat (elapsed=%.1fs, context_id=%s)",
                        elapsed,
                        context_id,
                    )
                    yield _sse("heartbeat", {"status": "waiting"})
                    continue

                # Any event received clears the continuation probe.
                _awaiting_continuation = False

                # Log every event type for diagnostics.
                _evt_type_raw = getattr(event, "type", type(event).__name__)
                logger.info(
                    "CopilotBackend._run_turn: dequeued event type=%s (context_id=%s, elapsed=%.1fs)",
                    _evt_type_raw,
                    context_id,
                    time.monotonic() - turn_start,
                )

                # Tool execution request from an SDK tool handler.
                if isinstance(event, _ToolExecutionRequest):
                    self._last_turn_had_bridged_tools = True
                    _turn_had_tools = True
                    yield _sse("tool.execution_request", event.data)
                    continue

                # Track SDK-internal tool execution for continuation detection.
                _evt_type = getattr(event, "type", None)
                if _evt_type == SessionEventType.TOOL_EXECUTION_START:
                    _turn_had_tools = True

                # --- Dedup guard ---
                # Build a fingerprint from event type + data repr.
                # ASSISTANT_MESSAGE_DELTA events naturally differ per chunk
                # so legitimate deltas are never suppressed.
                _evt_data = getattr(event, "data", None)
                _fp = f"{_evt_type}:{repr(_evt_data)}"
                _now = time.monotonic()
                _prev = _seen_fingerprints.get(_fp)
                if _prev is not None and (_now - _prev) < _DEDUP_WINDOW:
                    logger.debug(
                        "CopilotBackend: suppressed duplicate event %s (%.3fs since last)",
                        _evt_type,
                        _now - _prev,
                    )
                    continue
                _seen_fingerprints[_fp] = _now

                # Map SDK event → A2A SSE strings and yield
                try:
                    sse_strings = parse_copilot_event(event)
                    for sse_str in sse_strings:
                        yield sse_str
                except Exception as map_exc:
                    logger.warning(
                        "CopilotBackend: failed to map event %s: %s",
                        getattr(event, "type", "?"),
                        map_exc,
                    )

                # Check if this event signals end-of-turn
                if event.type in _TERMINAL:
                    # When tools were executed this turn, the SDK may fire
                    # ASSISTANT_TURN_END then immediately start a
                    # continuation turn (ASSISTANT_TURN_START).  Skip the
                    # TURN_END and probe with a short timeout to confirm
                    # the SDK is actually continuing.
                    if (
                        event.type == SessionEventType.ASSISTANT_TURN_END
                        and _turn_had_tools
                        and _continuation_count < _MAX_CONTINUATION_TURNS
                    ):
                        _continuation_count += 1
                        _turn_had_tools = False  # reset for next turn
                        _awaiting_continuation = True
                        logger.info(
                            "CopilotBackend._run_turn: skipping TURN_END after tools, "
                            "probing for continuation "
                            "(continuation=%d, context_id=%s, elapsed=%.1fs)",
                            _continuation_count,
                            context_id,
                            time.monotonic() - turn_start,
                        )
                        continue

                    # Some SDK builds enqueue SESSION_ERROR or SESSION_IDLE
                    # immediately after ASSISTANT_TURN_END. Drain any already
                    # buffered follow-up events before terminating so we do not
                    # falsely mark an errored turn as a clean blank success.
                    if event.type == SessionEventType.ASSISTANT_TURN_END:
                        while True:
                            try:
                                trailing_event = queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break

                            trailing_type = getattr(
                                trailing_event, "type", type(trailing_event).__name__
                            )
                            logger.info(
                                "CopilotBackend._run_turn: draining post-turn event type=%s "
                                "(context_id=%s, elapsed=%.1fs)",
                                trailing_type,
                                context_id,
                                time.monotonic() - turn_start,
                            )

                            if isinstance(trailing_event, _ToolExecutionRequest):
                                self._last_turn_had_bridged_tools = True
                                _turn_had_tools = True
                                yield _sse("tool.execution_request", trailing_event.data)
                                continue

                            try:
                                trailing_sse_strings = parse_copilot_event(trailing_event)
                                for sse_str in trailing_sse_strings:
                                    yield sse_str
                            except Exception as map_exc:
                                logger.warning(
                                    "CopilotBackend: failed to map trailing event %s: %s",
                                    getattr(trailing_event, "type", "?"),
                                    map_exc,
                                )

                            if (
                                getattr(trailing_event, "type", None)
                                == SessionEventType.SESSION_ERROR
                            ):
                                error_occurred = True

                    logger.info(
                        "CopilotBackend._run_turn: terminal event type=%s (context_id=%s, elapsed=%.1fs)",
                        event.type,
                        context_id,
                        time.monotonic() - turn_start,
                    )
                    if event.type == SessionEventType.SESSION_ERROR:
                        error_occurred = True
                    break
        finally:
            logger.info(
                "CopilotBackend._run_turn: generator exiting (context_id=%s, error=%s, elapsed=%.1fs)",
                context_id,
                error_occurred,
                time.monotonic() - turn_start,
            )
            unsubscribe()
            self._tool_stream_queue = None
            self._tool_stream_loop = None

        if error_occurred:
            # Remove the stale session so the next call creates a fresh one.
            self._sessions.pop(context_id, None)
            self._session_last_used.pop(context_id, None)

    # ------------------------------------------------------------------
    # Tool bridge: SDK tool creation and result delivery
    # ------------------------------------------------------------------

    def _create_sdk_tools(self, schemas: list[dict[str, Any]]) -> list[Any]:
        """Create Copilot SDK ``Tool`` objects from JSON schemas.

        Each tool's handler injects a ``_ToolExecutionRequest`` into the
        current turn's event queue and returns an *awaitable* that yields
        once :meth:`receive_tool_result` delivers the result via
        ``call_soon_threadsafe``.

        The SDK's ``_execute_tool_call`` is async and will ``await`` the
        returned coroutine, keeping the event loop free for heartbeats
        and SSE writes while the backend processes the tool invocation.
        """
        from copilot.tools import Tool, ToolResult

        sdk_tools: list[Any] = []

        for schema in schemas:
            tool_name = schema["name"]

            def _make_handler(name: str):
                """Closure factory — captures *name* per tool."""

                async def handler(invocation: Any) -> Any:
                    tool_call_id = str(_uuid.uuid4())
                    loop = asyncio.get_running_loop()

                    # Prepare the result slot using an asyncio.Event so we
                    # can await without blocking the event loop.
                    result_event = asyncio.Event()
                    result_holder: list[Any] = [None]
                    self._tool_result_slots[tool_call_id] = (
                        result_event,
                        result_holder,
                        loop,
                    )

                    # Inject the execution request into the SSE stream.
                    # NOTE: ToolInvocation is a TypedDict (dict), NOT a
                    # dataclass — access keys via [] / .get(), not getattr().
                    raw_args = (
                        invocation.get("arguments")
                        if isinstance(invocation, dict)
                        else getattr(invocation, "arguments", None)
                    )
                    req_data = {
                        "tool_call_id": tool_call_id,
                        "tool_name": name,
                        "arguments": (raw_args or {}),
                    }
                    q = self._tool_stream_queue
                    if q is not None:
                        q.put_nowait(_ToolExecutionRequest(data=req_data))
                    else:
                        logger.warning(
                            "CopilotBackend: no active stream queue for tool request %s (tool=%s)",
                            tool_call_id,
                            name,
                        )
                        self._tool_result_slots.pop(tool_call_id, None)
                        return ToolResult(
                            textResultForLlm=(
                                f"Tool '{name}' could not be executed: no active stream"
                            ),
                            resultType="error",
                        )

                    # Await without blocking the event loop.
                    try:
                        await asyncio.wait_for(result_event.wait(), timeout=self.config.timeout)
                    except asyncio.TimeoutError:
                        self._tool_result_slots.pop(tool_call_id, None)
                        return ToolResult(
                            textResultForLlm=(
                                f"Tool '{name}' execution timed out after {self.config.timeout}s"
                            ),
                            resultType="error",
                        )

                    result_text = str(result_holder[0]) if result_holder[0] is not None else ""
                    return ToolResult(
                        textResultForLlm=result_text,
                        resultType="success",
                    )

                return handler

            sdk_tools.append(
                Tool(
                    name=tool_name,
                    description=schema.get("description", ""),
                    parameters=schema.get("parameters", {"type": "object", "properties": {}}),
                    handler=_make_handler(tool_name),
                )
            )

        return sdk_tools

    def receive_tool_result(self, tool_call_id: str, result: str) -> bool:
        """Deliver a tool execution result from the backend.

        Called by the adapter's HTTP endpoint when the ii-agent inner loop
        posts a tool result.  Sets the ``asyncio.Event`` via
        ``call_soon_threadsafe`` so the awaiting handler coroutine resumes
        on its own event loop.

        Returns *True* if the result was delivered, *False* if no handler
        was waiting (e.g. already timed out).
        """
        slot = self._tool_result_slots.pop(tool_call_id, None)
        if slot is None:
            logger.warning(
                "CopilotBackend: received tool result for unknown call %s",
                tool_call_id,
            )
            return False
        result_event, result_holder, loop = slot
        result_holder[0] = result
        loop.call_soon_threadsafe(result_event.set)
        return True

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
        ttl = self.config.session_idle_ttl
        now = time.monotonic()
        stale: list[tuple[str, float]] = [
            (ctx, ts) for ctx, ts in self._session_last_used.items() if (now - ts) > ttl
        ]
        for ctx, ts in stale:
            sid = self._sessions.pop(ctx, None)
            self._session_last_used.pop(ctx, None)
            logger.info(
                "CopilotBackend: reaped idle session %s (context=%s, idle=%.0fs)",
                sid,
                ctx,
                now - ts,
            )
        return len(stale)

    async def _reaper_loop(self) -> None:
        """Background loop that periodically reaps idle sessions."""
        while True:
            try:
                await asyncio.sleep(_REAPER_INTERVAL)
                reaped = await self._reap_idle_sessions()
                if reaped:
                    logger.info("CopilotBackend: reaper swept %d idle sessions", reaped)
            except asyncio.CancelledError:
                logger.info("CopilotBackend: session reaper cancelled")
                break
            except Exception:
                logger.exception("CopilotBackend: error in session reaper loop")

    def start_reaper(self) -> None:
        """Start the background session reaper task (idempotent)."""
        if self._reaper_task is None or self._reaper_task.done():
            self._reaper_task = asyncio.create_task(self._reaper_loop())
            logger.info(
                "CopilotBackend: session reaper started (ttl=%.0fs, interval=%.0fs)",
                self.config.session_idle_ttl,
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
            logger.info("CopilotBackend: evicted session %s (context=%s)", sid, context_id)

    @property
    def session_count(self) -> int:
        """Return the number of active tracked sessions."""
        return len(self._sessions)
