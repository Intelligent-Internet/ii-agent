from dataclasses import dataclass
from datetime import datetime
from textwrap import dedent
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Union

from pydantic import BaseModel, Field

from ii_agent.agents.models.base import Model
from ii_agent.agents.models.metrics import Metrics
from ii_agent.agents.models.message import Message
from ii_agent.core.logger import logger

# TODO: Look into moving all managers into a separate dir
if TYPE_CHECKING:
    from ii_agent.agents.sessions.agent import AgentSession

# Default token threshold for triggering session summary creation
DEFAULT_TOKEN_THRESHOLD = 150_000

# Model-specific token thresholds (context window based)
# Models with larger context windows can have higher thresholds
MODEL_TOKEN_THRESHOLDS: Dict[str, int] = {
    # Anthropic Claude models
    "claude-opus-4-7": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-sonnet-4-5": 200_000,
    "claude-sonnet-4-5@20250929": 200_000,
    "claude-opus-4": 128_000,
    "claude-opus-4-5": 128_000,
    "claude-opus-4-5@20251101": 128_000,
    "claude-3-5-haiku": 150_000,
    # OpenAI models
    "gpt-4o": 100_000,
    "gpt-4o-mini": 100_000,
    "gpt-4-turbo": 100_000,
    "gpt-5": 300_000,
    "gpt-5.2": 300_000,
    "gpt-5-mini": 200_000,
    "gpt-5.4": 200_000,
    "gpt-5.4-pro": 200_000,
    # Google Gemini models
    "gemini-3.0-pro": 300_000,
    "gemini-3.0-flash": 300_000,
    "gemini-3-pro": 300_000,
    "gemini-3-flash": 300_000,
    "gemini-3-flash-preview": 300_000,
    "gemini-3-pro-preview": 300_000,
    "gemini-3.1-flash-lite-preview": 300_000,
}


DEFAULT_COMPACT_PROMPT = """
Your task is to create a detailed summary of the conversation so far, paying close attention to the user's explicit requests and your previous actions.
This summary should be thorough in capturing technical details, code patterns, and architectural decisions that would be essential for continuing development work without losing context.

Before providing your final summary, wrap your analysis in <analysis> tags to organize your thoughts and ensure you've covered all necessary points. In your analysis process:

1. Chronologically analyze each message and section of the conversation. For each section thoroughly identify:
   - The user's explicit requests and intents
   - Your approach to addressing the user's requests
   - Key decisions, technical concepts and code patterns
   - Specific details like file names, full code snippets, function signatures, file edits, etc
2. Double-check for technical accuracy and completeness, addressing each required element thoroughly.

Your summary should include the following sections:

1. Primary Request and Intent: Capture all of the user's explicit requests and intents in detail
2. Key Technical Concepts: List all important technical concepts, technologies, and frameworks discussed.
3. Files and Code Sections: Enumerate specific files and code sections examined, modified, or created. Pay special attention to the most recent messages and include full code snippets where applicable and include a summary of why this file read or edit is important.
4. Problem Solving: Document problems solved and any ongoing troubleshooting efforts.
5. Pending Tasks: Outline any pending tasks that you have explicitly been asked to work on.
6. Current Work: Describe in detail precisely what was being worked on immediately before this summary request, paying special attention to the most recent messages from both user and assistant. Include file names and code snippets where applicable.
7. Optional Next Step: List the next step that you will take that is related to the most recent work you were doing. IMPORTANT: ensure that this step is DIRECTLY in line with the user's explicit requests, and the task you were working on immediately before this summary request. If your last task was concluded, then only list next steps if they are explicitly in line with the users request. Do not start on tangential requests without confirming with the user first.
                       If there is a next step, include direct quotes from the most recent conversation showing exactly what task you were working on and where you left off. This should be verbatim to ensure there's no drift in task interpretation.

Here's an example of how your output should be structured:

<example>
<analysis>
[Your thought process, ensuring all points are covered thoroughly and accurately]
</analysis>

<summary>
1. Primary Request and Intent:
   [Detailed description]

2. Key Technical Concepts:
   - [Concept 1]
   - [Concept 2]
   - [...]

3. Files and Code Sections:
   - [File Name 1]
      - [Summary of why this file is important]
      - [Summary of the changes made to this file, if any]
      - [Important Code Snippet]
   - [File Name 2]
      - [Important Code Snippet]
   - [...]

4. Problem Solving:
   [Description of solved problems and ongoing troubleshooting]

5. Pending Tasks:
   - [Task 1]
   - [Task 2]
   - [...]

6. Current Work:
   [Precise description of current work]

7. Optional Next Step:
   [Optional Next step to take]

</summary>
</example>

There may be additional summarization instructions provided in the included context. If so, remember to follow these instructions when creating the above summary. Examples of instructions include:
<example>
## Compact Instructions
When summarizing the conversation focus on typescript code changes and also remember the mistakes you made and how you fixed them.
</example>

<example>
# Summary instructions
When you are using compact - please focus on test output and code changes. Include file reads verbatim.
</example>

MUST DO: Please provide your summary based on the conversation so far, following this structure and ensuring precision and thoroughness in your response.
"""


@dataclass
class SessionSummary:
    """Model for Session Summary."""

    content: str
    topics: Optional[List[str]] = None
    updated_at: Optional[datetime] = None
    metrics: Optional[Metrics] = None

    def to_dict(self) -> Dict[str, Any]:
        _dict = {
            "content": self.content,
            "topics": self.topics,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        return {k: v for k, v in _dict.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionSummary":
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            data["updated_at"] = datetime.fromisoformat(updated_at)
        metrics = data.pop("metrics", None)
        if metrics:
            metrics = Metrics(**metrics)
        data["metrics"] = metrics
        return cls(**data)


class SessionSummaryResponse(BaseModel):
    """Model for Session Summary."""

    summary: str = Field(
        ...,
        description="Summary of the session. Be concise and focus on only important information. Do not make anything up.",
    )
    topics: Optional[List[str]] = Field(None, description="Topics discussed in the session.")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)

    def to_json(self) -> str:
        return self.model_dump_json(exclude_none=True, indent=2)


@dataclass
class SessionSummaryManager:
    """Session Summary Manager"""

    # Model used for session summary generation
    model: Optional[Model] = None

    # Prompt used for session summary generation
    session_summary_prompt: Optional[str] = DEFAULT_COMPACT_PROMPT

    # User message prompt for requesting the summary
    summary_request_message: str = "Provide the structured conversation summaries"

    # Whether session summaries were created in the last run
    summaries_updated: bool = False

    # Token threshold for triggering summary creation (None = use model-based threshold)
    token_threshold: Optional[int] = None

    def _get_token_threshold(self, model_id: str) -> int:
        """Get the token threshold for the given model.

        Args:
            model_id: The model ID to get threshold for. If None, uses self.model.id

        Returns:
            Token threshold for the model, or DEFAULT_TOKEN_THRESHOLD if not found.
        """
        # Use explicit threshold if set
        if self.token_threshold is not None:
            return self.token_threshold

        return MODEL_TOKEN_THRESHOLDS.get(model_id, DEFAULT_TOKEN_THRESHOLD)

    def _count_session_tokens(self, session: "AgentSession") -> int:
        """Count total tokens used in the session from run metrics.

        Args:
            session: The agent session to count tokens from.

        Returns:
            Total token count from all runs in the session.
        """
        total_tokens = 0

        last_run = session.runs[-1] if session.runs else None
        if last_run and last_run.messages:
            for m in reversed(last_run.messages):
                if m.role in ["assistant", "model"] and m.metrics:
                    total_tokens = m.metrics.output_tokens + m.metrics.total_input_tokens
                    break

        return total_tokens

    def should_summary(
        self,
        session: "AgentSession",
    ) -> bool:
        """Check if session summary should be created based on token threshold.

        Args:
            session: The agent session to check.
            model_id: Optional model ID to use for threshold lookup.

        Returns:
            True if token count exceeds threshold and summary should be created.
        """
        token_threshold = self._get_token_threshold(self.model.id)
        session_tokens = self._count_session_tokens(session)

        should_create = session_tokens >= 0.9 * token_threshold

        if should_create:
            logger.debug(
                f"Session token count ({session_tokens}) >= threshold ({token_threshold}), "
                "will create summary"
            )
        else:
            logger.debug(
                f"Session token count ({session_tokens}) < threshold ({token_threshold}), "
                "skipping summary creation"
            )

        return should_create

    def get_response_format(self, model: "Model") -> Union[Dict[str, Any], Type[BaseModel]]:  # type: ignore
        if model.supports_native_structured_outputs:
            return SessionSummaryResponse

        elif model.supports_json_schema_outputs:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": SessionSummaryResponse.__name__,
                    "schema": SessionSummaryResponse.model_json_schema(),
                },
            }
        else:
            return {"type": "json_object"}

    def get_system_message(self, conversation: List[Message]) -> Message:
        if self.session_summary_prompt is not None:
            system_prompt = self.session_summary_prompt
        else:
            system_prompt = dedent("""\
            Analyze the following conversation between a user and an assistant, and extract the following details:
            - Summary (str): Provide a concise summary of the session, focusing on important information that would be helpful for future interactions.
            - Topics (Optional[List[str]]): List the topics discussed in the session.
            Keep the summary concise and to the point. Only include relevant information.
            """)
        conversation_messages = []
        system_prompt += "<conversation>"
        for message in conversation:
            if message.role == "user":
                # Handle empty user messages with media - note what media was provided
                if not message.content or (
                    isinstance(message.content, str) and message.content.strip() == ""
                ):
                    media_types = []
                    if hasattr(message, "images") and message.images:
                        media_types.append(f"{len(message.images)} image(s)")
                    if hasattr(message, "videos") and message.videos:
                        media_types.append(f"{len(message.videos)} video(s)")
                    if hasattr(message, "audio") and message.audio:
                        media_types.append(f"{len(message.audio)} audio file(s)")
                    if hasattr(message, "files") and message.files:
                        media_types.append(f"{len(message.files)} file(s)")

                    if media_types:
                        conversation_messages.append(f"User: [Provided {', '.join(media_types)}]")
                    # Skip empty messages with no media
                else:
                    conversation_messages.append(f"User: {message.content}")
            elif message.role in ["assistant", "model"]:
                conversation_messages.append(f"Assistant: {message.content}\n")
        system_prompt += "\n".join(conversation_messages)
        system_prompt += "</conversation>"

        return Message(role="system", content=system_prompt)

    def _prepare_summary_messages(
        self,
        session: Optional["AgentSession"] = None,
    ) -> Optional[List[Message]]:
        """Prepare messages for session summary generation. Returns None if no meaningful messages to summarize."""
        if not session:
            return None

        system_message = self.get_system_message(
            conversation=session.get_messages()  # type: ignore
        )

        if system_message is None:
            return None

        return [
            system_message,
            Message(role="user", content=self.summary_request_message),
        ]

    def _process_summary_response(
        self, summary_response, session_summary_model: "Model"
    ) -> Optional[SessionSummary]:  # type: ignore
        """Process the model response into a SessionSummary"""
        from datetime import datetime

        if summary_response is None:
            return None

        # Handle native structured outputs
        if (
            session_summary_model.supports_native_structured_outputs
            and summary_response.parsed is not None
            and isinstance(summary_response.parsed, SessionSummaryResponse)
        ):
            session_summary = SessionSummary(
                content=summary_response.parsed.summary,
                topics=summary_response.parsed.topics,
                updated_at=datetime.now(),
            )
            self.summary = session_summary
            logger.debug("Session summary created", center=True)
            return session_summary

        # Handle string responses
        if isinstance(summary_response.content, str):
            try:
                from ii_agent.agents.utils.string import parse_response_model_str

                parsed_summary: SessionSummaryResponse = parse_response_model_str(  # type: ignore
                    summary_response.content, SessionSummaryResponse
                )

                if parsed_summary is not None:
                    session_summary = SessionSummary(
                        content=parsed_summary.summary,
                        topics=parsed_summary.topics,
                        updated_at=datetime.now(),
                    )
                    self.summary = session_summary
                    logger.debug("Session summary created", center=True)
                    return session_summary
                else:
                    logger.warning("Failed to parse session summary response")

            except Exception as e:
                logger.warning(f"Failed to parse session summary response: {e}")

        return None

    async def acreate_session_summary(self, session: "AgentSession") -> Optional[SessionSummary]:
        """Creates a summary of the session.

        Args:
            session: The agent session to summarize.
            force: If True, bypasses the token threshold check and always creates a summary.

        Returns:
            SessionSummary if created, None otherwise.
        """
        logger.debug("Creating session summary")

        messages = self._prepare_summary_messages(session)

        # Skip summary generation if there are no meaningful messages
        if messages is None:
            logger.debug("No meaningful messages to summarize, skipping session summary")
            return None

        # response_format = self.get_response_format(self.model)

        summary_response = await self.model.aresponse(messages=messages, response_format=None)

        finalize_content = f"This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.\n{summary_response.content}."

        session_summary = SessionSummary(
            content=finalize_content,
            topics=None,
            updated_at=datetime.now(),
            metrics=summary_response.response_usage,
        )

        if session is not None and session_summary is not None:
            session.summary = session_summary
            self.summaries_updated = True

        return session_summary


# Backward-compat alias
AgentSummary = SessionSummary
