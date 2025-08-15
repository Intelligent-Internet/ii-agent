"""LLM client for Anthropic models."""

import json
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
    NOT_GIVEN as OpenAI_NOT_GIVEN,
)

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

        # Convert messages to input format for Responses API
        input_messages: list[dict[str, Any]] = []
        if system_prompt:
            input_messages.append({
                "role": "developer",
                "content": [{"type": "input_text", "text": system_prompt}],
            })
        
        # Track tool calls and their results for debugging
        tool_call_ids_sent = set()
        tool_result_ids_sent = set()

        for message_list in messages:
            if not message_list:
                continue
            
            # Process ALL messages in the message_list, not just the first one
            for internal_message in message_list:
                if isinstance(internal_message, TextPrompt):
                    input_messages.append({
                        "role": "user",
                        "content": [{"type": "input_text", "text": internal_message.text}],
                    })
                elif isinstance(internal_message, TextResult):
                    # Preserve previous assistant responses in context
                    input_messages.append({
                        "role": "assistant",
                        "id": internal_message.id,
                        "content": [{"type": "output_text", "text": internal_message.text}],
                    })
                elif isinstance(internal_message, ImageBlock):
                    input_messages.append({
                        "role": "user",
                        "content": [{
                            "type": "input_image",
                            "image_url": {
                                "url": f"data:{internal_message.source['media_type']};base64,{internal_message.source['data']}"
                            }
                        }],
                    })
                elif str(type(internal_message)) == str(ToolCall):
                    internal_message = cast(ToolCall, internal_message)
                    try:
                        arguments_str = json.dumps(internal_message.tool_input)
                    except TypeError as e:
                        logger.error(f"Failed to serialize tool_input to JSON string for tool '{internal_message.tool_name}': {internal_message.tool_input}. Error: {str(e)}")
                        raise ValueError(f"Cannot serialize tool arguments for {internal_message.tool_name}: {str(e)}") from e
                    
                    tool_call_payload = {
                        "type": "function_call",
                        "call_id": internal_message.tool_call_id,
                        "id": internal_message.tool_id,
                        "name": internal_message.tool_name,
                        "arguments": arguments_str,
                    }
                    input_messages.append(tool_call_payload)
                    tool_call_ids_sent.add(internal_message.tool_call_id)
                elif str(type(internal_message)) == str(ToolFormattedResult):
                    internal_message = cast(ToolFormattedResult, internal_message)
                    # Check if we have a matching tool call for this result
                    if internal_message.tool_call_id not in tool_call_ids_sent:
                        logger.warning(
                            f"Skipping orphaned tool result with call_id {internal_message.tool_call_id} "
                            f"(no matching tool call found in conversation)"
                        )
                        continue
                    
                    openai_message = {
                        "type": "function_call_output",
                        "call_id": internal_message.tool_call_id,
                        "output": internal_message.tool_output,
                    }
                    image_blocks = []
                    if isinstance(internal_message.tool_output, list):
                        for block in internal_message.tool_output:
                            if isinstance(block, dict) and block.get("type") == "image":
                                new_block = {
                                    "type": "input_image",
                                    "image_url": f"data:{block['source']['media_type']};base64,{block['source']['data']}"
                                }
                                image_blocks.append(new_block)
                    if len(image_blocks) > 0:
                        openai_message["output"] = "Executed tool successfully"
                        input_messages.append(openai_message)
                        input_messages.append({
                            "role": "user",
                            "content": image_blocks,
                        })
                    else:
                        input_messages.append(openai_message)
                    tool_result_ids_sent.add(internal_message.tool_call_id)
                elif str(type(internal_message)) == str(ThinkingBlock):
                    internal_message = cast(ThinkingBlock, internal_message)
                    openai_message = {
                        "type": "reasoning",
                        "id": internal_message.signature,
                        "summary": [{"type": "summary_text", "text": internal_message.thinking}],
                    }
                    input_messages.append(openai_message)
                else:
                    print(
                        f"Unknown message type: {type(internal_message)}, expected one of {str(TextPrompt)}, {str(TextResult)}, {str(ToolCall)}, {str(ToolFormattedResult)}"
                    )
                    raise ValueError(f"Unknown message type: {type(internal_message)}")


        # Log any tool call/result mismatches for debugging
        orphaned_calls = tool_call_ids_sent - tool_result_ids_sent
        if orphaned_calls:
            logger.debug(f"Tool calls without results: {orphaned_calls}")
        
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

        # Turn tools into Responses API tool format
        openai_tools = []
        for tool in tools:
            openai_tool_object = {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
            openai_tools.append(openai_tool_object)
        response = None
        for retry in range(self.max_retries):
            try:
                # Build parameters dict for responses.create()
                params = {
                    "model": self.model_name,
                    "input": input_messages,
                }

                params["store"] = True
                
                if len(openai_tools) > 0:
                    params["tools"] = openai_tools
                    
                if tool_choice_param != OpenAI_NOT_GIVEN:
                    params["tool_choice"] = tool_choice_param
                    
                # Reasoning configuration
                reasoning_effort = "high"
                params["reasoning"] = {"effort": reasoning_effort, "summary": "auto"}
                try:
                    response = self.client.responses.create(**params)
                except Exception as e:
                    print(f"Error: {e}")
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
        assert response is not None
        
        # Responses API has a different structure - extract content from the response object
        outputs = []
        for item in response.output:
            if item.type == "reasoning":
                reasoning_id = item.id
                reasoning_summaries = "".join([si.text for si in item.summary])
                outputs.append(ThinkingBlock(
                    signature=reasoning_id,
                    thinking=reasoning_summaries,
                ))
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
                outputs.append(ToolCall(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_id=tool_id,
                ))
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
        
        self.previous_response_id = None # for future supports

        return outputs, message_metadata
