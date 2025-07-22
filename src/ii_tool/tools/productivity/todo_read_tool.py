"""TodoRead tool for reading the current session's task list."""

from ii_tool.tools.base import BaseTool
from ii_tool.tools.productivity.shared_state import get_todo_manager


DESCRIPTION = """Use this tool to read the current to-do list for the session. This tool should be used proactively and frequently to ensure that you are aware of
the status of the current task list. You should make use of this tool as often as possible, especially in the following situations:
- At the beginning of conversations to see what's pending
- Before starting new tasks to prioritize work
- When the user asks about previous tasks or plans
- Whenever you're uncertain about what to do next
- After completing tasks to update your understanding of remaining work
- After every few messages to ensure you're on track

Usage:
- This tool takes in no parameters. So leave the input blank or empty. DO NOT include a dummy object, placeholder string or a key like \"input\" or \"empty\". LEAVE IT BLANK.
- Returns a list of todo items with their status, priority, and content
- Use this information to track progress and plan next steps
- If no todos exist yet, an empty list will be returned"""


EMPTY_MESSAGE = "No todos found"
SUCCESS_MESSAGE = "Remember to continue to use update and read from the todo list as you make progress. Here is the current list: {todos}"


class TodoReadTool(BaseTool):
    """Tool for reading the current to-do list for the session."""
    
    name = "TodoRead"
    description = DESCRIPTION
    read_only = True

    def run_impl(self):
        """Read and return the current todo list."""
        manager = get_todo_manager()
        todos = manager.get_todos()
        
        if not todos:
            return EMPTY_MESSAGE
        
        return SUCCESS_MESSAGE.format(todos=todos)