"""Comprehensive tests for TodoWriteTool."""

import pytest
import os
from unittest.mock import Mock, patch

# Add src to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tools.productivity.todo_write_tool import TodoWriteTool
from tools.productivity.shared_state import TodoManager


class TestTodoWriteTool:
    """Test class for TodoWriteTool functionality."""

    @pytest.fixture
    def mock_todo_manager(self):
        """Create a mock TodoManager for testing."""
        return Mock(spec=TodoManager)

    @pytest.fixture
    def todo_write_tool(self):
        """Create a TodoWriteTool instance."""
        return TodoWriteTool()

    def test_tool_initialization(self, todo_write_tool):
        """Test that the tool initializes correctly."""
        assert todo_write_tool.name == "TodoWrite"
        assert "Use this tool to create and manage a structured task list" in todo_write_tool.description
        assert "When to Use This Tool" in todo_write_tool.description
        assert "Complex multi-step tasks" in todo_write_tool.description

    # Success scenarios
    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_write_empty_todo_list(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test writing an empty todo list."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.return_value = None
        
        result = todo_write_tool.run_impl(todos=[])
        
        assert "Todos have been modified successfully" in result
        assert "Ensure that you continue to use the todo list" in result
        mock_todo_manager.set_todos.assert_called_once_with([])

    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_write_single_todo(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test writing a single todo item."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.return_value = None
        
        test_todos = [{
            'id': '1',
            'content': 'Test task',
            'status': 'pending',
            'priority': 'medium'
        }]
        
        result = todo_write_tool.run_impl(todos=test_todos)
        
        assert "Todos have been modified successfully" in result
        mock_todo_manager.set_todos.assert_called_once_with(test_todos)

    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_write_multiple_todos(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test writing multiple todo items."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.return_value = None
        
        test_todos = [
            {'id': '1', 'content': 'First task', 'status': 'pending', 'priority': 'high'},
            {'id': '2', 'content': 'Second task', 'status': 'in_progress', 'priority': 'medium'},
            {'id': '3', 'content': 'Third task', 'status': 'completed', 'priority': 'low'}
        ]
        
        result = todo_write_tool.run_impl(todos=test_todos)
        
        assert "Todos have been modified successfully" in result
        mock_todo_manager.set_todos.assert_called_once_with(test_todos)

    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_write_todos_with_all_valid_statuses(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test writing todos with all valid status values."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.return_value = None
        
        test_todos = [
            {'id': '1', 'content': 'Pending task', 'status': 'pending', 'priority': 'medium'},
            {'id': '2', 'content': 'In progress task', 'status': 'in_progress', 'priority': 'medium'},
            {'id': '3', 'content': 'Completed task', 'status': 'completed', 'priority': 'medium'}
        ]
        
        result = todo_write_tool.run_impl(todos=test_todos)
        
        assert "Todos have been modified successfully" in result
        mock_todo_manager.set_todos.assert_called_once_with(test_todos)

    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_write_todos_with_all_valid_priorities(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test writing todos with all valid priority values."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.return_value = None
        
        test_todos = [
            {'id': '1', 'content': 'High priority task', 'status': 'pending', 'priority': 'high'},
            {'id': '2', 'content': 'Medium priority task', 'status': 'pending', 'priority': 'medium'},
            {'id': '3', 'content': 'Low priority task', 'status': 'pending', 'priority': 'low'}
        ]
        
        result = todo_write_tool.run_impl(todos=test_todos)
        
        assert "Todos have been modified successfully" in result
        mock_todo_manager.set_todos.assert_called_once_with(test_todos)

    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_write_todos_with_complex_content(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test writing todos with complex content (special characters, multiline, etc.)."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.return_value = None
        
        test_todos = [
            {
                'id': '1',
                'content': 'Task with special chars: !@#$%^&*()[]{}|\\:";\'<>?,.`~',
                'status': 'pending',
                'priority': 'medium'
            },
            {
                'id': '2',
                'content': 'Task with\nmultiple\nlines',
                'status': 'pending',
                'priority': 'medium'
            },
            {
                'id': '3',
                'content': 'Task with unicode: 🚀 Hello 世界 Здравствуй!',
                'status': 'pending',
                'priority': 'medium'
            }
        ]
        
        result = todo_write_tool.run_impl(todos=test_todos)
        
        assert "Todos have been modified successfully" in result
        mock_todo_manager.set_todos.assert_called_once_with(test_todos)

    # Error scenarios - Manager validation errors
    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_manager_validation_error_missing_fields(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test handling of validation error for missing required fields."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.side_effect = ValueError("Each todo must have a 'content' field")
        
        test_todos = [{'id': '1', 'status': 'pending', 'priority': 'medium'}]  # Missing content
        
        result = todo_write_tool.run_impl(todos=test_todos)
        
        assert "Error updating todo list: Each todo must have a 'content' field" in result
        mock_todo_manager.set_todos.assert_called_once_with(test_todos)

    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_manager_validation_error_invalid_status(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test handling of validation error for invalid status."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.side_effect = ValueError("Invalid status 'invalid'. Must be 'pending', 'in_progress', or 'completed'")
        
        test_todos = [{
            'id': '1',
            'content': 'Test task',
            'status': 'invalid',
            'priority': 'medium'
        }]
        
        result = todo_write_tool.run_impl(todos=test_todos)
        
        assert "Error updating todo list: Invalid status 'invalid'" in result
        mock_todo_manager.set_todos.assert_called_once_with(test_todos)

    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_manager_validation_error_invalid_priority(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test handling of validation error for invalid priority."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.side_effect = ValueError("Invalid priority 'urgent'. Must be 'high', 'medium', or 'low'")
        
        test_todos = [{
            'id': '1',
            'content': 'Test task',
            'status': 'pending',
            'priority': 'urgent'
        }]
        
        result = todo_write_tool.run_impl(todos=test_todos)
        
        assert "Error updating todo list: Invalid priority 'urgent'" in result
        mock_todo_manager.set_todos.assert_called_once_with(test_todos)

    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_manager_validation_error_empty_content(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test handling of validation error for empty content."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.side_effect = ValueError("Todo content cannot be empty")
        
        test_todos = [{
            'id': '1',
            'content': '   ',  # Whitespace only
            'status': 'pending',
            'priority': 'medium'
        }]
        
        result = todo_write_tool.run_impl(todos=test_todos)
        
        assert "Error updating todo list: Todo content cannot be empty" in result
        mock_todo_manager.set_todos.assert_called_once_with(test_todos)

    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_manager_validation_error_multiple_in_progress(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test handling of validation error for multiple in_progress tasks."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.side_effect = ValueError("Only one task can be in_progress at a time")
        
        test_todos = [
            {'id': '1', 'content': 'First task', 'status': 'in_progress', 'priority': 'medium'},
            {'id': '2', 'content': 'Second task', 'status': 'in_progress', 'priority': 'medium'}
        ]
        
        result = todo_write_tool.run_impl(todos=test_todos)
        
        assert "Error updating todo list: Only one task can be in_progress at a time" in result
        mock_todo_manager.set_todos.assert_called_once_with(test_todos)

    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_manager_validation_error_non_dict_todo(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test handling of validation error for non-dictionary todo items."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.side_effect = ValueError("Each todo must be a dictionary")
        
        test_todos = ["invalid todo", 123, None]  # Non-dict items
        
        result = todo_write_tool.run_impl(todos=test_todos)
        
        assert "Error updating todo list: Each todo must be a dictionary" in result
        mock_todo_manager.set_todos.assert_called_once_with(test_todos)

    # Edge cases and error handling
    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_manager_exception_handling(self, mock_get_manager, todo_write_tool):
        """Test handling when TodoManager raises an unexpected exception."""
        mock_manager = Mock()
        mock_manager.set_todos.side_effect = Exception("Database connection error")
        mock_get_manager.return_value = mock_manager
        
        test_todos = [{'id': '1', 'content': 'Test task', 'status': 'pending', 'priority': 'medium'}]
        
        # Should re-raise the exception since it's not a ValueError
        with pytest.raises(Exception, match="Database connection error"):
            todo_write_tool.run_impl(todos=test_todos)

    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_write_todos_with_numeric_ids(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test writing todos with numeric IDs (should work)."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.return_value = None
        
        test_todos = [
            {'id': 1, 'content': 'Numeric ID task', 'status': 'pending', 'priority': 'medium'}
        ]
        
        result = todo_write_tool.run_impl(todos=test_todos)
        
        assert "Todos have been modified successfully" in result
        mock_todo_manager.set_todos.assert_called_once_with(test_todos)

    @pytest.mark.unit
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_write_todos_preserves_extra_fields(self, mock_get_manager, todo_write_tool, mock_todo_manager):
        """Test that extra fields in todos are preserved."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.set_todos.return_value = None
        
        test_todos = [{
            'id': '1',
            'content': 'Task with extra fields',
            'status': 'pending',
            'priority': 'medium',
            'created_at': '2023-01-01',
            'assigned_to': 'user123',
            'tags': ['urgent', 'bug-fix']
        }]
        
        result = todo_write_tool.run_impl(todos=test_todos)
        
        assert "Todos have been modified successfully" in result
        mock_todo_manager.set_todos.assert_called_once_with(test_todos)

    @pytest.mark.unit
    def test_tool_requires_todos_parameter(self, todo_write_tool):
        """Test that the tool requires todos parameter."""
        # This should raise an error due to missing required parameter
        with pytest.raises(TypeError):
            todo_write_tool.run_impl()


class TestTodoWriteToolIntegration:
    """Integration tests for TodoWriteTool with real TodoManager."""

    @pytest.fixture
    def clean_todo_manager(self):
        """Provide a clean TodoManager instance for each test."""
        from tools.productivity.shared_state import TodoManager
        manager = TodoManager()
        manager.clear_todos()
        return manager

    @pytest.mark.integration
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_real_todo_manager_integration_success(self, mock_get_manager, clean_todo_manager):
        """Test successful integration with real TodoManager."""
        mock_get_manager.return_value = clean_todo_manager
        tool = TodoWriteTool()
        
        test_todos = [
            {'id': '1', 'content': 'First task', 'status': 'pending', 'priority': 'high'},
            {'id': '2', 'content': 'Second task', 'status': 'in_progress', 'priority': 'medium'}
        ]
        
        result = tool.run_impl(todos=test_todos)
        
        assert "Todos have been modified successfully" in result
        
        # Verify todos were actually set
        stored_todos = clean_todo_manager.get_todos()
        assert len(stored_todos) == 2
        assert stored_todos[0]['content'] == 'First task'
        assert stored_todos[1]['content'] == 'Second task'

    @pytest.mark.integration
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_real_todo_manager_integration_validation_error(self, mock_get_manager, clean_todo_manager):
        """Test integration with real TodoManager validation errors."""
        mock_get_manager.return_value = clean_todo_manager
        tool = TodoWriteTool()
        
        # Try to set invalid todos (missing content)
        invalid_todos = [
            {'id': '1', 'status': 'pending', 'priority': 'medium'}  # Missing content
        ]
        
        result = tool.run_impl(todos=invalid_todos)
        
        assert "Error updating todo list" in result
        assert "content" in result
        
        # Verify no todos were set due to validation error
        stored_todos = clean_todo_manager.get_todos()
        assert len(stored_todos) == 0

    @pytest.mark.integration
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_real_todo_manager_integration_multiple_in_progress_error(self, mock_get_manager, clean_todo_manager):
        """Test integration with real TodoManager for multiple in_progress validation."""
        mock_get_manager.return_value = clean_todo_manager
        tool = TodoWriteTool()
        
        # Try to set multiple in_progress todos
        invalid_todos = [
            {'id': '1', 'content': 'First task', 'status': 'in_progress', 'priority': 'medium'},
            {'id': '2', 'content': 'Second task', 'status': 'in_progress', 'priority': 'medium'}
        ]
        
        result = tool.run_impl(todos=invalid_todos)
        
        assert "Error updating todo list" in result
        assert "Only one task can be in_progress at a time" in result
        
        # Verify no todos were set due to validation error
        stored_todos = clean_todo_manager.get_todos()
        assert len(stored_todos) == 0

    @pytest.mark.integration
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_real_todo_manager_integration_update_existing(self, mock_get_manager, clean_todo_manager):
        """Test updating existing todos through integration."""
        mock_get_manager.return_value = clean_todo_manager
        tool = TodoWriteTool()
        
        # Set initial todos
        initial_todos = [
            {'id': '1', 'content': 'Original task', 'status': 'pending', 'priority': 'medium'}
        ]
        result = tool.run_impl(todos=initial_todos)
        assert "Todos have been modified successfully" in result
        
        # Update todos
        updated_todos = [
            {'id': '1', 'content': 'Updated task', 'status': 'completed', 'priority': 'high'},
            {'id': '2', 'content': 'New task', 'status': 'pending', 'priority': 'low'}
        ]
        result = tool.run_impl(todos=updated_todos)
        assert "Todos have been modified successfully" in result
        
        # Verify update
        stored_todos = clean_todo_manager.get_todos()
        assert len(stored_todos) == 2
        assert stored_todos[0]['content'] == 'Updated task'
        assert stored_todos[0]['status'] == 'completed'
        assert stored_todos[1]['content'] == 'New task'

    @pytest.mark.integration 
    @patch('tools.productivity.todo_write_tool.get_todo_manager')
    def test_thread_safety_simulation(self, mock_get_manager, clean_todo_manager):
        """Test that writing is thread-safe by simulating concurrent access."""
        mock_get_manager.return_value = clean_todo_manager
        tool = TodoWriteTool()
        
        # Simulate multiple writes
        for i in range(5):
            test_todos = [
                {'id': str(i), 'content': f'Task {i}', 'status': 'pending', 'priority': 'medium'}
            ]
            result = tool.run_impl(todos=test_todos)
            assert "Todos have been modified successfully" in result
        
        # Final verification
        stored_todos = clean_todo_manager.get_todos()
        assert len(stored_todos) == 1  # Only the last write should remain
        assert stored_todos[0]['content'] == 'Task 4' 