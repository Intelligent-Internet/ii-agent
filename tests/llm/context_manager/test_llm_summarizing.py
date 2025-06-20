import logging
from unittest.mock import Mock

from ii_agent.llm.base import (
    TextPrompt,
    TextResult,
    LLMClient,
    ToolCall,
    ToolFormattedResult,
)
from ii_agent.llm.context_manager.llm_summarizing import LLMSummarizingContextManager
from ii_agent.llm.token_counter import TokenCounter


def test_llm_summarizing_context_manager():
    mock_logger = Mock(spec=logging.Logger)
    mock_llm_client = Mock(spec=LLMClient)

    # Mock the generate method to return a summary response
    def mock_generate(messages, max_tokens=None, thinking_tokens=None):
        return [TextResult(text="Generated summary of conversation events.")], None

    mock_llm_client.generate.side_effect = mock_generate
    token_counter = TokenCounter()

    context_manager = LLMSummarizingContextManager(
        client=mock_llm_client,
        token_counter=token_counter,
        logger=mock_logger,
        token_budget=1000,
        max_size=10,
    )

    for num_messages in range(9, 13):
        message_lists = []
        for j in range(num_messages):
            if j % 2 == 0:
                message_lists.append([TextPrompt(text=f"Turn {j // 2}")])
            else:
                message_lists.append([TextResult(text=f"Turn {j // 2}")])
        result = context_manager.apply_truncation_if_needed(message_lists)

        # Add assertions based on expected behavior
        if num_messages <= 10:  # No truncation needed (9 and 10 messages)
            assert len(result) == num_messages
            assert result == message_lists
        else:  # Truncation needed (11 and 12 messages)
            assert len(result) == 5  # target_size = max_size // 2 = 5
            # First 1 message should be kept
            assert result[0] == message_lists[0]
            # Second message should be the summary
            assert isinstance(result[1][0], TextResult)
            assert "Conversation Summary:" in result[1][0].text
            # Last message should be from the tail
            assert result[-1] == message_lists[-1]


def test_llm_calls_during_summarization():
    """Test that captures and inspects the actual LLM calls made during summarization."""

    # Create a spy that captures all LLM calls
    llm_calls = []

    def spy_generate(messages, max_tokens=None, **kwargs):
        # Capture the call details
        call_info = {
            "messages": messages,
            "max_tokens": max_tokens,
            "kwargs": kwargs,
            "prompt_text": messages[0][0].text
            if messages and messages[0] and hasattr(messages[0][0], "text")
            else None,
        }
        llm_calls.append(call_info)

        # Return a mock summary response
        return [
            TextResult(
                text="this_is_summary"
            )
        ], None

    mock_logger = Mock(spec=logging.Logger)
    mock_llm_client = Mock(spec=LLMClient)
    mock_llm_client.generate.side_effect = spy_generate
    token_counter = TokenCounter()

    context_manager = LLMSummarizingContextManager(
        client=mock_llm_client,
        token_counter=token_counter,
        logger=mock_logger,
        token_budget=1000,
        max_size=8,  # Smaller size to trigger summarization
    )

    # Create a conversation with tool calls that will trigger summarization
    conversation = [
        [TextPrompt(text="Can you read the contents of config.py?")],
        [
            ToolCall(
                tool_call_id="call_123",
                tool_name="read_file",
                tool_input={"file_path": "config.py"},
            )
        ],
        [
            ToolFormattedResult(
                tool_call_id="call_123",
                tool_name="read_file",
                tool_output="DEBUG = True\nDATABASE_URL = 'sqlite:///app.db'",
            )
        ],
        [
            TextResult(
                text="I can see the config.py file contains debug settings and database configuration."
            )
        ],
        [TextPrompt(text="Now check the main.py file")],
        [
            ToolCall(
                tool_call_id="call_456",
                tool_name="read_file",
                tool_input={"file_path": "main.py"},
            )
        ],
        [
            ToolFormattedResult(
                tool_call_id="call_456",
                tool_name="read_file",
                tool_output="file_content",
            )
        ],
        [TextResult(text="The main.py file contains a simple Flask application.")],
        [TextPrompt(text="Add error handling to the Flask app")],
        [
            ToolCall(
                tool_call_id="call_789",
                tool_name="edit_file",
                tool_input={
                    "file_path": "main.py",
                    "new_content": "file_content",
                },
            )
        ],
        [
            ToolFormattedResult(
                tool_call_id="call_789",
                tool_name="edit_file",
                tool_output="File successfully modified",
            )
        ],
        [TextResult(text="I've added error handling to the Flask application.")],
    ]

    result = context_manager.apply_truncation_if_needed(conversation)

    expected_result = [
        [TextPrompt(text='Can you read the contents of config.py?')], 
        [TextResult(text='Conversation Summary: this_is_summary')], 
        [ToolFormattedResult(tool_call_id='call_789', tool_name='edit_file', tool_output='File successfully modified')], 
        [TextResult(text="I've added error handling to the Flask application.")]
    ]

    assert result == expected_result

