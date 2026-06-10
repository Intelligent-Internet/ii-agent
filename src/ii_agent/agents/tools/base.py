"""Enhanced BaseTool for v2 agent system with hook support."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Type
from pydantic import BaseModel

if TYPE_CHECKING:
    from ii_agent.agents.agent import IIAgent
    from ii_agent.agents.tools.function import FunctionCall


@dataclass
class UserInputField:
    """Field definition for user input in HITL (Human-in-the-Loop) workflows."""

    name: str
    field_type: Type
    description: Optional[str] = None
    value: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "field_type": str(self.field_type.__name__),
            "description": self.description,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserInputField":
        # Use a safe type lookup instead of eval() to prevent code injection
        _SAFE_TYPES = {
            "str": str, "int": int, "float": float, "bool": bool,
            "list": list, "dict": dict, "tuple": tuple, "set": set,
            "bytes": bytes, "NoneType": type(None),
        }
        field_type_name = data["field_type"]
        field_type = _SAFE_TYPES.get(field_type_name, str)
        return cls(
            name=data["name"],
            field_type=field_type,
            description=data["description"],
            value=data["value"],
        )


class ToolParam(BaseModel):
    """Internal representation of LLM tool."""

    type: Literal["function", "custom"] = "function"
    name: str
    description: str
    input_schema: dict[str, Any]


class TextContent(BaseModel):
    type: Literal["text"]
    text: str


class ImageContent(BaseModel):
    type: Literal["image"]
    data: str  # base64 encoded image data
    mime_type: str  # e.g. "image/png"


class ToolResult(BaseModel):
    """Result of tool execution"""

    llm_content: str | List[TextContent | ImageContent]
    user_display_content: Optional[str | Dict[str, Any] | List[Dict[str, Any]]] = None
    is_error: Optional[bool] = None
    is_interrupted: bool = False
    cost: float = 0.0  # Direct USD cost from tool execution (e.g. image generation API)

    # Post-execution HITL (Human-in-the-Loop) fields
    # When True, the agent will pause after tool execution and wait for user input
    requires_user_input: bool = False
    # Schema for the user input fields (optional, for structured input)
    user_input_schema: Optional[List[UserInputField]] = None


class ToolConfirmationDetails(BaseModel):
    type: Literal["edit", "bash", "mcp"]
    message: str


class FileURLContent(BaseModel):
    type: Literal["file_url"]
    url: str
    mime_type: str
    name: str
    size: int


class BaseAgentTool(ABC):
    """
    Enhanced base class for v2 agent tools with hook support.

    Attributes:
        name: Tool name used for identification
        description: Tool description for LLM context
        input_schema: JSON schema for tool input parameters
        read_only: Whether the tool only reads data (no side effects)
        display_name: Human-readable name for UI display
        metadata: Optional metadata for custom tool configurations
        instructions: Optional instructions to add to system prompt
        add_instructions: Whether to add instructions to the agent's system message

    Hooks:agent
        Override `on_tool_start()` and `on_tool_end()` to add execution hooks.
        These methods are called directly before/after tool execution.

    Example:
        class MyTool(BaseTool):
            def __init__(self):
                self.name = "my_tool"
                self.description = "Does something useful"
                self.input_schema = {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"]
                }
                self.read_only = True
                self.display_name = "My Tool"

            async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall"):
                print(f"About to execute {self.name}")
                # Can do async operations like logging, API calls, etc.

            async def on_tool_end(self, agent: "IIAgent", fc: "FunctionCall"):
                if fc.error:
                    print(f"Failed: {fc.error}")
                else:
                    print(f"Result: {fc.result}")
                # Can do async cleanup, metrics reporting, etc.

            async def execute(self, tool_input: dict) -> ToolResult:
                query = tool_input.get("query", "")
                return ToolResult(llm_content=f"Result for: {query}")
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool
    display_name: str
    metadata: Optional[Dict[str, Any]] = None
    tool_logo: Optional[str] = None  # URL for tool icon/logo

    # Optional attributes for agent integration
    instructions: Optional[str] = None
    add_instructions: bool = True
    requires_sandbox: bool = False
    requires_confirmation: bool = False

    # Pre-execution HITL (Human-in-the-Loop) fields
    # When True, the tool pauses before execution and waits for user input
    requires_user_input: bool = False
    # List of field names that the user provides (empty means all fields)
    user_input_fields: Optional[List[str]] = None

    # If True, the agent will stop executing after this tool call completes
    stop_after_tool_call: bool = False

    def should_confirm_execute(self, tool_input: dict[str, Any]) -> ToolConfirmationDetails | bool:
        """
        Determine if the tool execution should be confirmed.

        In web application mode, the tool is executed without confirmation.
        In CLI mode, some tools should be confirmed by the user before execution
        (e.g. file edit, shell command, etc.)

        Args:
            tool_input: The input parameters for the tool.

        Returns:
            ToolConfirmationDetails with confirmation message, or bool.
        """
        return False

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        """
        Called before tool execution. Override to add pre-execution logic.

        Args:
            agent: The IIAgent instance executing the tool
            fc: The FunctionCall instance with arguments
        """
        pass

    async def on_tool_end(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        """
        Called after tool execution. Override to add post-execution logic.
        This is called regardless of whether the tool succeeded or failed.

        Args:
            agent: The IIAgent instance that executed the tool
            fc: The FunctionCall instance (contains result or error)
        """
        pass

    @abstractmethod
    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        """
        Execute the tool with the given input.

        Args:
            tool_input: Dictionary of input parameters matching input_schema.

        Returns:
            ToolResult containing the output for the LLM and optional display content.

        Raises:
            NotImplementedError: Must be implemented by child classes.
        """
        raise NotImplementedError


class AgentAsTool(BaseAgentTool):
    """Tool wrapper for an IIAgent."""

    def __init__(
        self,
        agent_instance: "IIAgent",
        input_schema: Dict[str, Any],
        read_only: bool = True,
        name: Optional[str] = None,
    ):
        self._agent = agent_instance
        self.name = name or agent_instance.name
        self.description = agent_instance.description
        self.input_schema = input_schema
        self.read_only = read_only

    async def execute(self, tool_input: Dict[str, Any]) -> ToolResult:
        """Execute the wrapped agent."""
        prompt = tool_input.get("prompt", "")

        try:
            run_response = await self._agent.arun(
                input=prompt,
                session_id=self._agent.session_id,
                user_id=self._agent.user_id,
            )

            return ToolResult(
                llm_content=run_response.content,
                user_display_content="Sub-agent completed",
                is_error=False,
            )

        except Exception as e:
            return ToolResult(
                llm_content=f"{self._agent.name} run failed: {str(e)}",
                user_display_content=f"Sub-agent failed: {str(e)}",
                is_error=True,
            )
