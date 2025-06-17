import os
import time
import random

from typing import Any, Tuple
from openai import OpenAI
from ii_agent.llm.base import (
    LLMClient,
    AssistantContentBlock,
    ToolParam,
    TextPrompt,
    ToolCall,
    TextResult,
    LLMMessages,
    ToolFormattedResult,
    ImageBlock,
)

def generate_tool_call_id() -> str:
    """Generate a unique ID for a tool call.
    
    Returns:
        A unique string ID combining timestamp and random number.
    """
    timestamp = int(time.time() * 1000)  # Current time in milliseconds
    random_num = random.randint(1000, 9999)  # Random 4-digit number
    return f"call_{timestamp}_{random_num}"


class GeminiDirectClient(LLMClient):
    """Use models via OpenRouter API with OpenAI-compatible format."""

    def __init__(self, model_name: str, max_retries: int = 2, site_url: str = None, site_name: str = None):
        self.model_name = model_name

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")
            
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        # Optional headers for OpenRouter rankings
        self.extra_headers = {}
        if site_url:
            self.extra_headers["HTTP-Referer"] = site_url
        if site_name:
            self.extra_headers["X-Title"] = site_name
            
        self.max_retries = max_retries
        print(f"====== Using {model_name} through OpenRouter API ======")

    def generate(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        tools: list[ToolParam] = [],
        tool_choice: dict[str, str] | None = None,
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        
        openai_messages = []
        
        # Add system message if provided
        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})
        
        for idx, message_list in enumerate(messages):
            role = "user" if idx % 2 == 0 else "assistant"
            content = []
            
            for message in message_list:
                if isinstance(message, TextPrompt):
                    content.append({"type": "text", "text": message.text})
                elif isinstance(message, ImageBlock):
                    # Convert image to base64 for OpenAI format
                    import base64
                    image_data = base64.b64encode(message.source["data"]).decode('utf-8')
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{message.source['media_type']};base64,{image_data}"
                        }
                    })
                elif isinstance(message, TextResult):
                    content.append({"type": "text", "text": message.text})
                elif isinstance(message, ToolCall):
                    # For tool calls, we need to format differently
                    if role == "assistant":
                        openai_messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": message.tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": message.tool_name,
                                    "arguments": str(message.tool_input)
                                }
                            }]
                        })
                        continue
                elif isinstance(message, ToolFormattedResult):
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": message.tool_call_id,
                        "content": str(message.tool_output)
                    })
                    continue
                else:
                    raise ValueError(f"Unknown message type: {type(message)}")
            
            if content:
                if len(content) == 1 and content[0]["type"] == "text":
                    openai_messages.append({"role": role, "content": content[0]["text"]})
                else:
                    openai_messages.append({"role": role, "content": content})

        # Convert tools to OpenAI format
        openai_tools = []
        if tools:
            for tool in tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    }
                })

        # Convert tool_choice to OpenAI format
        openai_tool_choice = None
        if tool_choice:
            if tool_choice['type'] == 'any':
                openai_tool_choice = "required"
            elif tool_choice['type'] == 'auto':
                openai_tool_choice = "auto"

        for retry in range(self.max_retries):
            try:
                kwargs = {
                    "model": self.model_name,
                    "messages": openai_messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                
                if openai_tools:
                    kwargs["tools"] = openai_tools
                    if openai_tool_choice:
                        kwargs["tool_choice"] = openai_tool_choice
                
                if self.extra_headers:
                    kwargs["extra_headers"] = self.extra_headers

                response = self.client.chat.completions.create(**kwargs)
                break
            except Exception as e:
                if retry == self.max_retries - 1:
                    print(f"Failed OpenRouter request after {retry + 1} retries")
                    raise e
                else:
                    print(f"Error: {e}")
                    print(f"Retrying OpenRouter request: {retry + 1}/{self.max_retries}")
                    # Sleep 12-18 seconds with jitter to avoid throttling
                    time.sleep(15 * random.uniform(0.8, 1.2))

        internal_messages = []
        choice = response.choices[0]
        
        if choice.message.content:
            internal_messages.append(TextResult(text=choice.message.content))

        if choice.message.tool_calls:
            for tool_call in choice.message.tool_calls:
                response_message_content = ToolCall(
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.function.name,
                    tool_input=eval(tool_call.function.arguments),  # Convert string back to dict
                )
                internal_messages.append(response_message_content)

        message_metadata = {
            "raw_response": response,
            "input_tokens": response.usage.prompt_tokens if response.usage and hasattr(response.usage, 'prompt_tokens') else 0,
            "output_tokens": response.usage.completion_tokens if response.usage and hasattr(response.usage, 'completion_tokens') else 0,
        }
        
        return internal_messages, message_metadata

