import os
import random
import time
from typing import Any, Tuple, cast

from openai import OpenAI, APIConnectionError, InternalServerError, RateLimitError
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall

from ii_agent.llm.base import (
    LLMClient,
    AssistantContentBlock,
    ToolParam,
    TextPrompt,
    ToolCall,
    TextResult,
    LLMMessages,
    ToolFormattedResult,
    ImageBlock, # Assuming ImageBlock might be used, though OpenRouter's OpenAI-compatible endpoint might not support it in the same way
)
from ii_agent.utils.constants import DEFAULT_MODEL # Or a new constant for default OpenRouter model


class OpenRouterClient(LLMClient):
    """Use OpenRouter models via OpenAI-compatible API."""

    def __init__(
        self,
        model_name: str = "anthropic/claude-3.5-sonnet", # Default to a common OpenRouter model
        max_retries: int = 2,
        # Caching is not directly supported by OpenRouter in the same way as Anthropic's prompt caching
        # use_caching: bool = False, 
        # thinking_tokens: int = 0, # Not a standard OpenAI/OpenRouter param
        # project_id: None | str = None, # Not applicable for OpenRouter
        # region: None | str = None, # Not applicable for OpenRouter
    ):
        """Initialize the OpenRouter client."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not set.")

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            max_retries=1,  # We handle retries manually
            timeout=60 * 5,
        )
        self.model_name = model_name
        self.max_retries = max_retries
        # self.thinking_tokens = thinking_tokens # Not applicable

    def _map_model_name(self, model_name: str) -> str:
        """Map Anthropic model names to OpenRouter model names."""
        model_mapping = {
            "claude-3-opus-20240229": "anthropic/claude-3-opus",
            "claude-3-sonnet-20240229": "anthropic/claude-3-sonnet",
            "claude-3-haiku-20240307": "anthropic/claude-3-haiku",
            # Add more mappings as needed
        }
        return model_mapping.get(model_name, "anthropic/claude-3-sonnet")  # Default to claude-3-sonnet if no match

    def generate(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        tools: list[ToolParam] = [],
        tool_choice: dict[str, str] | None = None,
        # thinking_tokens: int | None = None, # Not applicable
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        """Generate responses using OpenRouter.

        Args:
            messages: A list of messages.
            max_tokens: The maximum number of tokens to generate.
            system_prompt: A system prompt.
            temperature: The temperature.
            tools: A list of tools.
            tool_choice: A tool choice.

        Returns:
            A tuple containing a list of assistant content blocks and metadata.
        """
        openai_messages: list[ChatCompletionMessageParam] = []

        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})

        for idx, message_list in enumerate(messages):
            # Determine role based on index, assuming alternating user/assistant messages
            # For OpenRouter/OpenAI, the first message in `messages` (if no system prompt) will be 'user'
            # Subsequent messages alternate.
            # If system prompt is provided, messages[0] is user, messages[1] is assistant, etc.
            # This needs careful mapping based on how LLMMessages is structured.
            # Assuming LLMMessages is a list of turns, where each turn is a list of content blocks.
            # And the first turn is user, second is assistant, etc.

            role = "user" if idx % 2 == 0 else "assistant"
            
            # For OpenAI, multiple content blocks (like text and image) per message are usually
            # represented as a list in the 'content' field of a single message object.
            # However, tool calls and tool results are distinct message types.

            current_turn_content = []
            tool_calls_for_assistant_message = []
            tool_results_for_user_message = []

            for message_block in message_list:
                if isinstance(message_block, TextPrompt) or isinstance(message_block, TextResult):
                    current_turn_content.append({"type": "text", "text": message_block.text})
                elif isinstance(message_block, ImageBlock):
                    # OpenAI format for image content:
                    # {
                    #   "type": "image_url",
                    #   "image_url": { "url": "data:image/jpeg;base64,{base64_image}" }
                    # }
                    # This assumes message.source.data is base64 encoded image data
                    # and message.source.media_type is e.g. 'image/jpeg'
                    if message_block.source.type == "base64":
                         current_turn_content.append({
                             "type": "image_url",
                             "image_url": {
                                 "url": f"data:{message_block.source.media_type};base64,{message_block.source.data}"
                             }
                         })
                    else:
                        # Handle other image source types if necessary, or raise error
                        print(f"Warning: ImageBlock source type {message_block.source.type} not directly supported for OpenAI image_url. Skipping image.")
                
                elif isinstance(message_block, ToolCall):
                    # This block means the *assistant* previously made a tool call.
                    # These are added as a list to the assistant's message.
                    tool_calls_for_assistant_message.append(
                        ChatCompletionMessageToolCall(
                            id=message_block.tool_call_id,
                            function={
                                "name": message_block.tool_name,
                                "arguments": str(message_block.tool_input), # OpenAI expects stringified JSON
                            },
                            type="function",
                        )
                    )
                elif isinstance(message_block, ToolFormattedResult):
                    # This block means the *user* is providing a tool result.
                    # These are individual messages with role 'tool'.
                     openai_messages.append({
                         "role": "tool",
                         "tool_call_id": message_block.tool_call_id,
                         "content": str(message_block.tool_output), # Content of the tool result
                     })
                else:
                    raise ValueError(f"Unsupported message block type: {type(message_block)}")

            if role == "user":
                if current_turn_content: # User messages will have content
                    openai_messages.append({"role": "user", "content": current_turn_content})
                # tool_results_for_user_message are handled above as separate 'tool' role messages
            
            elif role == "assistant":
                assistant_message_parts: dict[str, Any] = {"role": "assistant"}
                if current_turn_content: # Assistant text response
                    # OpenAI expects a single string for content if no tool calls, or if text is the only part
                    # If there are multiple text parts (not typical for assistant), it should be a list.
                    # For simplicity, assuming assistant text response is a single string.
                    assistant_message_parts["content"] = current_turn_content[0]["text"] if len(current_turn_content) == 1 else current_turn_content
                
                if tool_calls_for_assistant_message: # Assistant tool calls
                    assistant_message_parts["tool_calls"] = tool_calls_for_assistant_message
                
                if "content" in assistant_message_parts or "tool_calls" in assistant_message_parts:
                    openai_messages.append(assistant_message_parts)


        openai_tools: list[ChatCompletionToolParam] | None = None
        if tools:
            openai_tools = []
            for tool in tools:
                openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.input_schema,
                        },
                    }
                )
        
        openai_tool_choice: str | dict[str, Any] | None = None
        if tool_choice:
            if tool_choice["type"] == "any":
                openai_tool_choice = "required"  # OpenAI's equivalent for forcing a tool call (any tool)
            elif tool_choice["type"] == "auto":
                openai_tool_choice = "auto"
            elif tool_choice["type"] == "tool":
                openai_tool_choice = {"type": "function", "function": {"name": tool_choice["name"]}}
            # OpenAI also supports "none" to prevent tool use. Not directly mapped from Anthropic's options.
        
        response = None
        # OpenRouter specific headers (optional, for leaderboard tracking)
        # Referer: Your app's domain
        # X-Title: Your app's name
        extra_headers = {
            "HTTP-Referer": "https://github.com/klimentij/ii-agent", # Replace with your actual site URL if applicable
            "X-Title": "ii-agent (klimentij fork)" # Replace with your actual site name if applicable
        }

        for attempt in range(self.max_retries + 1):
            try:
                api_response = self.client.chat.completions.create(
                    model=self._map_model_name(self.model_name),
                    messages=openai_messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    tools=openai_tools if openai_tools else None, # Pass None if no tools
                    tool_choice=openai_tool_choice if openai_tool_choice else None, # Pass None if no specific choice
                    extra_headers=extra_headers,
                )
                response = api_response # Keep the full response for metadata
                break 
            except (APIConnectionError, InternalServerError, RateLimitError) as e:
                if attempt == self.max_retries:
                    print(f"Failed OpenRouter request after {attempt + 1} retries: {e}")
                    raise
                else:
                    print(f"Retrying OpenRouter request: {attempt + 1}/{self.max_retries}. Error: {e}")
                    time.sleep(random.uniform(5, 10) * (attempt + 1)) # Exponential backoff with jitter
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                raise

        internal_messages: list[AssistantContentBlock] = []
        if response and response.choices and response.choices[0].message:
            choice_message = response.choices[0].message

            if choice_message.content:
                # Content can be a string or list of parts (e.g. for multimodal)
                # For now, assuming it's a string as per typical chat.
                if isinstance(choice_message.content, str):
                    internal_messages.append(TextResult(text=choice_message.content))
                # else:
                #   Handle list of content parts if necessary (e.g. multimodal responses)
                #   This might require changes to AssistantContentBlock or new types.
            
            if choice_message.tool_calls:
                internal_messages.extend(self._parse_tool_calls(choice_message.tool_calls))

        message_metadata = {
            "finish_reason": response.choices[0].finish_reason if response and response.choices else None,
            # Add any other metadata you want to track
        }

        return internal_messages, message_metadata

    def _parse_tool_calls(self, tool_calls: list[ChatCompletionMessageToolCall]) -> list[ToolCall]:
        """Parse OpenAI tool calls into our format."""
        result = []
        for tool_call in tool_calls:
            # Ensure tool input is a dictionary
            tool_input = tool_call.function.arguments
            if isinstance(tool_input, str):
                try:
                    import json
                    tool_input = json.loads(tool_input)
                except json.JSONDecodeError:
                    tool_input = {"text": tool_input}  # Fallback for string inputs
            
            result.append(
                ToolCall(
                    tool_name=tool_call.function.name,
                    tool_input=tool_input,
                    tool_call_id=tool_call.id
                )
            )
        return result 