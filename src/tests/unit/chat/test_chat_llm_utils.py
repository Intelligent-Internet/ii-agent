"""Tests for ii_agent.chat.llm.utils — make_message, extract_text_content, parse_tool_input, ToolLoopResult."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock


class TestChatLLMUtils:
    def _session_id(self):
        return uuid.uuid4()

    def test_make_message(self):
        """Line 30: creates Message with fresh UUID."""
        from ii_agent.chat.llm.utils import make_message
        from ii_agent.chat.types import MessageRole, TextContent

        sid = self._session_id()
        msg = make_message(
            role=MessageRole.USER,
            session_id=sid,
            parts=[TextContent(text="hello")],
        )
        assert msg.role == MessageRole.USER
        assert msg.session_id == sid
        assert msg.id is not None

    def test_make_message_assistant(self):
        from ii_agent.chat.llm.utils import make_message
        from ii_agent.chat.types import MessageRole

        msg = make_message(role=MessageRole.ASSISTANT, session_id=self._session_id(), parts=[])
        assert msg.role == MessageRole.ASSISTANT

    def test_extract_text_content_all_text(self):
        """Line 40: joins TextContent parts."""
        from ii_agent.chat.llm.utils import extract_text_content
        from ii_agent.chat.types import TextContent

        parts = [TextContent(text="hello"), TextContent(text="world")]
        result = extract_text_content(parts)
        assert result == "hello\nworld"

    def test_extract_text_content_empty(self):
        from ii_agent.chat.llm.utils import extract_text_content

        assert extract_text_content([]) == ""

    def test_extract_text_content_mixed_parts(self):
        """Skips non-TextContent parts."""
        from ii_agent.chat.llm.utils import extract_text_content
        from ii_agent.chat.types import TextContent

        text = TextContent(text="answer")
        mock_part = MagicMock(spec=[])  # no 'text' attribute
        result = extract_text_content([text, mock_part])
        assert result == "answer"

    def test_parse_tool_input_with_dict(self):
        """Lines 45-46: dict input returned as-is."""
        from ii_agent.chat.llm.utils import parse_tool_input

        d = {"key": "value", "count": 42}
        assert parse_tool_input(d) == d

    def test_parse_tool_input_with_non_dict(self):
        """Lines 45, 47: non-dict → empty dict."""
        from ii_agent.chat.llm.utils import parse_tool_input

        assert parse_tool_input("raw string") == {}
        assert parse_tool_input(None) == {}
        assert parse_tool_input(123) == {}
        assert parse_tool_input([1, 2]) == {}

    def test_tool_loop_result_constructor(self):
        """Lines 56-57: ToolLoopResult stores attributes."""
        from ii_agent.chat.llm.utils import ToolLoopResult

        payload = {"result": "ok"}
        msgs = [MagicMock()]
        tlr = ToolLoopResult(final_payload=payload, messages=msgs)
        assert tlr.final_payload == payload
        assert tlr.messages is msgs
