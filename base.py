from abc import ABC, abstractmethod
from typing import Any, Callable, Literal, List
from pydantic import BaseModel
from enum import Enum

class TextContent(BaseModel):
    type: Literal["text"]
    text: str

class ImageContent(BaseModel):
    type: Literal["image"]
    data: str # base64 encoded image data
    mimeType: str # e.g. "image/png"

class ToolResult(BaseModel):
    """Result of tool execution"""
    llm_content: str | List[TextContent | ImageContent]
    user_display_content: str

class ToolConfirmationOutcome(Enum):
    """Possible outcomes from tool confirmation dialog."""
    PROCEED_ONCE = "proceed_once"
    PROCEED_ALWAYS = "proceed_always"
    DO_OTHER = "do_other"

class ToolConfirmationDetails(BaseModel):
    type: Literal["edit", "bash", "mcp"]
    message: str
    on_confirm_callback: Callable[[ToolConfirmationOutcome], None]

class BaseTool(ABC):
    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        display_name: str | None = None,
    ):
        """Initialize a tool with its metadata and configuration.
        
        Args:
            name: The unique identifier for the tool used in function calls.
            description: A detailed description of what the tool does and when to use it.
            input_schema: JSON schema defining the tool's input parameters and validation rules.
            display_name: Human-readable name for UI display. Defaults to the tool name if not provided.
        """
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.display_name = display_name if display_name else name

    def is_read_only(self) -> bool:
        """Determine if this tool only performs read operations without side effects.
        
        Read-only tools can be safely executed concurrently for better performance,
        while non-read-only tools (those that write files, execute commands, modify
        state, or make external API calls) must be executed serially to avoid 
        conflicts and ensure data consistency.
        
        Override this method in subclasses to return True for tools that only
        read or query information without making any changes.
        
        Returns:
            bool: True if the tool is read-only, False otherwise. Defaults to False
                  for safety unless explicitly overridden.
        """
        return False

    @abstractmethod
    def should_confirm_execute(self, tool_input: dict[str, Any]) -> ToolConfirmationDetails | bool:
        """Whether the tool should be confirmed by the user before execution."""
        raise NotImplementedError()

    @abstractmethod
    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Execute the tool with the given input."""
        raise NotImplementedError()