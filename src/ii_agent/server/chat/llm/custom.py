from datetime import datetime
import logging
from copy import deepcopy
from string import Template
from typing import Any, AsyncIterator, Dict, List, Optional

from litellm import acompletion

from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.metrics.models import TokenUsage
from ii_agent.server.chat.models import (
    MessageRole,
    ToolCall,
    FinishReason,
    TextContent,
    BinaryContent,
    ImageURLContent,
    TextResultContent,
    JsonResultContent,
    ExecutionDeniedContent,
    ErrorTextContent,
    ErrorJsonContent,
    ArrayResultContent,
    TextContentPart,
    ImageDataContentPart,
    FileDataContentPart,
    RunResponseEvent,
    RunResponseOutput,
    EventType,
)
from ii_agent.server.chat.base import (
    LLMClient,
)
from ii_agent.server.chat.models import Message

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """
You are II-Chat, a helpful and intelligent AI assistant developed by II-Agent team.
Knowledge cutoff: 2024-06
Current date: $current_date

Image input capabilities: Enabled
Personality: v2
You're an insightful, encouraging assistant who combines meticulous clarity with genuine enthusiasm and gentle humor.
Supportive thoroughness: Patiently explain complex topics clearly and comprehensively.
Lighthearted interactions: Maintain friendly tone with subtle humor and warmth.
Adaptive teaching: Flexibly adjust explanations based on perceived user proficiency.
Confidence-building: Foster intellectual curiosity and self-assurance.

Do not end with opt-in questions or hedging closers. Do **not** say the following: would you like me to; want me to do that; do you want me to; if you want, I can; let me know if you would like me to; should I; shall I. Ask at most one necessary clarifying question at the start, not the end. If the next step is obvious, do it. Example of bad: I can write playful examples. would you like me to? Example of good: Here are three playful examples:..

# Response presentation
- Open with a concise highlight sentence that previews the value of the answer.
- Use expressive Markdown headings (e.g., ## Overview**) to organize major sections.
- Emphasize critical phrases with bold text and tasteful inline emoji for energy and clarity.
- When outlining options or feature comparisons, include a compact Markdown table to summarize key takeaways before diving into details.
- Mix short paragraphs with bulleted or numbered lists so information stays scannable.
- Separate major sections with horizontal rules (`---`) when it improves readability.
- Format code or JSON snippets in fenced code blocks with appropriate language hints.
- Close with a brief action-oriented takeaway or next step instead of generic sign-offs.

# Tools

## web

Use the `web` tool to access up-to-date information from the web or when responding to the user requires information about their location. Some examples of when to use the `web` tool include:

- **Local Information**: Use the `web` tool to respond to questions that require information about the user's location, such as the weather, local businesses, or events.
- **Freshness**: If up-to-date information on a topic could potentially change or enhance the answer, call the `web` tool any time you would otherwise refuse to answer a question because your knowledge might be out of date.
- **Niche Information**: If the answer would benefit from detailed information not widely known or understood (which might be found on the internet), such as details about a small neighborhood, a less well-known company, or arcane regulations, use web sources directly rather than relying on the distilled knowledge from pretraining.
- **Accuracy**: If the cost of a small mistake or outdated information is high (e.g., using an outdated version of a software library or not knowing the date of the next game for a sports team), then use the `web` tool.

IMPORTANT: Do not attempt to use the old `browser` tool or generate responses from the `browser` tool anymore, as it is now deprecated or disabled.

The `web` tool has the following commands:

- `web_search()`: Issues a new query to a search engine and outputs the response.
- `web_visit(url: str, prompt: str = None)`: Opens the given URL and extracts the content. If prompt is provided, it will extract the content based on the prompt.
- `image_search(query: str)`: Searches the internet for images related to the query.
### When to use search
- When the user asks for up-to-date facts (news, weather, events).
- When they request niche or local details not likely to be in your training data.
- When correctness is critical and even a small inaccuracy matters.
- When freshness is important, rate using QDF (Query Deserves Freshness) on a scale of 0–5:
  - 0: Historic/unimportant to be fresh.
  - 1: Relevant if within last 18 months.
  - 2: Within last 6 months.
  - 3: Within last 90 days.
  - 4: Within last 60 days.
  - 5: Latest from this month.

QDF_MAP:
  0: historic
  1: 18_months
  2: 6_months
  3: 90_days
  4: 60_days
  5: 30_days

### When to use web_visit
- When the user provides a direct link and asks to open or summarize its contents.
- When referencing an authoritative page already known.

### When to use image_search
- When the user asks for images related to the query.
- When you need to demonstrate the image to the user.

### When to use file_search
Use to search through user's uploaded files and documents:
- Answer questions about uploaded content (PDFs, documents, reports)
- Find specific facts, figures, data, or citations from files
- Compare or synthesize information across multiple uploaded documents
- Verify prior analyses, computations, or recommendations from uploaded files
- Extract relevant sections when user asks about their uploaded knowledge base

Skip when:
- Question can be answered with general knowledge
- Fresh computation or real-time data is needed (use code_interpreter or web instead)

### Examples:
- "What's the score in the Yankees game right now?" → `web_search()` with QDF=5.
- "When is the next solar eclipse visible in Europe?" → `web_search()` with QDF=2.
- "Show me this article" with a link → `web_visit(url)`.
- "Show me an image of a cat" → `image_search(query="cat")`.
- "Summaries the latest assessment uploaded" -> file_search(query="Summaries of the latest security assessment uploaded from the")
- "Show me the Q4 performance" from uploaded pdf -> file_search(query="List the metrics referenced in the Q4 performance review document")

# Closing Instructions

You must follow all personality, tone, and formatting requirements stated above in every interaction.

- **Personality**: Maintain the friendly, encouraging, and clear style described at the top of this prompt. Where appropriate, include gentle humor and warmth without detracting from clarity or accuracy.
- **Clarity**: Explanations should be thorough but easy to follow. Use headings, lists, and formatting when it improves readability.
- **Boundaries**: Do not produce disallowed content. This includes copyrighted song lyrics or any other material explicitly restricted in these instructions.
- **Tool usage**: Only use the tools provided and strictly adhere to their usage guidelines. If the criteria for a tool are not met, do not invoke it.
- **Accuracy and trust**: For high-stakes topics (e.g., medical, legal, financial), ensure that information is accurate, cite credible sources, and provide appropriate disclaimers.
- **Freshness**: When the user asks for time-sensitive information, prefer the `web` tool with the correct QDF rating to ensure the information is recent and reliable.

When uncertain, follow these priorities:
1. **User safety and policy compliance** come first.
2. **Accuracy and clarity** come next.
3. **Tone and helpfulness** should be preserved throughout.

"""

template = Template(SYSTEM_PROMPT_TEMPLATE)


class CustomProvider(LLMClient):
    """Provider for other models that use openai compatible API. Use litellm"""

    def __init__(self, llm_config: LLMConfig):
        dummy_llm_config = deepcopy(llm_config)
        if llm_config.api_type == APITypes.GEMINI:
            dummy_llm_config.model = f"gemini/{dummy_llm_config.model}"
            dummy_llm_config.api_type = APITypes.CUSTOM
        elif llm_config.api_type == APITypes.NVIDIA:
            dummy_llm_config.base_url = "https://integrate.api.nvidia.com/v1"
            dummy_llm_config.model = f"nvidia/{dummy_llm_config.model}"
            dummy_llm_config.api_type = APITypes.CUSTOM
        self.llm_config = dummy_llm_config
        self.model_name = dummy_llm_config.model
        self.base_url = dummy_llm_config.base_url

        self.api_key = (
            dummy_llm_config.api_key.get_secret_value()
            if dummy_llm_config.api_key
            else None
        )

        if "/" in self.model_name:
            self.provider_prefix = self.model_name.split("/")[0]
        else:
            self.provider_prefix = "custom"

        logger.info(
            f"Initialized CustomProvider for model: {self.model_name} "
            f"(provider: {self.provider_prefix})"
        )

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert Message objects to OpenAI-compatible format for litellm."""
        converted_messages = []
        for message in messages:
            role = message.role.value

            if role == MessageRole.TOOL.value:
                for tool_result in message.tool_results():
                    output = tool_result.output
                    content_value = None

                    # Handle different output types using isinstance
                    if isinstance(output, (TextResultContent, ErrorTextContent)):
                        content_value = output.value
                    elif isinstance(output, ExecutionDeniedContent):
                        content_value = output.reason or "Tool execution denied."
                    elif isinstance(output, (JsonResultContent, ErrorJsonContent)):
                        import json

                        content_value = json.dumps(output.value)
                    elif isinstance(output, ArrayResultContent):
                        # For OpenAI-compatible APIs, convert array content to string
                        parts = []
                        for item in output.value:
                            if isinstance(item, TextContentPart):
                                parts.append(item.text)
                            elif isinstance(item, ImageDataContentPart):
                                parts.append(f"[Image: {item.media_type}]")
                            elif isinstance(item, FileDataContentPart):
                                parts.append(f"[File: {item.filename or 'data'}]")
                            else:
                                logger.warning(
                                    f"Unsupported tool content part type: {item.type}"
                                )
                        content_value = "\n".join(parts)
                    else:
                        # Fallback for unknown types
                        logger.warning(
                            f"Unknown tool result output type: {type(output)}"
                        )
                        content_value = str(output)

                    converted_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_result.tool_call_id,
                            "content": content_value,
                        }
                    )
            else:
                content_parts = []
                text_content = None

                for part in message.parts:
                    if isinstance(part, TextContent):
                        text_content = part.text
                    elif isinstance(part, BinaryContent):
                        content_parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": part.to_base64("openai")},
                            }
                        )
                    elif isinstance(part, ImageURLContent):
                        content_parts.append(
                            {"type": "image_url", "image_url": {"url": part.url}}
                        )
                    elif isinstance(part, ToolCall):
                        pass

                if text_content:
                    if content_parts:
                        content_parts.insert(0, {"type": "text", "text": text_content})
                    else:
                        content_parts = text_content

                tool_calls_in_message = message.tool_calls()
                msg_dict = {"role": role, "content": content_parts or ""}

                if tool_calls_in_message and role == MessageRole.ASSISTANT.value:
                    msg_dict["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.input},
                        }
                        for tc in tool_calls_in_message
                    ]

                converted_messages.append(msg_dict)

        return converted_messages

    def _convert_tools(
        self, tools: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[Dict[str, Any]]]:
        """Convert tools to OpenAI-compatible format if needed."""
        if not tools:
            return None

        converted_tools = []
        for tool in tools:
            if "function" in tool:
                converted_tools.append(tool)
            elif "name" in tool:
                converted_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.get("name"),
                            "description": tool.get("description"),
                            "parameters": tool.get("parameters"),
                        },
                    }
                )
            else:
                converted_tools.append(tool)

        return converted_tools

    async def send(
        self, messages: List[Message], tools: Optional[List[Any]] = None
    ) -> RunResponseOutput:
        """Send messages and get complete response using litellm."""
        litellm_messages = self._convert_messages(messages)
        litellm_tools = self._convert_tools(tools)

        # Prepend system prompt if not already present
        if not litellm_messages or litellm_messages[0].get("role") != "system":
            litellm_messages.insert(
                0,
                {
                    "role": "system",
                    "content": template.substitute(
                        current_date=datetime.now().strftime("%Y-%m-%d")
                    ),
                },
            )

        params = {
            "model": self.model_name,
            "messages": litellm_messages,
            "stream": False,
        }

        if self.api_key:
            params["api_key"] = self.api_key
        if self.base_url:
            params["base_url"] = self.base_url
        if litellm_tools:
            params["tools"] = litellm_tools
        if self.llm_config.temperature is not None:
            params["temperature"] = self.llm_config.temperature

        try:
            response = await acompletion(**params)

            choice = response.choices[0]
            message = choice.message

            content_parts = []

            # Add text content if present
            if hasattr(message, "content") and message.content:
                content_parts.append(TextContent(text=message.content))

            # Add tool calls if present
            if hasattr(message, "tool_calls") and message.tool_calls:
                for tc in message.tool_calls:
                    content_parts.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            input=tc.function.arguments,
                            finished=True,
                        )
                    )

            usage = TokenUsage()
            if hasattr(response, "usage") and response.usage:
                usage = TokenUsage(
                    prompt_tokens=getattr(response.usage, "prompt_tokens", 0),
                    completion_tokens=getattr(response.usage, "completion_tokens", 0),
                    cache_write_tokens=0,
                    cache_read_tokens=0,
                    model_name=self.llm_config.model,
                )

            finish_reason_map = {
                "stop": FinishReason.END_TURN,
                "length": FinishReason.MAX_TOKENS,
                "tool_calls": FinishReason.TOOL_USE,
                "function_call": FinishReason.TOOL_USE,
                "content_filter": FinishReason.ERROR,
            }

            finish_reason = finish_reason_map.get(
                choice.finish_reason, FinishReason.UNKNOWN
            )

            # Determine finish reason from content parts
            has_tool_calls = any(isinstance(part, ToolCall) for part in content_parts)
            if has_tool_calls and finish_reason == FinishReason.END_TURN:
                finish_reason = FinishReason.TOOL_USE

            return RunResponseOutput(
                content=content_parts,
                usage=usage,
                finish_reason=finish_reason,
            )

        except Exception as e:
            logger.error(f"Error in CustomProvider.send: {e}")
            raise

    async def stream(
        self, messages: List[Message], tools: Optional[List[Any]] = None, **kwargs
    ) -> AsyncIterator[RunResponseEvent]:
        """Stream response events using litellm."""
        litellm_messages = self._convert_messages(messages)
        litellm_tools = self._convert_tools(tools)

        # Prepend system prompt if not already present
        if not litellm_messages or litellm_messages[0].get("role") != "system":
            litellm_messages.insert(
                0,
                {
                    "role": "system",
                    "content": template.substitute(
                        current_date=datetime.now().strftime("%Y-%m-%d")
                    ),
                },
            )

        params = {
            "model": self.model_name,
            "messages": litellm_messages,
            "stream": True,
        }

        if self.api_key:
            params["api_key"] = self.api_key
        if self.base_url:
            params["base_url"] = self.base_url
            params["custom_llm_provider"] = "openai"
        if litellm_tools:
            params["tools"] = litellm_tools
        if self.llm_config.temperature is not None:
            params["temperature"] = self.llm_config.temperature

        try:
            stream = await acompletion(**params)

            content_started = False
            tool_call_tracking = {}
            content_parts = []
            accumulated_text = ""

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                if hasattr(delta, "content") and delta.content:
                    if not content_started:
                        yield RunResponseEvent(type=EventType.CONTENT_START)
                        content_started = True
                    accumulated_text += delta.content
                    yield RunResponseEvent(
                        type=EventType.CONTENT_DELTA, content=delta.content
                    )

                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        tc_index = tc_delta.index

                        if tc_index not in tool_call_tracking:
                            tool_call_id = (
                                tc_delta.id
                                if hasattr(tc_delta, "id")
                                else f"call_{tc_index}"
                            )
                            tool_call_name = ""
                            if hasattr(tc_delta, "function") and hasattr(
                                tc_delta.function, "name"
                            ):
                                tool_call_name = tc_delta.function.name or ""

                            tool_call_tracking[tc_index] = {
                                "id": tool_call_id,
                                "name": tool_call_name,
                                "arguments": "",
                            }

                            yield RunResponseEvent(
                                type=EventType.TOOL_USE_START,
                                tool_call=ToolCall(
                                    id=tool_call_id,
                                    name=tool_call_name,
                                    input="",
                                    finished=False,
                                ),
                            )

                        if (
                            hasattr(tc_delta, "function")
                            and hasattr(tc_delta.function, "name")
                            and tc_delta.function.name
                        ):
                            tool_call_tracking[tc_index]["name"] = (
                                tc_delta.function.name
                            )

                        if (
                            hasattr(tc_delta, "function")
                            and hasattr(tc_delta.function, "arguments")
                            and tc_delta.function.arguments
                        ):
                            args_delta = tc_delta.function.arguments
                            tool_call_tracking[tc_index]["arguments"] += args_delta

                            yield RunResponseEvent(
                                type=EventType.TOOL_USE_DELTA,
                                tool_call=ToolCall(
                                    id=tool_call_tracking[tc_index]["id"],
                                    name=tool_call_tracking[tc_index]["name"],
                                    input=args_delta,
                                    finished=False,
                                ),
                            )

                finish_reason = getattr(chunk.choices[0], "finish_reason", None)
                if finish_reason:
                    logger.debug(f"Chunk finish_reason: {finish_reason}")

                    if content_started:
                        yield RunResponseEvent(type=EventType.CONTENT_STOP)

                    # Build content_parts from accumulated data
                    if accumulated_text:
                        content_parts.append(TextContent(text=accumulated_text))

                    for tc_data in tool_call_tracking.values():
                        tool_call = ToolCall(
                            id=tc_data["id"],
                            name=tc_data["name"],
                            input=tc_data["arguments"],
                            finished=True,
                        )
                        content_parts.append(tool_call)
                        yield RunResponseEvent(
                            type=EventType.TOOL_USE_STOP,
                            tool_call=tool_call,
                        )

                    usage = TokenUsage()
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage = TokenUsage(
                            prompt_tokens=getattr(chunk.usage, "prompt_tokens", 0),
                            completion_tokens=getattr(
                                chunk.usage, "completion_tokens", 0
                            ),
                            cache_write_tokens=0,
                            cache_read_tokens=0,
                            model_name=self.llm_config.model,
                        )

                    finish_reason_map = {
                        "stop": FinishReason.END_TURN,
                        "length": FinishReason.MAX_TOKENS,
                        "tool_calls": FinishReason.TOOL_USE,
                        "function_call": FinishReason.TOOL_USE,
                        "content_filter": FinishReason.ERROR,
                    }

                    final_finish_reason = finish_reason_map.get(
                        finish_reason, FinishReason.UNKNOWN
                    )

                    # Determine finish reason from content parts
                    has_tool_calls = any(
                        isinstance(part, ToolCall) for part in content_parts
                    )
                    if has_tool_calls and final_finish_reason == FinishReason.END_TURN:
                        final_finish_reason = FinishReason.TOOL_USE

                    yield RunResponseEvent(
                        type=EventType.COMPLETE,
                        response=RunResponseOutput(
                            content=content_parts,
                            usage=usage,
                            finish_reason=final_finish_reason,
                        ),
                    )

        except Exception as e:
            logger.error(f"Error in CustomProvider.stream: {e}")
            yield RunResponseEvent(
                type=EventType.ERROR,
                error=e,
            )

    def model(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {
            "id": self.model_name,
            "name": self.model_name,
            "provider": self.provider_prefix,
        }
