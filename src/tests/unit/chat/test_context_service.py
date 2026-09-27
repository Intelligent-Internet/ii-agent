"""Unit tests for ContextWindowManager and SummarizationService pure methods."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.chat.api.schemas import ChatMessageRequest
from ii_agent.chat.application.chat_service import ChatService
from ii_agent.chat.application.file_processing_service import ChatFileProcessor
from ii_agent.chat.application.file_processor import ProcessedFiles
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
    BinaryContent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000000")


@pytest.mark.asyncio
async def test_loaded_context_expires_images_without_changing_stored_messages():
    messages = [
        _msg(MessageRole.USER, "first"),
        _msg(MessageRole.ASSISTANT, "reply"),
        _msg(MessageRole.USER, "second"),
        _msg(MessageRole.USER, "third"),
    ]
    for message in (messages[0], messages[2], messages[3]):
        message.parts.append(BinaryContent(path="image.png", mime_type="image/png", data=b"img"))

    with (
        patch.object(
            ContextWindowManager, "_get_active_summary", new_callable=AsyncMock, return_value=None
        ),
        patch(
            "ii_agent.chat.application.context_service.MessageService.list_by_session",
            new_callable=AsyncMock,
            return_value=messages,
        ),
        patch("ii_agent.chat.application.context_service.get_settings") as settings,
    ):
        settings.return_value.agent.image_retention_turns = 2
        context = await ContextWindowManager.load_context_for_llm(
            db_session=AsyncMock(), session_id=SESSION_ID
        )
        settings.return_value.agent.image_retention_turns = 0
        no_history_images = await ContextWindowManager.load_context_for_llm(
            db_session=AsyncMock(), session_id=SESSION_ID
        )

    assert [any(isinstance(part, BinaryContent) for part in msg.parts) for msg in context] == [
        False,
        False,
        True,
        True,
    ]
    assert len(messages[0].parts) == 2
    assert all(
        not isinstance(part, BinaryContent)
        for message in no_history_images
        for part in message.parts
    )


@pytest.mark.asyncio
async def test_loaded_context_expires_pdf_after_five_follow_up_turns():
    upload = _msg(MessageRole.USER, "Please review this PDF")
    upload.parts.append(BinaryContent(path="report.pdf", mime_type="application/pdf", data=b"pdf"))
    messages = [upload] + [_msg(MessageRole.USER, f"follow-up {turn}") for turn in range(4)]

    with (
        patch.object(
            ContextWindowManager, "_get_active_summary", new_callable=AsyncMock, return_value=None
        ),
        patch(
            "ii_agent.chat.application.context_service.MessageService.list_by_session",
            new_callable=AsyncMock,
            return_value=messages,
        ),
        patch("ii_agent.chat.application.context_service.get_settings") as settings,
    ):
        settings.return_value.agent.image_retention_turns = 5
        retained = await ContextWindowManager.load_context_for_llm(
            db_session=AsyncMock(), session_id=SESSION_ID
        )
        messages.append(_msg(MessageRole.USER, "fifth completed follow-up"))
        expired = await ContextWindowManager.load_context_for_llm(
            db_session=AsyncMock(), session_id=SESSION_ID
        )

    assert any(isinstance(part, BinaryContent) for part in retained[0].parts)
    assert all(not isinstance(part, BinaryContent) for part in expired[0].parts)
    assert upload.parts[-1].data == b"pdf"


@pytest.mark.asyncio
@pytest.mark.parametrize("mime_type", ["image/png", "application/pdf"])
async def test_recalled_media_starts_a_new_five_turn_window(mime_type):
    original = _msg(MessageRole.USER, "original upload")
    original.parts.append(BinaryContent(path="asset", mime_type=mime_type, data=b"original"))
    recalled = _msg(MessageRole.USER, "recall the attachment")
    recalled.parts.append(BinaryContent(path="asset", mime_type=mime_type, data=b"recalled"))
    messages = [original] + [_msg(MessageRole.USER, str(turn)) for turn in range(5)] + [recalled]

    with (
        patch.object(
            ContextWindowManager, "_get_active_summary", new_callable=AsyncMock, return_value=None
        ),
        patch(
            "ii_agent.chat.application.context_service.MessageService.list_by_session",
            new_callable=AsyncMock,
            return_value=messages,
        ),
        patch("ii_agent.chat.application.context_service.get_settings") as settings,
    ):
        settings.return_value.agent.image_retention_turns = 5
        recent = await ContextWindowManager.load_context_for_llm(
            db_session=AsyncMock(), session_id=SESSION_ID
        )
        messages.extend(_msg(MessageRole.USER, str(turn)) for turn in range(4))
        almost_expired = await ContextWindowManager.load_context_for_llm(
            db_session=AsyncMock(), session_id=SESSION_ID
        )
        messages.append(_msg(MessageRole.USER, "fifth follow-up"))
        expired = await ContextWindowManager.load_context_for_llm(
            db_session=AsyncMock(), session_id=SESSION_ID
        )

    assert not any(isinstance(part, BinaryContent) for part in recent[0].parts)
    assert any(isinstance(part, BinaryContent) for part in recent[6].parts)
    assert any(isinstance(part, BinaryContent) for part in almost_expired[6].parts)
    assert not any(isinstance(part, BinaryContent) for part in expired[6].parts)


@pytest.mark.asyncio
async def test_chat_recall_preflight_attaches_or_clarifies_without_model_call():
    service = ChatService.__new__(ChatService)
    service._container = SimpleNamespace(file_service=SimpleNamespace(recall_for_turn=AsyncMock()))
    service._message_service = SimpleNamespace(
        create_message=AsyncMock(side_effect=[None, SimpleNamespace(id=uuid.uuid4())])
    )
    db = AsyncMock()

    @asynccontextmanager
    async def db_session():
        yield db

    request = ChatMessageRequest(
        content="show earlier image", session_id=SESSION_ID, model_id="test"
    )
    user_id = uuid.uuid4()
    with patch("ii_agent.chat.application.chat_service.get_db_session_local", db_session):
        service._container.file_service.recall_for_turn.return_value = ([str(uuid.uuid4())], None)
        assert await service._prepare_recalled_attachment(request, user_id) is None
        assert request.file_ids == service._container.file_service.recall_for_turn.return_value[0]
        service._container.file_service.recall_for_turn.return_value = (None, "Which file?")
        request.file_ids = None
        text, _ = await service._prepare_recalled_attachment(request, user_id)

    assert text == "Which file?"
    assert service._message_service.create_message.await_count == 2
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("council", [False, True])
async def test_chat_stream_clarification_skips_upload_and_model(council):
    service = ChatService.__new__(ChatService)
    service._prepare_recalled_attachment = AsyncMock(return_value=("Which file?", uuid.uuid4()))
    service._file_processor = MagicMock()
    request = ChatMessageRequest.model_construct(
        content="show the earlier image",
        session_id=SESSION_ID,
        model_id="test",
        council_preferences=SimpleNamespace(enabled=True) if council else None,
    )

    with patch("ii_agent.chat.application.chat_service.CouncilService.validate_preferences"):
        stream = service.stream_council_chat_response if council else service.stream_chat_response
        events = [event async for event in stream(chat_request=request, user_id=uuid.uuid4())]

    assert [event["type"] for event in events] == ["content_delta", "complete"]
    assert events[0]["content"] == "Which file?"
    service._file_processor.process_uploads.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("council", [False, True])
async def test_text_only_upload_is_persisted_before_model_execution(council):
    class StopAfterWriteback(Exception):
        pass

    service = ChatService.__new__(ChatService)
    service._prepare_recalled_attachment = AsyncMock(return_value=None)
    service._container = MagicMock()
    service._file_processor = ChatFileProcessor(config=MagicMock())
    service._message_service = MagicMock()
    message = _msg(MessageRole.USER, "Read the report")
    message.file_ids = [str(uuid.uuid4())]
    service._message_service.create_message = AsyncMock(return_value=message)
    service._message_service.update_message_parts = AsyncMock()
    service.get_model_config = AsyncMock(return_value=MagicMock())
    service._check_credits = AsyncMock()
    service._tool_service = MagicMock()
    service._tool_service.build_tool_registry = AsyncMock(side_effect=StopAfterWriteback)
    service._model_setting_service = MagicMock()
    service._model_setting_service.get_all_available_models = AsyncMock(
        side_effect=StopAfterWriteback
    )
    request = ChatMessageRequest.model_construct(
        session_id=SESSION_ID,
        content="Read the report",
        model_id="test",
        file_ids=message.file_ids,
        council_preferences=(
            SimpleNamespace(enabled=True, council_models=[], synthesis_model_id="test")
            if council
            else None
        ),
        media_preferences=None,
        github_repository=None,
        tools=None,
    )
    db = AsyncMock()

    @asynccontextmanager
    async def db_session():
        yield db

    processed = ProcessedFiles(
        binary_parts=[],
        text_parts=[TextContent(text="\n[Page 1] Invoice total: 42")],
        large_file_ids=set(),
        large_file_info=[],
        skipped_files=[],
    )
    with (
        patch("ii_agent.chat.application.chat_service.get_db_session_local", db_session),
        patch.object(
            ContextWindowManager, "load_context_for_llm", new_callable=AsyncMock, return_value=[]
        ),
        patch("ii_agent.chat.application.file_processing_service.get_storage"),
        patch(
            "ii_agent.chat.application.file_processing_service.process_files_for_message",
            new_callable=AsyncMock,
            return_value=processed,
        ),
        patch("ii_agent.chat.application.chat_service.cancel.register_run", new_callable=AsyncMock),
        patch("ii_agent.chat.application.chat_service.CouncilService.validate_preferences"),
    ):
        stream = service.stream_council_chat_response if council else service.stream_chat_response
        with pytest.raises(StopAfterWriteback):
            async for _ in stream(chat_request=request, user_id=uuid.uuid4()):
                pass

    service._message_service.update_message_parts.assert_awaited_once()
    saved_parts = service._message_service.update_message_parts.await_args.args[2]
    assert "[Page 1] Invoice total: 42" in saved_parts[0].text
    assert db.commit.await_count >= 2


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

    def test_opus_5_context_window_is_1m(self):
        assert CONTEXT_WINDOWS["claude-opus-5"] == 1_000_000

    def test_fable_5_context_window_is_1m(self):
        assert CONTEXT_WINDOWS["claude-fable-5"] == 1_000_000

    def test_opus_4_8_context_window_is_1m(self):
        assert CONTEXT_WINDOWS["claude-opus-4-8"] == 1_000_000

    def test_opus_4_7_context_window_is_1m(self):
        assert CONTEXT_WINDOWS["claude-opus-4-7"] == 1_000_000


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
