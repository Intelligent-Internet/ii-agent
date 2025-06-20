import os
import time
import random

from typing import Any, Tuple
from google import genai
from google.genai import types, errors
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
    """Use Gemini models via first party API."""

    def __init__(self, model_name: str, max_retries: int = 2, project_id: None | str = None, region: None | str = None):
        self.model_name = model_name

        if project_id and region:
            self.client = genai.Client(vertexai=True, project=project_id, location=region)
            print(f"====== Using Gemini through Vertex AI API with project_id: {project_id} and region: {region} ======")
        else:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY is not set")
            self.client = genai.Client(api_key=api_key)
            print("====== Using Gemini directly ======")
            
        self.max_retries = max_retries

    def generate(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        tools: list[ToolParam] = [],
        tool_choice: dict[str, str] | None = None,
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        
        gemini_messages = []
        for idx, message_list in enumerate(messages):
            role = "user" if idx % 2 == 0 else "model"
            message_content_list = []
            for message in message_list:
                if isinstance(message, TextPrompt):
                    message_content = types.Part(text=message.text)
                elif isinstance(message, ImageBlock):
                    message_content = types.Part.from_bytes(
                            data=message.source["data"],
                            mime_type=message.source["media_type"],
                        )
                elif isinstance(message, TextResult):
                    message_content = types.Part(text=message.text)
                elif isinstance(message, ToolCall):
                    message_content = types.Part.from_function_call(
                        name=message.tool_name,
                        args=message.tool_input,
                    )
                elif isinstance(message, ToolFormattedResult):
                    if isinstance(message.tool_output, str):
                        message_content = types.Part.from_function_response(
                            name=message.tool_name,
                            response={"result": message.tool_output}
                        )
                    # Handle tool return images. See: https://discuss.ai.google.dev/t/returning-images-from-function-calls/3166/6
                    elif isinstance(message.tool_output, list):
                        message_content = []
                        for item in message.tool_output:
                            if item['type'] == 'text':
                                message_content.append(types.Part(text=item['text']))
                            elif item['type'] == 'image':
                                message_content.append(types.Part.from_bytes(
                                    data=item['source']['data'],
                                    mime_type=item['source']['media_type']
                                ))
                else:
                    raise ValueError(f"Unknown message type: {type(message)}")
                
                if isinstance(message_content, list):
                    message_content_list.extend(message_content)
                else:
                    message_content_list.append(message_content)
            
            gemini_messages.append(types.Content(role=role, parts=message_content_list))
        
        tool_declarations = [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
            for tool in tools
        ]
        tool_params = [types.Tool(function_declarations=tool_declarations)] if tool_declarations else None

        mode = None
        if not tool_choice:
            mode = 'ANY' # This mode always requires a tool call
        elif tool_choice['type'] == 'any':
            mode = 'ANY'
        elif tool_choice['type'] == 'auto':
            mode = 'AUTO'
        else:
            raise ValueError(f"Unknown tool_choice type for Gemini: {tool_choice['type']}")

        for retry in range(self.max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    config=types.GenerateContentConfig(
                        tools=tool_params,
                        system_instruction=system_prompt,
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                        tool_config={'function_calling_config': {'mode': mode}}
                        ),
                    contents=gemini_messages,
                )
                break
            except errors.APIError as e:
                # 503: The service may be temporarily overloaded or down.
                # 429: The request was throttled.
                if e.code in [503, 429]:
                    if retry == self.max_retries - 1:
                        print(f"Failed Gemini request after {retry + 1} retries")
                        raise e
                    else:
                        print(f"Error: {e}")
                        print(f"Retrying Gemini request: {retry + 1}/{self.max_retries}")
                        # Sleep 12-18 seconds with jitter to avoid thundering herd.
                        time.sleep(15 * random.uniform(0.8, 1.2))
                else:
                    raise e

        internal_messages = []
        if response.text:
            internal_messages.append(TextResult(text=response.text))

        if response.function_calls:
            for fn_call in response.function_calls:
                response_message_content = ToolCall(
                    tool_call_id=fn_call.id if fn_call.id else generate_tool_call_id(),
                    tool_name=fn_call.name,
                    tool_input=fn_call.args,
                )
                internal_messages.append(response_message_content)

        message_metadata = {
            "raw_response": response,
            "input_tokens": response.usage_metadata.prompt_token_count,
            "output_tokens": response.usage_metadata.candidates_token_count,
        }
        
        return internal_messages, message_metadata