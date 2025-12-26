"""LLM client for OpenAI models."""

import asyncio
import json
import random
import time
from abc import ABC, abstractmethod
from typing import Any, Tuple, cast, Union
import openai
import logging

from openai import (
    APIConnectionError as OpenAI_APIConnectionError,
    InternalServerError as OpenAI_InternalServerError,
    RateLimitError as OpenAI_RateLimitError,
)
from openai._types import NOT_GIVEN as OpenAI_NOT_GIVEN

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.llm.base import (
    LLMClient,
    ImageBlock,
    ThinkingBlock,
    AssistantContentBlock,
    LLMMessages,
    ToolParam,
    TextPrompt,
    ToolCall,
    TextResult,
    ToolFormattedResult,
)

from transformers import AutoTokenizer

logger = logging.getLogger(__name__)

# Constants
RETRY_DELAY_MIN = 8.0
RETRY_DELAY_MAX = 12.0
RETRY_BASE_DELAY = 10.0


class BaseOpenAIClient(LLMClient, ABC):
    """Base class for OpenAI clients with common initialization logic."""

    def __init__(self, llm_config: LLMConfig):
        """Initialize the OpenAI client with common configuration."""
        super().__init__(llm_config)
        self.client = self._create_client(llm_config)
        self.async_client = self._create_async_client(llm_config)
        self.max_retries = llm_config.max_retries
        self.reasoning_effort = getattr(llm_config, "reasoning_effort", None)
        self.config = llm_config

    def _create_async_client(
        self, llm_config: LLMConfig
    ) -> Union[openai.AsyncOpenAI, openai.AsyncAzureOpenAI]:
        """Create OpenAI client based on configuration."""
        api_key = llm_config.api_key.get_secret_value() if llm_config.api_key else None

        if llm_config.azure_endpoint is not None:
            return openai.AsyncAzureOpenAI(
                api_key=api_key,
                azure_endpoint=llm_config.azure_endpoint,
                api_version=llm_config.azure_api_version,
                max_retries=llm_config.max_retries,
            )
        else:
            base_url = llm_config.base_url or "https://api.openai.com/v1"
            return openai.AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                max_retries=llm_config.max_retries,
            )

    def _create_client(
        self, llm_config: LLMConfig
    ) -> Union[openai.OpenAI, openai.AzureOpenAI]:
        """Create OpenAI client based on configuration."""
        api_key = llm_config.api_key.get_secret_value() if llm_config.api_key else None

        if llm_config.azure_endpoint is not None:
            return openai.AzureOpenAI(
                api_key=api_key,
                azure_endpoint=llm_config.azure_endpoint,
                api_version=llm_config.azure_api_version,
                max_retries=llm_config.max_retries,
            )
        else:
            base_url = llm_config.base_url or "https://api.openai.com/v1"
            return openai.OpenAI(
                api_key=api_key,
                base_url=base_url,
                max_retries=llm_config.max_retries,
            )

    async def _ahandle_retries(self, operation_func, *args, **kwargs):
        """Handle retry logic for API calls."""
        for retry in range(self.max_retries):
            try:
                return await operation_func(*args, **kwargs)
            except (
                OpenAI_APIConnectionError,
                OpenAI_InternalServerError,
                OpenAI_RateLimitError,
            ) as e:
                if retry == self.max_retries - 1:
                    logger.error(f"Failed OpenAI request after {retry + 1} retries")
                    raise e
                else:
                    logger.info(
                        f"Retrying OpenAI request: {retry + 1}/{self.max_retries}"
                    )
                    await asyncio.sleep(RETRY_BASE_DELAY * random.uniform(0.8, 1.2))

    def _handle_retries(self, operation_func, *args, **kwargs):
        """Handle retry logic for API calls."""
        for retry in range(self.max_retries):
            try:
                return operation_func(*args, **kwargs)
            except (
                OpenAI_APIConnectionError,
                OpenAI_InternalServerError,
                OpenAI_RateLimitError,
            ) as e:
                if retry == self.max_retries - 1:
                    logger.error(f"Failed OpenAI request after {retry + 1} retries")
                    raise e
                else:
                    logger.info(
                        f"Retrying OpenAI request: {retry + 1}/{self.max_retries}"
                    )
                    time.sleep(RETRY_BASE_DELAY * random.uniform(0.8, 1.2))

    def _process_tool_choice(self, tool_choice: dict[str, str] | None):
        """Convert tool choice to OpenAI format."""
        if tool_choice is None:
            return "auto"
        elif tool_choice["type"] == "any":
            return "required"
        elif tool_choice["type"] == "auto":
            return "auto"
        elif tool_choice["type"] == "tool":
            return {
                "type": "function",
                "function": {"name": tool_choice["name"]},
            }
        elif tool_choice["type"] == "none":
            return OpenAI_NOT_GIVEN
        else:
            raise ValueError(f"Unknown tool_choice type: {tool_choice['type']}")

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
        stop_sequence: list[str] | None = None,
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        """Generate responses - implemented by subclasses."""
        pass


class OpenAIResponsesClient(BaseOpenAIClient):
    """Use OpenAI models via Responses API."""

    def _process_message(
        self, internal_message, tool_call_ids_sent: set, tool_result_ids_sent: set
    ) -> dict[str, Any] | None:
        """Process a single internal message and return OpenAI format or None to skip."""
        if isinstance(internal_message, TextPrompt):
            return {
                "role": "user",
                "content": [{"type": "input_text", "text": internal_message.text}],
            }

        elif isinstance(internal_message, TextResult):
            return {
                "role": "assistant",
                "id": internal_message.id,
                "content": [{"type": "output_text", "text": internal_message.text}],
            }

        elif isinstance(internal_message, ImageBlock):
            return {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": f"data:{internal_message.source['media_type']};base64,{internal_message.source['data']}",
                        "detail": "high"
                    }
                ],
            }

        elif isinstance(internal_message, ToolCall):
            try:
                arguments_str = json.dumps(internal_message.tool_input)
            except TypeError as e:
                logger.error(
                    f"Failed to serialize tool_input to JSON string for tool '{internal_message.tool_name}': {internal_message.tool_input}. Error: {str(e)}"
                )
                raise ValueError(
                    f"Cannot serialize tool arguments for {internal_message.tool_name}: {str(e)}"
                ) from e

            tool_call_ids_sent.add(internal_message.tool_call_id)
            if internal_message.is_custom:
                return {
                    "type": "custom_tool_call",
                    "call_id": internal_message.tool_call_id,
                    "id": internal_message.tool_id,
                    "name": internal_message.tool_name,
                    "input": internal_message.tool_input.get(
                        "input", ""
                    ),  # NOTE: custom tool input is always a dict with "input" key
                }

            return {
                "type": "function_call",
                "call_id": internal_message.tool_call_id,
                "id": internal_message.tool_id,
                "name": internal_message.tool_name,
                "arguments": arguments_str,
            }

        elif isinstance(internal_message, ToolFormattedResult):
            if internal_message.tool_call_id not in tool_call_ids_sent:
                logger.warning(
                    f"Skipping orphaned tool result with call_id {internal_message.tool_call_id} "
                    f"(no matching tool call found in conversation)"
                )
                return None

            tool_result_ids_sent.add(internal_message.tool_call_id)
            return self._process_tool_result(internal_message)

        elif isinstance(internal_message, ThinkingBlock):
            return {
                "type": "reasoning",
                "id": internal_message.signature,
                "summary": [
                    {"type": "summary_text", "text": internal_message.thinking}
                ],
            }

        else:
            raise ValueError(f"Unknown message type: {type(internal_message)}")

    def _process_tool_result(self, tool_result: ToolFormattedResult) -> dict[str, Any]:
        """Process tool result with image handling."""
        if not tool_result.is_custom:
            openai_message = {
                "type": "function_call_output",
                "call_id": tool_result.tool_call_id,
                "output": tool_result.tool_output,
            }
        else:
            assert isinstance(tool_result.tool_output, str), (
                "Custom tool output must be a string"
            )
            openai_message = {
                "type": "custom_tool_call_output",
                "call_id": tool_result.tool_call_id,
                "output": tool_result.tool_output,
            }

        # Handle image blocks in tool output
        if isinstance(tool_result.tool_output, list):
            image_blocks = []
            for block in tool_result.tool_output:
                if isinstance(block, dict) and block.get("type") == "image":
                    image_blocks.append(
                        {
                            "type": "input_image",
                            "image_url": f"data:{block['source']['media_type']};base64,{block['source']['data']}",
                        }
                    )

            if image_blocks:
                # Store image blocks separately and mark as executed
                openai_message["output"] = "Executed tool successfully"
                self._pending_image_blocks = image_blocks

        return openai_message

    async def agenerate(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        tools: list[ToolParam] = [],
        tool_choice: dict[str, str] | None = None,
        thinking_tokens: int | None = None,
        prefix: bool = False,
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        """Generate responses.

        Args:
            messages: A list of messages.
            system_prompt: A system prompt.
            max_tokens: The maximum number of tokens to generate.
            temperature: The temperature.
            tools: A list of tools.
            tool_choice: A tool choice.

        Returns:
            A generated response.
        """

        # Convert messages to input format for Responses API
        input_messages: list[dict[str, Any]] = []
        if system_prompt:
            input_messages.append(
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                }
            )

        # Track tool calls and their results for debugging
        tool_call_ids_sent = set()
        tool_result_ids_sent = set()
        self._pending_image_blocks = None

        for message_list in messages:
            if not message_list:
                continue

            for internal_message in message_list:
                processed_message = self._process_message(
                    internal_message, tool_call_ids_sent, tool_result_ids_sent
                )
                if processed_message is not None:
                    input_messages.append(processed_message)

                    # Handle pending image blocks from tool results
                    if (
                        hasattr(self, "_pending_image_blocks")
                        and self._pending_image_blocks
                    ):
                        input_messages.append(
                            {
                                "role": "user",
                                "content": self._pending_image_blocks,
                            }
                        )
                        self._pending_image_blocks = None

        # Log any tool call/result mismatches for debugging
        orphaned_calls = tool_call_ids_sent - tool_result_ids_sent
        if orphaned_calls:
            logger.debug(f"Tool calls without results: {orphaned_calls}")

        tool_choice_param = self._process_tool_choice(tool_choice)

        # Turn tools into Responses API tool format
        openai_tools = [
            (
                {
                    "type": "custom",
                    "name": tool.name,
                    "description": tool.description,
                    "format": tool.input_schema,
                }
                if tool.type == "custom"
                else {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                }
            )
            for tool in tools
        ]

        async def _create_response():
            params = {
                "model": self.model_name,
                "input": input_messages,
                "store": True,
            }

            if openai_tools:
                params["tools"] = openai_tools

            if tool_choice_param != OpenAI_NOT_GIVEN:
                params["tool_choice"] = tool_choice_param
            if len(openai_tools)  == 0:
                # For summary/compact, we don't provide any tools
                params["tool_choice"] = None
            # Reasoning configuration
            reasoning_effort = self.reasoning_effort or "high"
            params["reasoning"] = {"effort": reasoning_effort, "summary": "auto"}

            try:
                return await self.async_client.responses.create(**params)
            except Exception as e:
                logger.error(f"Error creating response: {e}")
                raise

        response = await self._ahandle_retries(_create_response)
        assert response is not None

        # Responses API has a different structure - extract content from the response object
        outputs = []
        for item in response.output:
            if item.type == "reasoning":
                reasoning_id = item.id
                reasoning_summaries = "\n".join([si.text for si in item.summary])
                outputs.append(
                    ThinkingBlock(
                        signature=reasoning_id,
                        thinking=reasoning_summaries,
                    )
                )
            elif item.type == "function_call":
                tool_call_id = item.call_id
                tool_id = item.id
                tool_name = item.name
                arguments = item.arguments
                if isinstance(arguments, dict):
                    tool_input = arguments
                elif isinstance(arguments, str):
                    tool_input = json.loads(arguments)
                else:
                    continue
                outputs.append(
                    ToolCall(
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                        tool_input=tool_input,
                        tool_id=tool_id,
                    )
                )
            elif item.type == "custom_tool_call":
                tool_call_id = item.call_id
                tool_id = item.id
                tool_name = item.name
                tool_input = {
                    "input": item.input,
                }  # NOTE: custom tool input is always a dict with "input" key
                outputs.append(
                    ToolCall(
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                        tool_input=tool_input,
                        tool_id=tool_id,
                        is_custom=True,
                    )
                )

            elif item.type == "message":
                text = item.content[0].text
                id = item.id
                outputs.append(TextResult(text=text, id=id))
            else:
                outputs.append(TextResult(text=""))

        message_metadata = {
            "raw_response": response,
            "input_tokens": response.usage.input_tokens,
            "cache_read_input_tokens": response.usage.input_tokens_details.cached_tokens,
            "output_tokens": response.usage.total_tokens - response.usage.input_tokens,
            "total_tokens": response.usage.total_tokens,
        }

        self.previous_response_id = None  # for future supports

        return outputs, message_metadata

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
            system_prompt: A system prompt.
            max_tokens: The maximum number of tokens to generate.
            temperature: The temperature.
            tools: A list of tools.
            tool_choice: A tool choice.

        Returns:
            A generated response.
        """

        # Convert messages to input format for Responses API
        input_messages: list[dict[str, Any]] = []
        if system_prompt:
            input_messages.append(
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                }
            )

        # Track tool calls and their results for debugging
        tool_call_ids_sent = set()
        tool_result_ids_sent = set()
        self._pending_image_blocks = None

        for message_list in messages:
            if not message_list:
                continue

            for internal_message in message_list:
                processed_message = self._process_message(
                    internal_message, tool_call_ids_sent, tool_result_ids_sent
                )
                if processed_message is not None:
                    input_messages.append(processed_message)

                    # Handle pending image blocks from tool results
                    if (
                        hasattr(self, "_pending_image_blocks")
                        and self._pending_image_blocks
                    ):
                        input_messages.append(
                            {
                                "role": "user",
                                "content": self._pending_image_blocks,
                            }
                        )
                        self._pending_image_blocks = None

        # Log any tool call/result mismatches for debugging
        orphaned_calls = tool_call_ids_sent - tool_result_ids_sent
        if orphaned_calls:
            logger.debug(f"Tool calls without results: {orphaned_calls}")

        tool_choice_param = self._process_tool_choice(tool_choice)

        # Turn tools into Responses API tool format
        openai_tools = [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
            for tool in tools
        ]

        def _create_response():
            params = {
                "model": self.model_name,
                "input": input_messages,
                "store": True,
            }

            if openai_tools:
                params["tools"] = openai_tools

            if tool_choice_param != OpenAI_NOT_GIVEN:
                params["tool_choice"] = tool_choice_param

            # Reasoning configuration
            reasoning_effort = self.reasoning_effort or "high"
            params["reasoning"] = {"effort": reasoning_effort, "summary": "auto"}

            try:
                return self.client.responses.create(**params)
            except Exception as e:
                logger.error(f"Error creating response: {e}")
                raise

        response = self._handle_retries(_create_response)
        assert response is not None

        # Responses API has a different structure - extract content from the response object
        outputs = []
        for item in response.output:
            if item.type == "reasoning":
                reasoning_id = item.id
                reasoning_summaries = "\n".join([si.text for si in item.summary])
                outputs.append(
                    ThinkingBlock(
                        signature=reasoning_id,
                        thinking=reasoning_summaries,
                    )
                )
            elif item.type == "function_call":
                tool_call_id = item.call_id
                tool_id = item.id
                tool_name = item.name
                arguments = item.arguments
                if isinstance(arguments, dict):
                    tool_input = arguments
                elif isinstance(arguments, str):
                    tool_input = json.loads(arguments)
                else:
                    continue
                outputs.append(
                    ToolCall(
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                        tool_input=tool_input,
                        tool_id=tool_id,
                    )
                )
            elif item.type == "message":
                text = item.content[0].text
                id = item.id
                outputs.append(TextResult(text=text, id=id))
            else:
                outputs.append(TextResult(text=""))

        message_metadata = {
            "raw_response": response,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.total_tokens,
        }

        self.previous_response_id = None  # for future supports

        return outputs, message_metadata


class OpenAIDirectClient(BaseOpenAIClient):
    """Use OpenAI models via Chat Completions API."""

    def _process_message(self, internal_message) -> dict[str, Any] | None:
        """Process a single internal message for Chat API and return (message, system_prompt_applied)."""
        if isinstance(internal_message, TextPrompt):
            final_text = internal_message.text
            return {"role": "user", "content": final_text}

        elif isinstance(internal_message, TextResult):
            return {"role": "assistant", "content": internal_message.text}
        # TODO: update openai thinking format
        elif isinstance(internal_message, ThinkingBlock):
            return {
                "role": "assistant",
                "content": internal_message.thinking,
            }
        elif isinstance(internal_message, ImageBlock):
            content = {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{internal_message.source['media_type']};base64,{internal_message.source['data']}"
                },
            }
            return {"role": "user", "content": [content]}

        elif isinstance(internal_message, ToolCall):
            try:
                arguments_str = json.dumps(internal_message.tool_input)
            except TypeError as e:
                logger.error(
                    f"Failed to serialize tool_input to JSON string for tool '{internal_message.tool_name}': {internal_message.tool_input}. Error: {str(e)}"
                )
                raise ValueError(
                    f"Cannot serialize tool arguments for {internal_message.tool_name}: {str(e)}"
                ) from e

            tool_call_payload = {
                "type": "function",
                "id": internal_message.tool_call_id,
                "function": {
                    "name": internal_message.tool_name,
                    "arguments": arguments_str,
                },
            }
            return {"role": "assistant", "tool_calls": [tool_call_payload]}

        elif isinstance(internal_message, ToolFormattedResult):
            content = self._process_tool_result(internal_message)
            return {
                "role": "tool",
                "tool_call_id": internal_message.tool_call_id,
                "content": content,
            }
        else:
            print(internal_message)
            raise ValueError(f"Unknown message type: {type(internal_message)}")

    def _process_tool_result(self, tool_result: ToolFormattedResult):
        """Process tool result content for Chat API."""
        content = tool_result.tool_output
        if isinstance(tool_result.tool_output, list):
            processed_content = []
            for block in tool_result.tool_output:
                if isinstance(block, dict) and block.get("type") == "image":
                    processed_content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{block['source']['media_type']};base64,{block['source']['data']}"
                            },
                        }
                    )
                else:
                    processed_content.append(block)
            content = processed_content
        return content

    async def agenerate(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        tools: list[ToolParam] = [],
        tool_choice: dict[str, str] | None = None,
        thinking_tokens: int | None = None,
        stop_sequence: list[str] | None = None,
        prefix: bool = False,
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        """Generate responses.

        Args:
            messages: A list of messages.
            system_prompt: A system prompt.
            max_tokens: The maximum number of tokens to generate.
            temperature: The temperature.
            tools: A list of tools.
            tool_choice: A tool choice.

        Returns:
            A generated response.
        """
        # Cap max_tokens to model's maximum output tokens
        model_max_output = self.config.get_max_output_tokens()
        if max_tokens > model_max_output:
            logger.warning(
                f"Requested max_tokens ({max_tokens}) exceeds model's limit ({model_max_output}). "
                f"Capping to {model_max_output} for model {self.model_name}"
            )
            max_tokens = model_max_output

        openai_messages = []

        if system_prompt is not None:
            openai_messages.append({"role": "system", "content": system_prompt})

        for idx, message_list in enumerate(messages):
            turn_message = None
            # We have three part:
            # Thinking content, response content and tool-call contents for one-turn
            # {"role", ..., "conent": str, "reasoning_content": str, tool_calls: list}
            for internal_message in message_list:
                processed_message = self._process_message(internal_message)
                if turn_message is None:
                    turn_message = processed_message
                    # for thinking content we need to move the content -> reasoning content
                    if isinstance(internal_message, ThinkingBlock):
                        turn_message['reasoning_content'] = turn_message['content']
                        turn_message['content'] = ""
                else:
                    if processed_message.get("tool_calls", None):
                        if "tool_calls" not in turn_message:
                            turn_message['tool_calls'] = []
                        turn_message['tool_calls'].extend(processed_message["tool_calls"])
                        # We extend the tool_call -> tool_calls (for multiple tool-calls)
                    else:
                        if isinstance(internal_message, ThinkingBlock):
                            if "reasoning_content" not in turn_message:
                                turn_message['reasoning_content'] = ""
                                space = ""
                            else:
                                space = "\n"
                            turn_message['reasoning_content'] = turn_message['reasoning_content'] + space + processed_message['content']
                        else:
                            if 'content' not in turn_message:
                                turn_message['content'] = ''
                                space = ""
                            else:
                                space = "\n"
                            turn_message['content'] = turn_message['content'] + space + processed_message['content']

            openai_messages.append(turn_message)

        tool_choice_param = self._process_tool_choice(tool_choice)

        if (
            openai_messages
            and openai_messages[-1].get("role") == "assistant"
            and prefix
        ):
            openai_messages[-1]["prefix"] = prefix

        openai_tools = []
        for tool in tools:
            tool_def = {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
            tool_def["parameters"]["strict"] = True
            openai_tools.append(
                {
                    "type": "function",
                    "function": tool_def,
                }
            )
        if len(openai_tools) == 0:
            tool_choice_param=None

        async def _create_completion():
            response = await self.async_client.chat.completions.create(
                model=self.model_name,
                messages=openai_messages,
                tools=openai_tools if openai_tools else OpenAI_NOT_GIVEN,
                tool_choice=tool_choice_param,
                max_completion_tokens=max_tokens,
                stop=stop_sequence,
            )
            assert response is not None, "OpenAI response is None"
            return response

        response = await self._ahandle_retries(_create_completion)

        # Convert messages back to internal format
        internal_messages = []
        assert response is not None

        if len(response.choices) > 1:
            raise ValueError("Only one message supported for OpenAI")

        openai_response_message = response.choices[0].message
        tool_calls = openai_response_message.tool_calls
        content = openai_response_message.content
        if hasattr(openai_response_message, "reasoning_content"):
            reasoning = openai_response_message.reasoning_content
        else:
            reasoning = None

        if reasoning:
            internal_messages.append(
                ThinkingBlock(thinking=reasoning, signature="id_thinking")
            )  # currently chat.

        if content:
            internal_messages.append(TextResult(text=content))

        if tool_calls:
            internal_messages.extend(self._process_tool_calls(tool_calls, tools))

        if not content and not tool_calls:
            logger.warning(
                f"Response has no content or tool_calls: {openai_response_message}"
            )
            internal_messages.append(TextResult(text=""))

        assert response.usage is not None
        message_metadata = {
            "raw_response": response,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.total_tokens - response.usage.prompt_tokens,
        }

        return internal_messages, message_metadata

    def generate(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        tools: list[ToolParam] = [],
        tool_choice: dict[str, str] | None = None,
        thinking_tokens: int | None = None,
        stop_sequence: list[str] | None = None,
        prefix: bool = False,
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        """Generate responses.

        Args:
            messages: A list of messages.
            system_prompt: A system prompt.
            max_tokens: The maximum number of tokens to generate.
            temperature: The temperature.
            tools: A list of tools.
            tool_choice: A tool choice.

        Returns:
            A generated response.
        """

        openai_messages = []
        if system_prompt is not None:
            openai_messages.append({"role": "system", "content": system_prompt})

        for idx, message_list in enumerate(messages):
            for internal_message in message_list:
                processed_message = self._process_message(internal_message)
                if processed_message:
                    openai_messages.append(processed_message)

        tool_choice_param = self._process_tool_choice(tool_choice)

        openai_tools = []

        if (
            openai_messages
            and openai_messages[-1].get("role") == "assistant"
            and prefix
        ):
            openai_messages[-1]["prefix"] = prefix

        for tool in tools:
            tool_def = {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
            tool_def["parameters"]["strict"] = True
            openai_tools.append(
                {
                    "type": "function",
                    "function": tool_def,
                }
            )
        if len(openai_tools) == 0:
            tool_choice_param = None

        def _create_completion():
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=openai_messages,
                tools=openai_tools if openai_tools else OpenAI_NOT_GIVEN,
                tool_choice=tool_choice_param,
                max_completion_tokens=max_tokens,
                stop=stop_sequence,
            )
            assert response is not None, "OpenAI response is None"
            return response

        response = self._handle_retries(_create_completion)

        # Convert messages back to internal format
        internal_messages = []
        assert response is not None

        if len(response.choices) > 1:
            raise ValueError("Only one message supported for OpenAI")

        openai_response_message = response.choices[0].message
        tool_calls = openai_response_message.tool_calls
        content = openai_response_message.content

        if content:
            internal_messages.append(TextResult(text=content))

        if tool_calls:
            try:
                internal_messages.extend(self._process_tool_calls(tool_calls, tools))
            # TODO: custom exception handling for parsing tool calls
            except Exception as e:
                logger.error(f"Error parsing tool calls: {e}")
                internal_messages.append(
                    TextResult(
                        text="Cannot parse the text response to tool calls, retry with correct format"
                    )
                )

        if not content and not tool_calls:
            logger.warning(
                f"Response has no content or tool_calls: {openai_response_message}"
            )
            internal_messages.append(TextResult(text=""))

        assert response.usage is not None
        message_metadata = {
            "raw_response": response,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.total_tokens - response.usage.prompt_tokens,
        }

        return internal_messages, message_metadata

    def _process_tool_calls(self, tool_calls, tools: list[ToolParam]) -> list[ToolCall]:
        """Process tool calls and return valid ToolCall objects."""
        available_tool_names = {t.name for t in tools}
        logger.info(
            f"Model returned {len(tool_calls)} tool_calls. Available tools: {available_tool_names}"
        )

        processed_calls = []
        for tool_call_data in tool_calls:
            tool_name_from_model = tool_call_data.function.name
            if tool_name_from_model and tool_name_from_model in available_tool_names:
                logger.info(f"Attempting to process tool call: {tool_name_from_model}")
                try:
                    args_data = tool_call_data.function.arguments
                    if isinstance(args_data, dict):
                        tool_input = args_data
                    elif isinstance(args_data, str):
                        tool_input = json.loads(args_data)
                    else:
                        logger.error(
                            f"Tool arguments for '{tool_name_from_model}' are not a valid format (string or dict): {args_data}"
                        )
                        continue

                    processed_calls.append(
                        ToolCall(
                            tool_name=tool_name_from_model,
                            tool_input=tool_input,
                            tool_call_id=tool_call_data.id,
                        )
                    )
                    logger.info(
                        f"Successfully processed and selected tool call: {tool_name_from_model}"
                    )
                    break  # Process only the first valid tool call

                except json.JSONDecodeError as e:
                    logger.error(
                        f"Failed to parse JSON arguments for tool '{tool_name_from_model}': {tool_call_data.function.arguments}. Error: {str(e)}"
                    )
                    continue
                except Exception as e:
                    logger.error(
                        f"Unexpected error parsing arguments for tool '{tool_name_from_model}': {str(e)}"
                    )
                    continue
            else:
                logger.warning(
                    f"Skipping tool call with unknown or placeholder name: '{tool_name_from_model}'. Not in available tools: {available_tool_names}"
                )

        if not processed_calls:
            logger.warning("No valid and available tool calls found after filtering.")

        return processed_calls

    async def generate_stream(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        tools: list[ToolParam] = [],
        tool_choice: dict[str, str] | None = None,
        thinking_tokens: int | None = None,
        stop_sequence: list[str] | None = None,
        presence_penalty: float = 0.0,
        prefix: bool = False,
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        """Generate responses.

        Args:
            messages: A list of messages.
            system_prompt: A system prompt.
            max_tokens: The maximum number of tokens to generate.
            temperature: The temperature.
            tools: A list of tools.
            tool_choice: A tool choice.

        Returns:
            A generated response.
        """

        openai_messages = []

        if system_prompt is not None:
            openai_messages.append({"role": "system", "content": system_prompt})

        for idx, message_list in enumerate(messages):
            for internal_message in message_list:
                processed_message = self._process_message(internal_message)
                if processed_message:
                    openai_messages.append(processed_message)

        if (
            openai_messages
            and openai_messages[-1].get("role") == "assistant"
            and prefix
        ):
            openai_messages[-1]["prefix"] = prefix

        openai_tools = []
        for tool in tools:
            tool_def = {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
            tool_def["parameters"]["strict"] = True
            openai_tools.append(
                {
                    "type": "function",
                    "function": tool_def,
                }
            )

        async def _create_completion() -> str:
            stream = await self.async_client.chat.completions.create(
                model=self.model_name,
                messages=openai_messages,
                max_completion_tokens=max_tokens,
                stop=stop_sequence,
                presence_penalty=presence_penalty,
                stream=True,
            )
            response = ""
            async for chunk in stream:
                if chunk.choices and (chunk.choices[0].delta.content):
                    content = chunk.choices[0].delta.content
                    print(content, end="")
                    response += content

            return response

        response = await self._ahandle_retries(_create_completion)

        return cast(list[AssistantContentBlock], [TextResult(text=response)]), {}

    async def acompletion(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        stop_sequence: list[str] | None = None,
        presence_penalty: float = 0.0,
        top_p: float = 1.0,
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        """Generate responses using transformer tokenizer to tokenize messages before sending to OpenAI.

        Args:
            messages: A list of messages.
            system_prompt: A system prompt.
            max_tokens: The maximum number of tokens to generate.
            temperature: The temperature.
            tokenizer_name: Name of the tokenizer to use for preprocessing.

        Returns:
            A generated response.
        """
        # Cap max_tokens to model's maximum output tokens
        model_max_output = self.config.get_max_output_tokens()
        if max_tokens > model_max_output:
            logger.warning(
                f"Requested max_tokens ({max_tokens}) exceeds model's limit ({model_max_output}). "
                f"Capping to {model_max_output} for model {self.model_name}"
            )
            max_tokens = model_max_output

        # Initialize tokenizer

        # Convert internal messages to OpenAI format
        openai_messages = []
        if system_prompt is not None:
            openai_messages.append({"role": "system", "content": system_prompt})

        for idx, message_list in enumerate(messages):
            turn_message = None
            # We have three part:
            # Thinking content, response content and tool-call contents for one-turn
            # {"role", ..., "conent": str, "reasoning_content": str, tool_calls: list}
            for internal_message in message_list:
                processed_message = self._process_message(internal_message)
                if turn_message is None:
                    turn_message = processed_message
                    # for thinking content we need to move the content -> reasoning content
                    if isinstance(internal_message, ThinkingBlock):
                        turn_message['reasoning_content'] = turn_message['content']
                        turn_message['content'] = ""
                else:
                    if processed_message.get("tool_calls", None):
                        if "tool_calls" not in turn_message:
                            turn_message['tool_calls'] = []
                        turn_message['tool_calls'].extend(processed_message["tool_calls"])
                        # We extend the tool_call -> tool_calls (for multiple tool-calls)
                    else:
                        if isinstance(internal_message, ThinkingBlock):
                            if "reasoning_content" not in turn_message:
                                turn_message['reasoning_content'] = ""
                                space = ""
                            else:
                                space = "\n"
                            turn_message['reasoning_content'] = turn_message['reasoning_content'] + space + processed_message['content']
                        else:
                            if 'content' not in turn_message:
                                turn_message['content'] = ''
                                space = ""
                            else:
                                space = "\n"
                            turn_message['content'] = turn_message['content'] + space + processed_message['content']

            openai_messages.append(turn_message)

        # Create completion with tokenized messages
        async def _create_completion():
            tokenizer = AutoTokenizer.from_pretrained(self.config.tokenizer)
            prompt = tokenizer.apply_chat_template(
                openai_messages, tokenize=False, continue_final_message=True
            )
            stream = await self.async_client.completions.create(
                model=self.model_name,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                presence_penalty=presence_penalty,
                top_p=top_p,
                stop=stop_sequence,
                stream=True,
            )

            response = ""
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].text:
                    print(chunk.choices[0].text, end="", flush=True)
                    response += chunk.choices[0].text

            assert response is not None, "OpenAI response is None"
            return response

        response = await self._ahandle_retries(_create_completion)

        # Convert response back to internal format
        internal_messages = []
        assert response is not None

        content = response

        if content:
            internal_messages.append(TextResult(text=content))
        else:
            logger.warning(f"Response has no content: {response}")
            internal_messages.append(TextResult(text=""))
        message_metadata = {}
        return internal_messages, message_metadata
