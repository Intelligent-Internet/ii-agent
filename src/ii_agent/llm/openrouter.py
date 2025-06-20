"""LLM client for OpenRouter models."""

import json
import os
import random
import time
from typing import Any, Tuple, cast
import openai
import logging

logger = logging.getLogger(__name__)

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


def map_model_name_to_openrouter(model_name: str) -> str:
    """Map internal model names to OpenRouter format.
    
    Args:
        model_name: Internal model name (e.g., "claude-sonnet-4@20250514")
        
    Returns:
        OpenRouter model name (e.g., "anthropic/claude-3-5-sonnet-20241022")
    """
    # If already in OpenRouter format (contains '/'), return as-is
    if '/' in model_name:
        return model_name
    
    # Claude models mapping
    claude_mappings = {
        "claude-sonnet-4@20250514": "anthropic/claude-3-5-sonnet-20241022",
        "claude-opus-4@20250514": "anthropic/claude-3-opus-20240229", 
        "claude-3-7-sonnet@20250219": "anthropic/claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet": "anthropic/claude-3-5-sonnet-20241022",
        "claude-3-opus": "anthropic/claude-3-opus-20240229",
        "claude-3-haiku": "anthropic/claude-3-haiku-20240307",
    }
    
    # GPT models mapping
    gpt_mappings = {
        "gpt-4o": "openai/gpt-4o",
        "gpt-4.1": "openai/gpt-4-turbo",
        "gpt-4": "openai/gpt-4",
        "gpt-3.5-turbo": "openai/gpt-3.5-turbo",
        "o3": "openai/o1-preview",
        "o4-mini": "openai/o1-mini",
    }
    
    # Gemini models mapping
    gemini_mappings = {
        "gemini-2.5-pro-preview-05-06": "google/gemini-2.5-pro-preview",
        "gemini-pro": "google/gemini-pro",
        "gemini-flash": "google/gemini-1.5-flash",
        "gemini-2.5-pro": "google/gemini-2.5-pro-preview",
    }
    
    # Check mappings in order
    if model_name in claude_mappings:
        return claude_mappings[model_name]
    elif model_name in gpt_mappings:
        return gpt_mappings[model_name]
    elif model_name in gemini_mappings:
        return gemini_mappings[model_name]
    
    # If no specific mapping found, try to detect provider and format
    if "claude" in model_name.lower():
        return f"anthropic/{model_name}"
    elif "gpt" in model_name.lower() or model_name.lower().startswith("o"):
        return f"openai/{model_name}"
    elif "gemini" in model_name.lower():
        return f"google/{model_name}"
    
    # Default: return as-is, assuming it's already properly formatted
    return model_name


class OpenRouterClient(LLMClient):
    """Use various models via OpenRouter API."""

    def __init__(self, model_name: str, max_retries=2, site_url: str = "", site_name: str = ""):
        """Initialize the OpenRouter client."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is required")
        
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            max_retries=1  # We handle retries ourselves
        )
        
        # Map the model name to OpenRouter format
        self.model_name = map_model_name_to_openrouter(model_name)
        self.max_retries = max_retries
        self.site_url = site_url or os.getenv("OPENROUTER_SITE_URL", "")
        self.site_name = site_name or os.getenv("OPENROUTER_SITE_NAME", "")
        
        print(f"====== Using OpenRouter with model: {self.model_name} (mapped from {model_name}) ======")

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
            thinking_tokens: Ignored for OpenRouter.

        Returns:
            A generated response.
        """

        openai_messages = []
        
        # Add system prompt as system message if provided
        if system_prompt is not None:
            system_message = {"role": "system", "content": system_prompt}
            openai_messages.append(system_message)

        for idx, message_list in enumerate(messages):
            if len(message_list) > 1:
                raise ValueError("Only one entry per message supported for OpenRouter")
            internal_message = message_list[0]
            
            if str(type(internal_message)) == str(TextPrompt):
                internal_message = cast(TextPrompt, internal_message)
                message_content_obj = {"type": "text", "text": internal_message.text}
                openai_message = {"role": "user", "content": [message_content_obj]}
                openai_messages.append(openai_message)
                
            elif str(type(internal_message)) == str(TextResult):
                internal_message = cast(TextResult, internal_message)
                message_content_obj = {"type": "text", "text": internal_message.text}
                openai_message = {"role": "assistant", "content": [message_content_obj]}
                openai_messages.append(openai_message)
                
            elif str(type(internal_message)) == str(ToolCall):
                internal_message = cast(ToolCall, internal_message)
                try:
                    arguments_str = json.dumps(internal_message.tool_input)
                except TypeError as e:
                    logger.error(f"Failed to serialize tool_input to JSON string for tool '{internal_message.tool_name}': {internal_message.tool_input}. Error: {str(e)}")
                    raise ValueError(f"Cannot serialize tool arguments for {internal_message.tool_name}: {str(e)}") from e
                
                tool_call_payload = {
                    "type": "function",
                    "id": internal_message.tool_call_id,
                    "function": {
                        "name": internal_message.tool_name,
                        "arguments": arguments_str,
                    },
                }
                openai_message = {
                    "role": "assistant",
                    "tool_calls": [tool_call_payload],
                }
                openai_messages.append(openai_message)
                
            elif str(type(internal_message)) == str(ToolFormattedResult):
                internal_message = cast(ToolFormattedResult, internal_message)
                openai_message = {
                    "role": "tool",
                    "tool_call_id": internal_message.tool_call_id,
                    "content": internal_message.tool_output,
                }
                openai_messages.append(openai_message)
                
            else:
                print(
                    f"Unknown message type: {type(internal_message)}, expected one of {str(TextPrompt)}, {str(TextResult)}, {str(ToolCall)}, {str(ToolFormattedResult)}"
                )
                raise ValueError(f"Unknown message type: {type(internal_message)}")

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
            # OpenRouter doesn't require strict mode
            openai_tool_object = {
                "type": "function",
                "function": tool_def,
            }
            openai_tools.append(openai_tool_object)

        # Prepare extra headers for OpenRouter
        extra_headers = {}
        if self.site_url:
            extra_headers["HTTP-Referer"] = self.site_url
        if self.site_name:
            extra_headers["X-Title"] = self.site_name

        response = None
        for retry in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=openai_messages,
                    tools=openai_tools if len(openai_tools) > 0 else OpenAI_NOT_GIVEN,
                    tool_choice=tool_choice_param,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    extra_headers=extra_headers,
                )
                break
            except (
                OpenAI_APIConnectionError,
                OpenAI_InternalServerError,
                OpenAI_RateLimitError,
            ) as e:
                if retry == self.max_retries - 1:
                    print(f"Failed OpenRouter request after {retry + 1} retries")
                    raise e
                else:
                    print(f"Retrying OpenRouter request: {retry + 1}/{self.max_retries}")
                    # Sleep 8-12 seconds with jitter to avoid thundering herd.
                    time.sleep(10 * random.uniform(0.8, 1.2))

        # Convert messages back to internal format
        internal_messages = []
        assert response is not None
        openai_response_messages = response.choices
        if len(openai_response_messages) > 1:
            raise ValueError("Only one message supported for OpenRouter")
        openai_response_message = openai_response_messages[0].message
        tool_calls = openai_response_message.tool_calls
        content = openai_response_message.content

        # Handle both tool_calls and content (some models might return both)
        if content:
            internal_messages.append(TextResult(text=content))

        if tool_calls:
            available_tool_names = {t.name for t in tools}
            logger.info(f"Model returned {len(tool_calls)} tool_calls. Available tools: {available_tool_names}")
            
            processed_tool_call = False
            for tool_call_data in tool_calls:
                tool_name_from_model = tool_call_data.function.name
                if tool_name_from_model and tool_name_from_model in available_tool_names:
                    logger.info(f"Attempting to process tool call: {tool_name_from_model}")
                    try:
                        args_data = tool_call_data.function.arguments
                        if isinstance(args_data, dict):
                            tool_input = args_data
                        elif isinstance(args_data, str):
                            # Handle empty string arguments
                            if args_data.strip() == "":
                                tool_input = {}
                                logger.info(f"Using empty arguments for tool '{tool_name_from_model}'")
                            else:
                                tool_input = json.loads(args_data)
                        else:
                            logger.error(f"Tool arguments for '{tool_name_from_model}' are not a valid format (string or dict): {args_data}")
                            continue

                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON arguments for tool '{tool_name_from_model}': '{tool_call_data.function.arguments}'. Error: {str(e)}")
                        # For tools that don't require arguments, use empty dict as fallback
                        tool_input = {}
                        logger.info(f"Using empty arguments as fallback for tool '{tool_name_from_model}'")
                    except Exception as e:
                        logger.error(f"Unexpected error parsing arguments for tool '{tool_name_from_model}': {str(e)}")
                        continue

                    internal_messages.append(
                        ToolCall(
                            tool_name=tool_name_from_model,
                            tool_input=tool_input,
                            tool_call_id=tool_call_data.id,
                        )
                    )
                    processed_tool_call = True
                    logger.info(f"Successfully processed and selected tool call: {tool_name_from_model}")
                    break
                else:
                    logger.warning(f"Skipping tool call with unknown or placeholder name: '{tool_name_from_model}'. Not in available tools: {available_tool_names}")
            
            if not processed_tool_call:
                logger.warning("No valid and available tool calls found after filtering.")

        # If neither content nor valid tool calls, this is an error
        if not internal_messages:
            raise ValueError("No valid content or tool calls found in response")

        assert response.usage is not None
        message_metadata = {
            "raw_response": response,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        }

        return internal_messages, message_metadata 