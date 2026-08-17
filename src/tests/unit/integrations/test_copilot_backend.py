"""Tests for the GitHub Copilot CLI A2A adapter backend.

Tests are grouped into:
  * parse_copilot_event — pure event-object → A2A SSE mapping (no SDK)
  * CopilotConfig — dataclass defaults
  * CopilotBackend.stream — end-to-end streaming with fully mocked SDK
"""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncGenerator
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio

import pytest

from ii_agent.integrations.a2a.copilot_backend import (
    CopilotBackend,
    CopilotConfig,
    _build_tool_system_message,
    _sse,
    parse_copilot_event,
)
from ii_agent.integrations.a2a.extension_utils import (
    REASONING_EXTENSION_URI,
    TOOL_TELEMETRY_EXTENSION_URI,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse(sse_string: str) -> dict[str, Any]:
    """Strip 'data: ' prefix, strip trailing newlines, and parse JSON."""
    payload = sse_string.strip()
    assert payload.startswith("data: "), f"Not an SSE string: {payload!r}"
    return json.loads(payload[6:])


def _make_event(event_type: Any, **data_kwargs: Any) -> MagicMock:
    """Build a fake SDK SessionEvent with given type and data fields."""
    event = MagicMock()
    event.type = event_type
    for key, value in data_kwargs.items():
        setattr(event.data, key, value)
    return event


# ---------------------------------------------------------------------------
# Fake SessionEventType enum (plain namespace — no SDK import needed)
# ---------------------------------------------------------------------------


class _ET(SimpleNamespace):
    """Fake EventType constants mirroring copilot.generated.session_events.SessionEventType."""

    ASSISTANT_MESSAGE_DELTA = "assistant.message_delta"
    ASSISTANT_REASONING_DELTA = "assistant.reasoning_delta"
    ASSISTANT_REASONING = "assistant.reasoning"
    ASSISTANT_MESSAGE = "assistant.message"
    ASSISTANT_USAGE = "assistant.usage"
    SESSION_ERROR = "session.error"
    SESSION_IDLE = "session.idle"
    ASSISTANT_TURN_END = "assistant.turn_end"
    ABORT = "abort"
    SESSION_SHUTDOWN = "session.shutdown"
    TOOL_EXECUTION_START = "tool.execution.start"


# ---------------------------------------------------------------------------
# Install a minimal fake copilot SDK into sys.modules so the local imports
# inside copilot_backend functions succeed without the real SDK package.
# ---------------------------------------------------------------------------


def _install_fake_copilot_sdk() -> None:
    """Insert stub modules so `from copilot.generated.session_events import ...` works."""
    if "copilot.generated.session_events" in sys.modules:
        return
    _fc = ModuleType("copilot")
    _fc.CopilotClient = MagicMock  # overridden per-test via patch.object
    _fg = ModuleType("copilot.generated")
    _fse = ModuleType("copilot.generated.session_events")
    _fse.SessionEventType = _ET
    sys.modules.setdefault("copilot", _fc)
    sys.modules.setdefault("copilot.generated", _fg)
    sys.modules["copilot.generated.session_events"] = _fse


_install_fake_copilot_sdk()


# ---------------------------------------------------------------------------
# _sse helper
# ---------------------------------------------------------------------------


class TestSseHelper:
    def test_returns_sse_string_with_data_prefix(self) -> None:
        result = _sse("assistant.message_delta", {"delta": "hi"})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")

    def test_json_payload_is_correct(self) -> None:
        result = _sse("test.event", {"key": "value"})
        parsed = _parse_sse(result)
        assert parsed == {"type": "test.event", "data": {"key": "value"}}


# ---------------------------------------------------------------------------
# parse_copilot_event — pure mapping tests
# ---------------------------------------------------------------------------


def _parse(event_type: Any, **data_fields: Any) -> list[dict[str, Any]]:
    """Build a fake event, call parse_copilot_event, return parsed SSE dicts.

    No extra patching is needed — the fake copilot SDK is already installed in
    sys.modules by _install_fake_copilot_sdk() above.
    """
    event = _make_event(event_type, **data_fields)
    sse_strings = parse_copilot_event(event)
    return [_parse_sse(s) for s in sse_strings]


class TestParseCopilotEvent:
    # --- Message delta ---

    def test_message_delta_yields_sse(self) -> None:
        result = _parse(_ET.ASSISTANT_MESSAGE_DELTA, delta_content="Hello")
        assert len(result) == 1
        assert result[0]["type"] == "assistant.message_delta"
        assert result[0]["data"]["delta"] == "Hello"

    def test_empty_message_delta_is_skipped(self) -> None:
        result = _parse(_ET.ASSISTANT_MESSAGE_DELTA, delta_content="")
        assert result == []

    def test_none_message_delta_is_skipped(self) -> None:
        result = _parse(_ET.ASSISTANT_MESSAGE_DELTA, delta_content=None)
        assert result == []

    # --- Reasoning delta ---

    def test_reasoning_delta_includes_extension(self) -> None:
        result = _parse(_ET.ASSISTANT_REASONING_DELTA, delta_content="<thinking>")
        assert len(result) == 1
        entry = result[0]
        assert entry["type"] == "assistant.reasoning_delta"
        assert entry["data"]["delta"] == "<thinking>"
        exts = [e["uri"] for e in entry["data"]["extensions"]]
        assert REASONING_EXTENSION_URI in exts

    def test_empty_reasoning_delta_is_skipped(self) -> None:
        result = _parse(_ET.ASSISTANT_REASONING_DELTA, delta_content="")
        assert result == []

    # --- Reasoning (full) ---

    def test_reasoning_uses_reasoning_text(self) -> None:
        result = _parse(
            _ET.ASSISTANT_REASONING, reasoning_text="chain of thought", reasoning_opaque=None
        )
        assert result[0]["data"]["content"] == "chain of thought"

    def test_reasoning_falls_back_to_opaque(self) -> None:
        result = _parse(_ET.ASSISTANT_REASONING, reasoning_text=None, reasoning_opaque=b"opaque")
        assert result[0]["data"]["content"] == "opaque"

    def test_empty_reasoning_is_skipped(self) -> None:
        result = _parse(_ET.ASSISTANT_REASONING, reasoning_text=None, reasoning_opaque=None)
        assert result == []

    # --- Message (full) ---

    def test_assistant_message_with_no_tool_calls(self) -> None:
        result = _parse(_ET.ASSISTANT_MESSAGE, content="Done!", tool_requests=None)
        assert result[0]["type"] == "assistant.message"
        assert result[0]["data"]["content"] == "Done!"
        assert result[0]["data"]["tool_calls"] == []

    def test_assistant_message_maps_tool_requests(self) -> None:
        tr = MagicMock()
        tr.tool_call_id = "call_abc"
        # MagicMock treats `name` specially (it's a constructor param), so use
        # configure_mock to set it as an attribute.
        tr.configure_mock(name="bash")
        tr.arguments = {"cmd": "ls"}
        result = _parse(_ET.ASSISTANT_MESSAGE, content="ok", tool_requests=[tr])
        tool_calls = result[0]["data"]["tool_calls"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["id"] == "call_abc"
        assert tool_calls[0]["name"] == "bash"
        assert tool_calls[0]["arguments"] == {"cmd": "ls"}
        assert any(e["uri"] == TOOL_TELEMETRY_EXTENSION_URI for e in tool_calls[0]["extensions"])

    # --- Usage ---

    def test_usage_maps_all_token_fields(self) -> None:
        result = _parse(
            _ET.ASSISTANT_USAGE,
            input_tokens=100,
            output_tokens=200,
            cache_read_tokens=50,
            cache_write_tokens=10,
            cost=0.02,
            duration=1.5,
        )
        data = result[0]["data"]
        assert data["input_tokens"] == 100
        assert data["output_tokens"] == 200
        assert data["total_tokens"] == 300
        assert data["cache_read_tokens"] == 50
        assert data["cache_write_tokens"] == 10
        assert data["cost"] == pytest.approx(0.02)
        assert data["duration"] == pytest.approx(1.5)

    def test_usage_none_fields_default_to_zero(self) -> None:
        result = _parse(
            _ET.ASSISTANT_USAGE,
            input_tokens=None,
            output_tokens=None,
            cache_read_tokens=None,
            cache_write_tokens=None,
            cost=None,
            duration=None,
        )
        data = result[0]["data"]
        assert data["input_tokens"] == 0
        assert data["output_tokens"] == 0
        assert data["total_tokens"] == 0

    # --- Error ---

    def test_session_error_yields_sse(self) -> None:
        result = _parse(_ET.SESSION_ERROR, message="oops", error_type="auth_error")
        entry = result[0]
        assert entry["type"] == "session.error"
        assert entry["data"]["message"] == "oops"
        assert entry["data"]["error_type"] == "auth_error"

    def test_session_error_no_error_type(self) -> None:
        result = _parse(_ET.SESSION_ERROR, message="something broke", error_type=None)
        assert "error_type" not in result[0]["data"]

    def test_session_error_no_message_uses_default(self) -> None:
        result = _parse(_ET.SESSION_ERROR, message=None, error_type=None)
        assert "Copilot" in result[0]["data"]["message"]

    # --- Terminal events produce no SSE ---

    @pytest.mark.parametrize(
        "event_type",
        [_ET.SESSION_IDLE, _ET.ASSISTANT_TURN_END, _ET.ABORT, _ET.SESSION_SHUTDOWN],
    )
    def test_terminal_events_produce_no_sse(self, event_type: Any) -> None:
        result = _parse(event_type)
        assert result == []

    # --- Unknown events skipped ---

    def test_unknown_event_type_is_skipped(self) -> None:
        result = _parse(_ET.TOOL_EXECUTION_START)
        assert result == []


# ---------------------------------------------------------------------------
# CopilotConfig defaults
# ---------------------------------------------------------------------------


class TestCopilotConfig:
    def test_defaults(self) -> None:
        cfg = CopilotConfig()
        assert cfg.github_token == ""
        assert cfg.cli_path == "gh"
        assert cfg.model == ""
        assert cfg.timeout == 300.0
        assert cfg.working_directory is None
        assert cfg.extra_env == {}

    def test_custom_token(self) -> None:
        cfg = CopilotConfig(github_token="ghs_abc")
        assert cfg.github_token == "ghs_abc"

    def test_extra_env_is_independent_per_instance(self) -> None:
        a = CopilotConfig()
        b = CopilotConfig()
        a.extra_env["X"] = "1"
        assert "X" not in b.extra_env


# ---------------------------------------------------------------------------
# CopilotBackend.stream — integration tests with fully mocked SDK
# ---------------------------------------------------------------------------


def _build_sdk_mocks(events: list[Any]) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Build mocked CopilotClient + CopilotSession objects.

    Returns (mock_client_cls, mock_client, mock_session).
    The mock session's ``on()`` callback is wired so that the events are
    delivered to it immediately when ``send()`` is awaited.
    """
    mock_session = MagicMock()
    mock_session.session_id = "sess-001"

    # Track the registered callback and fire it when send() is called.
    registered_cb: list[Any] = []

    def _on(cb: Any) -> MagicMock:
        registered_cb.append(cb)
        return MagicMock()  # unsubscribe handle

    async def _send(payload: dict[str, Any]) -> str:
        for ev in events:
            for cb in registered_cb:
                cb(ev)
        return "msg-001"

    mock_session.on = _on
    mock_session.send = _send

    mock_client = MagicMock()
    mock_client.start = AsyncMock()
    mock_client.create_session = AsyncMock(return_value=mock_session)
    mock_client.resume_session = AsyncMock(return_value=mock_session)

    mock_client_cls = MagicMock(return_value=mock_client)
    return mock_client_cls, mock_client, mock_session


async def _collect(gen: AsyncGenerator[str, None]) -> list[str]:
    return [chunk async for chunk in gen]


@pytest.fixture()
def event_type_patch():
    with patch("copilot.generated.session_events.SessionEventType", _ET):
        yield


class TestCopilotBackendStream:
    def _make_event(self, event_type: Any, **data_fields: Any) -> MagicMock:
        return _make_event(event_type, **data_fields)

    @pytest.mark.asyncio
    async def test_always_yields_done_sentinel(self) -> None:
        idle_event = self._make_event(_ET.SESSION_IDLE)
        mock_cls, _, _ = _build_sdk_mocks([idle_event])

        backend = CopilotBackend(CopilotConfig())
        with (
            patch("ii_agent.integrations.a2a.copilot_backend.CopilotClient", mock_cls, create=True),
            patch("copilot.generated.session_events.SessionEventType", _ET),
        ):
            # Pre-load the client so the import inside _get_client works
            with patch(
                "builtins.__import__",
                side_effect=lambda name, *a, **kw: (
                    mock_cls if name == "copilot" else __import__(name, *a, **kw)
                ),
            ):
                pass
            # Patch the local import path used inside copilot_backend
            with patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_cls.return_value),
            ):
                with patch(
                    "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_or_create_session",
                    new=AsyncMock(return_value=mock_cls.return_value.create_session.return_value),
                ):
                    chunks = await _collect(backend.stream("hello", "ctx-1"))

        assert chunks[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_task_id_event_emitted_first(self) -> None:
        idle_event = self._make_event(_ET.SESSION_IDLE)
        mock_cls, mock_client, mock_session = _build_sdk_mocks([idle_event])

        backend = CopilotBackend(CopilotConfig())
        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_or_create_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("copilot.generated.session_events.SessionEventType", _ET),
        ):
            chunks = await _collect(backend.stream("hello", "ctx-1", task_id="task-42"))

        first = _parse_sse(chunks[0])
        assert first["type"] == "session.task_id"
        assert first["data"]["task_id"] == "task-42"

    @pytest.mark.asyncio
    async def test_message_delta_is_emitted(self) -> None:
        delta_event = self._make_event(_ET.ASSISTANT_MESSAGE_DELTA, delta_content="Hello!")
        idle_event = self._make_event(_ET.SESSION_IDLE)
        mock_cls, mock_client, mock_session = _build_sdk_mocks([delta_event, idle_event])

        backend = CopilotBackend(CopilotConfig())
        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_or_create_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("copilot.generated.session_events.SessionEventType", _ET),
        ):
            chunks = await _collect(backend.stream("hello", "ctx-1"))

        sse_types = [_parse_sse(c)["type"] for c in chunks if not c.startswith("data: [DONE]")]
        assert "assistant.message_delta" in sse_types

    @pytest.mark.asyncio
    async def test_session_error_removes_session_and_yields_done(self) -> None:
        error_event = self._make_event(_ET.SESSION_ERROR, message="auth failed", error_type="auth")
        mock_cls, mock_client, mock_session = _build_sdk_mocks([error_event])

        backend = CopilotBackend(CopilotConfig())
        backend._sessions["ctx-err"] = "sess-old"

        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_or_create_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("copilot.generated.session_events.SessionEventType", _ET),
        ):
            chunks = await _collect(backend.stream("hello", "ctx-err"))

        # Session should be cleared after error
        assert "ctx-err" not in backend._sessions
        assert chunks[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_timeout_yields_error_and_done(self) -> None:
        # Use a very short timeout and an event that never arrives.
        backend = CopilotBackend(CopilotConfig(timeout=0.01))

        mock_session = MagicMock()
        mock_session.session_id = "sess-timeout"

        # on() registers a callback but never delivers events.
        unsubscribe = MagicMock()
        mock_session.on = MagicMock(return_value=unsubscribe)
        mock_session.send = AsyncMock()  # no events fired

        mock_client = MagicMock()
        mock_client.start = AsyncMock()
        mock_client.create_session = AsyncMock(return_value=mock_session)

        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_or_create_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("copilot.generated.session_events.SessionEventType", _ET),
        ):
            chunks = await _collect(backend.stream("hi", "ctx-timeout"))

        error_chunks = [_parse_sse(c) for c in chunks if not c.startswith("data: [DONE]")]
        assert any(
            "timed out" in c["data"]["message"]
            for c in error_chunks
            if c.get("type") == "session.error"
        )
        assert chunks[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_second_turn_creates_fresh_session(self) -> None:
        """On the second call for the same context_id, a fresh session is created (not resumed).

        The implementation always discards cached sessions and calls create_session
        to ensure tool definitions and system messages are re-injected.
        """
        idle = self._make_event(_ET.SESSION_IDLE)
        mock_cls, mock_client, mock_session = _build_sdk_mocks([idle])

        backend = CopilotBackend(CopilotConfig())
        # Simulate that a session already exists for context "ctx-2"
        backend._sessions["ctx-2"] = "sess-existing"

        # Patch PermissionHandler so the local import inside _get_or_create_session works.
        fake_ph = MagicMock()
        fake_ph.approve_all = MagicMock()
        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_client),
            ),
            patch("copilot.generated.session_events.SessionEventType", _ET),
            patch("copilot.PermissionHandler", fake_ph, create=True),
        ):
            await backend._get_or_create_session("ctx-2")

        # Cached session is discarded; create_session is called (not resume_session).
        mock_client.create_session.assert_awaited_once()
        mock_client.resume_session.assert_not_awaited()
        session_kwargs = mock_client.create_session.call_args[0][0]
        assert "streaming" in session_kwargs
        assert session_kwargs["streaming"] is True
        assert "on_permission_request" in session_kwargs


# ---------------------------------------------------------------------------
# CopilotBackend — session reaper tests
# ---------------------------------------------------------------------------


class TestCopilotBackendReaper:
    def test_touch_session_records_timestamp(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        backend._touch_session("ctx-a")
        assert "ctx-a" in backend._session_last_used

    @pytest.mark.asyncio
    async def test_reap_idle_sessions_removes_stale(self) -> None:
        backend = CopilotBackend(CopilotConfig(session_idle_ttl=0.0))
        backend._sessions["ctx-old"] = "sess-old"
        backend._session_last_used["ctx-old"] = 0.0  # epoch — certainly stale

        reaped = await backend._reap_idle_sessions()

        assert reaped == 1
        assert "ctx-old" not in backend._sessions
        assert "ctx-old" not in backend._session_last_used

    @pytest.mark.asyncio
    async def test_reap_idle_sessions_keeps_active(self) -> None:
        import time

        backend = CopilotBackend(CopilotConfig(session_idle_ttl=9999.0))
        backend._sessions["ctx-fresh"] = "sess-fresh"
        backend._session_last_used["ctx-fresh"] = time.monotonic()

        reaped = await backend._reap_idle_sessions()

        assert reaped == 0
        assert "ctx-fresh" in backend._sessions

    def test_evict_session_removes_by_context_id(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        backend._sessions["ctx-x"] = "sess-x"
        backend._session_last_used["ctx-x"] = 1.0

        backend.evict_session("ctx-x")

        assert "ctx-x" not in backend._sessions
        assert "ctx-x" not in backend._session_last_used

    def test_evict_session_noop_for_unknown(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        backend.evict_session("nope")  # should not raise

    @pytest.mark.asyncio
    async def test_start_reaper_creates_task(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        backend.start_reaper()
        assert backend._reaper_task is not None
        assert not backend._reaper_task.done()
        backend.stop_reaper()
        # Let the cancellation propagate.
        try:
            await backend._reaper_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_stop_reaper_cancels_task(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        backend.start_reaper()
        task = backend._reaper_task
        backend.stop_reaper()
        assert task is not None
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert task.done()

    def test_session_count_property(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        assert backend.session_count == 0
        backend._sessions["ctx-1"] = "s1"
        assert backend.session_count == 1


# ---------------------------------------------------------------------------
# CopilotConfig — compaction threshold fields
# ---------------------------------------------------------------------------


class TestCopilotConfigCompaction:
    def test_defaults_are_none(self) -> None:
        cfg = CopilotConfig()
        assert cfg.background_compaction_threshold is None
        assert cfg.buffer_exhaustion_threshold is None

    def test_custom_thresholds(self) -> None:
        cfg = CopilotConfig(
            background_compaction_threshold=1.0,
            buffer_exhaustion_threshold=0.99,
        )
        assert cfg.background_compaction_threshold == 1.0
        assert cfg.buffer_exhaustion_threshold == 0.99

    @pytest.mark.asyncio
    async def test_create_session_passes_infinite_sessions(self) -> None:
        """Verify create_session receives an infinite_sessions kwarg with thresholds."""
        _, mock_client, mock_session = _build_sdk_mocks([])
        cfg = CopilotConfig(
            background_compaction_threshold=0.9,
            buffer_exhaustion_threshold=0.98,
        )
        backend = CopilotBackend(cfg)

        fake_ph = MagicMock()
        fake_ph.approve_all = MagicMock()
        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_client),
            ),
            patch("copilot.PermissionHandler", fake_ph, create=True),
        ):
            await backend._get_or_create_session("ctx-comp")

        mock_client.create_session.assert_awaited_once()
        # create_session receives a single positional dict of session kwargs.
        session_kwargs = mock_client.create_session.call_args[0][0]
        assert "infinite_sessions" in session_kwargs
        inf = session_kwargs["infinite_sessions"]
        assert inf["enabled"] is True
        assert inf["background_compaction_threshold"] == 0.9
        assert inf["buffer_exhaustion_threshold"] == 0.98


# ---------------------------------------------------------------------------
# _build_tool_system_message
# ---------------------------------------------------------------------------


class TestBuildToolSystemMessage:
    """Tests for the system message builder that informs the CLI about bridged tools."""

    def test_empty_schemas_returns_empty_string(self):
        assert _build_tool_system_message([]) == ""

    def test_browser_tools_section_present(self):
        schemas = [
            {"name": "browser_click", "description": "Click on an element"},
            {"name": "browser_navigation", "description": "Navigate browser to URL"},
        ]
        msg = _build_tool_system_message(schemas)
        assert "Browser Automation Tools" in msg
        assert "real Chromium browser" in msg
        assert "browser_click" in msg
        assert "browser_navigation" in msg

    def test_browser_captcha_hitl_instructions_present(self):
        schemas = [
            {"name": "browser_click", "description": "Click on an element"},
        ]
        msg = _build_tool_system_message(schemas)
        assert "CAPTCHA" in msg
        assert "noVNC" in msg or "vnc.html" in msg
        assert "register_port" in msg
        assert "6080" in msg
        assert "agent-browser" in msg

    def test_web_tools_section_present(self):
        schemas = [
            {"name": "web_search", "description": "Search the web"},
        ]
        msg = _build_tool_system_message(schemas)
        assert "Web Search" in msg
        assert "web_search" in msg

    def test_mixed_tools_all_sections(self):
        schemas = [
            {"name": "browser_click", "description": "Click element"},
            {"name": "web_search", "description": "Search the web"},
            {"name": "send_user_files", "description": "Send files to user"},
        ]
        msg = _build_tool_system_message(schemas)
        assert "Custom Tools Available" in msg
        assert "Browser Automation" in msg
        assert "Web Search" in msg
        assert "Additional Tools" in msg

    def test_must_use_instruction_present(self):
        schemas = [{"name": "browser_click", "description": "Click"}]
        msg = _build_tool_system_message(schemas)
        assert "MUST use them" in msg
        assert "Do NOT refuse" in msg


# ---------------------------------------------------------------------------
# System message forwarding — _get_or_create_session combines host system
# message with tool instructions
# ---------------------------------------------------------------------------


class TestSystemMessageForwarding:
    """Verify that the agent's system prompt is forwarded to the CLI session."""

    @pytest.mark.asyncio
    async def test_system_message_only_no_tools(self) -> None:
        """When system_message is provided but no tools, the session gets the raw system message."""
        _, mock_client, _ = _build_sdk_mocks([])
        backend = CopilotBackend(CopilotConfig())

        fake_ph = MagicMock()
        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_client),
            ),
            patch("copilot.PermissionHandler", fake_ph, create=True),
        ):
            await backend._get_or_create_session(
                "ctx-sys", system_message="You are a helpful agent."
            )

        session_kwargs = mock_client.create_session.call_args[0][0]
        assert "system_message" in session_kwargs
        assert session_kwargs["system_message"]["content"] == "You are a helpful agent."

    @pytest.mark.asyncio
    async def test_system_message_combined_with_tool_instructions(self) -> None:
        """When both system_message and tool_schemas are provided, they are combined."""
        _, mock_client, _ = _build_sdk_mocks([])
        backend = CopilotBackend(CopilotConfig())

        fake_ph = MagicMock()
        schemas = [{"name": "web_search", "description": "Search the web"}]
        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._create_sdk_tools",
                return_value=[],
            ),
            patch("copilot.PermissionHandler", fake_ph, create=True),
        ):
            await backend._get_or_create_session(
                "ctx-combined",
                tool_schemas=schemas,
                system_message="You are a helpful agent with BROWSER_RULES.",
            )

        session_kwargs = mock_client.create_session.call_args[0][0]
        content = session_kwargs["system_message"]["content"]
        # Agent system prompt comes first.
        assert content.startswith("You are a helpful agent with BROWSER_RULES.")
        # Tool instructions are appended after.
        assert "Custom Tools Available" in content
        assert "web_search" in content

    @pytest.mark.asyncio
    async def test_tools_only_no_system_message(self) -> None:
        """When tool_schemas are provided but no system_message, only tool instructions are set."""
        _, mock_client, _ = _build_sdk_mocks([])
        backend = CopilotBackend(CopilotConfig())

        fake_ph = MagicMock()
        schemas = [{"name": "browser_click", "description": "Click"}]
        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._create_sdk_tools",
                return_value=[],
            ),
            patch("copilot.PermissionHandler", fake_ph, create=True),
        ):
            await backend._get_or_create_session("ctx-tools", tool_schemas=schemas)

        session_kwargs = mock_client.create_session.call_args[0][0]
        content = session_kwargs["system_message"]["content"]
        assert "Custom Tools Available" in content
        assert "browser_click" in content

    @pytest.mark.asyncio
    async def test_no_system_message_no_tools(self) -> None:
        """When neither system_message nor tools are provided, no system_message kwarg is set."""
        _, mock_client, _ = _build_sdk_mocks([])
        backend = CopilotBackend(CopilotConfig())

        fake_ph = MagicMock()
        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_client),
            ),
            patch("copilot.PermissionHandler", fake_ph, create=True),
        ):
            await backend._get_or_create_session("ctx-bare")

        session_kwargs = mock_client.create_session.call_args[0][0]
        assert "system_message" not in session_kwargs


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------


class TestEventDeduplication:
    """Verify that duplicate SDK events are suppressed in _run_turn."""

    @pytest.mark.asyncio
    async def test_duplicate_events_deduplicated(self) -> None:
        """Events fired twice by the SDK (resume bug) are deduplicated."""
        msg_event = _make_event(_ET.ASSISTANT_MESSAGE_DELTA, delta_content="hi")
        usage_event = _make_event(
            _ET.ASSISTANT_USAGE, input_tokens=10, output_tokens=5, total_tokens=15
        )
        idle_event = _make_event(_ET.SESSION_IDLE)

        # Build a custom session mock that fires each event TWICE.
        mock_session = MagicMock()
        mock_session.session_id = "sess-dedup"
        registered_cb: list[Any] = []

        def _on(cb: Any) -> MagicMock:
            registered_cb.append(cb)
            return MagicMock()

        async def _send(payload: dict[str, Any]) -> str:
            # Fire each non-terminal event twice to simulate SDK resume bug.
            for ev in [msg_event, msg_event, usage_event, usage_event, idle_event]:
                for cb in registered_cb:
                    cb(ev)
            return "msg-001"

        mock_session.on = _on
        mock_session.send = _send

        mock_client = MagicMock()
        mock_client.start = AsyncMock()
        mock_client.create_session = AsyncMock(return_value=mock_session)

        backend = CopilotBackend(CopilotConfig())
        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_or_create_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("copilot.generated.session_events.SessionEventType", _ET),
        ):
            chunks = await _collect(backend.stream("hello", "ctx-dedup"))

        # Parse JSON SSE events (exclude [DONE] sentinel).
        parsed = [
            json.loads(c.strip().removeprefix("data: "))
            for c in chunks
            if c.strip().startswith("data: {")
        ]
        delta_events = [e for e in parsed if e.get("type") == "assistant.message_delta"]
        usage_events = [e for e in parsed if e.get("type") == "assistant.usage"]

        # Without dedup we'd get 2 of each.  With dedup, only 1.
        assert len(delta_events) == 1, f"Expected 1 delta, got {len(delta_events)}"
        assert len(usage_events) == 1, f"Expected 1 usage, got {len(usage_events)}"

    @pytest.mark.asyncio
    async def test_distinct_deltas_not_deduplicated(self) -> None:
        """Different delta events must NOT be suppressed by the dedup filter."""
        delta1 = _make_event(_ET.ASSISTANT_MESSAGE_DELTA, delta_content="Hello ")
        delta2 = _make_event(_ET.ASSISTANT_MESSAGE_DELTA, delta_content="world")
        idle_event = _make_event(_ET.SESSION_IDLE)

        mock_session = MagicMock()
        mock_session.session_id = "sess-distinct"
        registered_cb: list[Any] = []

        def _on(cb: Any) -> MagicMock:
            registered_cb.append(cb)
            return MagicMock()

        async def _send(payload: dict[str, Any]) -> str:
            for ev in [delta1, delta2, idle_event]:
                for cb in registered_cb:
                    cb(ev)
            return "msg-001"

        mock_session.on = _on
        mock_session.send = _send

        mock_client = MagicMock()
        mock_client.start = AsyncMock()
        mock_client.create_session = AsyncMock(return_value=mock_session)

        backend = CopilotBackend(CopilotConfig())
        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_or_create_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("copilot.generated.session_events.SessionEventType", _ET),
        ):
            chunks = await _collect(backend.stream("hello", "ctx-distinct"))

        parsed = [
            json.loads(c.strip().removeprefix("data: "))
            for c in chunks
            if c.strip().startswith("data: {")
        ]
        delta_events = [e for e in parsed if e.get("type") == "assistant.message_delta"]

        # Both distinct deltas must pass through.
        assert len(delta_events) == 2
        assert delta_events[0]["data"]["delta"] == "Hello "
        assert delta_events[1]["data"]["delta"] == "world"


# ---------------------------------------------------------------------------
# _get_client — CLI path resolution & options construction
# ---------------------------------------------------------------------------


class TestCopilotBackendGetClient:
    """Verify the options dict built by _get_client() for various CopilotConfig values."""

    async def _get_client_options(self, config: CopilotConfig) -> dict[str, Any]:
        """Create a backend, call _get_client(), and return the options dict passed to CopilotClient."""
        captured: dict[str, Any] = {}

        mock_client = MagicMock()
        mock_client.start = AsyncMock()

        def _capture_client(options: dict[str, Any]) -> Any:
            captured.update(options)
            return mock_client

        # _get_client() does `from copilot import CopilotClient` (local import),
        # which resolves via sys.modules["copilot"].CopilotClient.
        with patch.object(sys.modules["copilot"], "CopilotClient", side_effect=_capture_client):
            backend = CopilotBackend(config)
            await backend._get_client()

        return captured

    @pytest.mark.asyncio
    async def test_default_config_omits_cli_path(self) -> None:
        """Default cli_path='gh' should NOT pass cli_path to the SDK (uses bundled binary)."""
        opts = await self._get_client_options(CopilotConfig())
        assert "cli_path" not in opts

    @pytest.mark.asyncio
    async def test_default_config_sets_auto_start_and_restart(self) -> None:
        opts = await self._get_client_options(CopilotConfig())
        assert opts["auto_start"] is True
        assert opts["auto_restart"] is True

    @pytest.mark.asyncio
    async def test_default_config_uses_logged_in_user(self) -> None:
        """Without a github_token, the SDK should use the sandbox's gh login state."""
        opts = await self._get_client_options(CopilotConfig())
        assert opts["use_logged_in_user"] is True
        assert "github_token" not in opts

    @pytest.mark.asyncio
    async def test_github_token_passed_when_provided(self) -> None:
        opts = await self._get_client_options(CopilotConfig(github_token="ghs_abc"))
        assert opts["github_token"] == "ghs_abc"
        assert "use_logged_in_user" not in opts

    @pytest.mark.asyncio
    async def test_custom_absolute_cli_path_passed_directly(self) -> None:
        """An absolute custom cli_path is passed through without resolution."""
        opts = await self._get_client_options(CopilotConfig(cli_path="/usr/bin/gh"))
        assert opts["cli_path"] == "/usr/bin/gh"

    @pytest.mark.asyncio
    async def test_custom_relative_cli_path_resolved_via_which(self) -> None:
        """A non-default relative cli_path is resolved via shutil.which."""
        captured: dict[str, Any] = {}

        mock_client = MagicMock()
        mock_client.start = AsyncMock()

        def _capture_client(options: dict[str, Any]) -> Any:
            captured.update(options)
            return mock_client

        with (
            patch.object(sys.modules["copilot"], "CopilotClient", side_effect=_capture_client),
            patch("ii_agent.integrations.a2a.copilot_backend.shutil") as mock_shutil,
        ):
            mock_shutil.which.return_value = "/usr/local/bin/my-copilot"
            backend = CopilotBackend(CopilotConfig(cli_path="my-copilot"))
            await backend._get_client()
        assert captured["cli_path"] == "/usr/local/bin/my-copilot"
        mock_shutil.which.assert_called_once_with("my-copilot")

    @pytest.mark.asyncio
    async def test_custom_relative_cli_path_fallback_when_which_fails(self) -> None:
        """If shutil.which returns None for a relative cli_path, the raw value is used."""
        captured: dict[str, Any] = {}

        mock_client = MagicMock()
        mock_client.start = AsyncMock()

        def _capture_client(options: dict[str, Any]) -> Any:
            captured.update(options)
            return mock_client

        with (
            patch.object(sys.modules["copilot"], "CopilotClient", side_effect=_capture_client),
            patch("ii_agent.integrations.a2a.copilot_backend.shutil") as mock_shutil,
        ):
            mock_shutil.which.return_value = None
            backend = CopilotBackend(CopilotConfig(cli_path="my-copilot"))
            await backend._get_client()
        assert captured["cli_path"] == "my-copilot"

    @pytest.mark.asyncio
    async def test_default_working_directory_is_workspace(self) -> None:
        opts = await self._get_client_options(CopilotConfig())
        assert opts["cwd"] == "/workspace"

    @pytest.mark.asyncio
    async def test_custom_working_directory(self) -> None:
        opts = await self._get_client_options(CopilotConfig(working_directory="/tmp/project"))
        assert opts["cwd"] == "/tmp/project"

    @pytest.mark.asyncio
    async def test_extra_env_forwarded(self) -> None:
        env = {"MY_VAR": "value1", "OTHER": "value2"}
        opts = await self._get_client_options(CopilotConfig(extra_env=env))
        assert opts["env"] == env

    @pytest.mark.asyncio
    async def test_empty_extra_env_omitted(self) -> None:
        """Default empty extra_env dict should not result in an 'env' key."""
        opts = await self._get_client_options(CopilotConfig())
        assert "env" not in opts

    @pytest.mark.asyncio
    async def test_client_start_called(self) -> None:
        """_get_client() calls client.start() explicitly for early error detection."""
        mock_client = MagicMock()
        mock_client.start = AsyncMock()

        with patch.object(sys.modules["copilot"], "CopilotClient", return_value=mock_client):
            backend = CopilotBackend(CopilotConfig())
            await backend._get_client()

        mock_client.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_client_cached_after_first_call(self) -> None:
        """Second call to _get_client() returns cached client without creating a new one."""
        call_count = 0
        mock_client = MagicMock()
        mock_client.start = AsyncMock()

        def _factory(options: dict[str, Any]) -> Any:
            nonlocal call_count
            call_count += 1
            return mock_client

        with patch.object(sys.modules["copilot"], "CopilotClient", side_effect=_factory):
            backend = CopilotBackend(CopilotConfig())
            client1 = await backend._get_client()
            client2 = await backend._get_client()

        assert client1 is client2
        assert call_count == 1
