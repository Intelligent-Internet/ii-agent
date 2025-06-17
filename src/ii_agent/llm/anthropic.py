import os

import random
import time
from typing import Any, Tuple, cast
# 改为使用OpenAI SDK通过OpenRouter调用
from openai import OpenAI
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
import json
import logging

# 保留Anthropic的类型定义用于兼容性
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
)
from ii_agent.utils.constants import DEFAULT_MODEL

logger = logging.getLogger(__name__)


class AnthropicDirectClient(LLMClient):
    """Use Anthropic models via OpenRouter unified API."""

    def __init__(
        self,
        model_name=DEFAULT_MODEL,
        max_retries=2,
        use_caching=True,
        thinking_tokens: int = 0,
        project_id: None | str = None,
        region: None | str = None,
    ):
        """Initialize the Anthropic client via OpenRouter."""
        # 使用OpenRouter统一API
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "EMPTY")
        
        self.client = OpenAI(
            api_key=api_key, 
            base_url="https://openrouter.ai/api/v1",
            max_retries=1, 
            timeout=60 * 5
        )
        
        # 确保模型名称符合OpenRouter格式
        if not model_name.startswith("anthropic/"):
            if "claude" in model_name.lower():
                # 转换为OpenRouter格式
                model_name = "anthropic/claude-3.7-sonnet"
            else:
                model_name = "anthropic/claude-3.7-sonnet"
                
        self.model_name = model_name
        self.max_retries = max_retries
        self.use_caching = use_caching
        self.thinking_tokens = thinking_tokens
        
        # 设置OpenRouter专用headers
        self.extra_headers = {
            "HTTP-Referer": "https://github.com/ii-agent",
            "X-Title": "II-Agent",
        }
        
        # Anthropic特有功能的headers
        if "claude-opus-4" in model_name or "claude-sonnet-4" in model_name:
            self.extra_headers["anthropic-beta"] = "interleaved-thinking-2025-05-14,prompt-caching-2024-07-31"
        else:
            self.extra_headers["anthropic-beta"] = "prompt-caching-2024-07-31"

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
        """Generate responses using OpenRouter API with Anthropic models.

        Args:
            messages: A list of messages.
            max_tokens: The maximum number of tokens to generate.
            system_prompt: A system prompt.
            temperature: The temperature.
            tools: A list of tools.
            tool_choice: A tool choice.
            thinking_tokens: Number of thinking tokens for reasoning.

        Returns:
            A generated response.
        """

        # 转换为OpenAI格式的消息
        openai_messages = []
        
        # 添加系统消息
        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})

        # 转换消息格式
        for idx, message_list in enumerate(messages):
            role = "user" if isinstance(message_list[0], UserContentBlock) else "assistant"
            
            # 处理每个消息轮次中的每个消息
            for message in message_list:
                if isinstance(message, ToolFormattedResult):
                    # 工具结果总是独立的tool消息
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": message.tool_call_id,
                        "content": message.tool_output,
                    })
                elif isinstance(message, ToolCall):
                    # 工具调用需要创建assistant消息
                    openai_messages.append({
                        "role": "assistant",
                        "tool_calls": [{
                            "id": message.tool_call_id,
                            "type": "function",
                            "function": {
                                "name": message.tool_name,
                                "arguments": json.dumps(message.tool_input)
                            }
                        }]
                    })
                else:
                    # 处理其他类型的消息（文本、图片等）
                    content = self._convert_message_to_openai_format(message)
                    if content:
                        openai_messages.append({"role": role, "content": content})

        # 转换工具格式
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                }
            })

        # 转换tool_choice
        tool_choice_param = OpenAI_NOT_GIVEN
        if tool_choice:
            if tool_choice["type"] == "any":
                tool_choice_param = "required"
            elif tool_choice["type"] == "auto":
                tool_choice_param = "auto"
            elif tool_choice["type"] == "tool":
                tool_choice_param = {
                    "type": "function",
                    "function": {"name": tool_choice["name"]}
                }

        # 准备额外参数
        extra_body = {}
        if thinking_tokens is None:
            thinking_tokens = self.thinking_tokens
        if thinking_tokens and thinking_tokens > 0:
            extra_body["thinking"] = {"type": "enabled", "budget_tokens": thinking_tokens}
            temperature = 1.0

        # 调用OpenRouter API
        response = None
        for retry in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=openai_messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    tools=openai_tools if openai_tools else OpenAI_NOT_GIVEN,
                    tool_choice=tool_choice_param,
                    extra_headers=self.extra_headers,
                    extra_body=extra_body if extra_body else None,
                )
                break
            except Exception as e:
                # 检查是否是API错误响应
                error_msg = str(e)
                if "unexpected `tool_use_id` found in `tool_result` blocks" in error_msg:
                    logger.error(f"Tool sequence error: {error_msg}")
                    logger.error(f"OpenAI messages: {json.dumps(openai_messages, indent=2)}")
                    raise Exception(f"Tool sequence error in message construction: {error_msg}")
                
                if retry == self.max_retries - 1:
                    print(f"Failed OpenRouter request after {retry + 1} retries: {error_msg}")
                    raise e
                else:
                    print(f"Retrying OpenRouter request: {retry + 1}/{self.max_retries}")
                    time.sleep(15 * random.uniform(0.8, 1.2))

        # 转换响应格式
        internal_messages = []
        assert response is not None
        
        print(f"Debug: Response:\n {response}")
        # Parse response structure
        try:
            # Extract choice from response
            if hasattr(response, 'choices') and response.choices:
                choice = response.choices[0]
            else:
                # 检查是否是错误响应
                if hasattr(response, 'error'):
                    raise Exception(f"API Error: {response.error}")
                raise ValueError("LLM response is missing choices")
            
            # Extract message from choice
            if hasattr(choice, 'message'):
                message = choice.message
            else:
                raise ValueError("LLM response choice is missing message")
                
        except Exception as e:
            logger.error(f"Error parsing response structure: {e}")
            # Try to create a fallback response
            if hasattr(response, 'content'):
                internal_messages.append(TextResult(text=str(response.content)))
            elif hasattr(response, 'text'):
                internal_messages.append(TextResult(text=str(response.text)))
            else:
                internal_messages.append(TextResult(text="Error: Could not parse LLM response"))
            
            # Return fallback response
            return internal_messages, self._create_default_metadata(response)
        
        # Process the message content
        if hasattr(message, 'content') and message.content:
            # 检查是否包含意外的invoke标签
            if "</invoke>" in str(message.content):
                logger.warning("Unexpected 'invoke' tag found in message content")
            internal_messages.append(TextResult(text=message.content))
        
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tool_call in message.tool_calls:
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                
                internal_messages.append(
                    ToolCall(
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.function.name,
                        tool_input=recursively_remove_invoke_tag(args),
                    )
                )

        return internal_messages, self._create_message_metadata(response)

    def _create_default_metadata(self, response) -> dict[str, Any]:
        """Create default metadata for fallback responses."""
        return {
            "raw_response": response,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": -1,
            "cache_read_input_tokens": -1,
        }

    def _create_message_metadata(self, response) -> dict[str, Any]:
        """Create metadata from successful response."""
        return {
            "raw_response": response,
            "input_tokens": response.usage.prompt_tokens if response.usage and hasattr(response.usage, 'prompt_tokens') else 0,
            "output_tokens": response.usage.completion_tokens if response.usage and hasattr(response.usage, 'completion_tokens') else 0,
            "cache_creation_input_tokens": -1,  # OpenRouter不直接提供这些信息
            "cache_read_input_tokens": -1,
        }

    def _convert_message_to_openai_format(self, message) -> Any:
        """将内部消息格式转换为OpenAI格式"""
        if isinstance(message, TextPrompt):
            return message.text
        elif isinstance(message, TextResult):
            return message.text
        elif isinstance(message, ImageBlock):
            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{message.source['media_type']};base64,{message.source['data']}"
                }
            }
        elif isinstance(message, (AnthropicThinkingBlock, AnthropicRedactedThinkingBlock)):
            # 保持Anthropic thinking blocks的兼容性
            return str(message)
        else:
            return str(message)
