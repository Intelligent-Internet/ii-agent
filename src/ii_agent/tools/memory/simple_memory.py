from typing import Any, Optional, Dict
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import LLMTool, ToolImplOutput


class SimpleMemoryTool(LLMTool):
    """String-based memory tool for storing and modifying persistent text.

    This tool maintains a single in-memory string that can be read,
    replaced, or selectively edited using string replacement. It provides safety
    warnings when overwriting content or when edit operations would affect
    multiple occurrences.
    """

    name = "simple_memory"

    description = """Tool for managing persistent text memory with read, write and edit operations.
        
        MEMORY STORAGE GUIDANCE:
        Store information that needs to persist across agent interactions, including:
        - User context: Requirements, goals, preferences, and clarifications
        - Task state: Completed tasks, pending items, current progress
        - Code context: File paths, function signatures, data structures, dependencies
        - Research findings: Key facts, sources, URLs, and reference materials
        - Configuration: Settings, parameters, and environment details
        - Cross-session continuity: Information needed for future interactions
        
        OPERATIONS:
        - Read: Retrieves full memory contents as a string
        - Write: Replaces entire memory (warns when overwriting existing data)
        - Edit: Performs targeted string replacement (warns on multiple matches)
        
        Use structured formats (JSON, YAML, or clear sections) for complex data.
        Prioritize information that would be expensive to regenerate or re-research."""

    # single tool that exposes 3 distinct abilities
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "edit"],
                "description": "The memory operation to perform: read retrieves current content, write replaces everything, edit performs string replacement",
            },
            "content": {
                "type": "string",
                "description": "Full text content to store when using write action (ignored for read/edit)",
            },
            "old_string": {
                "type": "string",
                "description": "Exact text to find and replace when using edit action (must be unique in memory)",
            },
            "new_string": {
                "type": "string",
                "description": "Replacement text to insert when using edit action",
            },
        },
        "required": ["action"],
    }

    def __init__(self):
        self.full_memory = ""
        self.compressed_memory = ""  # not doing anything with this for now

    def _read_memory(self) -> str:
        """Read the current memory contents."""
        return self.full_memory

    def _write_memory(self, content: str) -> str:
        """Replace the entire memory with new content."""
        if self.full_memory:
            previous = self.full_memory
            self.full_memory = content
            return f"Warning: Overwriting existing content. Previous content was:\n{previous}\n\nMemory has been updated successfully."
        self.full_memory = content
        return "Memory updated successfully."

    def _edit_memory(self, old_string: str, new_string: str) -> str:
        """Replace occurrences of old string with new string."""
        if old_string not in self.full_memory:
            return f"Error: '{old_string}' not found in memory."

        old_memory = self.full_memory
        count = old_memory.count(old_string)

        if count > 1:
            return f"Warning: Found {count} occurrences of '{old_string}'. Please confirm which occurrence to replace or use more specific context."

        self.full_memory = self.full_memory.replace(old_string, new_string)
        return "Edited memory: 1 occurrence replaced."

    def __str__(self) -> str:
        return self.full_memory

    async def run_impl(
        self,
        tool_input: Dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        action = tool_input.get("action")
        content = tool_input.get("content", "")
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")

        if action == "read":
            result =  self._read_memory()
            return ToolImplOutput(result, "Memory read successfully", {"success": True})
        elif action == "write":
            result =  self._write_memory(content)
            return ToolImplOutput(result, "Memory write completed", {"success": True})
        elif action == "edit":
            result = self._edit_memory(old_string, new_string)
            return ToolImplOutput(result, "Memory edit completed", {"success": True})
        else:
            return ToolImplOutput(f"Error: Unknown action '{action}'. Valid actions are read, write, edit.", "Invalid action", {"success": False})
