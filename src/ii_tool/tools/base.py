from abc import ABC, abstractmethod
from typing import Any, List, Literal, Optional
from pydantic import BaseModel

class TextContent(BaseModel):
    type: Literal["text"]
    text: str

class ImageContent(BaseModel):
    type: Literal["image"]
    data: str # base64 encoded image data
    mime_type: str # e.g. "image/png"

class ToolResult(BaseModel):
    """Result of tool execution"""
    llm_content: str | List[TextContent | ImageContent]
    user_display_content: Optional[str] = None
    is_error: Optional[bool] = None

class ToolConfirmationDetails(BaseModel):
    type: Literal["edit", "bash", "mcp"]
    message: str

class BaseTool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool
    display_name: str

    def should_confirm_execute(self, tool_input: dict[str, Any]) -> ToolConfirmationDetails | bool:
        """
        Determine if the tool execution should be confirmed.
        In web application mode, the tool is executed without confirmation.
        In CLI mode, some tools should be confirmed by the user before execution (e.g. file edit, shell command, etc.)

        Args:
            tool_input (dict[str, Any]): The input to the tool.

        Returns:
            ToolConfirmationDetails | bool: The confirmation details or a boolean indicating if the execution should be confirmed.        
        """
        return False

    @abstractmethod
    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    async def _mcp_wrapper(self, tool_input: dict[str, Any]):
        """Wraps the tool execution to match with FastMCP Format"""

        from mcp.types import ImageContent as MCPImageContent, TextContent as MCPTextContent
        from fastmcp.tools.tool import ToolResult as FastMCPToolResult

        internal_result = await self.execute(tool_input)
        llm_content = internal_result.llm_content

        mcp_result = []

        if isinstance(llm_content, str):
            mcp_result.append(MCPTextContent(
                type="text",
                text=llm_content,
            ))
        elif isinstance(llm_content, list):
            for content in llm_content:
                if isinstance(content, ImageContent):
                    mcp_result.append(MCPImageContent(
                        type="image",
                        data=content.data,
                        mimeType=content.mime_type,
                    ))
                elif isinstance(content, TextContent):
                    mcp_result.append(MCPTextContent(
                        type="text",
                        text=content.text,
                    ))
        
        return FastMCPToolResult(content=mcp_result)