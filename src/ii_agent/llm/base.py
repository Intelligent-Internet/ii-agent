from abc import ABC, abstractmethod
import json
from typing import Any, Optional, Tuple, List
from pydantic import BaseModel
from typing import Literal


import logging

logging.getLogger("httpx").setLevel(logging.WARNING)


class ToolParam(BaseModel):
    """Internal representation of LLM tool."""

    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCall(BaseModel):
    """Internal representation of LLM-generated tool call."""

    tool_call_id: str
    tool_name: str
    tool_input: Any
    tool_id: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.tool_name} with input: {self.tool_input}"


class ToolResult(BaseModel):
    """Internal representation of LLM tool result."""

    tool_call_id: str
    tool_name: str
    tool_output: Any


class ToolFormattedResult(BaseModel):
    """Internal representation of formatted LLM tool result."""

    tool_call_id: str
    tool_name: str
    tool_output: list[dict[str, Any]] | str

    def __str__(self) -> str:
        if isinstance(self.tool_output, list):
            parts = []
            for item in self.tool_output:
                if isinstance(item, dict):
                    if item.get("type") == "image":
                        # Handle image in tool output
                        source = item.get("source", {})
                        media_type = source.get("media_type", "image/unknown")
                        parts.append(f"[Image attached - {media_type}]")
                    elif item.get("type") == "text":
                        # Handle text in tool output
                        parts.append(item.get("text", ""))
                    else:
                        # Handle other dict types
                        parts.append(str(item))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        else:
            return f"Name: {self.tool_name}\nOutput: {self.tool_output}"


class TextPrompt(BaseModel):
    """Internal representation of user-generated text prompt."""

    text: str
    type: Literal["text_prompt"] = "text_prompt"


class ImageBlock(BaseModel):
    type: Literal["image"] = "image"
    source: dict[str, Any]

    def __str__(self) -> str:
        source = self.source
        media_type = source.get("media_type", "image/unknown")
        source_type = source.get("type", "unknown")

        if source_type == "base64":
            return f"[Image attached - {media_type}]"
        else:
            # Handle other source types like URLs
            return f"[Image attached - {media_type}, source: {source_type}]"


class TextResult(BaseModel):
    """Internal representation of LLM-generated text result."""

    text: str
    type: Literal["text_result"] = "text_result"
    id: Optional[str] = None

class RedactedThinkingBlock(BaseModel):
    """Internal representation of redacted thinking block."""
    
    data: str
    type: Literal["redacted_thinking"] = "redacted_thinking"


class ThinkingBlock(BaseModel):
    """Internal representation of thinking block."""
    
    signature: str
    thinking: str
    type: Literal["thinking"] = "thinking"




AssistantContentBlock = (
    TextResult | ToolCall | RedactedThinkingBlock | ThinkingBlock
)
UserContentBlock = TextPrompt | ToolFormattedResult | ImageBlock

class SummaryBlock(BaseModel):
    data: List[UserContentBlock | AssistantContentBlock]
    type: Literal["llm-compact", "llm-summarizing"] = "llm-compact"

GeneralContentBlock = UserContentBlock | AssistantContentBlock | SummaryBlock
LLMMessages = list[list[GeneralContentBlock]]


class LLMClient(ABC):
    """A client for LLM APIs for the use in agents."""

    @abstractmethod
    def generate(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        tools: list[ToolParam] = [],
        tool_choice: dict[str, str] | None = None,
        thinking_tokens: int | None = None,
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        """Generate responses.

        Args:
            messages: A list of messages.
            max_tokens: The maximum number of tokens to generate.
            system_prompt: A system prompt.
            temperature: The temperature.
            tools: A list of tools.
            tool_choice: A tool choice.

        Returns:
            A generated response.
        """
        raise NotImplementedError


def recursively_remove_invoke_tag(obj):
    """Recursively remove the </invoke> tag from a dictionary or list."""
    result_obj = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            result_obj[key] = recursively_remove_invoke_tag(value)
    elif isinstance(obj, list):
        result_obj = [recursively_remove_invoke_tag(item) for item in obj]
    elif isinstance(obj, str):
        if "</invoke>" in obj:
            result_obj = json.loads(obj.replace("</invoke>", ""))
        else:
            result_obj = obj
    else:
        result_obj = obj
    return result_obj