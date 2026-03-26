"""LLM client for MiniMax models via OpenAI-compatible API."""

import re
from typing import Any, Tuple

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.llm.openai import OpenAIDirectClient
from ii_agent.llm.base import AssistantContentBlock, LLMMessages, ToolParam, TextResult
from ii_agent.utils.constants import MINIMAX_API_BASE_URL

# MiniMax temperature constraints: must be in (0.0, 1.0]
MINIMAX_TEMP_MIN = 0.01
MINIMAX_TEMP_MAX = 1.0

# Pattern to match <think>...</think> blocks (including multiline)
_THINK_TAG_PATTERN = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _clamp_temperature(temperature: float) -> float:
    """Clamp temperature to MiniMax's accepted range (0.01, 1.0]."""
    if temperature <= 0.0:
        return MINIMAX_TEMP_MIN
    return min(temperature, MINIMAX_TEMP_MAX)


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from model output."""
    return _THINK_TAG_PATTERN.sub("", text).strip()


def _strip_think_tags_from_outputs(
    outputs: list[AssistantContentBlock],
) -> list[AssistantContentBlock]:
    """Strip think tags from all TextResult blocks in the output list."""
    result = []
    for block in outputs:
        if isinstance(block, TextResult):
            cleaned = _strip_think_tags(block.text)
            result.append(TextResult(text=cleaned))
        else:
            result.append(block)
    return result


class MiniMaxDirectClient(OpenAIDirectClient):
    """MiniMax LLM client extending OpenAI-compatible client.

    Handles MiniMax-specific requirements:
    - Default API base URL (https://api.minimax.io/v1)
    - Temperature clamping to (0.01, 1.0] range
    - Stripping <think>...</think> tags from model responses
    """

    def __init__(self, llm_config: LLMConfig):
        if not llm_config.base_url:
            llm_config.base_url = MINIMAX_API_BASE_URL
        super().__init__(llm_config)

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
        clamped_temp = _clamp_temperature(temperature)
        outputs, metadata = super().generate(
            messages=messages,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            temperature=clamped_temp,
            tools=tools,
            tool_choice=tool_choice,
            thinking_tokens=thinking_tokens,
        )
        return _strip_think_tags_from_outputs(outputs), metadata
