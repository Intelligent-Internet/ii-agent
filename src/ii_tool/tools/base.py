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

class BaseTool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool
    display_name: str

    @abstractmethod
    async def execute(self, *args, **kwargs) -> ToolResult:
        raise NotImplementedError

    async def _mcp_wrapper(self, *args, **kwargs):
        from mcp.types import ImageContent as MCPImageContent, TextContent as MCPTextContent
        from fastmcp.tools.tool import ToolResult as FastMCPToolResult

        internal_result = await self.execute(*args, **kwargs)
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