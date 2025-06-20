"""LLM client for Anthropic models."""

import json
import os
import random
import time
from typing import Any, Tuple, cast
import openai
import logging



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
from ii_agent.llm.base import (
    LLMClient,
    AssistantContentBlock,
    LLMMessages,
    ToolParam,
    TextPrompt,
    ToolCall,
    TextResult,
    ToolFormattedResult,
)

logger = logging.getLogger(__name__)


class OpenAIDirectClient(LLMClient):
    """Use OpenAI models via first party API."""

    def __init__(self, llm_config: LLMConfig):
        """Initialize the OpenAI first party client."""
        if llm_config.azure_endpoint is not None:
            self.client = openai.AzureOpenAI(
                api_key=llm_config.api_key.get_secret_value() if llm_config.api_key else None,
                azure_endpoint=llm_config.azure_endpoint,
                api_version=llm_config.azure_api_version,
                max_retries=llm_config.max_retries,
            )

        else:
            base_url = llm_config.base_url or "https://api.openai.com/v1"
            self.client = openai.OpenAI(
                api_key=llm_config.api_key.get_secret_value() if llm_config.api_key else None,
                base_url=base_url,
                max_retries=llm_config.max_retries,
            )
        self.model_name = llm_config.model
        self.max_retries = llm_config.max_retries
        self.cot_model = llm_config.cot_model

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

        openai_messages = []
        system_prompt_applied = False

        if system_prompt is not None:
            if not self.cot_model:
                system_message = {"role": "system", "content": system_prompt}
                openai_messages.append(system_message)
                system_prompt_applied = True

        for idx, message_list in enumerate(messages):
            if len(message_list) > 1:
                raise ValueError("Only one entry per message supported for openai")
            internal_message = message_list[0]
            
            current_message_text = ""
            is_user_prompt = False

            if str(type(internal_message)) == str(TextPrompt):
                internal_message = cast(TextPrompt, internal_message)
                current_message_text = internal_message.text
                is_user_prompt = True
                role = "user"
            elif str(type(internal_message)) == str(TextResult):
                internal_message = cast(TextResult, internal_message)
                # For TextResult (assistant), content is handled differently by OpenAI API
                message_content_obj = {"type": "text", "text": internal_message.text}
                openai_message = {"role": "assistant", "content": [message_content_obj]}
                openai_messages.append(openai_message)
                continue # Move to next message in outer loop
            elif str(type(internal_message)) == str(ToolCall):
                internal_message = cast(ToolCall, internal_message)
                # Ensure arguments are stringified JSON for the OpenAI API call
                try:
                    arguments_str = json.dumps(internal_message.tool_input)
                except TypeError as e:
                    logger.error(f"Failed to serialize tool_input to JSON string for tool '{internal_message.tool_name}': {internal_message.tool_input}. Error: {str(e)}")
                    # Decide how to handle: skip this message, or raise, or send with potentially malformed args? For now, let's raise.
                    raise ValueError(f"Cannot serialize tool arguments for {internal_message.tool_name}: {str(e)}") from e
                
                tool_call_payload = {
                    "type": "function",
                    "id": internal_message.tool_call_id,
                    "function": {
                        "name": internal_message.tool_name,
                        "arguments": arguments_str, # Use the JSON string
                    },
                }
                openai_message = {
                    "role": "assistant",
                    "tool_calls": [tool_call_payload],
                    # Content is implicitly None or omitted by not setting it
                }
                openai_messages.append(openai_message)
                continue # Move to next message in outer loop
            elif str(type(internal_message)) == str(ToolFormattedResult):
                internal_message = cast(ToolFormattedResult, internal_message)
                openai_message = {
                    "role": "tool",
                    "tool_call_id": internal_message.tool_call_id,
                    "content": internal_message.tool_output,
                }
                openai_messages.append(openai_message)
                continue # Move to next message in outer loop
            else:
                print(
                    f"Unknown message type: {type(internal_message)}, expected one of {str(TextPrompt)}, {str(TextResult)}, {str(ToolCall)}, {str(ToolFormattedResult)}"
                )
                raise ValueError(f"Unknown message type: {type(internal_message)}")

            # This part now only applies to TextPrompt (user messages)
            if is_user_prompt:
                final_text_for_user_message = current_message_text
                # If cot_model is True, system_prompt is not None, and it hasn't been applied yet (i.e., this is the first user message opportunity)
                if self.cot_model and system_prompt and not system_prompt_applied:
                    final_text_for_user_message = f"{system_prompt}\n\n{current_message_text}"
                    system_prompt_applied = True # Mark as applied
                
                message_content_obj = {"type": "text", "text": final_text_for_user_message}
                openai_message = {"role": role, "content": [message_content_obj]}
                openai_messages.append(openai_message)

        # If cot_model is True and system_prompt was provided but not applied (e.g., no user messages found, though unlikely for an agent)
        if self.cot_model and system_prompt and not system_prompt_applied:
            # This is a fallback: if there were no user messages to prepend to, send it as a system message.
            # Or, one might argue it's an error condition for COT if no user prompt exists.
            # For now, let's log a warning and add it as a user message, as some COT models might expect user turn for instructions.
            logger.warning("COT mode: System prompt provided but no initial user message to prepend to. Adding as a separate user message.")
            openai_messages.insert(0, {"role": "user", "content": [{"type": "text", "text": system_prompt}]})

        # Turn tool_choice into OpenAI tool_choice format
        if tool_choice is None:
            tool_choice_param = OpenAI_NOT_GIVEN
        elif tool_choice["type"] == "any":
            tool_choice_param = "required"
        elif tool_choice["type"] == "auto":
            tool_choice_param = "auto"
        elif tool_choice["type"] == "tool":
            tool_choice_param = {
                "type": "function",
                "function": {"name": tool_choice["name"]},
            }
        else:
            raise ValueError(f"Unknown tool_choice type: {tool_choice['type']}")

        # Turn tools into OpenAI tool format
        openai_tools = []
        for tool in tools:
            tool_def = {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
            tool_def["parameters"]["strict"] = True
            openai_tool_object = {
                "type": "function",
                "function": tool_def,
            }
            openai_tools.append(openai_tool_object)

        response = None
        for retry in range(self.max_retries):
            try:
                extra_body = {}
                openai_max_tokens = max_tokens
                openai_temperature = temperature
                if self.cot_model:
                    extra_body["max_completion_tokens"] = max_tokens
                    openai_max_tokens = OpenAI_NOT_GIVEN
                    openai_temperature = OpenAI_NOT_GIVEN
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=openai_messages,
                    tools=openai_tools if len(openai_tools) > 0 else OpenAI_NOT_GIVEN,
                    tool_choice=tool_choice_param,
                    max_tokens=openai_max_tokens,
                    extra_body=extra_body,
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
        tool_calls = openai_response_message.tool_calls
        content = openai_response_message.content

        # Exactly one of tool_calls or content should be present
        if tool_calls and content:
            raise ValueError("Only one of tool_calls or content should be present")
        elif not tool_calls and not content:
            raise ValueError("Either tool_calls or content should be present")

        if tool_calls:
            available_tool_names = {t.name for t in tools} # Get set of known tool names
            logger.info(f"Model returned {len(tool_calls)} tool_calls. Available tools: {available_tool_names}")
            
            processed_tool_call = False
            for tool_call_data in tool_calls:
                tool_name_from_model = tool_call_data.function.name
                if tool_name_from_model and tool_name_from_model in available_tool_names:
                    logger.info(f"Attempting to process tool call: {tool_name_from_model}")
                    try:
                        # Ensure arguments are a string before trying to load as JSON, 
                        # as some models might already return a dict if the library handles it.
                        args_data = tool_call_data.function.arguments
                        if isinstance(args_data, dict):
                            tool_input = args_data
                        elif isinstance(args_data, str):
                            tool_input = json.loads(args_data)
                        else:
                            logger.error(f"Tool arguments for '{tool_name_from_model}' are not a valid format (string or dict): {args_data}")
                            continue # Skip this tool call

                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON arguments for tool '{tool_name_from_model}': {tool_call_data.function.arguments}. Error: {str(e)}")
                        continue # Skip this malformed tool call
                    except Exception as e:
                        logger.error(f"Unexpected error parsing arguments for tool '{tool_name_from_model}': {str(e)}")
                        continue # Skip this tool call

                    internal_messages.append(
                        ToolCall(
                            tool_name=tool_name_from_model,
                            tool_input=tool_input,
                            tool_call_id=tool_call_data.id,
                        )
                    )
                    processed_tool_call = True
                    logger.info(f"Successfully processed and selected tool call: {tool_name_from_model}")
                    break # Processed the first valid and available tool call
                else:
                    logger.warning(f"Skipping tool call with unknown or placeholder name: '{tool_name_from_model}'. Not in available tools: {available_tool_names}")
            
            if not processed_tool_call:
                logger.warning("No valid and available tool calls found after filtering.")

        elif content:
            internal_messages.append(TextResult(text=content))
        else:
            raise ValueError(f"Unknown message type: {openai_response_message}")

        assert response.usage is not None
        message_metadata = {
            "raw_response": response,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        }

        return internal_messages, message_metadata
