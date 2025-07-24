"""TodoWrite tool for creating and managing structured task lists."""

from typing import List, Dict, Any
from ii_tool.tools.base import BaseTool, ToolResult
from ii_tool.tools.productivity.shared_state import get_todo_manager


# Constants
SUCCESS_MESSAGE = "Todos have been modified successfully. Ensure that you continue to use the todo list to track your progress. Please proceed with the current tasks if applicable"
ERROR_MESSAGE = "Error updating todo list: {error}"

# Name
NAME = "TodoWrite"
DISPLAY_NAME = "Write todo list"

# Tool description
DESCRIPTION = """Use this tool to create and manage a structured task list for your current coding session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.
It also helps the user understand the progress of the task and overall progress of their requests.

## When to Use This Tool
Use this tool proactively in these scenarios:

1. Complex multi-step tasks - When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)
5. After receiving new instructions - Immediately capture user requirements as todos
6. When you start working on a task - Mark it as in_progress BEFORE beginning work. Ideally you should only have one todo as in_progress at a time
7. After completing a task - Mark it as completed and add any new follow-up tasks discovered during implementation

## When NOT to Use This Tool

Skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and tracking it provides no organizational benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

NOTE that you should not use this tool if there is only one trivial task to do. In this case you are better off just doing the task directly.

## Task States and Management

1. **Task States**: Use these states to track progress:
   - pending: Task not yet started
   - in_progress: Currently working on (limit to ONE task at a time)
   - completed: Task finished successfully

2. **Task Management**:
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
   - Only have ONE task in_progress at any time
   - Complete current tasks before starting new ones
   - Remove tasks that are no longer relevant from the list entirely

3. **Task Completion Requirements**:
   - ONLY mark a task as completed when you have FULLY accomplished it
   - If you encounter errors, blockers, or cannot finish, keep the task as in_progress
   - When blocked, create a new task describing what needs to be resolved
   - Never mark a task as completed if:
     - Tests are failing
     - Implementation is partial
     - You encountered unresolved errors
     - You couldn't find necessary files or dependencies

4. **Task Breakdown**:
   - Create specific, actionable items
   - Break complex tasks into smaller, manageable steps
   - Use clear, descriptive task names

When in doubt, use this tool. Being proactive with task management demonstrates attentiveness and ensures you complete all requirements successfully."""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "todos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "content": {"type": "string"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"]}
                },
                "required": ["id", "content", "status", "priority"]
            },
            "description": "The updated todo list. Each todo should have `content`, `status` (one of 'pending', 'in_progress', 'completed'), `priority` (one of 'low', 'medium', 'high'), and `id` (starts from 1) keys."
        }
    },
    "required": ["todos"]
}

class TodoWriteTool(BaseTool):
    """Tool for creating and managing a structured task list for the coding session."""
    
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Write/update the todo list."""
        todos = tool_input.get("todos")
        
        manager = get_todo_manager()
        
        try:
            # Set the new todo list (validation happens inside set_todos)
            manager.set_todos(todos)
            
            # Return the updated list
            return ToolResult(
                llm_content=SUCCESS_MESSAGE,
                is_error=False
            )
        except ValueError as e:
            return ToolResult(
                llm_content=ERROR_MESSAGE.format(error=e),
                is_error=True
            )

    async def execute_mcp_wrapper(
        self,
        todos: List[Dict[str, Any]],
    ):
        return await self._mcp_wrapper(
            tool_input={
                "todos": todos,
            }
        )