"""Integration tests for TodoReadTool using real shared state."""

import pytest
from src.tools.productivity.todo_read_tool import TodoReadTool, EMPTY_MESSAGE, SUCCESS_MESSAGE
from src.tools.productivity.shared_state import get_todo_manager


@pytest.fixture
def todo_read_tool():
    """Set up test fixtures and clear state."""
    tool = TodoReadTool()
    # Clear any existing todos before each test
    manager = get_todo_manager()
    manager.clear_todos()
    return tool


def test_read_empty_todo(todo_read_tool):
    """Test reading when no todos exist (real scenario)."""
    # Execute
    result = todo_read_tool.run_impl()

    # Assert
    assert result == EMPTY_MESSAGE


def test_read_existing_todo(todo_read_tool):
    """Test reading when todos exist (real scenario)."""
    # Setup: Add some real todos to the manager
    manager = get_todo_manager()
    todos = [
        {"id": "1", "content": "task 1", "status": "pending", "priority": "high"},
        {"id": "2", "content": "task 2", "status": "pending", "priority": "medium"}
    ]
    manager.set_todos(todos)

    # Execute
    result = todo_read_tool.run_impl()

    # Assert
    assert result == SUCCESS_MESSAGE.format(todos=todos)