import os

import random
import time
from typing import Any, Tuple, cast
import anthropic
from anthropic import (
    NOT_GIVEN as Anthropic_NOT_GIVEN,
)
from anthropic import (
    APIConnectionError as AnthropicAPIConnectionError,
)
from anthropic import (
    InternalServerError as AnthropicInternalServerError,
)
from anthropic import (
    RateLimitError as AnthropicRateLimitError,
)
from anthropic._exceptions import (
    OverloadedError as AnthropicOverloadedError,  # pyright: ignore[reportPrivateImportUsage]
)
from anthropic.types import (
    TextBlock as AnthropicTextBlock,
    ThinkingBlock as AnthropicThinkingBlock,
    RedactedThinkingBlock as AnthropicRedactedThinkingBlock,
    ImageBlockParam as AnthropicImageBlockParam,
)
from anthropic.types import ToolParam as AnthropicToolParam
from anthropic.types import (
    ToolResultBlockParam as AnthropicToolResultBlockParam,
)
from anthropic.types import (
    ToolUseBlock as AnthropicToolUseBlock,
)
from anthropic.types.message_create_params import (
    ToolChoiceToolChoiceAny,
    ToolChoiceToolChoiceAuto,
    ToolChoiceToolChoiceTool,
)


from ii_agent.llm.base import (
    LLMClient,
    AssistantContentBlock,
    ToolParam,
    TextPrompt,
    ToolCall,
    TextResult,
    LLMMessages,
    ToolFormattedResult,
    UserContentBlock,
    recursively_remove_invoke_tag,
    ImageBlock,
)
from ii_agent.utils.constants import DEFAULT_MODEL


class AnthropicDirectClient(LLMClient):
    """Use Anthropic models via first party API."""

    def __init__(
        self,
        model_name=DEFAULT_MODEL,
        max_retries=2,
        use_caching=True,
        thinking_tokens: int = 0,
        project_id: None | str = None,
        region: None | str = None,
    ):
        """Initialize the Anthropic first party client."""
        # Disable retries since we are handling retries ourselves.
        if (project_id is not None) and (region is not None):
            self.client = anthropic.AnthropicVertex(
                project_id=project_id,
                region=region,
                timeout=60 * 5,
                max_retries=1,
            )
        else:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            self.client = anthropic.Anthropic(
                api_key=api_key, max_retries=1, timeout=60 * 5
            )
            model_name = model_name.replace(
                "@", "-"
            )  # Quick fix for Anthropic Vertex API
        self.model_name = model_name
        self.max_retries = max_retries
        self.use_caching = use_caching
        if "claude-opus-4" in model_name or "claude-sonnet-4" in model_name: #Use Interleaved Thinking for Sonnet 4 and Opus 4
            self.headers = {"anthropic-beta": "interleaved-thinking-2025-05-14,prompt-caching-2024-07-31"}
        else:
            self.headers = {"anthropic-beta": "prompt-caching-2024-07-31"}
        self.thinking_tokens = thinking_tokens

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

        # Turn GeneralContentBlock into Anthropic message format
        anthropic_messages = []
        for idx, message_list in enumerate(messages):
            role = (
                "user" if isinstance(message_list[0], UserContentBlock) else "assistant"
            )
            message_content_list = []
            for message in message_list:
                # Check string type to avoid import issues particularly with reloads.
                if str(type(message)) == str(TextPrompt):
                    message = cast(TextPrompt, message)
                    message_content = AnthropicTextBlock(
                        type="text",
                        text=message.text,
                    )
                elif str(type(message)) == str(ImageBlock):
                    message = cast(ImageBlock, message)
                    message_content = AnthropicImageBlockParam(
                        type="image",
                        source=message.source,
                    )
                elif str(type(message)) == str(TextResult):
                    message = cast(TextResult, message)
                    message_content = AnthropicTextBlock(
                        type="text",
                        text=message.text,
                    )
                elif str(type(message)) == str(ToolCall):
                    message = cast(ToolCall, message)
                    message_content = AnthropicToolUseBlock(
                        type="tool_use",
                        id=message.tool_call_id,
                        name=message.tool_name,
                        input=message.tool_input,
                    )
                elif str(type(message)) == str(ToolFormattedResult):
                    message = cast(ToolFormattedResult, message)
                    message_content = AnthropicToolResultBlockParam(
                        type="tool_result",
                        tool_use_id=message.tool_call_id,
                        content=message.tool_output,
                    )
                elif str(type(message)) == str(AnthropicRedactedThinkingBlock):
                    message = cast(AnthropicRedactedThinkingBlock, message)
                    message_content = message
                elif str(type(message)) == str(AnthropicThinkingBlock):
                    message = cast(AnthropicThinkingBlock, message)
                    message_content = message
                else:
                    print(
                        f"Unknown message type: {type(message)}, expected one of {str(TextPrompt)}, {str(TextResult)}, {str(ToolCall)}, {str(ToolFormattedResult)}"
                    )
                    raise ValueError(
                        f"Unknown message type: {type(message)}, expected one of {str(TextPrompt)}, {str(TextResult)}, {str(ToolCall)}, {str(ToolFormattedResult)}"
                    )
                message_content_list.append(message_content)

            # Anthropic supports up to 4 cache breakpoints, so we put them on the last 4 messages.
            if self.use_caching and idx >= len(messages) - 4:
                if isinstance(message_content_list[-1], dict):
                    message_content_list[-1]["cache_control"] = {"type": "ephemeral"}
                else:
                    message_content_list[-1].cache_control = {"type": "ephemeral"}

            anthropic_messages.append(
                {
                    "role": role,
                    "content": message_content_list,
                }
            )

        if self.use_caching:
            extra_headers = self.headers
        else:
            extra_headers = None

        # Turn tool_choice into Anthropic tool_choice format
        if tool_choice is None:
            tool_choice_param = Anthropic_NOT_GIVEN
        elif tool_choice["type"] == "any":
            tool_choice_param = ToolChoiceToolChoiceAny(type="any")
        elif tool_choice["type"] == "auto":
            tool_choice_param = ToolChoiceToolChoiceAuto(type="auto")
        elif tool_choice["type"] == "tool":
            tool_choice_param = ToolChoiceToolChoiceTool(
                type="tool", name=tool_choice["name"]
            )
        else:
            raise ValueError(f"Unknown tool_choice type: {tool_choice['type']}")

        if len(tools) == 0:
            tool_params = Anthropic_NOT_GIVEN
        else:
            tool_params = [
                AnthropicToolParam(
                    input_schema=tool.input_schema,
                    name=tool.name,
                    description=tool.description,
                )
                for tool in tools
            ]

        response = None

        if thinking_tokens is None:
            thinking_tokens = self.thinking_tokens
        if thinking_tokens and thinking_tokens > 0:
            extra_body = {
                "thinking": {"type": "enabled", "budget_tokens": thinking_tokens}
            }
            temperature = 1
        else:
            extra_body = None

        for retry in range(self.max_retries):
            try:
                response = self.client.messages.create(  # type: ignore
                    max_tokens=max_tokens,
                    messages=anthropic_messages,
                    model=self.model_name,
                    temperature=temperature,
                    system=system_prompt or Anthropic_NOT_GIVEN,
                    tool_choice=tool_choice_param,  # type: ignore
                    tools=tool_params,
                    extra_headers=extra_headers,
                    extra_body=extra_body,
                )
                break
            except (
                AnthropicAPIConnectionError,
                AnthropicInternalServerError,
                AnthropicRateLimitError,
                AnthropicOverloadedError,
            ) as e:
                if retry == self.max_retries - 1:
                    print(f"Failed Anthropic request after {retry + 1} retries")
                    raise e
                else:
                    print(f"Retrying LLM request: {retry + 1}/{self.max_retries}")
                    # Sleep 12-18 seconds with jitter to avoid thundering herd.
                    time.sleep(15 * random.uniform(0.8, 1.2))
            except Exception as e:
                raise e

        # Convert messages back to internal format
        internal_messages = []
        assert response is not None
        for message in response.content:
            if "</invoke>" in str(message):
                warning_msg = "\n".join(
                    ["!" * 80, "WARNING: Unexpected 'invoke' in message", "!" * 80]
                )
                print(warning_msg)

            if str(type(message)) == str(AnthropicTextBlock):
                message = cast(AnthropicTextBlock, message)
                internal_messages.append(TextResult(text=message.text))
            elif str(type(message)) == str(AnthropicRedactedThinkingBlock):
                internal_messages.append(message)
            elif str(type(message)) == str(AnthropicThinkingBlock):
                message = cast(AnthropicThinkingBlock, message)
                internal_messages.append(message)
            elif str(type(message)) == str(AnthropicToolUseBlock):
                message = cast(AnthropicToolUseBlock, message)
                internal_messages.append(
                    ToolCall(
                        tool_call_id=message.id,
                        tool_name=message.name,
                        tool_input=recursively_remove_invoke_tag(message.input),
                    )
                )
            else:
                raise ValueError(f"Unknown message type: {type(message)}")

        message_metadata = {
            "raw_response": response,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_creation_input_tokens": getattr(
                response.usage, "cache_creation_input_tokens", -1
            ),
            "cache_read_input_tokens": getattr(
                response.usage, "cache_read_input_tokens", -1
            ),
        }

        return internal_messages, message_metadata
