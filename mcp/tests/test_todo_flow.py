"""Combined integration tests for TodoRead and TodoWrite tools working together."""

import pytest
from src.tools.productivity.todo_read_tool import TodoReadTool
from src.tools.productivity.todo_write_tool import TodoWriteTool
from src.tools.productivity.shared_state import get_todo_manager


@pytest.fixture
def todo_tools():
    """Set up test fixtures and clear state."""
    read_tool = TodoReadTool()
    write_tool = TodoWriteTool()
    # Clear any existing todos before each test
    manager = get_todo_manager()
    manager.clear_todos()
    return read_tool, write_tool


def test_write_then_read_workflow(todo_tools):
    """Test the complete workflow: write todos then read them back."""
    read_tool, write_tool = todo_tools
    
    # Step 1: Verify starting with empty list
    read_result = read_tool.run_impl()
    assert read_result == "No todos found"

    # Step 2: Write some todos
    todos = [
        {"id": "1", "content": "Learn Python", "status": "completed", "priority": "high"},
        {"id": "2", "content": "Write tests", "status": "in_progress", "priority": "medium"},
        {"id": "3", "content": "Deploy code", "status": "pending", "priority": "low"}
    ]
    write_result = write_tool.run_impl(todos=todos)
    assert "Todos have been modified successfully" in write_result

    # Step 3: Read them back and verify
    read_result = read_tool.run_impl()
    assert "Remember to continue to use update and read from the todo list" in read_result
    assert "Learn Python" in read_result
    assert "Write tests" in read_result
    assert "Deploy code" in read_result
    assert read_result.count("in_progress") == 1
    assert read_result.count("pending") == 1
    assert read_result.count("completed") == 1


def test_progressive_todo_updates(todo_tools):
    """Test progressively updating todos through multiple write operations."""
    read_tool, write_tool = todo_tools
    
    # Step 1: Start with one todo
    initial_todos = [
        {"id": "1", "content": "Initial task", "status": "pending", "priority": "medium"}
    ]
    write_tool.run_impl(todos=initial_todos)
    
    read_result = read_tool.run_impl()
    assert "Initial task" in read_result
    assert "pending" in read_result

    # Step 2: Update status to in_progress
    updated_todos = [
        {"id": "1", "content": "Initial task", "status": "in_progress", "priority": "medium"}
    ]
    write_tool.run_impl(todos=updated_todos)
    
    read_result = read_tool.run_impl()
    assert "Initial task" in read_result
    assert "in_progress" in read_result

    # Step 3: Mark complete and add new task
    final_todos = [
        {"id": "1", "content": "Initial task", "status": "completed", "priority": "medium"},
        {"id": "2", "content": "Follow-up task", "status": "pending", "priority": "high"}
    ]
    write_tool.run_impl(todos=final_todos)
    
    read_result = read_tool.run_impl()
    assert "Initial task" in read_result
    assert "Follow-up task" in read_result
    assert "completed" in read_result
    assert "pending" in read_result


def test_validation_error_then_recovery(todo_tools):
    """Test handling validation errors and then successful recovery."""
    read_tool, write_tool = todo_tools
    
    # Step 1: Try to write invalid todos
    invalid_todos = [
        {"id": "1", "content": "Task 1", "status": "in_progress", "priority": "high"},
        {"id": "2", "content": "Task 2", "status": "in_progress", "priority": "medium"}  # Invalid: multiple in_progress
    ]
    write_result = write_tool.run_impl(todos=invalid_todos)
    assert "Error updating todo list:" in write_result
    assert "Only one task can be in_progress at a time" in write_result

    # Step 2: Verify no todos were saved due to validation error
    read_result = read_tool.run_impl()
    assert read_result == "No todos found"

    # Step 3: Write valid todos
    valid_todos = [
        {"id": "1", "content": "Task 1", "status": "in_progress", "priority": "high"},
        {"id": "2", "content": "Task 2", "status": "pending", "priority": "medium"}  # Fixed: only one in_progress
    ]
    write_result = write_tool.run_impl(todos=valid_todos)
    assert "Todos have been modified successfully" in write_result

    # Step 4: Verify todos were saved successfully
    read_result = read_tool.run_impl()
    assert "Task 1" in read_result
    assert "Task 2" in read_result
    assert "in_progress" in read_result
    assert "pending" in read_result


def test_clear_and_repopulate(todo_tools):
    """Test clearing todos and repopulating them."""
    read_tool, write_tool = todo_tools
    
    # Step 1: Add initial todos
    initial_todos = [
        {"id": "1", "content": "Temporary task 1", "status": "pending", "priority": "low"},
        {"id": "2", "content": "Temporary task 2", "status": "completed", "priority": "medium"}
    ]
    write_tool.run_impl(todos=initial_todos)
    
    read_result = read_tool.run_impl()
    assert "Temporary task 1" in read_result
    assert "Temporary task 2" in read_result

    # Step 2: Clear all todos
    write_tool.run_impl(todos=[])
    
    read_result = read_tool.run_impl()
    assert read_result == "No todos found"

    # Step 3: Add new todos
    new_todos = [
        {"id": "1", "content": "New task 1", "status": "in_progress", "priority": "high"},
        {"id": "2", "content": "New task 2", "status": "pending", "priority": "low"}
    ]
    write_tool.run_impl(todos=new_todos)
    
    read_result = read_tool.run_impl()
    assert "New task 1" in read_result
    assert "New task 2" in read_result
    assert "Temporary task" not in read_result  # Old tasks should be gone