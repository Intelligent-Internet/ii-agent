"""Tests for ThinkingBlock sanitization in State and AgentController.

Covers the bug where assistant turns ending with a ThinkingBlock caused
Claude API 400 errors ("The final block in an assistant message cannot be
`thinking`") on subsequent calls.

AgentController imports are deferred to test time to avoid triggering the
full server import chain at collection time (circular imports).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from ii_agent.llm.base import (
    TextPrompt,
    TextResult,
    ThinkingBlock,
    RedactedThinkingBlock,
    ToolCall,
    ToolFormattedResult,
)
from ii_agent.controller.state import State
from ii_agent.utils.constants import COMPLETE_MESSAGE


# ---------------------------------------------------------------------------
# State._sanitize_thinking_blocks
# ---------------------------------------------------------------------------


class TestSanitizeThinkingBlocks:
    """Tests for State._sanitize_thinking_blocks()."""

    def test_empty_turns_unchanged(self):
        result = State._sanitize_thinking_blocks([])
        assert result == []

    def test_no_thinking_blocks_unchanged(self):
        turns = [
            [TextPrompt(text="Hello")],
            [TextResult(text="Hi")],
        ]
        result = State._sanitize_thinking_blocks(turns)
        assert len(result) == 2
        assert isinstance(result[1][-1], TextResult)

    def test_thinking_block_not_last_unchanged(self):
        """ThinkingBlock followed by TextResult should be left alone."""
        turns = [
            [ThinkingBlock(thinking="analyzing", signature="sig"), TextResult(text="done")],
        ]
        result = State._sanitize_thinking_blocks(turns)
        assert len(result[0]) == 2
        assert isinstance(result[0][-1], TextResult)

    def test_thinking_block_last_gets_text_appended(self):
        """A turn ending with ThinkingBlock must get a TextResult appended."""
        turns = [
            [ThinkingBlock(thinking="analyzing", signature="sig")],
        ]
        result = State._sanitize_thinking_blocks(turns)
        assert len(result[0]) == 2
        assert isinstance(result[0][-1], TextResult)
        assert result[0][-1].text == "(continued)"

    def test_multiple_turns_only_trailing_thinking_fixed(self):
        """Only turns where the LAST block is ThinkingBlock are fixed."""
        turns = [
            [TextPrompt(text="Hello")],
            [ThinkingBlock(thinking="think1", signature="s1"), TextResult(text="ok")],
            [ThinkingBlock(thinking="think2", signature="s2")],  # broken
            [TextResult(text="final")],
        ]
        result = State._sanitize_thinking_blocks(turns)
        # Turn 1: unchanged (ThinkingBlock not last)
        assert len(result[1]) == 2
        assert isinstance(result[1][-1], TextResult)
        # Turn 2: fixed
        assert len(result[2]) == 2
        assert isinstance(result[2][-1], TextResult)
        assert result[2][-1].text == "(continued)"
        # Turn 3: unchanged
        assert len(result[3]) == 1

    def test_multiple_trailing_thinking_blocks(self):
        """Multiple ThinkingBlocks at the end — only need one TextResult."""
        turns = [
            [
                ThinkingBlock(thinking="first", signature="s1"),
                ThinkingBlock(thinking="second", signature="s2"),
            ],
        ]
        result = State._sanitize_thinking_blocks(turns)
        assert isinstance(result[0][-1], TextResult)

    def test_redacted_thinking_block_last_gets_text_appended(self):
        """A turn ending with RedactedThinkingBlock must also get a TextResult appended."""
        turns = [
            [RedactedThinkingBlock(data="abc123")],
        ]
        result = State._sanitize_thinking_blocks(turns)
        assert len(result[0]) == 2
        assert isinstance(result[0][-1], TextResult)
        assert result[0][-1].text == "(continued)"

    def test_turn_with_tool_call_after_thinking_unchanged(self):
        """A turn ending with a ToolCall after ThinkingBlock should be fine."""
        turns = [
            [
                ThinkingBlock(thinking="plan", signature="s"),
                ToolCall(tool_call_id="tc1", tool_name="ls", tool_input="{}"),
            ],
        ]
        result = State._sanitize_thinking_blocks(turns)
        # ToolCall is last, not ThinkingBlock, so no change
        assert len(result[0]) == 2
        assert isinstance(result[0][-1], ToolCall)


# ---------------------------------------------------------------------------
# State.restore_from_session — applies sanitization
# ---------------------------------------------------------------------------


class TestRestoreFromSessionSanitization:
    """Ensure restore_from_session sanitizes ThinkingBlock-trailing turns."""

    def test_corrupted_state_is_sanitized_on_restore(self):
        """A persisted state with trailing ThinkingBlock gets fixed on load."""
        state = State()

        # Build a corrupted state dict as it would appear serialized
        corrupted_state = State()
        corrupted_state.add_user_prompt("hello")
        corrupted_state.add_assistant_turn(
            [ThinkingBlock(thinking="I'm analyzing...", signature="abc")]
        )
        json_bytes = corrupted_state.model_dump()

        import json, io

        json_str = json.dumps(json_bytes)

        mock_store = MagicMock()
        mock_store.read.return_value = io.BytesIO(json_str.encode("utf-8"))

        state.restore_from_session("test-session-id", mock_store)

        # The assistant turn should now end with TextResult, not ThinkingBlock
        assistant_turn = state.message_lists[1]
        assert isinstance(assistant_turn[-1], TextResult)
        assert assistant_turn[-1].text == "(continued)"


# ---------------------------------------------------------------------------
# State.save_to_session — sanitizes before writing (defense-in-depth)
# ---------------------------------------------------------------------------


class TestSaveToSessionSanitization:
    """Ensure save_to_session sanitizes ThinkingBlock-trailing turns before persisting."""

    def test_corrupted_turns_sanitized_before_save(self):
        """Trailing ThinkingBlock must be fixed before JSON is written to storage."""
        import json, io

        state = State()
        state.add_user_prompt("hello")
        # Directly inject corrupted turn (bypass add_assistant_turn which might not corrupt)
        state.message_lists.append(
            [ThinkingBlock(thinking="analyzing", signature="abc")]
        )

        written_data = io.BytesIO()
        mock_store = MagicMock()
        mock_store.write = MagicMock(side_effect=lambda content, path: written_data.write(content.read()))

        state.save_to_session("test-session-id", mock_store)

        # Parse what was written and verify the turn was sanitized
        written_data.seek(0)
        saved = json.loads(written_data.read().decode("utf-8"))
        assistant_turn = saved["message_lists"][1]
        assert len(assistant_turn) == 2
        assert assistant_turn[-1]["type"] == "text_result"
        assert assistant_turn[-1]["text"] == "(continued)"

    def test_redacted_thinking_sanitized_before_save(self):
        """Trailing RedactedThinkingBlock must also be fixed before saving."""
        import json, io

        state = State()
        state.add_user_prompt("hello")
        state.message_lists.append(
            [RedactedThinkingBlock(data="secret")]
        )

        written_data = io.BytesIO()
        mock_store = MagicMock()
        mock_store.write = MagicMock(side_effect=lambda content, path: written_data.write(content.read()))

        state.save_to_session("test-session-id", mock_store)

        written_data.seek(0)
        saved = json.loads(written_data.read().decode("utf-8"))
        assistant_turn = saved["message_lists"][1]
        assert len(assistant_turn) == 2
        assert assistant_turn[-1]["type"] == "text_result"
        assert assistant_turn[-1]["text"] == "(continued)"

    def test_clean_state_unchanged_on_save(self):
        """State without trailing thinking should be saved as-is."""
        import json, io

        state = State()
        state.add_user_prompt("hello")
        state.message_lists.append([TextResult(text="done")])

        written_data = io.BytesIO()
        mock_store = MagicMock()
        mock_store.write = MagicMock(side_effect=lambda content, path: written_data.write(content.read()))

        state.save_to_session("test-session-id", mock_store)

        written_data.seek(0)
        saved = json.loads(written_data.read().decode("utf-8"))
        assistant_turn = saved["message_lists"][1]
        assert len(assistant_turn) == 1
        assert assistant_turn[0]["type"] == "text_result"


# ---------------------------------------------------------------------------
# AgentController.run_impl — appends TextResult when response ends with thinking
#
# Importing agent_controller triggers ii_agent.server.__init__ → create_app
# via ii_agent.server.services.agent_run_service.  We temporarily stub only
# the specific service module in sys.modules, import AgentController, then
# restore the originals so later tests aren't affected.
# ---------------------------------------------------------------------------

import sys
import types

_stubs = {}
_originals = {}

for _mod_name in [
    "ii_agent.server",
    "ii_agent.server.services",
    "ii_agent.server.services.agent_run_service",
]:
    _originals[_mod_name] = sys.modules.get(_mod_name)

# Install temporary stubs
_server_stub = types.ModuleType("ii_agent.server")
_server_stub.__path__ = []  # type: ignore[attr-defined]
_server_stub.__package__ = "ii_agent.server"

_services_stub = types.ModuleType("ii_agent.server.services")
_services_stub.__path__ = []  # type: ignore[attr-defined]
_services_stub.__package__ = "ii_agent.server.services"

_agent_run_service_stub = types.ModuleType("ii_agent.server.services.agent_run_service")
_agent_run_service_stub.__package__ = "ii_agent.server.services.agent_run_service"
_agent_run_service_stub.AgentRunService = MagicMock()  # type: ignore[attr-defined]

for _mod_name, _mod in [
    ("ii_agent.server", _server_stub),
    ("ii_agent.server.services", _services_stub),
    ("ii_agent.server.services.agent_run_service", _agent_run_service_stub),
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _mod

from ii_agent.controller.agent_controller import AgentController
from ii_agent.controller.agent import AgentResponse

# Restore original modules (or remove stubs) so other tests aren't affected
for _mod_name, _orig in _originals.items():
    if _orig is None:
        sys.modules.pop(_mod_name, None)
    else:
        sys.modules[_mod_name] = _orig


class TestAgentControllerThinkingBlock:
    """Tests for AgentController handling of ThinkingBlock-only responses."""

    @pytest.mark.asyncio
    async def test_thinking_only_response_gets_text_appended(self):
        """When LLM returns only ThinkingBlock, a TextResult should be appended
        so the response doesn't end with a thinking block."""
        mock_agent = MagicMock()
        # Return only a ThinkingBlock
        mock_agent.astep = AsyncMock(
            return_value=AgentResponse(
                content=[ThinkingBlock(thinking="deep thought", signature="sig")],
                metrics=None,
            )
        )

        mock_history = State()

        mock_event_stream = MagicMock()
        mock_event_stream.publish = AsyncMock()

        mock_tool_manager = MagicMock()

        mock_context_manager = MagicMock()
        mock_context_manager.should_truncate.return_value = False
        mock_context_manager.apply_truncation_if_needed = AsyncMock(side_effect=lambda msgs: msgs)

        session_id = uuid4()
        run_id = uuid4()

        controller = AgentController(
            agent=mock_agent,
            tool_manager=mock_tool_manager,
            history=mock_history,
            event_stream=mock_event_stream,
            context_manager=mock_context_manager,
            session_id=session_id,
            run_id=run_id,
            max_turns=1,
        )

        with patch.object(controller, "is_interrupted", new_callable=AsyncMock, return_value=False):
            result = await controller.run_impl({"instruction": "test"})

        # run_impl adds user prompt at index 0, assistant response at index 1
        last_assistant_turn = mock_history.message_lists[1]
        assert not isinstance(last_assistant_turn[-1], ThinkingBlock)
        assert isinstance(last_assistant_turn[-1], TextResult)

    @pytest.mark.asyncio
    async def test_text_response_not_modified(self):
        """A normal TextResult response should not be modified."""
        mock_agent = MagicMock()
        mock_agent.astep = AsyncMock(
            return_value=AgentResponse(
                content=[TextResult(text="Done!")],
                metrics=None,
            )
        )

        mock_history = State()

        mock_event_stream = MagicMock()
        mock_event_stream.publish = AsyncMock()

        mock_context_manager = MagicMock()
        mock_context_manager.should_truncate.return_value = False
        mock_context_manager.apply_truncation_if_needed = AsyncMock(side_effect=lambda msgs: msgs)

        session_id = uuid4()
        run_id = uuid4()

        controller = AgentController(
            agent=mock_agent,
            tool_manager=MagicMock(),
            history=mock_history,
            event_stream=mock_event_stream,
            context_manager=mock_context_manager,
            session_id=session_id,
            run_id=run_id,
            max_turns=1,
        )

        with patch.object(controller, "is_interrupted", new_callable=AsyncMock, return_value=False):
            result = await controller.run_impl({"instruction": "test"})

        # run_impl adds user prompt at index 0, assistant response at index 1
        last_assistant_turn = mock_history.message_lists[1]
        assert len(last_assistant_turn) == 1
        assert isinstance(last_assistant_turn[0], TextResult)

    @pytest.mark.asyncio
    async def test_thinking_then_tool_call_not_modified(self):
        """ThinkingBlock followed by ToolCall (not trailing) should not be modified."""
        tool_call = ToolCall(tool_call_id="tc1", tool_name="bash", tool_input={"command": "ls"})

        mock_agent = MagicMock()
        mock_agent.astep = AsyncMock(
            return_value=AgentResponse(
                content=[
                    ThinkingBlock(thinking="plan", signature="s"),
                    TextResult(text="Let me check"),
                    tool_call,
                ],
                metrics=None,
            )
        )

        mock_history = State()

        mock_event_stream = MagicMock()
        mock_event_stream.publish = AsyncMock()

        mock_tool_manager = MagicMock()
        mock_tool_manager.get_tool.return_value = MagicMock(display_name="bash")
        mock_tool_manager.run_tools_batch = AsyncMock(
            return_value=[MagicMock(
                llm_content="output",
                user_display_content="output",
                is_error=False,
            )]
        )

        mock_context_manager = MagicMock()
        mock_context_manager.should_truncate.return_value = False
        mock_context_manager.apply_truncation_if_needed = AsyncMock(side_effect=lambda msgs: msgs)

        session_id = uuid4()
        run_id = uuid4()

        controller = AgentController(
            agent=mock_agent,
            tool_manager=mock_tool_manager,
            history=mock_history,
            event_stream=mock_event_stream,
            context_manager=mock_context_manager,
            session_id=session_id,
            run_id=run_id,
            max_turns=1,
        )

        with patch.object(controller, "is_interrupted", new_callable=AsyncMock, return_value=False):
            result = await controller.run_impl({"instruction": "test"})

        # run_impl: index 0 = user prompt, index 1 = assistant turn (ThinkingBlock, TextResult, ToolCall)
        assistant_turn = mock_history.message_lists[1]
        assert len(assistant_turn) == 3
        assert isinstance(assistant_turn[0], ThinkingBlock)
        assert isinstance(assistant_turn[2], ToolCall)

    @pytest.mark.asyncio
    async def test_redacted_thinking_only_response_gets_text_appended(self):
        """When LLM returns only RedactedThinkingBlock, a TextResult should be appended."""
        mock_agent = MagicMock()
        mock_agent.astep = AsyncMock(
            return_value=AgentResponse(
                content=[RedactedThinkingBlock(data="redacted-data")],
                metrics=None,
            )
        )

        mock_history = State()

        mock_event_stream = MagicMock()
        mock_event_stream.publish = AsyncMock()

        mock_context_manager = MagicMock()
        mock_context_manager.should_truncate.return_value = False
        mock_context_manager.apply_truncation_if_needed = AsyncMock(side_effect=lambda msgs: msgs)

        session_id = uuid4()
        run_id = uuid4()

        controller = AgentController(
            agent=mock_agent,
            tool_manager=MagicMock(),
            history=mock_history,
            event_stream=mock_event_stream,
            context_manager=mock_context_manager,
            session_id=session_id,
            run_id=run_id,
            max_turns=1,
        )

        with patch.object(controller, "is_interrupted", new_callable=AsyncMock, return_value=False):
            result = await controller.run_impl({"instruction": "test"})

        last_assistant_turn = mock_history.message_lists[1]
        assert not isinstance(last_assistant_turn[-1], RedactedThinkingBlock)
        assert isinstance(last_assistant_turn[-1], TextResult)
