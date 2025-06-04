import logging
from ii_agent.llm.base import GeneralContentBlock, TextPrompt, TextResult, AnthropicThinkingBlock, AnthropicRedactedThinkingBlock
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.llm.base import LLMClient
from ii_agent.utils.constants import TOKEN_BUDGET, SUMMARY_MAX_TOKENS


class LLMSummarizingContextManager(ContextManager):
    """A context manager that summarizes forgotten events using LLM.

    Maintains a condensed history and forgets old events when it grows too large,
    keeping a special summarization event after the prefix that summarizes all previous
    summarizations and newly forgotten events.
    """

    def __init__(
        self,
        client: LLMClient,
        token_counter: TokenCounter,
        logger: logging.Logger,
        token_budget: int = TOKEN_BUDGET,
        max_size: int = 100,
        max_event_length: int = 10_000,
    ):
        if max_size < 1:
            raise ValueError(f"max_size ({max_size}) cannot be non-positive")

        super().__init__(token_counter, logger, token_budget)
        self.client = client
        self.max_size = max_size
        self.keep_first = 1
        self.max_event_length = max_event_length

    def _truncate_content(self, content: str) -> str:
        """Truncate the content to fit within the specified maximum event length."""
        if len(content) <= self.max_event_length:
            return content
        return content[: self.max_event_length] + "... [truncated]"

    def _message_list_to_string(self, message_list: list[GeneralContentBlock]) -> str:
        """Convert a message list to a string representation."""
        parts = []
        for message in message_list:
            if isinstance(message, TextPrompt):
                parts.append(f"USER: {message.text}")
            elif isinstance(message, TextResult):
                parts.append(f"ASSISTANT: {message.text}")
            elif isinstance(message, AnthropicThinkingBlock):
                parts.append(f"ASSISTANT: {message.thinking}")
            elif isinstance(message, AnthropicRedactedThinkingBlock):
                continue
            else:
                parts.append(f"{type(message).__name__}: {str(message)}")
        return "\n".join(parts)

    def should_truncate(self, message_lists: list[list[GeneralContentBlock]]) -> bool:
        """Check if condensation is needed based on the number of message lists."""
        return len(message_lists) > self.max_size or super().should_truncate(
            message_lists
        )

    def _has_thinking_blocks(self, message_lists: list[list[GeneralContentBlock]]) -> bool:
        """Check if any message lists contain ThinkingBlock or RedactedThinkingBlock."""
        for message_list in message_lists:
            for message in message_list:
                if isinstance(message, (AnthropicThinkingBlock, AnthropicRedactedThinkingBlock)):
                    return True
        return False

    def _find_last_text_prompt_index(self, message_lists: list[list[GeneralContentBlock]]) -> int:
        """Find the index of the last message list that contains a TextPrompt."""
        for i in range(len(message_lists) - 1, -1, -1):
            for message in message_lists[i]:
                if isinstance(message, TextPrompt):
                    return i
        return len(message_lists) - 1  # Fallback to last index

    def apply_truncation(
        self, message_lists: list[list[GeneralContentBlock]]
    ) -> list[list[GeneralContentBlock]]:
        """Apply truncation with LLM summarization when needed."""
        # Check if we have thinking blocks and route to appropriate method
        has_thinking_blocks = self._has_thinking_blocks(message_lists)
        
        if has_thinking_blocks:
            return self._apply_truncation_with_thinking_blocks(message_lists)
        else:
            return self._apply_truncation_without_thinking_blocks(message_lists)

    def _apply_truncation_with_thinking_blocks(
        self, message_lists: list[list[GeneralContentBlock]]
    ) -> list[list[GeneralContentBlock]]:
        """Apply truncation when thinking blocks are present - only truncate before last TextPrompt."""
        # New logic: only truncate before the last user message (TextPrompt)
        last_prompt_index = self._find_last_text_prompt_index(message_lists)
        
        # If we only have one or no TextPrompt, don't truncate
        if last_prompt_index <= 0:
            return message_lists
            
        # target size is half of the max size but we must keep from last text prompt onwards
        target_size = min(self.max_size, len(message_lists)) // 2
        last_summary_index = min(last_prompt_index, self.keep_first + target_size)
        events_to_summarize = message_lists[self.keep_first:last_summary_index]
        events_to_keep = message_lists[last_summary_index:]

        
        if len(events_to_summarize) <= 1: # If there is only one event to summarize, don't summarize
            self.logger.info(
                "No events to summarize, returning original message lists"
            )
            return message_lists
            
        # Generate summary for events before the last TextPrompt
        summary = self._generate_summary(events_to_summarize)
        
        # Create condensed message list with summary + events from last TextPrompt
        condensed_messages = []
        condensed_messages.extend(message_lists[:self.keep_first])
        summary_message = [TextResult(text=f"Conversation Summary: {summary}")]
        condensed_messages.append(summary_message)
        condensed_messages.extend(events_to_keep)
        
        self.logger.info(
            f"Condensed {len(message_lists)} message lists to {len(condensed_messages)} "
            f"(kept {self.keep_first} head + 1 summary + {len(events_to_keep)} from last TextPrompt onwards)"
        )
        
        return condensed_messages

    def _apply_truncation_without_thinking_blocks(
        self, message_lists: list[list[GeneralContentBlock]]
    ) -> list[list[GeneralContentBlock]]:
        """Apply truncation when no thinking blocks are present - use original logic."""
        head = message_lists[: self.keep_first]
        target_size = min(self.max_size, len(message_lists)) // 2
        events_from_tail = target_size - len(head) - 1

        # Check if we already have a summary in the expected position
        summary_content = "No events summarized"
        summary_start_idx = self.keep_first

        if (
            len(message_lists) > self.keep_first
            and message_lists[self.keep_first]
            and isinstance(message_lists[self.keep_first][0], TextPrompt)
            and message_lists[self.keep_first][0].text.startswith(
                "Conversation Summary:"
            )
        ):  # TODO: this is a hack to get the summary from the previous summary
            summary_content = message_lists[self.keep_first][0].text
            summary_start_idx = self.keep_first + 1

        # Identify events to be forgotten (those not in head or tail)
        forgotten_events = (
            message_lists[summary_start_idx:-events_from_tail]
            if events_from_tail > 0
            else message_lists[summary_start_idx:]
        )

        if not forgotten_events:
            return message_lists

        # Generate summary using existing logic
        summary = self._generate_summary(forgotten_events, summary_content)

        # Create new condensed message list
        condensed_messages = []

        # Add head messages
        condensed_messages.extend(head)

        # Add summary as a new message
        summary_message = [TextResult(text=f"Conversation Summary: {summary}")]
        condensed_messages.append(summary_message)

        # Add tail messages
        if events_from_tail > 0:
            condensed_messages.extend(message_lists[-events_from_tail:])

        self.logger.info(
            f"Condensed {len(message_lists)} message lists to {len(condensed_messages)} "
            f"(kept {len(head)} head + 1 summary + {events_from_tail} tail)"
        )

        return condensed_messages

    def _generate_summary(self, forgotten_events: list[list[GeneralContentBlock]], previous_summary_content: str = "No events summarized") -> str:
        """Generate a summary for the given forgotten events."""
        # Construct prompt for summarization
        prompt = """You are maintaining a context-aware state summary for an interactive agent. You will be given a list of events corresponding to actions taken by the agent, and the most recent previous summary if one exists. Track:

USER_CONTEXT: (Preserve essential user requirements, goals, and clarifications in concise form)

COMPLETED: (Tasks completed so far, with brief results)
PENDING: (Tasks that still need to be done)
CURRENT_STATE: (Current variables, data structures, or relevant state)

For code-specific tasks, also include:
CODE_STATE: {File paths, function signatures, data structures}
TESTS: {Failing cases, error messages, outputs}
CHANGES: {Code edits, variable updates}
DEPS: {Dependencies, imports, external calls}
VERSION_CONTROL_STATUS: {Repository state, current branch, PR status, commit history}

PRIORITIZE:
1. Adapt tracking format to match the actual task type
2. Capture key user requirements and goals
3. Distinguish between completed and pending tasks
4. Keep all sections concise and relevant

SKIP: Tracking irrelevant details for the current task type

Example formats:

For code tasks:
USER_CONTEXT: Fix FITS card float representation issue
COMPLETED: Modified mod_float() in card.py, all tests passing
PENDING: Create PR, update documentation
CODE_STATE: mod_float() in card.py updated
TESTS: test_format() passed
CHANGES: str(val) replaces f"{val:.16G}"
DEPS: None modified
VERSION_CONTROL_STATUS: Branch: fix-float-precision, Latest commit: a1b2c3d

For other tasks:
USER_CONTEXT: Write 20 haikus based on coin flip results
COMPLETED: 15 haikus written for results [T,H,T,H,T,H,T,T,H,T,H,T,H,T,H]
PENDING: 5 more haikus needed
CURRENT_STATE: Last flip: Heads, Haiku count: 15/20

"""

        # Add the previous summary if it exists
        previous_summary = (
            previous_summary_content.replace("Conversation Summary: ", "")
            if previous_summary_content != "No events summarized"
            else ""
        )
        prompt += f"<PREVIOUS SUMMARY>\n{self._truncate_content(previous_summary)}\n</PREVIOUS SUMMARY>\n\n"

        # Add all events that are being forgotten
        for i, forgotten_event in enumerate(forgotten_events):
            event_content = self._truncate_content(
                self._message_list_to_string(forgotten_event)
            )
            prompt += f"<EVENT id={i}>\n{event_content}\n</EVENT>\n"

        prompt += "\nNow summarize the events using the rules above."
        
        # Generate summary using LLM
        try:
            summary_messages = [[TextPrompt(text=prompt)]]
            model_response, _ = self.client.generate(
                messages=summary_messages,
                max_tokens=SUMMARY_MAX_TOKENS,
                thinking_tokens=0,
            )
            summary = ""
            for message in model_response:
                if isinstance(message, TextResult):
                    summary += message.text

            self.logger.info(
                f"Generated summary for {len(forgotten_events)} forgotten events"
            )

        except Exception as e:
            self.logger.error(f"Failed to generate summary: {e}")
            summary = f"Failed to summarize {len(forgotten_events)} events due to error: {str(e)}"

        return summary
