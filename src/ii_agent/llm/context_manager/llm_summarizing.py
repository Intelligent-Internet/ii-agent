import logging
from ii_agent.llm.base import GeneralContentBlock, TextPrompt, TextResult
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.llm.base import LLMClient


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
        token_budget: int = 120_000,
        max_size: int = 100,
        keep_first: int = 1,
        max_event_length: int = 10_000,
    ):
        if keep_first >= max_size // 2:
            raise ValueError(
                f"keep_first ({keep_first}) must be less than half of max_size ({max_size})"
            )
        if keep_first < 0:
            raise ValueError(f"keep_first ({keep_first}) cannot be negative")
        if max_size < 1:
            raise ValueError(f"max_size ({max_size}) cannot be non-positive")

        super().__init__(token_counter, logger, token_budget)
        self.client = client
        self.max_size = max_size
        self.keep_first = keep_first
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
            else:
                parts.append(f"{type(message).__name__}: {str(message)}")
        return "\n".join(parts)

    def should_truncate(self, message_lists: list[list[GeneralContentBlock]]) -> bool:
        """Check if condensation is needed based on the number of message lists."""
        return len(message_lists) > self.max_size or super().should_truncate(
            message_lists
        )

    def apply_truncation(
        self, message_lists: list[list[GeneralContentBlock]]
    ) -> list[list[GeneralContentBlock]]:
        """Apply truncation with LLM summarization when needed."""

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
            summary_content.replace("Conversation Summary: ", "")
            if summary_content != "No events summarized"
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
                max_tokens=4000,
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

        # Create new condensed message list
        condensed_messages = []

        # Add head messages
        condensed_messages.extend(head)

        # Add summary as a new message
        summary_message = [TextPrompt(text=f"Conversation Summary: {summary}")]
        condensed_messages.append(summary_message)

        # Add tail messages
        if events_from_tail > 0:
            condensed_messages.extend(message_lists[-events_from_tail:])

        self.logger.info(
            f"Condensed {len(message_lists)} message lists to {len(condensed_messages)} "
            f"(kept {len(head)} head + 1 summary + {events_from_tail} tail)"
        )

        return condensed_messages
