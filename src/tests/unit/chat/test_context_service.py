"""Unit tests for ContextWindowManager and SummarizationService pure methods."""

from __future__ import annotations

import uuid

from ii_agent.chat.application.context_service import (
    ContextWindowManager,
    SummarizationService,
    CONTEXT_WINDOWS,
)
from ii_agent.chat.types import (
    CouncilMemberOutput,
    CouncilSynthesis,
    Message,
    MessageRole,
    TextContent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000000")


def _msg(role: MessageRole, text: str, *, tokens: int = 10) -> Message:
    return Message(
        id=uuid.uuid4(),
        role=role,
        session_id=SESSION_ID,
        parts=[TextContent(text=text)],
        tokens=tokens,
    )


def _council_msg(synthesis: str | None = "synth", members: int = 2) -> Message:
    parts = [
        CouncilMemberOutput(
            model_id=f"m{i}",
            model_name=f"Model{i}",
            role="assistant",
            content=f"output from model {i}",
        )
        for i in range(members)
    ]
    if synthesis is not None:
        parts.append(CouncilSynthesis(synthesis_model_id="synth-model", content=synthesis))
    return Message(
        id=uuid.uuid4(),
        role=MessageRole.ASSISTANT,
        session_id=SESSION_ID,
        parts=parts,
        tokens=200,
    )


# ---------------------------------------------------------------------------
# CONTEXT_WINDOWS constant tests
# ---------------------------------------------------------------------------


class TestContextWindows:
    def test_default_key_exists(self):
        assert "__default__" in CONTEXT_WINDOWS

    def test_default_value_is_positive(self):
        assert CONTEXT_WINDOWS["__default__"] > 0

    def test_known_models_present(self):
        # At least one of these should exist
        model_keys = list(CONTEXT_WINDOWS.keys())
        assert len(model_keys) >= 2


# ---------------------------------------------------------------------------
# _collapse_council_messages
# ---------------------------------------------------------------------------


class TestCollapseCouncilMessages:
    def test_non_assistant_messages_pass_through_unchanged(self):
        msgs = [
            _msg(MessageRole.USER, "hello"),
            _msg(MessageRole.SYSTEM, "system prompt"),
        ]
        result = ContextWindowManager._collapse_council_messages(msgs)
        assert result == msgs

    def test_regular_assistant_messages_pass_through(self):
        msg = _msg(MessageRole.ASSISTANT, "regular response")
        result = ContextWindowManager._collapse_council_messages([msg])
        assert len(result) == 1
        assert result[0] is msg

    def test_council_message_collapsed_to_synthesis(self):
        msg = _council_msg(synthesis="Final answer here")
        result = ContextWindowManager._collapse_council_messages([msg])
        assert len(result) == 1
        collapsed = result[0]
        assert len(collapsed.parts) == 1
        assert isinstance(collapsed.parts[0], TextContent)
        assert collapsed.parts[0].text == "Final answer here"

    def test_council_message_without_synthesis_uses_placeholder(self):
        msg = _council_msg(synthesis=None)
        result = ContextWindowManager._collapse_council_messages([msg])
        assert len(result) == 1
        part = result[0].parts[0]
        assert isinstance(part, TextContent)
        assert "unavailable" in part.text.lower() or "synthesis" in part.text.lower()

    def test_council_message_preserves_id_and_role(self):
        msg = _council_msg(synthesis="synth")
        result = ContextWindowManager._collapse_council_messages([msg])
        assert result[0].id == msg.id
        assert result[0].role == MessageRole.ASSISTANT

    def test_mixed_messages_collapsed_correctly(self):
        msgs = [
            _msg(MessageRole.USER, "question"),
            _council_msg(synthesis="answer"),
            _msg(MessageRole.USER, "follow up"),
            _msg(MessageRole.ASSISTANT, "plain response"),
        ]
        result = ContextWindowManager._collapse_council_messages(msgs)
        assert len(result) == 4
        # Council message collapsed
        assert result[1].parts[0].text == "answer"
        # Others unchanged
        assert result[0] is msgs[0]
        assert result[2] is msgs[2]
        assert result[3] is msgs[3]

    def test_empty_list_returns_empty(self):
        result = ContextWindowManager._collapse_council_messages([])
        assert result == []


# ---------------------------------------------------------------------------
# _find_last_user_message
# ---------------------------------------------------------------------------


class TestFindLastUserMessage:
    def test_returns_index_of_last_user_message(self):
        msgs = [
            _msg(MessageRole.USER, "first"),
            _msg(MessageRole.ASSISTANT, "response"),
            _msg(MessageRole.USER, "second"),
            _msg(MessageRole.ASSISTANT, "response2"),
        ]
        idx = ContextWindowManager._find_last_user_message(msgs)
        assert idx == 2

    def test_returns_negative_when_no_user_message(self):
        msgs = [
            _msg(MessageRole.ASSISTANT, "hello"),
            _msg(MessageRole.SYSTEM, "system"),
        ]
        idx = ContextWindowManager._find_last_user_message(msgs)
        assert idx == -1

    def test_single_user_message_returns_zero(self):
        msgs = [_msg(MessageRole.USER, "only")]
        idx = ContextWindowManager._find_last_user_message(msgs)
        assert idx == 0

    def test_empty_returns_negative(self):
        idx = ContextWindowManager._find_last_user_message([])
        assert idx == -1

    def test_returns_last_not_first(self):
        msgs = [
            _msg(MessageRole.USER, "first"),
            _msg(MessageRole.USER, "last"),
        ]
        idx = ContextWindowManager._find_last_user_message(msgs)
        assert idx == 1


# ---------------------------------------------------------------------------
# SummarizationService._build_conversation_text
# ---------------------------------------------------------------------------


class TestBuildConversationText:
    def test_includes_user_and_assistant_text(self):
        msgs = [
            _msg(MessageRole.USER, "what is 2+2?"),
            _msg(MessageRole.ASSISTANT, "It is 4."),
        ]
        text = SummarizationService._build_conversation_text(msgs)
        assert "USER: what is 2+2?" in text
        assert "ASSISTANT: It is 4." in text

    def test_skips_system_messages(self):
        msgs = [
            _msg(MessageRole.SYSTEM, "system prompt"),
            _msg(MessageRole.USER, "hello"),
        ]
        text = SummarizationService._build_conversation_text(msgs)
        assert "SYSTEM" not in text
        assert "system prompt" not in text

    def test_separates_messages_with_double_newline(self):
        msgs = [
            _msg(MessageRole.USER, "q1"),
            _msg(MessageRole.ASSISTANT, "a1"),
        ]
        text = SummarizationService._build_conversation_text(msgs)
        assert "\n\n" in text

    def test_empty_list_returns_empty_string(self):
        text = SummarizationService._build_conversation_text([])
        assert text == ""

    def test_skips_messages_without_text_parts(self):
        from ii_agent.chat.types import ToolCall

        msg = Message(
            id=uuid.uuid4(),
            role=MessageRole.ASSISTANT,
            session_id=SESSION_ID,
            parts=[
                ToolCall(
                    id="tc1",
                    name="run_code",
                    input='{"code": "print(1)"}',
                )
            ],
        )
        text = SummarizationService._build_conversation_text([msg])
        # Should not have ASSISTANT line since no TextContent
        assert "ASSISTANT" not in text

    def test_multiple_text_parts_joined(self):
        msg = Message(
            id=uuid.uuid4(),
            role=MessageRole.USER,
            session_id=SESSION_ID,
            parts=[
                TextContent(text="part1"),
                TextContent(text="part2"),
            ],
        )
        text = SummarizationService._build_conversation_text([msg])
        assert "part1" in text
        assert "part2" in text


# ---------------------------------------------------------------------------
# SummarizationService._create_fallback_summary
# ---------------------------------------------------------------------------


class TestCreateFallbackSummary:
    def test_returns_tuple_of_str_and_int(self):
        msgs = [_msg(MessageRole.USER, "hello", tokens=5)]
        result = SummarizationService._create_fallback_summary(msgs)
        assert isinstance(result, tuple)
        summary_text, total_tokens = result
        assert isinstance(summary_text, str)
        assert isinstance(total_tokens, int)

    def test_includes_recent_messages_section(self):
        msgs = [_msg(MessageRole.USER, "hello")]
        text, _ = SummarizationService._create_fallback_summary(msgs)
        assert "Recent" in text or "recent" in text

    def test_uses_last_5_messages_only(self):
        msgs = [_msg(MessageRole.USER, f"msg{i}", tokens=10) for i in range(10)]
        _, tokens = SummarizationService._create_fallback_summary(msgs)
        # tokens should be sum of last 5 only: 5 * 10 = 50
        assert tokens == 50

    def test_includes_parent_summary_when_provided(self):
        msgs = [_msg(MessageRole.USER, "hello")]
        text, _ = SummarizationService._create_fallback_summary(msgs, "prior summary content")
        assert "prior summary content" in text

    def test_empty_messages_returns_string(self):
        text, _ = SummarizationService._create_fallback_summary([])
        assert isinstance(text, str)
