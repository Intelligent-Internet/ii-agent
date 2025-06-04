import json
import logging
from abc import ABC, abstractmethod
from typing import final
from ii_agent.llm.base import (
    GeneralContentBlock,
    TextPrompt,
    TextResult,
    ToolCall,
    ToolFormattedResult,
    ImageBlock,
)
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.llm.base import (
    AnthropicRedactedThinkingBlock,
    AnthropicThinkingBlock,
)
from ii_agent.utils.constants import TOKEN_BUDGET


class ContextManager(ABC):
    """Abstract base class for context management strategies."""

    def __init__(
        self,
        token_counter: TokenCounter,
        logger: logging.Logger,
        token_budget: int = TOKEN_BUDGET,
    ):
        self.token_counter = token_counter
        self.logger = logger
        self._token_budget = token_budget

    @property
    def token_budget(self) -> int:
        """Return the token budget."""
        return self._token_budget

    def count_tokens(self, message_lists: list[list[GeneralContentBlock]]) -> int:
        """Counts tokens, ignoring thinking blocks except in the very last message."""
        total_tokens = 0
        num_turns = len(message_lists)
        for i, message_list in enumerate(message_lists):
            is_last_turn = i == num_turns - 1
            for message in message_list:
                if isinstance(message, (TextPrompt, TextResult)):
                    total_tokens += self.token_counter.count_tokens(message.text)
                elif isinstance(message, ToolFormattedResult):
                    # Count truncated output if already truncated
                    total_tokens += self.token_counter.count_tokens(message.tool_output)
                elif isinstance(message, ToolCall):
                    # Basic counting of input JSON
                    try:
                        input_str = json.dumps(message.tool_input)
                        total_tokens += self.token_counter.count_tokens(input_str)
                    except TypeError:
                        self.logger.warning(
                            f"Could not serialize tool input for token counting: {message.tool_input}"
                        )
                        total_tokens += 100  # Add arbitrary penalty
                elif isinstance(message, ImageBlock):
                    # Images are expensive - assign a reasonable token count
                    # Typical image tokens range from 85-1700+ depending on size and detail
                    # Using a conservative estimate of 1000 tokens per image
                    total_tokens += 1000
                elif isinstance(message, AnthropicRedactedThinkingBlock):
                    pass  # Always 0 tokens
                elif isinstance(message, AnthropicThinkingBlock):
                    # Only count thinking if it's in the very last message list
                    if is_last_turn:
                        total_tokens += self.token_counter.count_tokens(
                            message.thinking
                        )
                else:
                    self.logger.warning(
                        f"Unhandled message type for token counting: {type(message)}"
                    )
        return total_tokens

    def should_truncate(self, message_lists: list[list[GeneralContentBlock]]) -> bool:
        """Check if truncation is needed based on the number of message lists."""
        return self.count_tokens(message_lists) > self._token_budget

    @final
    def apply_truncation_if_needed(
        self, message_lists: list[list[GeneralContentBlock]]
    ) -> list[list[GeneralContentBlock]]:
        if not self.should_truncate(message_lists):
            return message_lists

        current_tokens = self.count_tokens(message_lists)
        self.logger.warning(
            f"Token count {current_tokens}."
        )
        truncated_message_lists = self.apply_truncation(message_lists)
        new_token_count = self.count_tokens(truncated_message_lists)
        tokens_saved = current_tokens - new_token_count
        self.logger.info(
            f"Truncation saved ~{tokens_saved} tokens. New count: {new_token_count}"
        )
        return truncated_message_lists

    @abstractmethod
    def apply_truncation(
        self, message_lists: list[list[GeneralContentBlock]]
    ) -> list[list[GeneralContentBlock]]:
        """Apply truncation to message lists if needed."""
        pass
