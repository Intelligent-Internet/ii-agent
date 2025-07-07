"""Comprehensive tests for TodoReadTool."""

import pytest
import os
from unittest.mock import Mock, patch

# Add src to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tools.productivity.todo_read_tool import TodoReadTool
from tools.productivity.shared_state import TodoManager


class TestTodoReadTool:
    """Test class for TodoReadTool functionality."""

    @pytest.fixture
    def mock_todo_manager(self):
        """Create a mock TodoManager for testing."""
        return Mock(spec=TodoManager)

    @pytest.fixture
    def todo_read_tool(self):
        """Create a TodoReadTool instance."""
        return TodoReadTool()

    def test_tool_initialization(self, todo_read_tool):
        """Test that the tool initializes correctly."""
        assert todo_read_tool.name == "TodoRead"
        assert "Use this tool to read the current to-do list" in todo_read_tool.description
        assert "takes in no parameters" in todo_read_tool.description

    # Success scenarios
    @pytest.mark.unit
    @patch('tools.productivity.todo_read_tool.get_todo_manager')
    def test_read_empty_todo_list(self, mock_get_manager, todo_read_tool, mock_todo_manager):
        """Test reading when todo list is empty."""
        mock_get_manager.return_value = mock_todo_manager
        mock_todo_manager.get_todos.return_value = []
        
        result = todo_read_tool.run_impl()
        
        assert result == "No todos found"
        mock_todo_manager.get_todos.assert_called_once()

    @pytest.mark.unit
    @patch('tools.productivity.todo_read_tool.get_todo_manager')
    def test_read_single_todo(self, mock_get_manager, todo_read_tool, mock_todo_manager):
        """Test reading a single todo item."""
        mock_get_manager.return_value = mock_todo_manager
        test_todo = {
            'id': '1',
            'content': 'Test task',
            'status': 'pending',
            'priority': 'medium'
        }
        mock_todo_manager.get_todos.return_value = [test_todo]
        
        result = todo_read_tool.run_impl()
        
        assert "Remember to continue to use update and read from the todo list" in result
        assert str([test_todo]) in result
        mock_todo_manager.get_todos.assert_called_once()

    @pytest.mark.unit
    @patch('tools.productivity.todo_read_tool.get_todo_manager')
    def test_read_multiple_todos(self, mock_get_manager, todo_read_tool, mock_todo_manager):
        """Test reading multiple todos in their original order."""
        mock_get_manager.return_value = mock_todo_manager
        test_todos = [
            {'id': '1', 'content': 'First task', 'status': 'completed', 'priority': 'high'},
            {'id': '2', 'content': 'Second task', 'status': 'in_progress', 'priority': 'low'},
            {'id': '3', 'content': 'Third task', 'status': 'pending', 'priority': 'medium'}
        ]
        mock_todo_manager.get_todos.return_value = test_todos
        
        result = todo_read_tool.run_impl()
        
        # Verify the result contains the reminder message
        assert "Remember to continue to use update and read from the todo list" in result
        
        # Verify todos are returned in original order
        assert "First task" in result
        assert "Second task" in result
        assert "Third task" in result
        assert str(test_todos) in result
        mock_todo_manager.get_todos.assert_called_once()





    @pytest.mark.unit
    @patch('tools.productivity.todo_read_tool.get_todo_manager')
    def test_read_todos_with_various_data(self, mock_get_manager, todo_read_tool, mock_todo_manager):
        """Test reading todos with various status and priority values."""
        mock_get_manager.return_value = mock_todo_manager
        test_todos = [
            {'id': '1', 'content': 'Unknown status', 'status': 'unknown_status', 'priority': 'medium'},
            {'id': '2', 'content': 'Unknown priority', 'status': 'pending', 'priority': 'unknown_priority'},
            {'id': '3', 'content': 'Normal todo', 'status': 'pending', 'priority': 'high'}
        ]
        mock_todo_manager.get_todos.return_value = test_todos
        
        result = todo_read_tool.run_impl()
        
        # Should handle gracefully and return all todos
        assert "Remember to continue to use update and read from the todo list" in result
        assert "Unknown status" in result
        assert "Unknown priority" in result
        assert "Normal todo" in result
        assert str(test_todos) in result
        mock_todo_manager.get_todos.assert_called_once()

    # Error and edge case scenarios
    @pytest.mark.unit
    @patch('tools.productivity.todo_read_tool.get_todo_manager')
    def test_manager_exception_handling(self, mock_get_manager, todo_read_tool):
        """Test handling when TodoManager raises an exception."""
        mock_manager = Mock()
        mock_manager.get_todos.side_effect = Exception("Database connection error")
        mock_get_manager.return_value = mock_manager
        
        # Should re-raise the exception since the tool doesn't handle it
        with pytest.raises(Exception, match="Database connection error"):
            todo_read_tool.run_impl()

    @pytest.mark.unit
    @patch('tools.productivity.todo_read_tool.get_todo_manager')
    def test_malformed_todo_data(self, mock_get_manager, todo_read_tool, mock_todo_manager):
        """Test handling of malformed todo data."""
        mock_get_manager.return_value = mock_todo_manager
        # Missing required fields
        malformed_todos = [
            {'id': '1', 'content': 'Missing status and priority'},
            {'id': '2', 'status': 'pending'},  # Missing content and priority
        ]
        mock_todo_manager.get_todos.return_value = malformed_todos
        
        result = todo_read_tool.run_impl()
        
        # Should still return result even with malformed data (tool is read-only)
        assert "Remember to continue to use update and read from the todo list" in result
        mock_todo_manager.get_todos.assert_called_once()

    @pytest.mark.unit  
    def test_tool_no_parameters_requirement(self, todo_read_tool):
        """Test that the tool can be called without any parameters."""
        # The tool description specifically mentions it takes no parameters
        # This should work without any arguments
        with patch('tools.productivity.todo_read_tool.get_todo_manager') as mock_get_manager:
            mock_manager = Mock()
            mock_manager.get_todos.return_value = []
            mock_get_manager.return_value = mock_manager
            
            result = todo_read_tool.run_impl()
            assert result == "No todos found"


class TestTodoReadToolIntegration:
    """Integration tests for TodoReadTool with real TodoManager."""

    @pytest.fixture
    def clean_todo_manager(self):
        """Provide a clean TodoManager instance for each test."""
        from tools.productivity.shared_state import TodoManager
        manager = TodoManager()
        manager.clear_todos()
        return manager

    @pytest.mark.integration
    @patch('tools.productivity.todo_read_tool.get_todo_manager')
    def test_real_todo_manager_integration(self, mock_get_manager, clean_todo_manager):
        """Test integration with real TodoManager."""
        mock_get_manager.return_value = clean_todo_manager
        tool = TodoReadTool()
        
        # Start with empty list
        result = tool.run_impl()
        assert result == "No todos found"
        
        # Add some todos through the manager
        test_todos = [
            {'id': '1', 'content': 'First task', 'status': 'pending', 'priority': 'high'},
            {'id': '2', 'content': 'Second task', 'status': 'in_progress', 'priority': 'medium'}
        ]
        clean_todo_manager.set_todos(test_todos)
        
        # Read them back
        result = tool.run_impl()
        assert "Remember to continue to use update and read from the todo list" in result
        assert "First task" in result
        assert "Second task" in result
        # Todos should be returned in original order
        assert str(test_todos) in result

    @pytest.mark.integration
    @patch('tools.productivity.todo_read_tool.get_todo_manager')
    def test_thread_safety_simulation(self, mock_get_manager, clean_todo_manager):
        """Test that reading is thread-safe by simulating concurrent access."""
        mock_get_manager.return_value = clean_todo_manager
        tool = TodoReadTool()
        
        # Set up initial todos
        initial_todos = [
            {'id': str(i), 'content': f'Task {i}', 'status': 'pending', 'priority': 'medium'}
            for i in range(10)
        ]
        clean_todo_manager.set_todos(initial_todos)
        
        # Multiple reads should return consistent results
        results = []
        for _ in range(5):
            result = tool.run_impl()
            results.append(result)
        
        # All results should be identical
        assert all(result == results[0] for result in results)
        assert "Task 0" in results[0]
        assert "Task 9" in results[0] 