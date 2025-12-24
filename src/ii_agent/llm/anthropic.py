import asyncio
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


from ii_agent.core.config.llm_config import LLMConfig
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
    ThinkingBlock,
    RedactedThinkingBlock,
)


class AnthropicDirectClient(LLMClient):
    """Use Anthropic models via first party API."""

    def __init__(self, llm_config: LLMConfig):
        """Initialize the Anthropic first party client."""
        super().__init__(llm_config)
        api_key = (
            llm_config.api_key.get_secret_value() if llm_config.api_key else None
        )

        self._vertex_client = None
        self._vertex_async_client = None
        self._direct_client = None
        self._direct_async_client = None
        self._direct_model_name = self.model_name.replace("@", "-")

        if (llm_config.vertex_project_id is not None) and (
            llm_config.vertex_region is not None
        ):
            self._vertex_client = anthropic.AnthropicVertex(
                project_id=llm_config.vertex_project_id,
                region=llm_config.vertex_region,
                timeout=60 * 5,
                max_retries=1,
            )
            self._vertex_async_client = anthropic.AsyncAnthropicVertex(
                project_id=llm_config.vertex_project_id,
                region=llm_config.vertex_region,
                timeout=60 * 5,
                max_retries=1,
            )
            self.client = self._vertex_client
            self.async_client = self._vertex_async_client

            # Support custom base_url for Anthropic-compatible APIs (e.g., Minimax)
            client_kwargs = {
                "api_key": api_key,
                "max_retries": 3,
                "timeout": 60 * 5,
            }
            if llm_config.base_url:
                client_kwargs["base_url"] = llm_config.base_url

            self._direct_client = anthropic.Anthropic(**client_kwargs)
            self._direct_async_client = anthropic.AsyncAnthropic(**client_kwargs)
        else:
            # Support custom base_url for Anthropic-compatible APIs (e.g., Minimax)
            client_kwargs = {
                "api_key": api_key,
                "max_retries": 3,
                "timeout": 60 * 5,
            }
            if llm_config.base_url:
                client_kwargs["base_url"] = llm_config.base_url

            direct_client = anthropic.Anthropic(**client_kwargs)
            direct_async_client = anthropic.AsyncAnthropic(**client_kwargs)
            self.client = direct_client
            self.async_client = direct_async_client
            self._direct_client = direct_client
            self._direct_async_client = direct_async_client
            self.model_name = self._direct_model_name
        self.max_retries = llm_config.max_retries
        self._vertex_fallback_retries = 3

        # Build beta headers
        beta_headers = []
        if (
            "claude-opus-4" in self.model_name or "claude-sonnet-4" in self.model_name
        ):  # Use Interleaved Thinking for Sonnet 4 and Opus 4
            beta_headers.append("interleaved-thinking-2025-05-14")

        # Enable 1M context window if configured
        if llm_config.enable_extended_context:
            beta_headers.append("context-1m-2025-08-07")

        self.headers = {"anthropic-beta": ",".join(beta_headers)} if beta_headers else None
        self.thinking_tokens = llm_config.thinking_tokens

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
                elif str(type(message)) == str(RedactedThinkingBlock):
                    message = cast(RedactedThinkingBlock, message)
                    # Convert to Anthropic format for API call
                    message_content = AnthropicRedactedThinkingBlock(
                        type="redacted_thinking", data=message.data
                    )
                elif str(type(message)) == str(ThinkingBlock):
                    message = cast(ThinkingBlock, message)
                    # Convert to Anthropic format for API call
                    message_content = AnthropicThinkingBlock(
                        type="thinking",
                        thinking=message.thinking,
                        signature=message.signature,
                    )
                else:
                    print(
                        f"Unknown message type: {type(message)}, expected one of {str(TextPrompt)}, {str(TextResult)}, {str(ToolCall)}, {str(ToolFormattedResult)}"
                    )
                    raise ValueError(
                        f"Unknown message type: {type(message)}, expected one of {str(TextPrompt)}, {str(TextResult)}, {str(ToolCall)}, {str(ToolFormattedResult)}"
                    )
                message_content_list.append(message_content)

            # Anthropic supports up to 4 cache breakpoints, so we put them on the last 4 messages.
            if idx >= len(messages) - 4:
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

        attempt = 0
        max_attempts = self.max_retries
        use_vertex = self._vertex_client is not None
        vertex_failures = 0

        while attempt < max_attempts:
            client_to_use = (
                self._vertex_client
                if use_vertex and self._vertex_client is not None
                else self._direct_client or self.client
            )
            model_to_use = (
                self.model_name
                if client_to_use is self._vertex_client
                else self._direct_model_name
            )
            try:
                response = client_to_use.messages.create(  # type: ignore
                    max_tokens=max_tokens,
                    messages=anthropic_messages,
                    model=model_to_use,
                    temperature=temperature,
                    system=system_prompt or Anthropic_NOT_GIVEN,
                    tool_choice=tool_choice_param,  # type: ignore
                    tools=tool_params,
                    extra_headers=self.headers,
                    extra_body=extra_body,
                )
                break
            except Exception as e:
                attempt += 1
                fallback_triggered = False
                if (
                    use_vertex
                    and self._direct_client is not None
                    and (
                        isinstance(e, AnthropicOverloadedError)
                        or isinstance(e, AnthropicRateLimitError)
                    )
                ):
                    vertex_failures += 1
                    if vertex_failures >= self._vertex_fallback_retries:
                        use_vertex = False
                        fallback_triggered = True
                        if attempt >= max_attempts:
                            max_attempts += 1
                        print(
                            "Vertex client overloaded; falling back to Anthropic direct client"
                        )
                if fallback_triggered:
                    continue
                if attempt >= max_attempts:
                    print(f"Failed Anthropic request after {attempt} retries")
                    raise
                print(f"Retrying LLM request: {attempt}/{max_attempts}")
                # Sleep 12-18 seconds with jitter to avoid thundering herd.
                time.sleep(15 * random.uniform(0.8, 1.2))

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
                # Convert Anthropic response back to internal format
                message = cast(AnthropicRedactedThinkingBlock, message)
                internal_messages.append(RedactedThinkingBlock(data=message.data))
            elif str(type(message)) == str(AnthropicThinkingBlock):
                # Convert Anthropic response back to internal format
                message = cast(AnthropicThinkingBlock, message)
                internal_messages.append(
                    ThinkingBlock(
                        thinking=message.thinking, signature=message.signature
                    )
                )
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

        cache_creation_input_tokens = getattr(
            response.usage, "cache_creation_input_tokens", 0
        )
        cache_read_input_tokens = getattr(response.usage, "cache_read_input_tokens", 0)

        input_tokens = (
            response.usage.input_tokens
            + cache_creation_input_tokens
            + cache_read_input_tokens
        )
        output_tokens = response.usage.output_tokens
        message_metadata = {
            "raw_response": response,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
        }

        return internal_messages, message_metadata

    async def agenerate(
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
                elif str(type(message)) == str(RedactedThinkingBlock):
                    message = cast(RedactedThinkingBlock, message)
                    # Convert to Anthropic format for API call
                    message_content = AnthropicRedactedThinkingBlock(
                        type="redacted_thinking", data=message.data
                    )
                elif str(type(message)) == str(ThinkingBlock):
                    message = cast(ThinkingBlock, message)
                    # Convert to Anthropic format for API call
                    message_content = AnthropicThinkingBlock(
                        type="thinking",
                        thinking=message.thinking,
                        signature=message.signature,
                    )
                else:
                    print(
                        f"Unknown message type: {type(message)}, expected one of {str(TextPrompt)}, {str(TextResult)}, {str(ToolCall)}, {str(ToolFormattedResult)}"
                    )
                    raise ValueError(
                        f"Unknown message type: {type(message)}, expected one of {str(TextPrompt)}, {str(TextResult)}, {str(ToolCall)}, {str(ToolFormattedResult)}"
                    )
                message_content_list.append(message_content)

            # Anthropic supports up to 4 cache breakpoints, so we put them on the last 4 messages.
            if idx >= len(messages) - 4:
                if isinstance(message_content_list[-1], dict):
                    if "type" in message_content_list[-1] and message_content_list[-1]["type"] != "thinking":
                        message_content_list[-1]["cache_control"] = {"type": "ephemeral"}
                else:
                    if not isinstance(message_content_list[-1], (AnthropicThinkingBlock, AnthropicRedactedThinkingBlock)):
                        message_content_list[-1].cache_control = {"type": "ephemeral"}

            anthropic_messages.append(
                {
                    "role": role,
                    "content": message_content_list,
                }
            )

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

        attempt = 0
        max_attempts = self.max_retries
        use_vertex = self._vertex_async_client is not None
        vertex_failures = 0

        while attempt < max_attempts:
            client_to_use = (
                self._vertex_async_client
                if use_vertex and self._vertex_async_client is not None
                else self._direct_async_client or self.async_client
            )
            model_to_use = (
                self.model_name
                if client_to_use is self._vertex_async_client
                else self._direct_model_name
            )
            try:
                response = await client_to_use.messages.create(  # type: ignore[attr-defined]
                    max_tokens=max_tokens,
                    messages=anthropic_messages,
                    model=model_to_use,
                    temperature=temperature,
                    system=system_prompt or Anthropic_NOT_GIVEN,
                    tool_choice=tool_choice_param,  # type: ignore[arg-type]
                    tools=tool_params,
                    extra_headers=self.headers,
                    extra_body=extra_body,
                )
                break
            except Exception as e:
                attempt += 1
                fallback_triggered = False
                if (
                    use_vertex
                    and self._direct_async_client is not None
                    and (
                        isinstance(e, AnthropicOverloadedError)
                        or isinstance(e, AnthropicRateLimitError)
                    )
                ):
                    vertex_failures += 1
                    if vertex_failures >= self._vertex_fallback_retries:
                        use_vertex = False
                        fallback_triggered = True
                        if attempt >= max_attempts:
                            max_attempts += 1
                        print(
                            "Vertex client overloaded; falling back to Anthropic direct client"
                        )
                if fallback_triggered:
                    continue
                if attempt >= max_attempts:
                    print(f"Failed Anthropic request after {attempt} retries")
                    raise
                print(f"Retrying LLM request: {attempt}/{max_attempts}")
                # Sleep 12-18 seconds with jitter to avoid thundering herd.
                await asyncio.sleep(15 * random.uniform(0.8, 1.2))

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
                # Convert Anthropic response back to internal format
                message = cast(AnthropicRedactedThinkingBlock, message)
                internal_messages.append(RedactedThinkingBlock(data=message.data))
            elif str(type(message)) == str(AnthropicThinkingBlock):
                # Convert Anthropic response back to internal format
                message = cast(AnthropicThinkingBlock, message)
                internal_messages.append(
                    ThinkingBlock(
                        thinking=message.thinking, signature=message.signature
                    )
                )
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

        cache_creation_input_tokens = getattr(
            response.usage, "cache_creation_input_tokens", 0
        )
        cache_read_input_tokens = getattr(response.usage, "cache_read_input_tokens", 0)
        input_tokens = (
            response.usage.input_tokens
            + cache_creation_input_tokens
            + cache_read_input_tokens
        )
        output_tokens = response.usage.output_tokens
        message_metadata = {
            "raw_response": response,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
        }

        return internal_messages, message_metadata
