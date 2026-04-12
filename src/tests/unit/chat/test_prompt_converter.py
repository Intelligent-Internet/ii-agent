"""Unit tests for Anthropic prompt_converter pure functions.

Tests for:
- group_into_blocks: pure message grouping logic
- convert_tool_result_content: pure output-type conversion
"""

from __future__ import annotations

import json
import uuid
from typing import List
from unittest.mock import MagicMock

import pytest

from ii_agent.chat.llm.anthropic.prompt_converter import (
    AssistantBlock,
    SystemBlock,
    UserBlock,
    convert_tool_result_content,
    group_into_blocks,
)
from ii_agent.chat.types import (
    ArrayResultContent,
    ErrorJsonContent,
    ErrorTextContent,
    ExecutionDeniedContent,
    FileDataContentPart,
    FileUrlContentPart,
    ImageDataContentPart,
    ImageUrlContentPart,
    JsonResultContent,
    Message,
    MessageRole,
    StorybookPageResult,
    StorybookProgressContent,
    StorybookResultContent,
    TextContent,
    TextResultContent,
    ToolResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msg(role: MessageRole, text: str = "hello") -> Message:
    """Make a minimal Message with a single TextContent part."""
    return Message(
        id=uuid.uuid4(),
        role=role,
        session_id=uuid.uuid4(),
        parts=[TextContent(text=text)],
        model="claude-3-5-sonnet",
    )


def _tool_result(output) -> MagicMock:
    """Make a fake tool result container with the given output."""
    result = MagicMock()
    result.output = output
    return result


# ---------------------------------------------------------------------------
# group_into_blocks
# ---------------------------------------------------------------------------


class TestGroupIntoBlocks:
    def test_empty_input_returns_empty_list(self):
        assert group_into_blocks([]) == []

    def test_single_user_message_creates_user_block(self):
        msgs = [_msg(MessageRole.USER)]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 1
        assert isinstance(blocks[0], UserBlock)
        assert len(blocks[0].messages) == 1

    def test_single_assistant_message_creates_assistant_block(self):
        msgs = [_msg(MessageRole.ASSISTANT)]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 1
        assert isinstance(blocks[0], AssistantBlock)

    def test_single_system_message_creates_system_block(self):
        msgs = [_msg(MessageRole.SYSTEM)]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 1
        assert isinstance(blocks[0], SystemBlock)

    def test_tool_messages_grouped_with_user(self):
        user = _msg(MessageRole.USER)
        tool = _msg(MessageRole.TOOL)
        blocks = group_into_blocks([user, tool])
        # Both belong to a single UserBlock
        assert len(blocks) == 1
        assert isinstance(blocks[0], UserBlock)
        assert len(blocks[0].messages) == 2

    def test_consecutive_user_messages_in_same_block(self):
        msgs = [_msg(MessageRole.USER), _msg(MessageRole.USER)]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 1
        assert isinstance(blocks[0], UserBlock)
        assert len(blocks[0].messages) == 2

    def test_alternating_user_assistant_creates_two_blocks(self):
        msgs = [_msg(MessageRole.USER), _msg(MessageRole.ASSISTANT)]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 2
        assert isinstance(blocks[0], UserBlock)
        assert isinstance(blocks[1], AssistantBlock)

    def test_full_turn_order(self):
        msgs = [
            _msg(MessageRole.USER, "user turn 1"),
            _msg(MessageRole.ASSISTANT, "assistant turn 1"),
            _msg(MessageRole.USER, "user turn 2"),
            _msg(MessageRole.ASSISTANT, "assistant turn 2"),
        ]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 4
        assert [b.type for b in blocks] == ["user", "assistant", "user", "assistant"]

    def test_system_then_user_then_assistant(self):
        msgs = [
            _msg(MessageRole.SYSTEM),
            _msg(MessageRole.USER),
            _msg(MessageRole.ASSISTANT),
        ]
        blocks = group_into_blocks(msgs)
        assert len(blocks) == 3
        assert blocks[0].type == "system"
        assert blocks[1].type == "user"
        assert blocks[2].type == "assistant"

    def test_tool_without_preceding_user_starts_new_user_block(self):
        """Tool message with no prior user message starts a fresh UserBlock."""
        msgs = [_msg(MessageRole.ASSISTANT), _msg(MessageRole.TOOL)]
        blocks = group_into_blocks(msgs)
        # AssistantBlock then UserBlock (tool grouped into user)
        assert len(blocks) == 2
        assert blocks[0].type == "assistant"
        assert blocks[1].type == "user"
        assert blocks[1].messages[0].role == MessageRole.TOOL

    def test_message_order_preserved_within_block(self):
        m1 = _msg(MessageRole.USER, "first")
        m2 = _msg(MessageRole.TOOL, "second")
        m3 = _msg(MessageRole.USER, "third")
        blocks = group_into_blocks([m1, m2, m3])
        assert len(blocks) == 1
        assert blocks[0].messages[0].parts[0].text == "first"
        assert blocks[0].messages[2].parts[0].text == "third"


# ---------------------------------------------------------------------------
# convert_tool_result_content
# ---------------------------------------------------------------------------


class TestConvertToolResultContent:
    def test_text_result_content_not_error(self):
        output = TextResultContent(value="the search found something")
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert content == "the search found something"
        assert not is_error

    def test_error_text_content_is_error(self):
        output = ErrorTextContent(value="something went wrong")
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert content == "something went wrong"
        assert is_error

    def test_execution_denied_content_not_error(self):
        output = ExecutionDeniedContent(reason="permission denied")
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert content == "permission denied"
        assert not is_error

    def test_execution_denied_without_reason_returns_default(self):
        output = ExecutionDeniedContent(reason=None)
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert "denied" in content.lower()
        assert not is_error

    def test_json_result_content_serialized(self):
        data = {"key": "value", "count": 3}
        output = JsonResultContent(value=data)
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert json.loads(content) == data
        assert not is_error

    def test_error_json_content_is_error(self):
        output = ErrorJsonContent(value={"error": "oops"})
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert json.loads(content) == {"error": "oops"}
        assert is_error

    def test_array_result_with_text_parts(self):
        from ii_agent.chat.types import TextContentPart

        output = ArrayResultContent(
            value=[
                TextContentPart(type="text", text="part one"),
                TextContentPart(type="text", text="part two"),
            ]
        )
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert not is_error
        assert isinstance(content, list)
        assert len(content) == 2
        assert content[0] == {"type": "text", "text": "part one"}

    def test_array_result_with_image_data(self):
        from ii_agent.chat.types import ImageDataContentPart

        output = ArrayResultContent(
            value=[
                ImageDataContentPart(
                    type="image-data",
                    media_type="image/png",
                    data="base64data",
                )
            ]
        )
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert not is_error
        assert isinstance(content, list)
        assert content[0]["type"] == "image"
        assert content[0]["source"]["media_type"] == "image/png"

    def test_array_result_with_image_url(self):
        from ii_agent.chat.types import ImageUrlContentPart

        output = ArrayResultContent(
            value=[
                ImageUrlContentPart(type="image-url", url="https://example.com/img.png")
            ]
        )
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert not is_error
        assert isinstance(content, list)
        # Image URLs converted to text markdown
        assert content[0]["type"] == "text"
        assert "https://example.com/img.png" in content[0]["text"]

    def test_array_result_pdf_file_data(self):
        from ii_agent.chat.types import FileDataContentPart

        output = ArrayResultContent(
            value=[
                FileDataContentPart(
                    type="file-data",
                    mime_type="application/pdf",
                    data="pdfbase64",
                )
            ]
        )
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert not is_error
        assert isinstance(content, list)
        assert content[0]["type"] == "document"
        assert content[0]["source"]["data"] == "pdfbase64"

    def test_array_result_empty_returns_no_content(self):
        output = ArrayResultContent(value=[])
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert not is_error
        assert content == "No content"

    def test_array_result_file_url_converted_to_text(self):
        from ii_agent.chat.types import FileUrlContentPart

        output = ArrayResultContent(
            value=[
                FileUrlContentPart(
                    type="file-url", url="https://example.com/doc.pdf", mime_type="application/pdf"
                )
            ]
        )
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert not is_error
        assert isinstance(content, list)
        assert content[0]["type"] == "text"
        assert "https://example.com/doc.pdf" in content[0]["text"]

    def test_array_result_non_pdf_file_data_warns(self):
        """Non-PDF file data should log a warning and produce no content block."""
        from ii_agent.chat.types import FileDataContentPart

        output = ArrayResultContent(
            value=[
                FileDataContentPart(
                    type="file-data",
                    mime_type="image/tiff",
                    data="base64data",
                )
            ]
        )
        result = _tool_result(output)
        # Should produce "No content" because unsupported type is skipped
        content, is_error = convert_tool_result_content(result)
        assert not is_error
        assert content == "No content"

    def test_storybook_progress_content(self, monkeypatch):
        import uuid as _uuid
        import json as _json

        from ii_agent.chat.types import StorybookProgressContent

        # Patch json.dumps to handle UUID → str
        original_dumps = _json.dumps
        def _dumps(obj, **kwargs):
            import uuid as _u
            class _Enc(_json.JSONEncoder):
                def default(self, o):
                    if isinstance(o, _u.UUID):
                        return str(o)
                    return super().default(o)
            return original_dumps(obj, cls=_Enc, **kwargs)
        monkeypatch.setattr("ii_agent.chat.llm.anthropic.prompt_converter.json.dumps", _dumps)

        output = StorybookProgressContent(
            storybook_id=_uuid.uuid4(),
            storybook_name="My Story",
            total_pages=5,
            completed_pages=2,
            current_page=3,
            status="generating",
            generating_pages=[3, 4],
        )
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert not is_error
        parsed = _json.loads(content)
        assert parsed["type"] == "storybook_progress"
        assert parsed["storybook_name"] == "My Story"
        assert parsed["total_pages"] == 5

    def test_storybook_result_content(self, monkeypatch):
        import uuid as _uuid
        import json as _json

        from ii_agent.chat.types import StorybookPageResult, StorybookResultContent

        # Patch json.dumps to handle UUID → str
        original_dumps = _json.dumps
        def _dumps(obj, **kwargs):
            import uuid as _u
            class _Enc(_json.JSONEncoder):
                def default(self, o):
                    if isinstance(o, _u.UUID):
                        return str(o)
                    return super().default(o)
            return original_dumps(obj, cls=_Enc, **kwargs)
        monkeypatch.setattr("ii_agent.chat.llm.anthropic.prompt_converter.json.dumps", _dumps)

        page = StorybookPageResult(page_number=1, image_url="https://example.com/p1.jpg")
        output = StorybookResultContent(
            storybook_id=_uuid.uuid4(),
            storybook_name="Final Story",
            pages=[page],
        )
        result = _tool_result(output)
        content, is_error = convert_tool_result_content(result)
        assert not is_error
        parsed = _json.loads(content)
        assert parsed["type"] == "storybook"
        assert parsed["storybook_name"] == "Final Story"
        assert parsed["page_count"] == 1
        assert parsed["pages"][0]["image_url"] == "https://example.com/p1.jpg"

    def test_unknown_output_type_returns_string(self):
        """Unknown types fall through to str(output)."""

        class UnknownOutput:
            def __str__(self):
                return "mystery output"

        result = _tool_result(UnknownOutput())
        content, is_error = convert_tool_result_content(result)
        assert "mystery output" in content
        assert not is_error
