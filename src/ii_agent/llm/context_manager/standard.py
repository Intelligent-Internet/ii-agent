import copy
import logging
from termcolor import colored

from ii_agent.llm.base import GeneralContentBlock, ToolCall, ToolFormattedResult
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.llm.token_counter import TokenCounter


class StandardContextManager(ContextManager):
    """Standard implementation of context management with token counting and truncation."""

    TRUNCATED_TOOL_OUTPUT_MSG = (
        "[Truncated...re-run tool if you need to see output again.]"
    )
    TRUNCATED_TOOL_INPUT_MSG = (
        "[Truncated...re-run tool if you need to see input/output again.]"
    )

    def __init__(
        self,
        token_counter: TokenCounter,
        logger: logging.Logger,
        token_budget: int = 120_000,
        truncate_keep_n_turns: int = 3,  # Number of recent turns (user+assistant pairs) to keep fully
    ):
        super().__init__(token_counter, logger, token_budget)
        self.truncate_keep_n_turns = max(1, truncate_keep_n_turns)  # Ensure at least 1
        self.truncation_history_token_savings: list[int] = []

    def apply_truncation_if_needed(
        self, message_lists: list[list[GeneralContentBlock]]
    ) -> list[list[GeneralContentBlock]]:
        """Applies truncation strategy if token count exceeds budget."""
        current_tokens = self.count_tokens(message_lists)
        if current_tokens <= self._token_budget:
            return message_lists  # No truncation needed

        self.logger.warning(
            f"Token count {current_tokens} exceeds budget {self._token_budget}. "
            f"Truncating history, keeping last {self.truncate_keep_n_turns} turns."
        )
        print(
            colored(
                f"Token count {current_tokens} exceeds budget {self._token_budget}. "
                f"Truncating history, keeping last {self.truncate_keep_n_turns} turns.",
                "yellow",
            )
        )

        # Make a deep copy to modify
        truncated_message_lists = copy.deepcopy(message_lists)

        truncation_point = len(truncated_message_lists) - self.truncate_keep_n_turns

        # Apply generic truncation to older turns
        for i in range(truncation_point):
            for message in truncated_message_lists[i]:
                if isinstance(message, ToolFormattedResult):
                    message.tool_output = self.TRUNCATED_TOOL_OUTPUT_MSG
                elif isinstance(message, ToolCall):
                    if message.tool_name == "sequential_thinking":
                        message.tool_input["thought"] = self.TRUNCATED_TOOL_INPUT_MSG
                    elif message.tool_name == "str_replace_editor":
                        if "file_text" in message.tool_input:
                            message.tool_input["file_text"] = (
                                self.TRUNCATED_TOOL_INPUT_MSG
                            )
                        if "old_str" in message.tool_input:
                            message.tool_input["old_str"] = (
                                self.TRUNCATED_TOOL_INPUT_MSG
                            )
                        if "new_str" in message.tool_input:
                            message.tool_input["new_str"] = (
                                self.TRUNCATED_TOOL_INPUT_MSG
                            )

                # We could also truncate TextPrompt/TextResult if needed
                # elif isinstance(message, TextPrompt):
                #     message.text = generic_truncation_message
                # elif isinstance(message, TextResult):
                #     message.text = generic_truncation_message

        new_token_count = self.count_tokens(truncated_message_lists)
        tokens_saved = current_tokens - new_token_count
        self.logger.info(
            f"Truncation saved ~{tokens_saved} tokens. New count: {new_token_count}"
        )
        print(
            colored(
                f" [ContextManager] Token count after truncation: {new_token_count}",
                "yellow",
            )
        )

        return truncated_message_lists
