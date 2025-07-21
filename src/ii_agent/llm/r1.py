"""LLM client for Anthropic models."""

import random
import time
from typing import Any, Tuple, cast
import openai
from openai import AsyncOpenAI
import logging
from ii_agent.llm.parsers.r1_parser import (
    parse_code_blobs,
    evaluate_block,
    format_tool_call,
    format_tool_result,
)
from datetime import datetime, timezone


from openai import (
    APIConnectionError as OpenAI_APIConnectionError,
)
from openai import (
    InternalServerError as OpenAI_InternalServerError,
)
from openai import (
    RateLimitError as OpenAI_RateLimitError,
)
from openai._types import (
    NOT_GIVEN as OpenAI_NOT_GIVEN,  # pyright: ignore[reportPrivateImportUsage]
)

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.prompts.researcher_system_prompt import AgentConfig, ConfigConstants
from ii_agent.llm.base import (
    LLMClient,
    AssistantContentBlock,
    LLMMessages,
    TextPrompt,
    TextResult,
    ToolCall,
    ToolFormattedResult,
    ToolParam,
    ToolResult,
    ThinkingBlock,
)

logger = logging.getLogger(__name__)


class R1DirectClient(LLMClient):
    """Use OpenAI models via first party API."""

    def __init__(self, llm_config: LLMConfig):
        """Initialize the OpenAI first party client."""
        base_url = llm_config.base_url
        import ipdb

        ipdb.set_trace()
        self.client = openai.OpenAI(
            api_key=llm_config.api_key.get_secret_value()
            if llm_config.api_key
            else None,
            base_url=base_url,
            max_retries=llm_config.max_retries,
        )
        self.async_client = AsyncOpenAI(
            api_key=llm_config.api_key.get_secret_value()
            if llm_config.api_key
            else None,
            base_url=base_url,
            max_retries=llm_config.max_retries,
        )
        self.llm_config = llm_config
        self.model_name = llm_config.model
        self.max_retries = llm_config.max_retries
        self.cot_model = llm_config.cot_model

    def generate(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        tools: list[ToolParam] | None = None,
        temperature: float = 0.0,
        thinking_tokens: int | None = None,
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        """Generate responses.

        Args:
            messages: A list of messages.
            system_prompt: A system prompt.
            max_tokens: The maximum number of tokens to generate.
            temperature: The temperature.

        Returns:
            A generated response.
        """
        openai_messages = self._prepare_messages(messages, system_prompt, tools)
        openai_max_tokens, openai_temperature, extra_body = (
            self._prepare_request_params(max_tokens, temperature)
        )

        response = None
        for retry in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=openai_messages,
                    max_tokens=openai_max_tokens,
                    extra_body=extra_body,
                    stop=self.llm_config.stop_sequence,
                )
                break
            except (
                OpenAI_APIConnectionError,
                OpenAI_InternalServerError,
                OpenAI_RateLimitError,
            ) as e:
                if retry == self.max_retries - 1:
                    print(f"Failed OpenAI request after {retry + 1} retries")
                    raise e
                else:
                    print(f"Retrying OpenAI request: {retry + 1}/{self.max_retries}")
                    # Sleep 8-12 seconds with jitter to avoid thundering herd.
                    time.sleep(10 * random.uniform(0.8, 1.2))

        # Convert messages back to internal format
        internal_messages = []
        assert response is not None
        openai_response_messages = response.choices
        if len(openai_response_messages) > 1:
            raise ValueError("Only one message supported for OpenAI")
        openai_response_message = openai_response_messages[0].message
        content = openai_response_message.content

        # Handle text content
        if not content:
            raise ValueError("Content should be present")

        # Handle text content
        if content:
            internal_messages.append(TextResult(text=content))

        # Extract actions from model response
        result = []
        for model_response in internal_messages:
            result.extend(self.parse_model_response(model_response.text))

        assert response.usage is not None
        message_metadata = {
            "raw_response": response,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        }

        return result, message_metadata

    async def generate_stream(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        tools: list[ToolParam] | None = None,
        temperature: float = 0.0,
        thinking_tokens: int | None = None,
    ) -> list[AssistantContentBlock]:
        """Generate streaming responses for debugging.

        Args:
            messages: A list of messages.
            system_prompt: A system prompt.
            max_tokens: The maximum number of tokens to generate.
            temperature: The temperature.
            thinking_tokens: Max thinking tokens for CoT models.

        Yields:
            Chunks of the response as they are generated.
        """
        openai_messages = self._prepare_messages(messages, system_prompt, tools)
        openai_max_tokens, openai_temperature, extra_body = (
            self._prepare_request_params(max_tokens, temperature)
        )

        try:
            stream = await self.async_client.chat.completions.create(
                model=self.model_name,
                messages=openai_messages,
                max_tokens=openai_max_tokens,
                # extra_body=extra_body,
                stop=self.llm_config.stop_sequence,
                stream=True,
            )

            collected_content = ""
            async for chunk in stream:
                if chunk.choices and (chunk.choices[0].delta.content):
                    content = chunk.choices[0].delta.content
                    collected_content += content

            return self.parse_model_response(collected_content)

        except (
            OpenAI_APIConnectionError,
            OpenAI_InternalServerError,
            OpenAI_RateLimitError,
        ) as e:
            logger.error(f"Streaming request failed: {e}")
            raise e

    def _prepare_messages(
        self,
        messages: LLMMessages,
        system_prompt: str | None = None,
        tools: list[ToolParam] | None = None,
    ) -> list[dict[str, Any]]:
        """Prepare messages for OpenAI API format.

        Args:
            messages: Internal message format
            system_prompt: System prompt to apply
            tools: Available tools for compression

        Returns:
            List of messages in OpenAI format
        """
        openai_messages = []
        system_prompt_applied = False

        # Add system prompt for non-COT models
        if system_prompt is not None and not self.cot_model:
            system_message = {"role": "system", "content": system_prompt}
            openai_messages.append(system_message)
            system_prompt_applied = True

        # Process messages into temporary format
        temp_messages = []

        for message_list in messages:
            # Determine the role for this message turn
            role = "user" if isinstance(message_list[0], TextPrompt) else "assistant"

            if role == "user":
                temp_messages.append(
                    self._process_user_message(
                        message_list, system_prompt, system_prompt_applied
                    )
                )
                if self.cot_model and system_prompt and not system_prompt_applied:
                    system_prompt_applied = True

            elif role == "assistant":
                temp_messages.append(self._process_assistant_message(message_list))

        # Compress adjacent assistant messages
        if temp_messages[-1]["role"] == "user":
            temp_messages.append(
                {"role": "assistant", "content": [TextResult(text="")]}
            )
        openai_messages.extend(
            self._compress_adjacent_assistant_messages(temp_messages, tools)
        )

        # Handle COT fallback for system prompt
        if self.cot_model and system_prompt and not system_prompt_applied:
            logger.warning(
                "COT mode: System prompt provided but no initial user message to prepend to. Adding as a separate user message."
            )
            openai_messages.insert(
                0,
                {"role": "user", "content": [{"type": "text", "text": system_prompt}]},
            )

        return openai_messages

    def _process_user_message(
        self, message_list: list, system_prompt: str | None, system_prompt_applied: bool
    ) -> dict:
        """Process user messages into OpenAI format."""
        user_content = []
        user_text = ""

        for internal_message in message_list:
            if str(type(internal_message)) == str(TextPrompt):
                internal_message = cast(TextPrompt, internal_message)
                user_text = internal_message.text

                # Apply system prompt for COT models if needed
                if self.cot_model and system_prompt and not system_prompt_applied:
                    user_text = f"{system_prompt}\n\n{user_text}"

        # Add user text message if present
        if user_text:
            user_content.append({"type": "text", "text": user_text})

        return {"role": "user", "content": user_content}

    def _process_assistant_message(self, message_list: list) -> dict:
        """Process assistant messages into OpenAI format."""
        assistant_content = []

        for internal_message in message_list:
            if isinstance(
                internal_message,
                (TextResult, ToolCall, ToolResult, ToolFormattedResult),
            ):
                assistant_content.append(internal_message)
            if isinstance(internal_message, ThinkingBlock):
                assistant_content.append(internal_message)

        # Create assistant message
        assistant_message = {"role": "assistant"}
        if assistant_content:
            assistant_message["content"] = assistant_content

        return assistant_message

    def _compress_adjacent_assistant_messages(
        self, temp_messages: list[dict], tools: list[ToolParam] | None
    ) -> list[dict]:
        """Compress adjacent assistant messages and return final message list."""
        openai_messages = []
        i = 0
        prev_user_msg = None
        while i < len(temp_messages):
            current_msg = temp_messages[i]

            if current_msg["role"] == "user":
                prev_user_msg = (
                    current_msg["content"][0]["text"]
                    if current_msg["content"]
                    else None
                )
                openai_messages.append(current_msg)
                i += 1

            elif current_msg["role"] == "assistant":
                # Collect adjacent assistant messages
                adjacent_assistant_msgs = [current_msg]
                j = i + 1
                while (
                    j < len(temp_messages) and temp_messages[j]["role"] == "assistant"
                ):
                    adjacent_assistant_msgs.append(temp_messages[j])
                    j += 1

                # Compress if we have multiple adjacent assistant messages
                if len(adjacent_assistant_msgs) >= 1:
                    compressed_msg = self._compress(
                        prev_user_msg=prev_user_msg,
                        assistant_messages=adjacent_assistant_msgs,
                        tools=tools or [],
                    )
                    openai_messages.append(compressed_msg)
                else:
                    openai_messages.append(current_msg)

                i = j  # Skip the compressed messages
            else:
                openai_messages.append(current_msg)
                i += 1

        return openai_messages

    def _prepare_request_params(
        self, max_tokens: int, temperature: float = 0.0
    ) -> tuple[int | type(OpenAI_NOT_GIVEN), float | type(OpenAI_NOT_GIVEN), dict]:
        """Prepare request parameters based on model type."""
        extra_body = {}
        openai_max_tokens = max_tokens
        openai_temperature = temperature

        if self.cot_model:
            extra_body["max_completion_tokens"] = max_tokens
            openai_max_tokens = OpenAI_NOT_GIVEN
            openai_temperature = OpenAI_NOT_GIVEN

        return openai_max_tokens, openai_temperature, extra_body

    def _compress(
        self,
        prev_user_msg: str,
        assistant_messages: list[AssistantContentBlock],
        tools: list[ToolParam],
    ) -> dict:
        """Compress a list of adjacent assistant messages into a single message."""
        if not assistant_messages:
            return {"role": "assistant", "content": ""}

        combined_text = []

        for msg in assistant_messages:
            if msg.get("content"):
                for content_item in msg["content"]:
                    if isinstance(content_item, ThinkingBlock):
                        combined_text.append(content_item.thinking)
                    elif isinstance(content_item, TextResult):
                        combined_text.append(content_item.text)
                    elif isinstance(content_item, ToolCall):
                        combined_text.append(format_tool_call(content_item))
                    elif isinstance(content_item, ToolResult) or isinstance(
                        content_item, ToolFormattedResult
                    ):
                        combined_text.append(format_tool_result(content_item))
                    else:
                        raise ValueError(
                            f"Unsupported content type: {type(content_item)}"
                        )

        instruction = AgentConfig().instructions.format(
            current_date=datetime.now(timezone.utc).isoformat(),
            available_tools="\n".join(
                [
                    f"- {tool.name}: {tool.description} with input schema: {tool.input_schema}"
                    for tool in tools
                ]
            ),
        )

        compressed_message = {"role": "assistant", "prefix": True}
        if combined_text:
            content = (
                f"{ConfigConstants.THINK_TAG_OPEN} So, the user's question is: '{prev_user_msg}' "
                + "\n".join(combined_text)
                + f"\n{instruction if instruction else ''}"
            )
            if isinstance(assistant_messages[-1].get("content"), ThinkingBlock) and (
                not content.strip().endswith(ConfigConstants.THINK_TAG_CLOSE)
            ):
                content += ConfigConstants.THINK_TAG_CLOSE
            compressed_message["content"] = content
        else:
            compressed_message["content"] = (
                f"{ConfigConstants.THINK_TAG_OPEN} {instruction if instruction else ''} \nSo, the user's question is: '{prev_user_msg}' \n"
                + "\n".join(combined_text)
            )

        return compressed_message

    def parse_model_response(self, content: str) -> list[AssistantContentBlock]:
        """Parse the model response."""
        raw = content
        _, action_string = parse_code_blobs(raw)
        result = []

        if action_string:
            try:
                action = evaluate_block(action_string)
                result.append(
                    ThinkingBlock(
                        signature="",
                        thinking=raw.replace(ConfigConstants.THINK_TAG_CLOSE, ""),
                    )
                )
                result.append(action)
            except ValueError:
                result.append(TextResult(text=action_string))
        else:
            if ConfigConstants.THINK_TAG_CLOSE in raw:
                split_result = raw.rsplit(ConfigConstants.THINK_TAG_CLOSE, 1)
                thoughts, text_result = split_result[0], split_result[1]
                result.append(ThinkingBlock(signature="", thinking=thoughts))
                result.append(TextResult(text=text_result))

        return result
