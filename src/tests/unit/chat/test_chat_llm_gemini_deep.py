"""Deep unit tests for GeminiProvider - coverage gaps."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.chat.llm.gemini import (
    GeminiProvider,
    GeminiStreamState,
    generate_tool_call_id,
    get_thought_signature_from_content,
    get_thought_signature_from_provider_options,
    get_tool_call_from_parts,
    map_googe_finish_reason,
)
from ii_agent.chat.types import (
    EventType,
    FinishReason,
    Message,
    MessageRole,
    ReasoningContent,
    TextContent,
    ToolCall,
)
from ii_agent.core.config.llm_config import LLMConfig

_SESSION_ID = "deep-gemini-test-001"


def _make_llm_config(model="gemini-pro", temperature=None) -> LLMConfig:
    cfg = MagicMock(spec=LLMConfig)
    cfg.model = model
    cfg.api_key = None
    cfg.vertex_project_id = None
    cfg.vertex_region = None
    cfg.temperature = temperature
    cfg.thinking_tokens = 0
    cfg.setting_id = "test-setting"
    return cfg


def _make_provider(model="gemini-pro", temperature=None) -> GeminiProvider:
    cfg = _make_llm_config(model, temperature)
    with patch("ii_agent.chat.llm.gemini.genai") as mock_genai:
        mock_genai.Client.return_value = MagicMock()
        provider = GeminiProvider(cfg)
    provider.client = MagicMock()
    return provider


def _make_message(role: MessageRole, parts=None) -> Message:
    msg = MagicMock(spec=Message)
    msg.role = role
    msg.parts = parts or []
    msg.tool_results = MagicMock(return_value=[])
    msg.tool_calls = MagicMock(return_value=[])
    return msg


def _make_user_message(text: str = "Hello") -> Message:
    return _make_message(MessageRole.USER, [TextContent(text=text)])


def _make_assistant_message(text: str = "Hi") -> Message:
    return _make_message(MessageRole.ASSISTANT, [TextContent(text=text)])


# ---------------------------------------------------------------------------
# GeminiProvider initialization - vertex vs standard
# ---------------------------------------------------------------------------


class TestGeminiProviderInitDeep:
    def test_standard_init_with_api_key(self):
        cfg = MagicMock(spec=LLMConfig)
        cfg.model = "gemini-pro"
        cfg.api_key = MagicMock()
        cfg.api_key.get_secret_value = MagicMock(return_value="test-api-key")
        cfg.vertex_project_id = None
        cfg.vertex_region = None
        cfg.temperature = None

        with patch("ii_agent.chat.llm.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = MagicMock()
            GeminiProvider(cfg)
            mock_genai.Client.assert_called_once_with(api_key="test-api-key")

    def test_vertex_init_uses_vertex_project_and_region(self):
        cfg = MagicMock(spec=LLMConfig)
        cfg.model = "gemini-pro"
        cfg.api_key = None
        cfg.vertex_project_id = "my-gcp-project"
        cfg.vertex_region = "us-central1"
        cfg.temperature = None

        with patch("ii_agent.chat.llm.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = MagicMock()
            GeminiProvider(cfg)
            mock_genai.Client.assert_called_once_with(
                vertexai=True,
                project="my-gcp-project",
                location="us-central1",
            )

    def test_standard_init_without_api_key(self):
        cfg = MagicMock(spec=LLMConfig)
        cfg.model = "gemini-pro"
        cfg.api_key = None
        cfg.vertex_project_id = None
        cfg.vertex_region = None
        cfg.temperature = None

        with patch("ii_agent.chat.llm.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = MagicMock()
            GeminiProvider(cfg)
            mock_genai.Client.assert_called_once_with(api_key=None)


# ---------------------------------------------------------------------------
# GeminiProvider._convert_messages - deeper coverage
# ---------------------------------------------------------------------------


class TestConvertMessagesDeep:
    """Deep tests for _convert_messages covering all message types."""

    def test_assistant_message_with_reasoning_content(self):
        provider = _make_provider()
        rc = ReasoningContent(thinking="I'm thinking...", signature="sig123")
        # Set provider options for thought signature
        rc.provider_options = {"google": {"thoughtSignature": base64.b64encode(b"sig123").decode()}}

        msg = _make_message(MessageRole.ASSISTANT, [rc])

        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_part = MagicMock()
            mock_types.Part.return_value = mock_part
            mock_types.Content.return_value = MagicMock()
            result = provider._convert_messages([msg])

        assert len(result) == 1

    def test_assistant_message_with_tool_call_finished(self):
        """Finished ToolCall in assistant message creates function_call part."""
        provider = _make_provider()
        tc = ToolCall(id="call_1", name="search", input='{"q": "test"}', finished=True)
        msg = _make_message(MessageRole.ASSISTANT, [tc])

        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_fc = MagicMock()
            mock_types.FunctionCall.return_value = mock_fc
            mock_types.Part.return_value = MagicMock()
            mock_types.Content.return_value = MagicMock()
            result = provider._convert_messages([msg])

        assert len(result) == 1

    def test_assistant_message_with_unfinished_tool_call_skipped(self):
        """Unfinished ToolCall in assistant message should be skipped."""
        provider = _make_provider()
        tc = ToolCall(id="call_1", name="search", input='{"q": "test"}', finished=False)
        msg = _make_message(MessageRole.ASSISTANT, [tc])

        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.Content.return_value = MagicMock()
            result = provider._convert_messages([msg])

        # No parts created for unfinished tool call -> model content with empty parts
        assert len(result) == 1  # Content still created even if parts empty

    def test_assistant_message_with_invalid_json_tool_call(self):
        """ToolCall with invalid JSON input should use empty dict."""
        provider = _make_provider()
        tc = ToolCall(id="call_1", name="search", input="invalid json {", finished=True)
        msg = _make_message(MessageRole.ASSISTANT, [tc])

        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.FunctionCall.return_value = MagicMock()
            mock_types.Part.return_value = MagicMock()
            mock_types.Content.return_value = MagicMock()
            provider._convert_messages([msg])

        # Should not raise
        mock_types.FunctionCall.assert_called()
        call_kwargs = mock_types.FunctionCall.call_args[1]
        assert call_kwargs["args"] == {}

    def test_tool_message_with_multiple_results(self):
        """Tool message with multiple tool results creates multiple function responses."""
        provider = _make_provider()

        tr1 = MagicMock()
        tr1.name = "search"
        tr1.output = MagicMock()
        tr1.output.model_dump.return_value = {"result": "result1"}

        tr2 = MagicMock()
        tr2.name = "calc"
        tr2.output = MagicMock()
        tr2.output.model_dump.return_value = {"result": "result2"}

        msg = _make_message(MessageRole.TOOL)
        msg.tool_results = MagicMock(return_value=[tr1, tr2])

        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.FunctionResponse.return_value = MagicMock()
            mock_types.Part.return_value = MagicMock()
            mock_types.Content.return_value = MagicMock()
            result = provider._convert_messages([msg])

        assert len(result) == 1

    def test_user_message_text_empty_not_added(self):
        """User text content with empty text should not be added."""
        provider = _make_provider()
        msg = _make_message(MessageRole.USER, [TextContent(text="")])

        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.Content.return_value = MagicMock()
            mock_types.Part.return_value = MagicMock()
            provider._convert_messages([msg])

        # Empty text should not add a Part
        mock_types.Part.assert_not_called()

    def test_user_message_unsupported_part_type_logged(self):
        """Unsupported part types should be logged and skipped."""
        provider = _make_provider()
        unsupported_part = MagicMock()
        unsupported_part.__class__.__name__ = "SomeWeirdPart"
        msg = _make_message(MessageRole.USER, [unsupported_part])

        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.Content.return_value = MagicMock()
            result = provider._convert_messages([msg])

        assert len(result) == 1  # Content still created

    def test_assistant_message_unsupported_part_type_logged(self):
        """Unsupported parts in assistant messages should be logged and skipped."""
        provider = _make_provider()
        unsupported = MagicMock()
        unsupported.__class__.__name__ = "UnknownPart"
        msg = _make_message(MessageRole.ASSISTANT, [unsupported])

        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.Content.return_value = MagicMock()
            result = provider._convert_messages([msg])

        assert len(result) == 1

    def test_assistant_empty_text_not_added(self):
        """Assistant message with empty text should not add part."""
        provider = _make_provider()
        msg = _make_message(MessageRole.ASSISTANT, [TextContent(text="")])

        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.Content.return_value = MagicMock()
            provider._convert_messages([msg])

        # Empty text should not add a Part
        mock_types.Part.assert_not_called()

    def test_unknown_message_role_logged_skipped(self):
        """Messages with unknown roles should be logged and skipped."""
        provider = _make_provider()
        msg = MagicMock(spec=Message)
        msg.role = "unknown_role_xyz"
        msg.parts = []
        msg.tool_results = MagicMock(return_value=[])

        with patch("ii_agent.chat.llm.gemini.types"):
            result = provider._convert_messages([msg])

        assert result == []


# ---------------------------------------------------------------------------
# GeminiProvider.send() - response parsing coverage
# ---------------------------------------------------------------------------


class TestGeminiProviderSendDeep:
    """Deep tests for send() covering response parsing edge cases."""

    @pytest.mark.asyncio
    async def test_send_with_thought_part_creates_reasoning_content(self):
        """Thought parts in response should create ReasoningContent."""
        provider = _make_provider()

        thought_part = MagicMock()
        thought_part.text = "My thinking process"
        thought_part.thought = True
        thought_part.thought_signature = b"sig123"
        thought_part.function_call = None

        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = [thought_part]
        candidate.finish_reason = "STOP"

        mock_response = MagicMock()
        mock_response.candidates = [candidate]
        mock_response.usage_metadata = None

        provider.client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await provider.send(messages=[_make_user_message()])

        reasoning_parts = [p for p in result.content if isinstance(p, ReasoningContent)]
        assert len(reasoning_parts) == 1
        assert reasoning_parts[0].thinking == "My thinking process"

    @pytest.mark.asyncio
    async def test_send_with_text_part_and_thought_signature(self):
        """Text parts with thought_signature should have provider_options set."""
        provider = _make_provider()

        text_part = MagicMock()
        text_part.text = "Regular text response"
        text_part.thought = False
        text_part.thought_signature = b"text_sig"
        text_part.function_call = None

        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = [text_part]
        candidate.finish_reason = "STOP"

        mock_response = MagicMock()
        mock_response.candidates = [candidate]
        mock_response.usage_metadata = None

        provider.client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await provider.send(messages=[_make_user_message()])

        text_parts = [p for p in result.content if isinstance(p, TextContent)]
        assert len(text_parts) == 1
        assert text_parts[0].provider_options is not None

    @pytest.mark.asyncio
    async def test_send_with_function_call_and_thought_signature(self):
        """Function call parts with thought_signature should have provider_options."""
        provider = _make_provider()

        fc = MagicMock()
        fc.name = "search"
        fc.args = {"q": "test"}

        func_part = MagicMock()
        func_part.text = None
        func_part.function_call = fc
        func_part.thought_signature = b"fc_sig"

        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = [func_part]
        candidate.finish_reason = "STOP"

        mock_response = MagicMock()
        mock_response.candidates = [candidate]
        mock_response.usage_metadata = None

        provider.client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await provider.send(messages=[_make_user_message()])

        tool_calls = [p for p in result.content if isinstance(p, ToolCall)]
        assert len(tool_calls) == 1
        assert tool_calls[0].provider_options is not None

    @pytest.mark.asyncio
    async def test_send_with_empty_candidates(self):
        """Response with no candidates should return empty content."""
        provider = _make_provider()

        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.usage_metadata = None

        provider.client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await provider.send(messages=[_make_user_message()])

        assert result.content == []
        assert result.finish_reason == FinishReason.UNKNOWN

    @pytest.mark.asyncio
    async def test_send_with_no_content_in_candidate(self):
        """Candidate with no content should return empty content."""
        provider = _make_provider()

        candidate = MagicMock()
        candidate.content = None
        candidate.finish_reason = "STOP"

        mock_response = MagicMock()
        mock_response.candidates = [candidate]
        mock_response.usage_metadata = None

        provider.client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await provider.send(messages=[_make_user_message()])

        assert result.content == []

    @pytest.mark.asyncio
    async def test_send_with_no_parts_in_content(self):
        """Candidate content with no parts should return empty content."""
        provider = _make_provider()

        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = []
        candidate.finish_reason = "STOP"

        mock_response = MagicMock()
        mock_response.candidates = [candidate]
        mock_response.usage_metadata = None

        provider.client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await provider.send(messages=[_make_user_message()])

        assert result.content == []

    @pytest.mark.asyncio
    async def test_send_usage_extraction(self):
        """Usage tokens should be correctly extracted from response."""
        provider = _make_provider()

        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = []
        candidate.finish_reason = "STOP"

        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 100
        mock_usage.candidates_token_count = 50
        mock_usage.cached_content_token_count = 20

        mock_response = MagicMock()
        mock_response.candidates = [candidate]
        mock_response.usage_metadata = mock_usage

        provider.client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await provider.send(messages=[_make_user_message()])

        assert result.usage.input_tokens == 100
        assert result.usage.output_tokens == 50
        assert result.usage.cache_read_tokens == 20

    @pytest.mark.asyncio
    async def test_send_no_usage_metadata(self):
        """No usage_metadata should default to zeros."""
        provider = _make_provider()

        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = []
        candidate.finish_reason = "STOP"

        mock_response = MagicMock()
        mock_response.candidates = [candidate]
        mock_response.usage_metadata = None

        provider.client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await provider.send(messages=[_make_user_message()])

        assert result.usage.input_tokens == 0
        assert result.usage.output_tokens == 0

    @pytest.mark.asyncio
    async def test_send_finish_reason_safety_maps_to_error(self):
        """SAFETY finish reason should map to ERROR."""
        provider = _make_provider()

        candidate = MagicMock()
        candidate.content = None
        candidate.finish_reason = "SAFETY"

        mock_response = MagicMock()
        mock_response.candidates = [candidate]
        mock_response.usage_metadata = None

        provider.client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await provider.send(messages=[_make_user_message()])

        assert result.finish_reason == FinishReason.ERROR

    @pytest.mark.asyncio
    async def test_send_finish_reason_recitation_maps_to_error(self):
        """RECITATION finish reason should map to ERROR."""
        provider = _make_provider()

        candidate = MagicMock()
        candidate.content = None
        candidate.finish_reason = "RECITATION"

        mock_response = MagicMock()
        mock_response.candidates = [candidate]
        mock_response.usage_metadata = None

        provider.client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await provider.send(messages=[_make_user_message()])

        assert result.finish_reason == FinishReason.ERROR

    @pytest.mark.asyncio
    async def test_send_overrides_stop_to_tool_use_when_tool_calls_present(self):
        """STOP finish reason should be overridden to TOOL_USE when tool calls present."""
        provider = _make_provider()

        fc = MagicMock()
        fc.name = "search"
        fc.args = {"q": "test"}

        func_part = MagicMock()
        func_part.text = None
        func_part.function_call = fc
        func_part.thought_signature = None

        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = [func_part]
        candidate.finish_reason = "STOP"

        mock_response = MagicMock()
        mock_response.candidates = [candidate]
        mock_response.usage_metadata = None

        provider.client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await provider.send(messages=[_make_user_message()])

        assert result.finish_reason == FinishReason.TOOL_USE

    @pytest.mark.asyncio
    async def test_send_with_temperature_set(self):
        """Temperature should be passed to config when set."""
        provider = _make_provider(temperature=0.5)
        provider.llm_config.temperature = 0.5

        candidate = MagicMock()
        candidate.content = None
        candidate.finish_reason = "STOP"

        mock_response = MagicMock()
        mock_response.candidates = [candidate]
        mock_response.usage_metadata = None

        provider.client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch("ii_agent.chat.llm.gemini.types") as mock_types:
            mock_types.GenerateContentConfig.return_value = MagicMock()
            mock_types.ThinkingConfig.return_value = MagicMock()
            mock_types.ThinkingLevel.LOW = "LOW"
            await provider.send(messages=[_make_user_message()])

        mock_types.GenerateContentConfig.assert_called_once()
        call_kwargs = mock_types.GenerateContentConfig.call_args[1]
        assert call_kwargs.get("temperature") == 0.5

    @pytest.mark.asyncio
    async def test_send_code_interpreter_uses_code_execution_tool(self):
        """When code interpreter enabled, should use code_execution_tool instead of regular tools."""
        provider = _make_provider()

        candidate = MagicMock()
        candidate.content = None
        candidate.finish_reason = "STOP"

        mock_response = MagicMock()
        mock_response.candidates = [candidate]
        mock_response.usage_metadata = None

        provider.client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_add_code_execution_tool") as mock_add:
            mock_add.return_value = [MagicMock()]
            with patch.object(provider, "_convert_tools") as mock_conv:
                await provider.send(
                    messages=[_make_user_message()],
                    is_code_interpreter_enabled=True,
                )

        mock_add.assert_called_once()
        mock_conv.assert_not_called()


# ---------------------------------------------------------------------------
# GeminiProvider.stream() - deeper coverage
# ---------------------------------------------------------------------------


class TestGeminiProviderStreamDeep:
    """Deep tests for stream() method."""

    @pytest.mark.asyncio
    async def test_stream_emits_complete_at_end(self):
        provider = _make_provider()

        # Create a chunk with no candidates
        empty_chunk = MagicMock()
        empty_chunk.candidates = []
        empty_chunk.usage_metadata = None

        # Create finish chunk
        finish_candidate = MagicMock()
        finish_candidate.content = None
        finish_candidate.finish_reason = "STOP"
        finish_chunk = MagicMock()
        finish_chunk.candidates = [finish_candidate]
        finish_chunk.usage_metadata = None

        async def fake_stream():
            yield empty_chunk
            yield finish_chunk

        provider.client.aio.models.generate_content_stream = AsyncMock(return_value=fake_stream())

        events = []
        async for event in provider.stream(messages=[_make_user_message()]):
            events.append(event)

        # Should have COMPLETE event at end
        complete_events = [e for e in events if e.type == EventType.COMPLETE]
        assert len(complete_events) == 1

    @pytest.mark.asyncio
    async def test_stream_usage_metadata_updated_per_chunk(self):
        provider = _make_provider()

        usage_meta = MagicMock()
        usage_meta.prompt_token_count = 100
        usage_meta.candidates_token_count = 50
        usage_meta.cached_content_token_count = 10
        usage_meta.total_token_count = 160

        # text_part must NOT have function_call or it must be None (falsy)
        text_part = MagicMock(spec=["text", "thought", "thought_signature", "function_call"])
        text_part.text = "Hello"
        text_part.thought = False
        text_part.thought_signature = None
        text_part.function_call = None

        candidate = MagicMock()
        candidate.content = MagicMock()
        candidate.content.parts = [text_part]
        candidate.finish_reason = "STOP"

        chunk = MagicMock()
        chunk.candidates = [candidate]
        chunk.usage_metadata = usage_meta

        async def fake_stream():
            yield chunk

        provider.client.aio.models.generate_content_stream = AsyncMock(return_value=fake_stream())

        events = []
        async for event in provider.stream(messages=[_make_user_message()]):
            events.append(event)

        complete_events = [e for e in events if e.type == EventType.COMPLETE]
        assert len(complete_events) == 1
        assert complete_events[0].response.usage.input_tokens == 100
        assert complete_events[0].response.usage.output_tokens == 50

    @pytest.mark.asyncio
    async def test_stream_with_no_finish_reason_produces_unknown(self):
        provider = _make_provider()

        candidate = MagicMock()
        candidate.content = None
        candidate.finish_reason = None  # No finish reason

        chunk = MagicMock()
        chunk.candidates = [candidate]
        chunk.usage_metadata = None

        async def fake_stream():
            yield chunk

        provider.client.aio.models.generate_content_stream = AsyncMock(return_value=fake_stream())

        events = []
        async for event in provider.stream(messages=[_make_user_message()]):
            events.append(event)

        complete_events = [e for e in events if e.type == EventType.COMPLETE]
        assert complete_events[0].response.finish_reason == FinishReason.UNKNOWN

    @pytest.mark.asyncio
    async def test_stream_code_interpreter_disabled_overrides_input(self):
        """GeminiProvider.stream() hardcodes is_code_interpreter_enabled=False."""
        provider = _make_provider()

        candidate = MagicMock()
        candidate.content = None
        candidate.finish_reason = "STOP"

        chunk = MagicMock()
        chunk.candidates = [candidate]
        chunk.usage_metadata = None

        async def fake_stream():
            yield chunk

        provider.client.aio.models.generate_content_stream = AsyncMock(return_value=fake_stream())

        add_code_execution_called = []

        original_add = provider._add_code_execution_tool

        def mock_add(tools):
            add_code_execution_called.append(True)
            return original_add(tools)

        provider._add_code_execution_tool = mock_add

        events = []
        async for event in provider.stream(
            messages=[_make_user_message()],
            is_code_interpreter_enabled=True,  # Should be overridden to False
        ):
            events.append(event)

        # Code execution should NOT have been called because it's hardcoded to False
        assert len(add_code_execution_called) == 0

    @pytest.mark.asyncio
    async def test_stream_null_usage_fields_default_to_zero(self):
        """Null usage fields should default to 0."""
        provider = _make_provider()

        usage_meta = MagicMock()
        usage_meta.prompt_token_count = None
        usage_meta.candidates_token_count = None
        usage_meta.cached_content_token_count = None
        usage_meta.total_token_count = None

        candidate = MagicMock()
        candidate.content = None
        candidate.finish_reason = "STOP"

        chunk = MagicMock()
        chunk.candidates = [candidate]
        chunk.usage_metadata = usage_meta

        async def fake_stream():
            yield chunk

        provider.client.aio.models.generate_content_stream = AsyncMock(return_value=fake_stream())

        events = []
        async for event in provider.stream(messages=[_make_user_message()]):
            events.append(event)

        complete = [e for e in events if e.type == EventType.COMPLETE][0]
        assert complete.response.usage.input_tokens == 0
        assert complete.response.usage.output_tokens == 0


# ---------------------------------------------------------------------------
# GeminiStreamState - deeper edge cases
# ---------------------------------------------------------------------------


class TestGeminiStreamStateDeep:
    """Additional edge case tests for GeminiStreamState."""

    def test_close_empty_text_block_no_content_added(self):
        """Closing text block with no accumulated text should not add content part."""
        parts = []
        state = GeminiStreamState(content_parts=parts)
        state.current_block = "text"
        state.accumulated_text = ""  # Empty, nothing to flush

        events = state._close_text_block()
        assert len(parts) == 0
        # CONTENT_STOP is only emitted when there's accumulated text
        assert not any(e.type == EventType.CONTENT_STOP for e in events)

    def test_close_empty_reasoning_block_no_content_added(self):
        """Closing reasoning block with no accumulated thinking should not add content part."""
        parts = []
        state = GeminiStreamState(content_parts=parts)
        state.current_block = "reasoning"
        state.accumulated_thinking = ""  # Empty

        events = state._close_reasoning_block()
        assert len(parts) == 0
        assert not any(e.type == EventType.THINKING_STOP for e in events)

    def test_flush_when_no_active_block(self):
        """flush() with no active block should return empty list."""
        parts = []
        state = GeminiStreamState(content_parts=parts)
        state.current_block = None

        events = state.flush()
        assert events == []
        assert len(parts) == 0

    def test_text_to_text_no_transition(self):
        """Consecutive text parts should not create CONTENT_STOP/CONTENT_START."""
        parts = []
        state = GeminiStreamState(content_parts=parts)

        for text in ["Hello", " ", "world"]:
            part = MagicMock()
            part.text = text
            part.thought = False
            part.thought_signature = None
            events = state.handle_text_or_reasoning_part(part)
            types = [e.type for e in events]
            # Should not close and reopen text block for consecutive text
            assert EventType.CONTENT_STOP not in types

    def test_reasoning_to_reasoning_no_transition(self):
        """Consecutive reasoning parts should not create THINKING_STOP/THINKING_START."""
        parts = []
        state = GeminiStreamState(content_parts=parts)

        for thinking in ["Step 1", " Step 2", " Step 3"]:
            part = MagicMock()
            part.text = thinking
            part.thought = True
            part.thought_signature = None
            events = state.handle_text_or_reasoning_part(part)
            types = [e.type for e in events]
            # Second and beyond calls should not emit THINKING_START again
            if state.accumulated_thinking != thinking:  # Not first call
                assert EventType.THINKING_START not in types

    def test_handle_tool_calls_sets_has_tool_calls_flag(self):
        """handle_tool_calls() should set has_tool_calls=True when tool calls present."""
        parts = []
        state = GeminiStreamState(content_parts=parts)

        fc = MagicMock()
        fc.name = "search"
        fc.args = {"q": "test"}
        part = MagicMock()
        part.function_call = fc
        part.thought_signature = None

        assert state.has_tool_calls is False
        state.handle_tool_calls([part])
        assert state.has_tool_calls is True

    def test_multiple_tool_calls_all_added_to_content_parts(self):
        """Multiple tool calls should all be added to content_parts."""
        parts = []
        state = GeminiStreamState(content_parts=parts)

        tool_parts = []
        for i in range(3):
            fc = MagicMock()
            fc.name = f"tool_{i}"
            fc.args = {"index": i}
            p = MagicMock()
            p.function_call = fc
            p.thought_signature = None
            tool_parts.append(p)

        state.handle_tool_calls(tool_parts)
        assert len(parts) == 3
        assert state.has_tool_calls is True

    def test_signature_carried_to_content_part_on_close(self):
        """The last_text_signature should be attached to the content part on close."""
        parts = []
        state = GeminiStreamState(content_parts=parts)
        state.current_block = "text"
        state.accumulated_text = "some text"
        state.last_text_signature = "my_signature_b64"

        state._close_text_block()

        assert len(parts) == 1
        assert parts[0].provider_options["google"]["thoughtSignature"] == "my_signature_b64"

    def test_reasoning_signature_carried_to_content_part(self):
        """The last_thinking_signature should be attached to reasoning content part."""
        parts = []
        state = GeminiStreamState(content_parts=parts)
        state.current_block = "reasoning"
        state.accumulated_thinking = "deep thought"
        state.last_thinking_signature = "reasoning_sig_b64"

        state._close_reasoning_block()

        assert len(parts) == 1
        assert isinstance(parts[0], ReasoningContent)
        assert parts[0].signature == "reasoning_sig_b64"
        assert parts[0].provider_options["google"]["thoughtSignature"] == "reasoning_sig_b64"

    def test_close_text_block_without_signature_no_provider_options(self):
        """Text block without signature should not have provider_options."""
        parts = []
        state = GeminiStreamState(content_parts=parts)
        state.current_block = "text"
        state.accumulated_text = "text without sig"
        state.last_text_signature = ""  # No signature

        state._close_text_block()

        assert len(parts) == 1
        assert parts[0].provider_options is None or not parts[0].provider_options


# ---------------------------------------------------------------------------
# Helper functions - deeper tests
# ---------------------------------------------------------------------------


class TestHelperFunctionsDeep:
    """Deep tests for helper functions."""

    def test_generate_tool_call_id_format(self):
        """Tool call ID should be in format call_{hex_chars}."""
        id_ = generate_tool_call_id()
        assert id_.startswith("call_")
        suffix = id_[len("call_") :]
        assert len(suffix) > 0
        assert all(c in "0123456789abcdef" for c in suffix)

    def test_get_thought_signature_encoding_consistency(self):
        """Encoding and decoding thought signature should be consistent."""
        original_bytes = b"\xde\xad\xbe\xef\xca\xfe"
        part = MagicMock()
        part.thought_signature = original_bytes

        encoded = get_thought_signature_from_content(part)

        # Should be valid base64
        decoded = base64.b64decode(encoded)
        assert decoded == original_bytes

    def test_get_thought_signature_from_provider_options_roundtrip(self):
        """Provider options extraction should be inverse of encoding."""
        original_bytes = b"\x01\x02\x03\x04"
        b64_str = base64.b64encode(original_bytes).decode("utf-8")

        opts = {"google": {"thoughtSignature": b64_str}}
        result = get_thought_signature_from_provider_options(opts)
        assert result == original_bytes

    def test_get_tool_call_from_parts_includes_thought_signature(self):
        """Tool calls should include thought_signature in provider_options."""
        sig_bytes = b"tool_sig"
        fc = MagicMock()
        fc.name = "search"
        fc.args = {"q": "test"}

        part = MagicMock()
        part.function_call = fc
        part.thought_signature = sig_bytes

        calls = get_tool_call_from_parts([part])
        assert len(calls) == 1
        google_opts = calls[0].provider_options.get("google", {})
        signature = google_opts.get("thoughtSignature", "")
        # Signature should be base64 encoded
        assert base64.b64decode(signature) == sig_bytes

    def test_get_tool_call_from_parts_mixed_parts(self):
        """Parts without function_call should be filtered out."""
        fc = MagicMock()
        fc.name = "search"
        fc.args = {}

        tool_part = MagicMock()
        tool_part.function_call = fc
        tool_part.thought_signature = None

        text_part = MagicMock()
        text_part.function_call = None  # Not a tool call

        calls = get_tool_call_from_parts([text_part, tool_part, text_part])
        assert len(calls) == 1
        assert calls[0].name == "search"

    def test_map_google_finish_reason_with_unknown_value(self):
        """Unknown finish reason should map to UNKNOWN."""
        result = map_googe_finish_reason("SOMETHING_WEIRD_AND_NEW", False)
        assert result == FinishReason.UNKNOWN

    def test_map_google_finish_reason_safety_with_tool_calls(self):
        """SAFETY with tool calls should still map to ERROR."""
        result = map_googe_finish_reason("SAFETY", True)
        assert result == FinishReason.ERROR
