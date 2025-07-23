"""Shared state management for productivity tools."""

from typing import List, Dict, Any
from threading import Lock


class TodoManager:
    """Manages the todo list state across productivity tools."""
    
    def __init__(self):
        self._todos: List[Dict[str, Any]] = []
        self._lock = Lock()
    
    def get_todos(self) -> List[Dict[str, Any]]:
        """Get the current list of todos."""
        with self._lock:
            return self._todos.copy()
    
    def set_todos(self, todos: List[Dict[str, Any]]) -> None:
        """Set the entire todo list."""
        # Validate todo structure
        for todo in todos:
            if not isinstance(todo, dict):
                raise ValueError("Each todo must be a dictionary")
            
            # Required fields
            if 'content' not in todo:
                raise ValueError("Each todo must have a 'content' field")
            if 'status' not in todo:
                raise ValueError("Each todo must have a 'status' field")
            if 'priority' not in todo:
                raise ValueError("Each todo must have a 'priority' field")
            if 'id' not in todo:
                raise ValueError("Each todo must have an 'id' field")
            
            # Validate status
            if todo['status'] not in ['pending', 'in_progress', 'completed']:
                raise ValueError(f"Invalid status '{todo['status']}'. Must be 'pending', 'in_progress', or 'completed'")
            
            # Validate priority
            if todo['priority'] not in ['high', 'medium', 'low']:
                raise ValueError(f"Invalid priority '{todo['priority']}'. Must be 'high', 'medium', or 'low'")
            
            # Ensure content is not empty
            if not todo['content'].strip():
                raise ValueError("Todo content cannot be empty")
        
        # Ensure only one task is in_progress
        in_progress_count = sum(1 for todo in todos if todo['status'] == 'in_progress')
        if in_progress_count > 1:
            raise ValueError("Only one task can be in_progress at a time")
        
        with self._lock:
            self._todos = [todo.copy() for todo in todos]
    
    def clear_todos(self) -> None:
        """Clear all todos."""
        with self._lock:
            self._todos = []


# Global instance to be shared across tools
_global_manager: TodoManager | None = None


def get_todo_manager() -> TodoManager:
    """Get the global todo manager instance."""
    global _global_manager
    if _global_manager is None:
        _global_manager = TodoManager()
    return _global_manager