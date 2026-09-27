"""Tests for the OpenAI Codex CLI subprocess backend.

Tests are grouped into:
  * TestParseCodexLine  — pure JSON / plain-text → CodexLineResult mapping (no subprocess)
  * TestCodexBackendInternals — _build_cmd, _build_env, _apply_line_result
  * TestCodexBackendStream — subprocess interaction via mocked asyncio primitives
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.integrations.a2a.codex_backend import (
    CodexBackend,
    CodexConfig,
    CodexLineResult,
    parse_codex_line,
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


def _make_cfg(**kwargs: Any) -> CodexConfig:
    return CodexConfig(api_key="test-openai-key", **kwargs)


def _make_backend(**kwargs: Any) -> CodexBackend:
    return CodexBackend(_make_cfg(**kwargs))


# ---------------------------------------------------------------------------
# TestParseCodexLine — pure mapping tests
# ---------------------------------------------------------------------------


class TestParseCodexLine:
    # ---- blank / malformed ------------------------------------------------

    def test_empty_string_returns_empty_result(self):
        r = parse_codex_line("")
        assert r.sse_events == []
        assert r.text_fragment == ""
        assert r.conversation_id == ""
        assert r.usage == {}
        assert r.is_error is False

    def test_whitespace_only_returns_empty_result(self):
        r = parse_codex_line("   \n\t  ")
        assert r.sse_events == []

    # ---- plain text (non-JSON) -------------------------------------------

    def test_plain_text_becomes_message_delta_with_text_fragment(self):
        r = parse_codex_line("Hello, world!")
        assert len(r.sse_events) == 1
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["type"] == "assistant.message_delta"
        assert parsed["data"]["delta"] == "Hello, world!"
        assert r.text_fragment == "Hello, world!"

    def test_plain_text_is_stripped_of_outer_whitespace(self):
        r = parse_codex_line("  trimmed  \n")
        assert r.text_fragment == "trimmed"
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["data"]["delta"] == "trimmed"

    def test_invalid_json_treated_as_plain_text(self):
        r = parse_codex_line("{not valid json")
        assert len(r.sse_events) == 1
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["type"] == "assistant.message_delta"

    # ---- system / init event ---------------------------------------------

    def test_system_event_extracts_conversation_id(self):
        line = json.dumps({"type": "system", "conversation_id": "conv_abc", "model": "o4-mini"})
        r = parse_codex_line(line)
        assert r.sse_events == []
        assert r.conversation_id == "conv_abc"

    def test_system_event_extracts_session_id_fallback(self):
        line = json.dumps({"type": "system", "session_id": "ses_xyz"})
        r = parse_codex_line(line)
        assert r.conversation_id == "ses_xyz"

    def test_init_event_extracts_conversation_id(self):
        line = json.dumps({"type": "init", "conversation_id": "conv_init"})
        r = parse_codex_line(line)
        assert r.conversation_id == "conv_init"
        assert r.sse_events == []

    def test_system_event_without_conversation_id_is_empty(self):
        line = json.dumps({"type": "system", "model": "o4-mini"})
        r = parse_codex_line(line)
        assert r.conversation_id == ""
        assert r.sse_events == []

    # ---- message event ---------------------------------------------------

    def test_message_assistant_string_content_emits_delta(self):
        line = json.dumps({"type": "message", "role": "assistant", "content": "Hello!"})
        r = parse_codex_line(line)
        assert len(r.sse_events) == 1
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["type"] == "assistant.message_delta"
        assert parsed["data"]["delta"] == "Hello!"
        assert r.text_fragment == "Hello!"

    def test_message_assistant_content_array_joined(self):
        line = json.dumps(
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Part one. "},
                    {"type": "text", "text": "Part two."},
                ],
            }
        )
        r = parse_codex_line(line)
        assert len(r.sse_events) == 1
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["data"]["delta"] == "Part one. Part two."
        assert r.text_fragment == "Part one. Part two."

    def test_message_assistant_content_array_with_string_items(self):
        line = json.dumps(
            {"type": "message", "role": "assistant", "content": ["chunk A", "chunk B"]}
        )
        r = parse_codex_line(line)
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["data"]["delta"] == "chunk Achunk B"

    def test_message_user_role_produces_no_sse(self):
        line = json.dumps({"type": "message", "role": "user", "content": "echo hi"})
        r = parse_codex_line(line)
        assert r.sse_events == []
        assert r.text_fragment == ""

    def test_message_empty_role_treated_as_assistant(self):
        line = json.dumps({"type": "message", "content": "fallback text"})
        r = parse_codex_line(line)
        assert len(r.sse_events) == 1
        assert _parse_json_sse(r.sse_events[0])["type"] == "assistant.message_delta"

    def test_message_empty_content_produces_no_sse(self):
        line = json.dumps({"type": "message", "role": "assistant", "content": ""})
        r = parse_codex_line(line)
        assert r.sse_events == []
        assert r.text_fragment == ""

    # ---- reasoning event -------------------------------------------------

    def test_reasoning_event_emits_reasoning_delta(self):
        line = json.dumps({"type": "reasoning", "content": "internal thoughts"})
        r = parse_codex_line(line)
        assert len(r.sse_events) == 1
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["type"] == "assistant.reasoning_delta"
        assert parsed["data"]["delta"] == "internal thoughts"
        extensions = parsed["data"]["extensions"]
        assert any(e["uri"] == REASONING_EXTENSION_URI for e in extensions)

    def test_reasoning_event_text_fallback_field(self):
        line = json.dumps({"type": "reasoning", "text": "alternate field"})
        r = parse_codex_line(line)
        assert len(r.sse_events) == 1
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["data"]["delta"] == "alternate field"

    def test_reasoning_event_empty_content_produces_no_sse(self):
        line = json.dumps({"type": "reasoning", "content": ""})
        r = parse_codex_line(line)
        assert r.sse_events == []

    # ---- tool_call event -------------------------------------------------

    def test_tool_call_dict_arguments_emits_tool_call(self):
        line = json.dumps(
            {
                "type": "tool_call",
                "id": "call_123",
                "name": "bash",
                "arguments": {"command": "ls -la"},
            }
        )
        r = parse_codex_line(line)
        assert len(r.sse_events) == 1
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["type"] == "assistant.tool_call"
        data = parsed["data"]
        assert data["id"] == "call_123"
        assert data["name"] == "bash"
        assert data["input"] == {"command": "ls -la"}
        assert any(e["uri"] == TOOL_TELEMETRY_EXTENSION_URI for e in data["extensions"])

    def test_tool_call_string_arguments_parsed_as_json(self):
        args_str = json.dumps({"command": "cat file.txt"})
        line = json.dumps(
            {
                "type": "tool_call",
                "id": "call_456",
                "name": "bash",
                "arguments": args_str,
            }
        )
        r = parse_codex_line(line)
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["data"]["input"] == {"command": "cat file.txt"}

    def test_tool_call_string_arguments_invalid_json_wraps_in_raw(self):
        line = json.dumps(
            {
                "type": "tool_call",
                "id": "call_789",
                "name": "bash",
                "arguments": "not-json{--}",
            }
        )
        r = parse_codex_line(line)
        parsed = _parse_json_sse(r.sse_events[0])
        assert "raw" in parsed["data"]["input"]

    def test_tool_call_uses_call_id_fallback_for_id(self):
        line = json.dumps(
            {"type": "tool_call", "call_id": "cid_abc", "name": "bash", "arguments": {}}
        )
        r = parse_codex_line(line)
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["data"]["id"] == "cid_abc"

    def test_tool_call_uses_function_fallback_for_name(self):
        line = json.dumps(
            {"type": "tool_call", "id": "cid_xyz", "function": "read_file", "arguments": {}}
        )
        r = parse_codex_line(line)
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["data"]["name"] == "read_file"

    def test_tool_call_uses_input_field_when_no_arguments(self):
        line = json.dumps(
            {"type": "tool_call", "id": "c1", "name": "bash", "input": {"cmd": "pwd"}}
        )
        r = parse_codex_line(line)
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["data"]["input"] == {"cmd": "pwd"}

    # ---- tool_result events (no SSE) ------------------------------------

    def test_tool_result_produces_no_sse(self):
        line = json.dumps({"type": "tool_result", "call_id": "c1", "output": "ok"})
        r = parse_codex_line(line)
        assert r.sse_events == []

    def test_tool_output_produces_no_sse(self):
        line = json.dumps({"type": "tool_output", "output": "stdout"})
        r = parse_codex_line(line)
        assert r.sse_events == []

    def test_function_call_output_produces_no_sse(self):
        line = json.dumps({"type": "function_call_output", "output": "result"})
        r = parse_codex_line(line)
        assert r.sse_events == []

    # ---- done / completion events ----------------------------------------

    def test_done_event_extracts_usage(self):
        line = json.dumps(
            {
                "type": "done",
                "usage": {"input_tokens": 100, "output_tokens": 50, "reasoning_tokens": 200},
            }
        )
        r = parse_codex_line(line)
        assert r.sse_events == []
        assert r.usage["input_tokens"] == 100
        assert r.usage["output_tokens"] == 50
        assert r.usage["reasoning_tokens"] == 200
        assert r.usage["total_tokens"] == 150

    def test_completion_event_extracts_usage_with_openai_field_names(self):
        line = json.dumps(
            {
                "type": "completion",
                "usage": {"prompt_tokens": 80, "completion_tokens": 30},
            }
        )
        r = parse_codex_line(line)
        assert r.usage["input_tokens"] == 80
        assert r.usage["output_tokens"] == 30
        assert r.usage["total_tokens"] == 110

    def test_done_event_with_reasoning_tokens_in_details(self):
        line = json.dumps(
            {
                "type": "done",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "completion_tokens_details": {"reasoning_tokens": 100},
                },
            }
        )
        r = parse_codex_line(line)
        assert r.usage["reasoning_tokens"] == 100

    def test_done_event_with_conversation_id_extracted(self):
        line = json.dumps({"type": "done", "conversation_id": "conv_final", "usage": {}})
        r = parse_codex_line(line)
        assert r.conversation_id == "conv_final"

    def test_done_event_with_result_text_sets_text_fragment(self):
        line = json.dumps({"type": "done", "result": "Final summary text", "usage": {}})
        r = parse_codex_line(line)
        assert r.text_fragment == "Final summary text"

    def test_done_event_with_empty_usage_produces_zero_values(self):
        line = json.dumps({"type": "done", "usage": {}})
        r = parse_codex_line(line)
        assert r.usage["input_tokens"] == 0
        assert r.usage["output_tokens"] == 0
        assert r.usage["total_tokens"] == 0

    def test_done_event_with_no_usage_key_produces_zero_values(self):
        line = json.dumps({"type": "done"})
        r = parse_codex_line(line)
        assert r.usage["input_tokens"] == 0

    # ---- error event -----------------------------------------------------

    def test_error_event_emits_session_error_and_sets_is_error(self):
        line = json.dumps({"type": "error", "message": "Authentication failed"})
        r = parse_codex_line(line)
        assert len(r.sse_events) == 1
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["type"] == "session.error"
        assert "Authentication failed" in parsed["data"]["message"]
        assert r.is_error is True

    def test_error_event_uses_error_field_fallback(self):
        line = json.dumps({"type": "error", "error": "Rate limit exceeded"})
        r = parse_codex_line(line)
        parsed = _parse_json_sse(r.sse_events[0])
        assert "Rate limit exceeded" in parsed["data"]["message"]

    def test_error_event_fallback_message_when_no_message_field(self):
        line = json.dumps({"type": "error"})
        r = parse_codex_line(line)
        assert len(r.sse_events) == 1
        assert r.is_error is True

    # ---- unknown event types -------------------------------------------

    def test_unknown_type_with_content_emits_message_delta(self):
        line = json.dumps({"type": "custom_output", "content": "Some text"})
        r = parse_codex_line(line)
        assert len(r.sse_events) == 1
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["type"] == "assistant.message_delta"
        assert r.text_fragment == "Some text"

    def test_unknown_type_without_content_produces_no_sse(self):
        line = json.dumps({"type": "internal_state", "data": [1, 2, 3]})
        r = parse_codex_line(line)
        assert r.sse_events == []

    def test_json_array_at_top_level_falls_back_to_plain_text(self):
        """Top-level JSON arrays are not valid events — treated as plain text."""
        r = parse_codex_line("[1, 2, 3]")
        assert len(r.sse_events) == 1
        parsed = _parse_json_sse(r.sse_events[0])
        assert parsed["type"] == "assistant.message_delta"


# ---------------------------------------------------------------------------
# TestCodexBackendInternals
# ---------------------------------------------------------------------------


class TestCodexBackendInternals:
    # ---- _build_cmd ------------------------------------------------------

    def test_build_cmd_always_includes_full_auto_and_no_sandbox(self):
        b = _make_backend()
        cmd = b._build_cmd("prompt text", "ctx1")
        assert "--full-auto" in cmd
        assert "--no-sandbox" in cmd

    def test_build_cmd_uses_configured_binary(self):
        b = _make_backend(codex_bin="/usr/local/bin/codex")
        cmd = b._build_cmd("prompt", "ctx")
        assert cmd[0] == "/usr/local/bin/codex"

    def test_build_cmd_prompt_is_last_argument(self):
        b = _make_backend()
        cmd = b._build_cmd("my prompt", "ctx")
        assert cmd[-1] == "my prompt"

    def test_build_cmd_no_conversation_id_by_default(self):
        b = _make_backend()
        cmd = b._build_cmd("prompt", "ctx")
        assert "--conversation-id" not in cmd

    def test_build_cmd_includes_conversation_id_when_stored(self):
        b = _make_backend()
        b._conversations["ctx"] = "conv_stored_123"
        cmd = b._build_cmd("follow-up", "ctx")
        assert "--conversation-id" in cmd
        idx = cmd.index("--conversation-id")
        assert cmd[idx + 1] == "conv_stored_123"

    def test_build_cmd_conversation_id_not_added_for_different_context(self):
        b = _make_backend()
        b._conversations["other_ctx"] = "conv_other"
        cmd = b._build_cmd("prompt", "my_ctx")
        assert "--conversation-id" not in cmd

    def test_build_cmd_model_flag_added_when_set(self):
        b = _make_backend(model="o3")
        cmd = b._build_cmd("prompt", "ctx")
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "o3"

    def test_build_cmd_no_model_flag_when_model_empty(self):
        b = _make_backend(model="")
        cmd = b._build_cmd("prompt", "ctx")
        assert "--model" not in cmd

    def test_build_cmd_instructions_flag_added_when_set(self):
        b = _make_backend(instructions="You are a helpful assistant.")
        cmd = b._build_cmd("prompt", "ctx")
        assert "--instructions" in cmd
        idx = cmd.index("--instructions")
        assert cmd[idx + 1] == "You are a helpful assistant."

    def test_build_cmd_no_instructions_flag_when_empty(self):
        b = _make_backend(instructions="")
        cmd = b._build_cmd("prompt", "ctx")
        assert "--instructions" not in cmd

    # ---- _build_env ------------------------------------------------------

    def test_build_env_injects_openai_api_key(self):
        b = _make_backend()
        env = b._build_env()
        assert env["OPENAI_API_KEY"] == "test-openai-key"

    def test_build_env_extra_env_merged(self):
        b = _make_backend(extra_env={"MY_custom_VAR": "hello"})
        env = b._build_env()
        assert env["MY_custom_VAR"] == "hello"

    def test_build_env_extra_env_can_override_api_key(self):
        b = _make_backend(extra_env={"OPENAI_API_KEY": "override"})
        env = b._build_env()
        assert env["OPENAI_API_KEY"] == "override"

    # ---- _apply_line_result ----------------------------------------------

    def test_apply_line_result_stores_conversation_id(self):
        b = _make_backend()
        result = CodexLineResult(conversation_id="conv_new")
        b._apply_line_result(result, "ctx1")
        assert b._conversations["ctx1"] == "conv_new"

    def test_apply_line_result_empty_conversation_id_does_not_store(self):
        b = _make_backend()
        result = CodexLineResult(conversation_id="")
        b._apply_line_result(result, "ctx1")
        assert "ctx1" not in b._conversations

    def test_apply_line_result_updates_existing_conversation_id(self):
        b = _make_backend()
        b._conversations["ctx1"] = "conv_old"
        result = CodexLineResult(conversation_id="conv_newer")
        b._apply_line_result(result, "ctx1")
        assert b._conversations["ctx1"] == "conv_newer"


# ---------------------------------------------------------------------------
# TestCodexBackendStream — subprocess interaction (mocked)
# ---------------------------------------------------------------------------


def _make_proc_mock(stdout_lines: list[bytes], returncode: int = 0) -> MagicMock:
    """Build a mock asyncio subprocess with the given stdout lines."""
    proc = MagicMock()
    proc.returncode = returncode

    readline_returns = list(stdout_lines) + [b""]
    proc.stdout = AsyncMock()
    proc.stdout.readline = AsyncMock(side_effect=readline_returns)

    proc.stderr = AsyncMock()
    proc.stderr.read = AsyncMock(return_value=b"")

    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=None)

    return proc


def _json_lines(events: list[dict[str, Any]]) -> list[bytes]:
    return [json.dumps(e).encode() + b"\n" for e in events]


async def _collect(gen) -> list[str]:
    return [chunk async for chunk in gen]


class TestCodexBackendStream:
    """Tests for CodexBackend.stream() with mocked subprocess."""

    @pytest.mark.asyncio
    async def test_always_ends_with_done(self):
        proc = _make_proc_mock(_json_lines([{"type": "done", "usage": {}}]))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("hi", "ctx"))
        assert chunks[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_task_id_emitted_first_when_provided(self):
        proc = _make_proc_mock(_json_lines([{"type": "done", "usage": {}}]))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("hi", "ctx", task_id="t-001"))
        first = _parse_json_sse(chunks[0])
        assert first["type"] == "session.task_id"
        assert first["data"]["task_id"] == "t-001"

    @pytest.mark.asyncio
    async def test_no_task_id_no_session_task_id_event(self):
        proc = _make_proc_mock(_json_lines([{"type": "done", "usage": {}}]))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("hi", "ctx"))
        sse_types = [
            _parse_json_sse(c)["type"] for c in chunks if c.startswith("data:") and "DONE" not in c
        ]
        assert "session.task_id" not in sse_types

    @pytest.mark.asyncio
    async def test_plain_text_line_emits_message_delta(self):
        proc = _make_proc_mock([b"Running your request...\n"])
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("hi", "ctx"))
        sse_types = [
            _parse_json_sse(c)["type"] for c in chunks if c.startswith("data:") and "DONE" not in c
        ]
        assert "assistant.message_delta" in sse_types

    @pytest.mark.asyncio
    async def test_json_message_line_emits_message_delta(self):
        events = [
            {"type": "message", "role": "assistant", "content": "Done."},
        ]
        proc = _make_proc_mock(_json_lines(events))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("hi", "ctx"))
        deltas = [
            _parse_json_sse(c) for c in chunks if c.startswith("data:") and "message_delta" in c
        ]
        assert len(deltas) >= 1
        assert deltas[0]["data"]["delta"] == "Done."

    @pytest.mark.asyncio
    async def test_conversation_id_stored_from_system_event(self):
        events = [
            {"type": "system", "conversation_id": "conv_12345"},
        ]
        proc = _make_proc_mock(_json_lines(events))
        b = _make_backend()
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            await _collect(b.stream("prompt", "my_ctx"))
        assert b._conversations.get("my_ctx") == "conv_12345"

    @pytest.mark.asyncio
    async def test_conversation_id_used_on_second_call(self):
        first_events = [
            {"type": "system", "conversation_id": "conv_persist"},
        ]
        proc = _make_proc_mock(_json_lines(first_events))
        b = _make_backend()
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
            await _collect(b.stream("first", "ctx"))
            proc2 = _make_proc_mock([])
            mock_exec.return_value = proc2
            await _collect(b.stream("second", "ctx"))

        second_args = mock_exec.call_args_list[1][0]
        assert "--conversation-id" in second_args
        idx = list(second_args).index("--conversation-id")
        assert second_args[idx + 1] == "conv_persist"

    @pytest.mark.asyncio
    async def test_done_event_emits_usage_sse(self):
        events = [
            {"type": "done", "usage": {"input_tokens": 50, "output_tokens": 25}},
        ]
        proc = _make_proc_mock(_json_lines(events))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("hi", "ctx"))
        usage_chunks = [
            _parse_json_sse(c) for c in chunks if c.startswith("data:") and "assistant.usage" in c
        ]
        assert len(usage_chunks) == 1
        assert usage_chunks[0]["data"]["input_tokens"] == 50
        assert usage_chunks[0]["data"]["backend"] == "codex"

    @pytest.mark.asyncio
    async def test_accumulated_text_emits_final_assistant_message(self):
        events = [
            {"type": "message", "role": "assistant", "content": "Line one."},
            {"type": "message", "role": "assistant", "content": "Line two."},
        ]
        proc = _make_proc_mock(_json_lines(events))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("hi", "ctx"))
        msg_chunks = [
            _parse_json_sse(c)
            for c in chunks
            if c.startswith("data:") and "assistant.message" in c and "delta" not in c
        ]
        # Should emit exactly one assistant.message with the full accumulated text
        assert any(e["type"] == "assistant.message" for e in msg_chunks)
        msg_event = next(e for e in msg_chunks if e["type"] == "assistant.message")
        assert "Line one." in msg_event["data"]["content"]
        assert "Line two." in msg_event["data"]["content"]

    @pytest.mark.asyncio
    async def test_no_text_produces_no_final_assistant_message(self):
        events = [
            {"type": "done", "usage": {"input_tokens": 5, "output_tokens": 1}},
        ]
        proc = _make_proc_mock(_json_lines(events))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("hi", "ctx"))
        msg_chunks = [
            _parse_json_sse(c)
            for c in chunks
            if c.startswith("data:")
            and "DONE" not in c
            and _parse_json_sse(c)["type"] == "assistant.message"
        ]
        assert msg_chunks == []

    @pytest.mark.asyncio
    async def test_error_event_emits_session_error(self):
        events = [
            {"type": "error", "message": "Connection reset"},
        ]
        proc = _make_proc_mock(_json_lines(events))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("hi", "ctx"))
        err_chunks = [
            _parse_json_sse(c) for c in chunks if c.startswith("data:") and "DONE" not in c
        ]
        assert any(e["type"] == "session.error" for e in err_chunks)
        err_event = next(e for e in err_chunks if e["type"] == "session.error")
        assert "Connection reset" in err_event["data"]["message"]

    @pytest.mark.asyncio
    async def test_no_final_message_or_usage_after_error_event(self):
        """When error_seen=True, assistant.message and assistant.usage are suppressed."""
        events = [
            {"type": "error", "message": "Fatal error"},
        ]
        proc = _make_proc_mock(_json_lines(events))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("hi", "ctx"))
        types = [
            _parse_json_sse(c)["type"] for c in chunks if c.startswith("data:") and "DONE" not in c
        ]
        assert "assistant.message" not in types
        assert "assistant.usage" not in types

    @pytest.mark.asyncio
    async def test_nonzero_exit_without_structured_error_emits_session_error(self):
        proc = _make_proc_mock([], returncode=1)
        proc.stderr.read = AsyncMock(return_value=b"Permission denied")
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("hi", "ctx"))
        err_chunks = [
            _parse_json_sse(c) for c in chunks if c.startswith("data:") and "session.error" in c
        ]
        assert len(err_chunks) == 1
        assert "Permission denied" in err_chunks[0]["data"]["message"]

    @pytest.mark.asyncio
    async def test_nonzero_exit_with_prior_error_event_no_double_emit(self):
        events = [
            {"type": "error", "message": "Codex error"},
        ]
        proc = _make_proc_mock(_json_lines(events), returncode=1)
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("hi", "ctx"))
        err_events = [
            _parse_json_sse(c)
            for c in chunks
            if c.startswith("data:")
            and "DONE" not in c
            and _parse_json_sse(c)["type"] == "session.error"
        ]
        assert len(err_events) == 1

    @pytest.mark.asyncio
    async def test_zero_exit_after_nonzero_exit_path_uses_env_correctly(self):
        """Build env is called with correct binary and API key."""
        proc = _make_proc_mock([], returncode=0)
        b = CodexBackend(CodexConfig(api_key="sk-real-key"))
        captured_env: list[dict] = []

        async def fake_exec(*args: Any, **kwargs: Any) -> MagicMock:
            captured_env.append(kwargs.get("env", {}))
            return proc

        with patch("asyncio.create_subprocess_exec", new=fake_exec):
            await _collect(b.stream("prompt", "ctx"))

        assert captured_env[0]["OPENAI_API_KEY"] == "sk-real-key"

    @pytest.mark.asyncio
    async def test_timeout_emits_session_error_and_done(self):
        b = _make_backend(timeout=0.001)

        proc = MagicMock()
        proc.returncode = None
        proc.stdout = AsyncMock()
        proc.stdout.readline = AsyncMock(side_effect=asyncio.TimeoutError)
        proc.stderr = AsyncMock()
        proc.stderr.read = AsyncMock(return_value=b"")
        proc.kill = MagicMock()
        proc.wait = AsyncMock(return_value=None)

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(b.stream("prompt", "ctx"))

        sse_parsed = [
            _parse_json_sse(c) for c in chunks if c.startswith("data:") and "DONE" not in c
        ]
        assert any(e["type"] == "session.error" for e in sse_parsed)
        assert chunks[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_tool_call_event_yields_assistant_tool_call(self):
        events = [
            {"type": "tool_call", "id": "tc1", "name": "bash", "arguments": {"command": "pwd"}},
            {"type": "done", "usage": {}},
        ]
        proc = _make_proc_mock(_json_lines(events))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("run ls", "ctx"))
        tool_chunks = [
            _parse_json_sse(c) for c in chunks if c.startswith("data:") and "tool_call" in c
        ]
        assert len(tool_chunks) == 1
        assert tool_chunks[0]["data"]["name"] == "bash"

    @pytest.mark.asyncio
    async def test_reasoning_event_yields_reasoning_delta(self):
        events = [
            {"type": "reasoning", "content": "Let me think..."},
            {"type": "done", "usage": {}},
        ]
        proc = _make_proc_mock(_json_lines(events))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("think", "ctx"))
        reasoning = [
            _parse_json_sse(c) for c in chunks if c.startswith("data:") and "reasoning_delta" in c
        ]
        assert len(reasoning) == 1
        assert reasoning[0]["data"]["delta"] == "Let me think..."

    @pytest.mark.asyncio
    async def test_zero_usage_emitted_when_no_done_event(self):
        """When no done event is seen, usage SSE is still emitted with zeros."""
        events = [
            {"type": "message", "role": "assistant", "content": "Hello!"},
        ]
        proc = _make_proc_mock(_json_lines(events))
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            chunks = await _collect(_make_backend().stream("hi", "ctx"))
        usage_chunks = [
            _parse_json_sse(c) for c in chunks if c.startswith("data:") and "assistant.usage" in c
        ]
        assert len(usage_chunks) == 1
        assert usage_chunks[0]["data"]["total_tokens"] == 0
        assert usage_chunks[0]["data"]["backend"] == "codex"

    @pytest.mark.asyncio
    async def test_cwd_passed_to_subprocess(self):
        proc = _make_proc_mock([])
        b = _make_backend(cwd="/tmp/workspace")
        captured_kwargs: list[dict] = []

        async def fake_exec(*args: Any, **kwargs: Any) -> MagicMock:
            captured_kwargs.append(kwargs)
            return proc

        with patch("asyncio.create_subprocess_exec", new=fake_exec):
            await _collect(b.stream("hi", "ctx"))

        assert captured_kwargs[0]["cwd"] == "/tmp/workspace"
