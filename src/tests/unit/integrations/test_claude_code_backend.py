"""Tests for the Claude Code subprocess backend.

Tests are grouped into:
  * parse_claude_event_line — pure JSON → A2A SSE mapping (no subprocess)
  * ClaudeCodeBackend internals — _build_cmd, _build_env, _update_session_id, _is_error_event
  * ClaudeCodeBackend.stream — subprocess interaction via mocked asyncio primitives
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.integrations.a2a.claude_code_backend import (
    ClaudeCodeBackend,
    ClaudeCodeConfig,
    parse_claude_event_line,
)
from ii_agent.integrations.a2a.extension_utils import (
    REASONING_EXTENSION_URI,
    TOOL_TELEMETRY_EXTENSION_URI,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_sse(sse_line: str) -> dict[str, Any]:
    """Strip the 'data: ' prefix and parse as JSON."""
    assert sse_line.startswith("data: "), f"Not an SSE line: {sse_line!r}"
    return json.loads(sse_line[6:].strip())


def _make_cfg(**kwargs: Any) -> ClaudeCodeConfig:
    return ClaudeCodeConfig(api_key="test-key", **kwargs)


# ---------------------------------------------------------------------------
# parse_claude_event_line — pure mapping tests
# ---------------------------------------------------------------------------


class TestParseClaudeEventLine:
    def test_empty_string_returns_empty_list(self):
        assert parse_claude_event_line("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert parse_claude_event_line("   \n  ") == []

    def test_malformed_json_returns_empty_list(self):
        assert parse_claude_event_line("{not valid json}") == []

    def test_system_init_event_produces_no_sse(self):
        line = json.dumps(
            {
                "type": "system",
                "subtype": "init",
                "session_id": "ses_abc",
                "model": "claude-sonnet-4-5",
            }
        )
        assert parse_claude_event_line(line) == []

    def test_user_tool_result_event_produces_no_sse(self):
        line = json.dumps(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_123",
                            "content": [{"type": "text", "text": "ok"}],
                        }
                    ],
                },
            }
        )
        assert parse_claude_event_line(line) == []

    def test_unknown_event_type_produces_no_sse(self):
        line = json.dumps({"type": "something_unknown", "data": "x"})
        assert parse_claude_event_line(line) == []

    def test_thinking_block_maps_to_reasoning_delta(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "thinking", "thinking": "Let me analyse this..."}],
                },
            }
        )
        events = parse_claude_event_line(line)
        assert len(events) == 1
        parsed = _parse_json_sse(events[0])
        assert parsed["type"] == "assistant.reasoning_delta"
        assert parsed["data"]["delta"] == "Let me analyse this..."
        assert any(ext["uri"] == REASONING_EXTENSION_URI for ext in parsed["data"]["extensions"])

    def test_empty_thinking_block_produces_no_sse(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "thinking", "thinking": ""}],
                },
            }
        )
        assert parse_claude_event_line(line) == []

    def test_text_block_maps_to_message_delta(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hello world!"}],
                },
            }
        )
        events = parse_claude_event_line(line)
        assert len(events) == 1
        parsed = _parse_json_sse(events[0])
        assert parsed["type"] == "assistant.message_delta"
        assert parsed["data"]["delta"] == "Hello world!"

    def test_empty_text_block_produces_no_sse(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": ""}]},
            }
        )
        assert parse_claude_event_line(line) == []

    def test_tool_use_block_maps_to_tool_call(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_xyz",
                            "name": "Bash",
                            "input": {"command": "ls -la"},
                        }
                    ]
                },
            }
        )
        events = parse_claude_event_line(line)
        assert len(events) == 1
        parsed = _parse_json_sse(events[0])
        assert parsed["type"] == "assistant.tool_call"
        data = parsed["data"]
        assert data["id"] == "toolu_xyz"
        assert data["name"] == "Bash"
        assert data["input"] == {"command": "ls -la"}
        assert any(ext["uri"] == TOOL_TELEMETRY_EXTENSION_URI for ext in data["extensions"])

    def test_multiple_content_blocks_emitted_in_order(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "thinking", "thinking": "plan"},
                        {"type": "text", "text": "Result"},
                        {"type": "tool_use", "id": "t1", "name": "Read", "input": {}},
                    ]
                },
            }
        )
        events = parse_claude_event_line(line)
        assert len(events) == 3
        types = [_parse_json_sse(e)["type"] for e in events]
        assert types == [
            "assistant.reasoning_delta",
            "assistant.message_delta",
            "assistant.tool_call",
        ]

    def test_result_success_emits_message_and_usage(self):
        line = json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "Done!",
                "session_id": "ses_xyz",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 20,
                    "cache_creation_input_tokens": 5,
                },
            }
        )
        events = parse_claude_event_line(line)
        assert len(events) == 2
        msg = _parse_json_sse(events[0])
        usage = _parse_json_sse(events[1])
        assert msg["type"] == "assistant.message"
        assert msg["data"]["content"] == "Done!"
        assert usage["type"] == "assistant.usage"
        assert usage["data"]["input_tokens"] == 100
        assert usage["data"]["output_tokens"] == 50
        assert usage["data"]["total_tokens"] == 150
        assert usage["data"]["cache_read_input_tokens"] == 20
        assert usage["data"]["cache_creation_input_tokens"] == 5
        assert usage["data"]["backend"] == "claude-code"

    def test_result_success_empty_result_omits_message_event(self):
        line = json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        )
        events = parse_claude_event_line(line)
        # Only usage, no message
        assert len(events) == 1
        assert _parse_json_sse(events[0])["type"] == "assistant.usage"

    def test_result_is_error_true_emits_session_error(self):
        line = json.dumps(
            {
                "type": "result",
                "subtype": "error_during_execution",
                "is_error": True,
                "error": {"message": "Permission denied"},
            }
        )
        events = parse_claude_event_line(line)
        assert len(events) == 1
        parsed = _parse_json_sse(events[0])
        assert parsed["type"] == "session.error"
        assert "Permission denied" in parsed["data"]["message"]

    def test_result_error_with_string_error_field(self):
        line = json.dumps(
            {
                "type": "result",
                "is_error": True,
                "error": "Something went wrong",
            }
        )
        events = parse_claude_event_line(line)
        assert len(events) == 1
        parsed = _parse_json_sse(events[0])
        assert parsed["type"] == "session.error"
        assert "Something went wrong" in parsed["data"]["message"]

    def test_result_error_no_error_field_uses_fallback_message(self):
        line = json.dumps({"type": "result", "is_error": True})
        events = parse_claude_event_line(line)
        assert len(events) == 1
        assert _parse_json_sse(events[0])["type"] == "session.error"


# ---------------------------------------------------------------------------
# ClaudeCodeBackend internals
# ---------------------------------------------------------------------------


class TestClaudeCodeBackendInternals:
    def _backend(self, **kwargs: Any) -> ClaudeCodeBackend:
        return ClaudeCodeBackend(_make_cfg(**kwargs))

    def test_build_cmd_default_no_resume(self):
        b = self._backend()
        cmd = b._build_cmd("hello", "ctx1")
        assert cmd[0] == "claude"
        assert "--print" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--resume" not in cmd
        assert cmd[-1] == "hello"

    def test_build_cmd_with_stored_session_id_adds_resume(self):
        b = self._backend()
        b._sessions["ctx1"] = "ses_abc"
        cmd = b._build_cmd("next prompt", "ctx1")
        assert "--resume" in cmd
        idx = cmd.index("--resume")
        assert cmd[idx + 1] == "ses_abc"

    def test_build_cmd_with_model_override(self):
        b = self._backend(model="claude-opus-4-5")
        cmd = b._build_cmd("prompt", "ctx")
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "claude-opus-4-5"

    def test_build_cmd_no_model_flag_when_empty(self):
        b = self._backend(model="")
        cmd = b._build_cmd("prompt", "ctx")
        assert "--model" not in cmd

    def test_build_env_injects_api_key(self):
        b = self._backend()
        env = b._build_env()
        assert env["ANTHROPIC_API_KEY"] == "test-key"

    def test_build_env_extra_env_is_merged(self):
        b = self._backend(extra_env={"MY_VAR": "my_value"})
        env = b._build_env()
        assert env["MY_VAR"] == "my_value"

    def test_build_env_extra_env_overrides_parent(self):
        b = self._backend(extra_env={"ANTHROPIC_API_KEY": "overridden"})
        env = b._build_env()
        assert env["ANTHROPIC_API_KEY"] == "overridden"

    def test_update_session_id_from_system_init(self):
        b = self._backend()
        line = json.dumps({"type": "system", "subtype": "init", "session_id": "ses_111"})
        b._update_session_id(line, "ctx1")
        assert b._sessions["ctx1"] == "ses_111"

    def test_update_session_id_from_result(self):
        b = self._backend()
        line = json.dumps(
            {"type": "result", "subtype": "success", "session_id": "ses_222", "result": ""}
        )
        b._update_session_id(line, "ctx2")
        assert b._sessions["ctx2"] == "ses_222"

    def test_update_session_id_ignores_lines_without_session_id(self):
        b = self._backend()
        line = json.dumps({"type": "assistant", "message": {}})
        b._update_session_id(line, "ctx3")
        assert "ctx3" not in b._sessions

    def test_update_session_id_ignores_malformed_json(self):
        b = self._backend()
        b._update_session_id("{bad}", "ctx4")
        assert "ctx4" not in b._sessions

    def test_is_error_event_true_for_is_error(self):
        b = self._backend()
        line = json.dumps({"type": "result", "is_error": True})
        assert b._is_error_event(line) is True

    def test_is_error_event_true_for_error_during_execution(self):
        b = self._backend()
        line = json.dumps({"type": "result", "subtype": "error_during_execution"})
        assert b._is_error_event(line) is True

    def test_is_error_event_false_for_success(self):
        b = self._backend()
        line = json.dumps({"type": "result", "subtype": "success", "is_error": False})
        assert b._is_error_event(line) is False

    def test_is_error_event_false_for_non_result_type(self):
        b = self._backend()
        line = json.dumps({"type": "assistant", "is_error": True})
        assert b._is_error_event(line) is False

    def test_is_error_event_false_for_malformed(self):
        b = self._backend()
        assert b._is_error_event("{") is False

    def test_is_error_event_false_for_empty(self):
        b = self._backend()
        assert b._is_error_event("") is False


# ---------------------------------------------------------------------------
# ClaudeCodeBackend.stream — subprocess integration (mocked)
# ---------------------------------------------------------------------------


def _make_proc_mock(stdout_lines: list[bytes], returncode: int = 0) -> MagicMock:
    """Build a mock asyncio subprocess with the given stdout lines."""
    proc = MagicMock()
    proc.returncode = returncode

    # stdout: each readline() call returns the next line, then b"" (EOF).
    readline_returns = list(stdout_lines) + [b""]
    proc.stdout = AsyncMock()
    proc.stdout.readline = AsyncMock(side_effect=readline_returns)

    # stderr: .read() returns empty bytes by default.
    proc.stderr = AsyncMock()
    proc.stderr.read = AsyncMock(return_value=b"")

    # kill + wait are no-ops.
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=None)

    return proc


async def _collect_stream(gen) -> list[str]:
    """Drain an async generator into a list."""
    return [chunk async for chunk in gen]


class TestClaudeCodeBackendStream:
    """Tests for ClaudeCodeBackend.stream() with mocked subprocess."""

    def _backend(self, **kwargs: Any) -> ClaudeCodeBackend:
        return ClaudeCodeBackend(_make_cfg(**kwargs))

    def _make_stdout(self, events: list[dict[str, Any]]) -> list[bytes]:
        return [json.dumps(e).encode() + b"\n" for e in events]

    @pytest.mark.asyncio
    async def test_stream_emits_task_id_first_when_provided(self):
        events = [
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "ok",
                "usage": {},
            },
        ]
        proc = _make_proc_mock(self._make_stdout(events))

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect_stream(
                self._backend().stream("hello", "ctx", task_id="task-abc")
            )

        first = _parse_json_sse(chunks[0])
        assert first["type"] == "session.task_id"
        assert first["data"]["task_id"] == "task-abc"

    @pytest.mark.asyncio
    async def test_stream_no_task_id_first_event_not_task_id(self):
        events = [
            {"type": "result", "subtype": "success", "is_error": False, "result": "r", "usage": {}},
        ]
        proc = _make_proc_mock(self._make_stdout(events))

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect_stream(self._backend().stream("hi", "ctx"))

        assert not any(chunk.startswith("data:") and "session.task_id" in chunk for chunk in chunks)

    @pytest.mark.asyncio
    async def test_stream_text_block_yields_message_delta(self):
        events = [
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Hello!"}]},
            },
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "Hello!",
                "usage": {},
            },
        ]
        proc = _make_proc_mock(self._make_stdout(events))

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect_stream(self._backend().stream("hi", "ctx"))

        sse_types = [
            _parse_json_sse(c)["type"]
            for c in chunks
            if c.startswith("data:") and c.strip() != "data: [DONE]"
        ]
        assert "assistant.message_delta" in sse_types

    @pytest.mark.asyncio
    async def test_stream_session_id_stored_after_system_init(self):
        events = [
            {"type": "system", "subtype": "init", "session_id": "ses_999"},
            {"type": "result", "subtype": "success", "is_error": False, "result": "", "usage": {}},
        ]
        proc = _make_proc_mock(self._make_stdout(events))
        b = self._backend()

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            await _collect_stream(b.stream("prompt", "myctx"))

        assert b._sessions.get("myctx") == "ses_999"

    @pytest.mark.asyncio
    async def test_stream_session_id_used_on_second_call(self):
        events = [
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "",
                "session_id": "ses_r",
                "usage": {},
            },
        ]
        proc = _make_proc_mock(self._make_stdout(events))
        b = self._backend()

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
            await _collect_stream(b.stream("first", "ctx"))

            # Second call should include --resume
            proc2 = _make_proc_mock(self._make_stdout(events))
            mock_exec.return_value = proc2
            await _collect_stream(b.stream("second", "ctx"))

        # Check that the second invocation had --resume in args
        second_call_args = mock_exec.call_args_list[1][0]
        assert "--resume" in second_call_args
        resume_idx = list(second_call_args).index("--resume")
        assert second_call_args[resume_idx + 1] == "ses_r"

    @pytest.mark.asyncio
    async def test_stream_nonzero_exit_emits_session_error(self):
        proc = _make_proc_mock([], returncode=1)
        proc.stderr.read = AsyncMock(return_value=b"API error: invalid key")

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect_stream(self._backend().stream("hi", "ctx"))

        sse_types = [
            _parse_json_sse(c)["type"] for c in chunks if c.startswith("data:") and "DONE" not in c
        ]
        assert "session.error" in sse_types

    @pytest.mark.asyncio
    async def test_stream_nonzero_exit_with_structured_error_no_double_emit(self):
        """When claude itself emits is_error, non-zero exit should not add a second error."""
        events = [
            {
                "type": "result",
                "is_error": True,
                "error": {"message": "Claude error"},
                "subtype": "error_during_execution",
            },
        ]
        proc = _make_proc_mock(self._make_stdout(events), returncode=1)

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect_stream(self._backend().stream("hi", "ctx"))

        error_events = [
            _parse_json_sse(c)
            for c in chunks
            if c.startswith("data:") and "DONE" not in c and "session.error" in c
        ]
        assert len(error_events) == 1, "Expected exactly one session.error, got multiple"

    @pytest.mark.asyncio
    async def test_stream_always_ends_with_done(self):
        proc = _make_proc_mock([], returncode=0)

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect_stream(self._backend().stream("hi", "ctx"))

        assert chunks[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_stream_timeout_emits_error_and_done(self):
        """When readline times out, stream emits session.error then [DONE]."""
        b = self._backend(timeout=0.001)

        proc = MagicMock()
        proc.returncode = None
        proc.stdout = AsyncMock()
        # readline hangs forever → TimeoutError after deadline
        proc.stdout.readline = AsyncMock(side_effect=asyncio.TimeoutError)
        proc.stderr = AsyncMock()
        proc.stderr.read = AsyncMock(return_value=b"")
        proc.kill = MagicMock()
        proc.wait = AsyncMock(return_value=None)

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect_stream(b.stream("hi", "ctx"))

        sse_parsed = [
            _parse_json_sse(c) for c in chunks if c.startswith("data:") and "DONE" not in c
        ]
        assert any(e["type"] == "session.error" for e in sse_parsed)
        assert chunks[-1] == "data: [DONE]\n\n"
