from unittest.mock import Mock

from ii_agent.llm.base import (
    TextPrompt,
    TextResult,
    LLMClient,
)
from ii_agent.llm.context_manager.llm_compact import LLMCompact
from ii_agent.llm.token_counter import TokenCounter


def test_llm_compact_no_truncation_needed():
    """Test that no truncation occurs when only one message list exists."""
    mock_llm_client = Mock(spec=LLMClient)
    token_counter = TokenCounter()

    context_manager = LLMCompact(
        client=mock_llm_client,
        token_counter=token_counter,
        token_budget=1000,
    )

    # Single message list should not trigger truncation
    message_lists = [[TextPrompt(text="Hello")]]
    result = context_manager.apply_truncation(message_lists)

    assert result == message_lists
    # Should not call LLM for single message
    mock_llm_client.generate.assert_not_called()


def test_llm_compact_basic_truncation():
    """Test basic compact truncation with multiple message lists."""
    mock_llm_client = Mock(spec=LLMClient)

    # Mock the generate method to return a summary response
    def mock_generate(messages, max_tokens=None, thinking_tokens=None):
        return [
            TextResult(
                text="This is a detailed summary of the conversation focusing on the key points and next steps."
            )
        ], None

    mock_llm_client.generate.side_effect = mock_generate
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

    result = context_manager.apply_truncation(message_lists)

    # Should return system prompt + summary
    assert len(result) == 2
    assert result[0] == message_lists[0]  # System prompt preserved
    assert isinstance(result[1][0], TextPrompt)  # Summary as user message
    assert "This is a detailed summary" in result[1][0].text


def test_llm_compact_llm_call_parameters():
    """Test that LLM is called with correct parameters during compact truncation."""
    llm_calls = []

    def spy_generate(messages, max_tokens=None, thinking_tokens=None):
        call_info = {
            "messages": messages,
            "max_tokens": max_tokens,
            "thinking_tokens": thinking_tokens,
        }
        llm_calls.append(call_info)
        return [TextResult(text="Summary of the conversation.")], None

    mock_llm_client = Mock(spec=LLMClient)
    mock_llm_client.generate.side_effect = spy_generate
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

    context_manager.apply_truncation(message_lists)

    # Verify LLM was called once
    assert len(llm_calls) == 1
    call = llm_calls[0]

    # Check parameters
    assert call["max_tokens"] == 4000  # SUMMARY_MAX_TOKENS
    assert call["thinking_tokens"] == 0

    # Check messages structure
    messages = call["messages"]
    assert len(messages) == 5  # system + original 3 + COMPACT_PROMPT
    assert (
        messages[0][0].text
        == "You are a helpful AI assistant tasked with summarizing conversations."
    )
    assert (
        "Your task is to create a detailed summary" in messages[-1][0].text
    )  # COMPACT_PROMPT


def test_llm_compact_error_handling():
    """Test error handling when LLM generation fails."""
    mock_llm_client = Mock(spec=LLMClient)
    mock_llm_client.generate.side_effect = Exception("LLM service unavailable")

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

    result = context_manager.apply_truncation(message_lists)

    # Should still return system prompt + error message
    assert len(result) == 2
    assert result[0] == message_lists[0]
    assert isinstance(result[1][0], TextPrompt)
    assert "Failed to generate summary due to error" in result[1][0].text
    assert "LLM service unavailable" in result[1][0].text


def test_llm_compact_empty_response_handling():
    """Test handling when LLM returns empty response."""
    mock_llm_client = Mock(spec=LLMClient)
    mock_llm_client.generate.return_value = ([], None)  # Empty response

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

    result = context_manager.apply_truncation(message_lists)

    # Should use fallback message
    assert len(result) == 2
    assert result[0] == message_lists[0]
    assert isinstance(result[1][0], TextPrompt)
    assert "Conversation summary could not be generated." in result[1][0].text
