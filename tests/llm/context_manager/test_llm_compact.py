import pytest
from unittest.mock import Mock, AsyncMock

from ii_agent.llm.base import (
    TextPrompt,
    TextResult,
    LLMClient,
)
from ii_agent.llm.context_manager.llm_compact import LLMCompact, COMPACT_USER_MESSAGE
from ii_agent.llm.token_counter import TokenCounter


@pytest.mark.asyncio
async def test_llm_compact_no_truncation_needed():
    """Test that compact compression creates a summary for all message lists."""
    mock_llm_client = Mock(spec=LLMClient)
    mock_llm_client.agenerate = AsyncMock(return_value=([TextResult(text="Summary")], None))
    token_counter = TokenCounter()

    context_manager = LLMCompact(
        client=mock_llm_client,
        token_counter=token_counter,
        token_budget=1000,
    )

    # Single message list will be compressed
    message_lists = [[TextPrompt(text="Hello")]]
    result = await context_manager.apply_truncation(message_lists)

    # Should compress to a single message with summary
    assert len(result) == 1
    # Should have called LLM to generate summary
    mock_llm_client.agenerate.assert_called_once()


@pytest.mark.asyncio
async def test_llm_compact_basic_truncation():
    """Test basic compact truncation with multiple message lists."""
    mock_llm_client = Mock(spec=LLMClient)

    # Mock the agenerate method to return a summary response
    async def mock_agenerate(
        messages, max_tokens=None, thinking_tokens=None, system_prompt=None
    ):
        return [
            TextResult(
                text="This is a detailed summary of the conversation focusing on the key points and next steps."
            )
        ], None

    mock_llm_client.agenerate = AsyncMock(side_effect=mock_agenerate)
    token_counter = TokenCounter()

    context_manager = LLMCompact(
        client=mock_llm_client,
        token_counter=token_counter,
        token_budget=1000,
    )

    # Create multiple message lists to trigger truncation
    message_lists = [
        [TextPrompt(text="System: You are a helpful assistant")],  # System prompt
        [TextPrompt(text="User: Hello")],
        [TextResult(text="Assistant: Hi there!")],
        [TextPrompt(text="User: Can you help me?")],
        [TextResult(text="Assistant: Of course!")],
    ]

    result = await context_manager.apply_truncation(message_lists)

    # Should return a single summarized message
    assert len(result) == 1
    assert isinstance(result[0][0], TextPrompt)  # Summary message
    assert "This is a detailed summary" in result[0][0].text


@pytest.mark.asyncio
async def test_llm_compact_llm_call_parameters():
    """Test that LLM is called with correct parameters during compact truncation."""
    llm_calls = []

    async def spy_agenerate(
        messages, max_tokens=None, thinking_tokens=None, system_prompt=None
    ):
        call_info = {
            "messages": messages,
            "max_tokens": max_tokens,
            "thinking_tokens": thinking_tokens,
            "system_prompt": system_prompt,
        }
        llm_calls.append(call_info)
        return [TextResult(text="Summary of the conversation.")], None

    mock_llm_client = Mock(spec=LLMClient)
    mock_llm_client.agenerate = AsyncMock(side_effect=spy_agenerate)
    token_counter = TokenCounter()

    context_manager = LLMCompact(
        client=mock_llm_client,
        token_counter=token_counter,
        token_budget=1000,
    )

    message_lists = [
        [TextPrompt(text="System: You are a helpful assistant")],
        [TextPrompt(text="User: Hello")],
        [TextResult(text="Assistant: Hi!")],
    ]

    await context_manager.apply_truncation(message_lists)

    # Verify LLM was called once
    assert len(llm_calls) == 1
    call = llm_calls[0]

    # Check parameters
    assert call["max_tokens"] == 8192  # SUMMARY_MAX_TOKENS
    # thinking_tokens is not passed, so it won't be in the call

    # Check messages structure
    messages = call["messages"]
    assert len(messages) == 4  # original 3 + COMPACT_PROMPT
    assert (
        "Your task is to create a detailed summary" in messages[-1][0].text
    )  # COMPACT_PROMPT


@pytest.mark.asyncio
async def test_llm_compact_error_handling():
    """Test error handling when LLM generation fails."""
    mock_llm_client = Mock(spec=LLMClient)
    mock_llm_client.agenerate = AsyncMock(side_effect=Exception("LLM service unavailable"))

    token_counter = TokenCounter()

    context_manager = LLMCompact(
        client=mock_llm_client,
        token_counter=token_counter,
        token_budget=1000,
    )

    message_lists = [
        [TextPrompt(text="System: You are a helpful assistant")],
        [TextPrompt(text="User: Hello")],
        [TextResult(text="Assistant: Hi!")],
    ]

    # Exception should propagate
    with pytest.raises(Exception, match="LLM service unavailable"):
        await context_manager.apply_truncation(message_lists)


@pytest.mark.asyncio
async def test_llm_compact_empty_response_handling():
    """Test handling when LLM returns empty response."""
    mock_llm_client = Mock(spec=LLMClient)
    mock_llm_client.agenerate = AsyncMock(return_value=([], None))  # Empty response

    token_counter = TokenCounter()

    context_manager = LLMCompact(
        client=mock_llm_client,
        token_counter=token_counter,
        token_budget=1000,
    )

    message_lists = [
        [TextPrompt(text="System: You are a helpful assistant")],
        [TextPrompt(text="User: Hello")],
    ]

    result = await context_manager.apply_truncation(message_lists)

    # Should create a summary even with empty LLM response
    assert len(result) == 1
    assert isinstance(result[0][0], TextPrompt)  # Summary message
