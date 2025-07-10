"""Integration tests for TodoWriteTool using real shared state"""

import pytest
from src.tools.productivity.todo_write_tool import TodoWriteTool
from src.tools.productivity.shared_state import get_todo_manager


@pytest.fixture
def todo_write_tool():
    """Set up test fixtures and clear state"""
    tool = TodoWriteTool()
    # Clear any existing todos before each test
    manager = get_todo_manager()
    manager.clear_todos()
    return tool


def test_write_single_todo(todo_write_tool):
    """Test writing a single todo item"""
    # Test data
    todos = [
        {"id": "1", "content": "Single task", "status": "in_progress", "priority": "high"}
    ]

    # Execute
    result = todo_write_tool.run_impl(todos=todos)

    # Assert
    assert result == "Todos have been modified successfully. Ensure that you continue to use the todo list to track your progress. Please proceed with the current tasks if applicable"
    
    # Verify todo was actually stored
    manager = get_todo_manager()
    stored_todos = manager.get_todos()
    assert len(stored_todos) == 1
    assert stored_todos[0]["content"] == "Single task"
    assert stored_todos[0]["status"] == "in_progress"
    assert stored_todos[0]["priority"] == "high"


def test_write_multiple_todos(todo_write_tool):
    """Test writing valid todos successfully"""
    # Test data
    todos = [
        {"id": "1", "content": "task 1", "status": "pending", "priority": "high"},
        {"id": "2", "content": "task 2", "status": "pending", "priority": "medium"}
    ]

    # Execute
    result = todo_write_tool.run_impl(todos=todos)

    # Assert
    assert result == "Todos have been modified successfully. Ensure that you continue to use the todo list to track your progress. Please proceed with the current tasks if applicable"
    
    # Verify todos were actually stored
    manager = get_todo_manager()
    stored_todos = manager.get_todos()
    assert len(stored_todos) == 2
    assert stored_todos[0]["content"] == "task 1"
    assert stored_todos[1]["content"] == "task 2"


def test_write_todos_invalid_status(todo_write_tool):
    """Test handling validation errors for invalid status"""
    # Test data with invalid status
    todos = [
        {"id": "1", "content": "Invalid task", "status": "invalid_status", "priority": "high"}
    ]

    # Execute
    result = todo_write_tool.run_impl(todos=todos)

    # Assert
    assert "Error updating todo list:" in result
    assert "Invalid status 'invalid_status'" in result
    
    # Verify no todos were stored due to validation error
    manager = get_todo_manager()
    stored_todos = manager.get_todos()
    assert len(stored_todos) == 0


def test_write_todos_invalid_priority(todo_write_tool):
    """Test handling validation errors for invalid priority"""
    # Test data with invalid priority
    todos = [
        {"id": "1", "content": "Invalid task", "status": "pending", "priority": "invalid_priority"}
    ]

    # Execute
    result = todo_write_tool.run_impl(todos=todos)

    # Assert
    assert "Error updating todo list:" in result
    assert "Invalid priority 'invalid_priority'" in result
    
    # Verify no todos were stored due to validation error
    manager = get_todo_manager()
    stored_todos = manager.get_todos()
    assert len(stored_todos) == 0


def test_write_todos_missing_field(todo_write_tool):
    """Test handling validation errors for missing required fields"""
    # Test data missing 'content' field
    todos = [
        {"id": "1", "status": "pending", "priority": "high"}  # Missing 'content'
    ]

    # Execute
    result = todo_write_tool.run_impl(todos=todos)

    # Assert
    assert "Error updating todo list:" in result
    assert "must have a 'content' field" in result
    
    # Verify no todos were stored due to validation error
    manager = get_todo_manager()
    stored_todos = manager.get_todos()
    assert len(stored_todos) == 0


def test_write_todos_empty_content(todo_write_tool):
    """Test handling validation errors for empty content"""
    # Test data with empty content
    todos = [
        {"id": "1", "content": "   ", "status": "pending", "priority": "high"}  # Empty/whitespace content
    ]

    # Execute
    result = todo_write_tool.run_impl(todos=todos)

    # Assert
    assert "Error updating todo list:" in result
    assert "Todo content cannot be empty" in result
    
    # Verify no todos were stored due to validation error
    manager = get_todo_manager()
    stored_todos = manager.get_todos()
    assert len(stored_todos) == 0


def test_write_todos_multiple_in_progress(todo_write_tool):
    """Test the 'only one in_progress task' validation rule"""
    # Test data with multiple in_progress tasks
    todos = [
        {"id": "1", "content": "First in progress", "status": "in_progress", "priority": "high"},
        {"id": "2", "content": "Second in progress", "status": "in_progress", "priority": "medium"}
    ]

    # Execute
    result = todo_write_tool.run_impl(todos=todos)

    # Assert
    assert "Error updating todo list:" in result
    assert "Only one task can be in_progress at a time" in result
    
    # Verify no todos were stored due to validation error
    manager = get_todo_manager()
    stored_todos = manager.get_todos()
    assert len(stored_todos) == 0


def test_write_todos_with_all_valid_combinations(todo_write_tool):
    """Test writing todos with all valid statuses and priorities"""
    # Test data with all valid combinations
    todos = [
        {"id": "1", "content": "Pending high", "status": "pending", "priority": "high"},
        {"id": "2", "content": "In progress medium", "status": "in_progress", "priority": "medium"},
        {"id": "3", "content": "Completed low", "status": "completed", "priority": "low"}
    ]

    # Execute
    result = todo_write_tool.run_impl(todos=todos)

    # Assert
    assert result == "Todos have been modified successfully. Ensure that you continue to use the todo list to track your progress. Please proceed with the current tasks if applicable"
    
    # Verify all todos were stored correctly
    manager = get_todo_manager()
    stored_todos = manager.get_todos()
    assert len(stored_todos) == 3
    
    # Check each todo was stored correctly
    contents = [todo["content"] for todo in stored_todos]
    assert "Pending high" in contents
    assert "In progress medium" in contents
    assert "Completed low" in contents


def test_write_update_existing_todos(todo_write_tool):
    """Test updating existing todos"""
    # Setup: Add initial todos
    initial_todos = [
        {"id": "1", "content": "Initial task", "status": "pending", "priority": "low"}
    ]
    todo_write_tool.run_impl(todos=initial_todos)
    
    # Verify initial state
    manager = get_todo_manager()
    assert len(manager.get_todos()) == 1

    # Execute: Update with new todos
    updated_todos = [
        {"id": "1", "content": "Updated task", "status": "completed", "priority": "high"},
        {"id": "2", "content": "New task", "status": "pending", "priority": "medium"}
    ]
    result = todo_write_tool.run_impl(todos=updated_todos)

    # Assert
    expected_message = "Todos have been modified successfully. Ensure that you continue to use the todo list to track your progress. Please proceed with the current tasks if applicable"
    assert result == expected_message
    
    # Verify todos were updated/replaced
    stored_todos = manager.get_todos()
    assert len(stored_todos) == 2
    assert stored_todos[0]["content"] == "Updated task"
    assert stored_todos[0]["status"] == "completed"
    assert stored_todos[0]["priority"] == "high"
    assert stored_todos[1]["content"] == "New task"
    assert stored_todos[1]["status"] == "pending"
    assert stored_todos[1]["priority"] == "medium"