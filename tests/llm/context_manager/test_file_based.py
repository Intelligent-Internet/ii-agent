import os
import shutil
from unittest.mock import Mock

import pytest

from ii_agent.llm.base import ToolCall, ToolFormattedResult
from ii_agent.llm.context_manager.file_based import FileBasedContextManager
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.tools.str_replace_tool_relative import StrReplaceEditorTool
from ii_agent.utils.workspace_manager import WorkspaceManager


@pytest.fixture
def mock_file_writer():
    return Mock(spec=StrReplaceEditorTool)


@pytest.fixture
def mock_logger():
    return Mock()


@pytest.fixture
def context_manager(mock_logger, tmp_path):
    # Use a temporary directory for each test
    manager = FileBasedContextManager(
        workspace_manager=WorkspaceManager(root=tmp_path),
        token_counter=TokenCounter(),
        logger=mock_logger,
        token_budget=1000,
    )
    manager.truncate_keep_n_turns = 3  # Set the required attribute
    yield manager
    # Cleanup after each test
    if os.path.exists(manager.agent_memory_dir):
        shutil.rmtree(manager.agent_memory_dir)


def test_init(context_manager):
    """Test initialization of FileBasedContextManager"""
    assert context_manager._token_budget == 1000
    assert context_manager.hash_map == {}
    assert os.path.exists(context_manager.agent_memory_dir)
    assert context_manager.truncate_keep_n_turns == 3


def test_sanitize_for_filename(context_manager):
    """Test filename sanitization"""
    # Test basic sanitization
    assert context_manager._sanitize_for_filename("test file.txt") == "test_file_txt"

    # Test empty string
    assert context_manager._sanitize_for_filename("") == ""

    # Test long string
    long_str = "a" * 50
    assert len(context_manager._sanitize_for_filename(long_str)) == 30

    # Test special characters
    assert context_manager._sanitize_for_filename("test@#$%^&*()") == "test"


def test_get_content_hash(context_manager):
    """Test content hashing"""
    content = "test content"
    hash_value = context_manager._get_content_hash(content)
    assert len(hash_value) == 10  # HASH_LENGTH
    assert hash_value.isalnum()


def test_apply_truncation_if_needed(context_manager):
    """Test truncation functionality"""

    # Create test messages
    tool_output = ToolFormattedResult(
        tool_name="str_replace_editor",
        tool_output="This is a long tool output that should be truncated" * 1000,
        tool_call_id="test_call_1",
    )
    tool_call = ToolCall(
        tool_name="str_replace_editor",
        tool_input={
            "file_text": "This is a long file text" * 1000,
            "old_str": "old string",
            "new_str": "new string",
        },
        tool_call_id="test_call_2",
    )
    tavily_visit_webpage = ToolFormattedResult(
        tool_name="tavily_visit_webpage",
        tool_output="This is a long tool output that should be truncated" * 1000,
        tool_call_id="test_call_3",
    )
    tavily_visit_webpage_call = ToolCall(
        tool_name="tavily_visit_webpage",
        tool_input={"url": "https://www.google.com"},
        tool_call_id="test_call_3",
    )

    message_lists = [
        [tool_call],
        [tool_output],
        [tavily_visit_webpage_call],
        [tavily_visit_webpage],
    ] * 5  # Because by default 3 last messages are kept

    # Apply truncation
    truncated_lists = context_manager.apply_truncation_if_needed(message_lists)

    # Verify truncation
    assert len(truncated_lists) == 20
    assert (
        truncated_lists[0][0].tool_input["file_text"]
        == FileBasedContextManager.TRUNCATED_TOOL_INPUT_MSG
    )
    assert (
        truncated_lists[1][0].tool_output
        == FileBasedContextManager.TRUNCATED_TOOL_OUTPUT_MSG
    )
    assert "Truncated...content saved to" in truncated_lists[3][0].tool_output

    # Verify files were created
    truncated_files = os.listdir(context_manager.agent_memory_dir)
    assert len(truncated_files) == 1


def test_apply_truncation_not_needed(context_manager):
    """Test that truncation is not applied when under budget"""

    # Create test messages
    tool_output = ToolFormattedResult(
        tool_name="test_tool",
        tool_output="This is a short tool output",
        tool_call_id="test_call_3",
    )
    message_lists = [[tool_output]]

    # Apply truncation
    truncated_lists = context_manager.apply_truncation_if_needed(message_lists)

    # Verify no truncation occurred
    assert truncated_lists == message_lists
    assert len(os.listdir(context_manager.agent_memory_dir)) == 0
