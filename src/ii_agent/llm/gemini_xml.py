"""
Gemini XML Client for ii-agent
A specialized Gemini client designed for XML-based tool calling (no native function calling)
"""

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


class GeminiXMLClient(LLMClient):
    """Gemini client optimized for XML tool calling without native function calling."""

    def __init__(self, model_name: str, max_retries: int = 2, project_id: None | str = None, region: None | str = None):
        self.model_name = model_name

        if project_id and region:
            self.endpoint = "vertex"
            self.client = genai.Client(vertexai=True, project=project_id, location=region)
            print(f"====== Using Gemini XML Client through Vertex AI API with project_id: {project_id} and region: {region} ======")
        else:
            self.endpoint = "studio"
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY is not set")
            self.client = genai.Client(api_key=api_key)
            print(f"====== Using Gemini XML Client directly ======")
            
        self.max_retries = max_retries

    def generate(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        tools: list[ToolParam] = [],
        tool_choice: dict[str, str] | None = None,
        thinking_tokens: int = 8192,
        temperature: float = 0.0,
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        """
        Generate response using Gemini without native tool calling.
        This client is designed for XML-based tool parsing only.
        """
        
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
                    # For XML client, convert tool calls to text representation
                    # This handles the case where we have tool calls in the conversation history
                    tool_text = f"[Tool Call: {message.tool_name}({message.tool_input})]"
                    message_content = types.Part(text=tool_text)
                elif isinstance(message, ToolFormattedResult):
                    # Convert tool results to text representation
                    if isinstance(message.tool_output, str):
                        tool_result_text = f"[Tool Result from {message.tool_name}]: {message.tool_output}"
                        message_content = types.Part(text=tool_result_text)
                    elif isinstance(message.tool_output, list):
                        # Handle mixed content (text + images)
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
        
        # For XML client, we don't use native tool declarations
        # Tools are handled through XML parsing in the agent
        
        # Create configuration without tool parameters
        if self.endpoint == "vertex":
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
        else:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                thinking_config=types.ThinkingConfig(thinking_budget=thinking_tokens),
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
        
        for retry in range(self.max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    config=config,
                    contents=gemini_messages,
                )
                break
            except errors.APIError as e:
                # 503: The service may be temporarily overloaded or down.
                # 429: The request was throttled.
                if e.code in [503, 429]:
                    if retry == self.max_retries - 1:
                        print(f"Failed Gemini XML request after {retry + 1} retries")
                        raise e
                    else:
                        print(f"Error: {e}")
                        print(f"Retrying Gemini XML request: {retry + 1}/{self.max_retries}")
                        # Sleep 12-18 seconds with jitter to avoid thundering herd.
                        time.sleep(15 * random.uniform(0.8, 1.2))
                else:
                    raise e

        internal_messages = []
        
        # Extract text parts directly from response.candidates
        text_parts = []
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if hasattr(part, 'text') and part.text:
                        text_parts.append(part.text)
        
        if text_parts:
            combined_text = ''.join(text_parts)
            internal_messages.append(TextResult(text=combined_text))

        # For XML client, we don't process native function calls
        # All tool calling is handled through XML parsing in the agent
        
        message_metadata = {
            "raw_response": response,
            "input_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
            "output_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
        }
        
        return internal_messages, message_metadata