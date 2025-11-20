"""Context window management for chat sessions."""

import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.server.chat.models import Message, TextContent, MessageRole
from ii_agent.server.chat.message_service import MessageService
from ii_agent.db.models import Session
from ii_agent.storage.slab_checkpoint import SlabCheckpoint
from ii_agent.llm.base import GeneralContentBlock

logger = logging.getLogger(__name__)


# Model context window limits (in tokens)
CONTEXT_WINDOWS = {
    # Anthropic
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-5-haiku-20241022": 200_000,
    "claude-3-opus-20240229": 200_000,
    "claude-3-sonnet-20240229": 200_000,
    "claude-3-haiku-20240307": 200_000,

    # OpenAI
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,

    # Google
    "gemini-1.5-pro": 1_000_000,
    "gemini-1.5-flash": 1_000_000,
    "gemini-pro": 32_768,

    # Default
    "default": 128_000,
}


def calculate_checkpoint_threshold(context_window: int) -> float:
    """
    Calculate checkpoint threshold based on context window size.

    Gradient scale:
    - 64K context → 90% threshold (aggressive checkpointing)
    - 1MB context → 15% threshold (relaxed checkpointing)

    Rationale: Smaller windows need aggressive checkpointing to avoid hitting limits.
    Larger windows can afford lower rates with more headroom for context pressure.

    Args:
        context_window: Context window size in tokens

    Returns:
        Checkpoint threshold as percentage (0.0 to 1.0)
    """
    MIN_WINDOW = 64_000  # 64K tokens
    MAX_WINDOW = 1_000_000  # 1MB tokens

    MIN_THRESHOLD = 0.90  # 90% for small windows
    MAX_THRESHOLD = 0.15  # 15% for large windows

    # Clamp to bounds
    if context_window <= MIN_WINDOW:
        return MIN_THRESHOLD
    if context_window >= MAX_WINDOW:
        return MAX_THRESHOLD

    # Linear interpolation on log scale (better for exponential growth)
    import math
    log_min = math.log(MIN_WINDOW)
    log_max = math.log(MAX_WINDOW)
    log_current = math.log(context_window)

    # Normalize to 0-1 range
    normalized = (log_current - log_min) / (log_max - log_min)

    # Interpolate threshold (inverse: larger window = lower threshold)
    threshold = MIN_THRESHOLD - (normalized * (MIN_THRESHOLD - MAX_THRESHOLD))

    return threshold


class ContextWindowManager:
    """Manages context window and auto-summarization."""

    SUMMARIZATION_THRESHOLD = 0.95  # 95% of context window
    TILE_GENERATION_THRESHOLD = 0.33  # 33% - dump and generate future tiles

    _checkpoint_system: Optional[SlabCheckpoint] = None
    _tile_generator: Optional['TileGenerator'] = None
    _harmonic_miss_tracker: dict[str, list[dict]] = {}  # Track edit slips per model

    @classmethod
    def get_checkpoint_system(cls) -> SlabCheckpoint:
        """Get or create checkpoint system singleton."""
        if cls._checkpoint_system is None:
            cls._checkpoint_system = SlabCheckpoint()
        return cls._checkpoint_system

    @classmethod
    def get_tile_generator(cls):
        """Get or create tile generator singleton."""
        if cls._tile_generator is None:
            from ii_agent.storage.tile_generator import TileGenerator
            cls._tile_generator = TileGenerator(
                cls.get_checkpoint_system(),
                dump_threshold=cls.TILE_GENERATION_THRESHOLD,
            )
        return cls._tile_generator

    @classmethod
    def get_checkpoint_threshold_for_model(cls, model_id: str) -> float:
        """Get dynamic checkpoint threshold based on model's context window."""
        context_window = CONTEXT_WINDOWS.get(model_id, CONTEXT_WINDOWS["default"])
        return calculate_checkpoint_threshold(context_window)

    @classmethod
    def track_harmonic_miss(cls, model_id: str, error_type: str, context_tokens: int):
        """
        Track 'harmonic miss' - errors caused by context pressure.

        Args:
            model_id: Model identifier
            error_type: Type of error (e.g., "edit_slip", "hallucination", "inconsistency")
            context_tokens: Token count when error occurred
        """
        if model_id not in cls._harmonic_miss_tracker:
            cls._harmonic_miss_tracker[model_id] = []

        from datetime import datetime
        cls._harmonic_miss_tracker[model_id].append({
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "context_tokens": context_tokens,
            "context_window": CONTEXT_WINDOWS.get(model_id, CONTEXT_WINDOWS["default"]),
            "pressure_ratio": context_tokens / CONTEXT_WINDOWS.get(model_id, CONTEXT_WINDOWS["default"]),
        })

        # Keep last 100 errors per model
        if len(cls._harmonic_miss_tracker[model_id]) > 100:
            cls._harmonic_miss_tracker[model_id] = cls._harmonic_miss_tracker[model_id][-100:]

        logger.warning(
            f"Harmonic miss tracked for {model_id}: {error_type} at {context_tokens} tokens "
            f"({cls._harmonic_miss_tracker[model_id][-1]['pressure_ratio']:.1%} context pressure)"
        )

    @classmethod
    def get_harmonic_miss_stats(cls, model_id: str) -> dict:
        """Get harmonic miss statistics for a model."""
        errors = cls._harmonic_miss_tracker.get(model_id, [])
        if not errors:
            return {"model_id": model_id, "total_errors": 0}

        error_types = {}
        for error in errors:
            error_type = error["error_type"]
            error_types[error_type] = error_types.get(error_type, 0) + 1

        avg_pressure = sum(e["pressure_ratio"] for e in errors) / len(errors)

        return {
            "model_id": model_id,
            "total_errors": len(errors),
            "error_types": error_types,
            "avg_context_pressure": avg_pressure,
            "recent_errors": errors[-10:],  # Last 10 errors
        }

    @classmethod
    async def check_and_summarize(
        cls, *, db_session: AsyncSession, session: Session, model_id: str
    ) -> Optional[str]:
        """
        Check if summarization is needed and create summary if so.

        Args:
            db_session: Database session
            session: Session object
            model_id: Model ID for context window lookup

        Returns:
            Summary message ID if created, None otherwise
        """
        # Get context window for model
        context_window = CONTEXT_WINDOWS.get(model_id, 128_000)
        threshold = int(context_window * cls.SUMMARIZATION_THRESHOLD)

        # Check if we're at threshold
        total_tokens = session.prompt_tokens + session.completion_tokens
        if total_tokens < threshold:
            return None

        logger.info(
            f"Context window threshold reached ({total_tokens}/{context_window}). "
            f"Creating summary for session {session.id}"
        )

        # Get all messages
        messages = await MessageService.list_by_session(
            db_session=db_session,
            session_id=session.id,
            limit=1000,  # Get all messages
        )

        # Build summarization prompt
        # conversation_text = cls._build_conversation_text(messages)
        # TODO: Integrate with LLM to generate actual summary using conversation_text
        # summary_prompt = f"""Please provide a concise summary of the following conversation,
        # focusing on key points, decisions, and context that would be important to continue the conversation.
        # Conversation: {conversation_text}
        # Summary:"""

        # Create summary message (simplified - in real implementation, call LLM)
        # For now, create a placeholder summary
        summary_text = f"[Summary of {len(messages)} messages, {total_tokens} tokens]"

        summary_message = await MessageService.create_message(
            db_session=db_session,
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            model_id=model_id,
            parts=[TextContent(text=summary_text)],
        )

        # Update session with summary_message_id
        session.summary_message_id = str(summary_message.id)
        await db_session.commit()

        logger.info(f"Created summary message {summary_message.id}")
        return summary_message.id

    @classmethod
    def _build_conversation_text(cls, messages: List[Message]) -> str:
        """Build text representation of conversation."""
        lines = []
        for msg in messages:
            text_part = msg.content()
            if text_part:
                lines.append(f"{msg.role.value}: {text_part.text}")
        return "\n\n".join(lines)

    @classmethod
    async def get_messages_with_summary(
        cls,
        *,
        db_session: AsyncSession,
        session_id: str,
        summary_message_id: Optional[str],
    ) -> List[Message]:
        """
        Get messages filtered from summary point.

        Args:
            db_session: Database session
            session_id: Session ID
            summary_message_id: Summary message ID (filter point)

        Returns:
            Messages from summary onward, with summary role changed to USER
        """
        messages = await MessageService.list_by_session(
            db_session=db_session, session_id=session_id, limit=1000
        )

        if not summary_message_id:
            return messages

        # Find summary message index
        summary_index = -1
        for i, msg in enumerate(messages):
            if msg.id == summary_message_id:
                summary_index = i
                break

        if summary_index == -1:
            logger.warning(
                f"Summary message {summary_message_id} not found, returning all messages"
            )
            return messages

        # Keep messages from summary onward
        filtered_messages = messages[summary_index:]

        # Change summary message role to USER so LLM sees it as context
        if filtered_messages:
            filtered_messages[0].role = MessageRole.USER

        logger.info(
            f"Filtered history from {len(messages)} to {len(filtered_messages)} messages using summary"
        )
        return filtered_messages


    @classmethod
    async def dump_and_tile_if_needed(
        cls,
        *,
        messages: List[Message],
        model_id: str = "default",
    ) -> Optional[Dict]:
        """
        Check if should dump and generate tiles (at 33% context).

        Returns:
            Dump metadata if created, None otherwise
        """
        context_window = CONTEXT_WINDOWS.get(model_id, CONTEXT_WINDOWS["default"])
        total_tokens = sum(msg.tokens or 0 for msg in messages)

        tile_generator = cls.get_tile_generator()

        if tile_generator.should_dump_and_tile(total_tokens, context_window):
            # Convert messages to GeneralContentBlock format
            from ii_agent.llm.base import TextPrompt, TextResult
            message_lists = []
            for msg in messages:
                content = msg.content()
                if content and content.text:
                    if msg.role == MessageRole.USER:
                        message_lists.append([TextPrompt(text=content.text)])
                    else:
                        message_lists.append([TextResult(text=content.text)])

            # Dump and generate tiles
            result = await tile_generator.dump_and_generate_tiles(
                message_lists, context_window
            )

            logger.info(
                f"Dumped at 33% ({total_tokens}/{context_window}), "
                f"generated {len(result['tiles_generated'])} tiles, "
                f"retained {len(result['retained_breadcrumbs'])} breadcrumbs"
            )

            return result

        return None

    @classmethod
    async def create_checkpoint_if_needed(
        cls,
        *,
        messages: List[Message],
        model_id: str = "default",
    ) -> Optional[str]:
        """
        Create checkpoint if at threshold (context NOT evicted).
        Uses model-specific dynamic threshold based on context window size.

        Args:
            messages: List of messages to checkpoint
            model_id: Model identifier for threshold calculation

        Returns:
            Checkpoint ID if created, None otherwise
        """
        context_window = CONTEXT_WINDOWS.get(model_id, CONTEXT_WINDOWS["default"])
        checkpoint_threshold_pct = cls.get_checkpoint_threshold_for_model(model_id)
        checkpoint_threshold = int(context_window * checkpoint_threshold_pct)

        total_tokens = sum(msg.tokens or 0 for msg in messages)

        if total_tokens < checkpoint_threshold:
            return None

        logger.info(
            f"Checkpoint threshold reached for {model_id}: {total_tokens}/{checkpoint_threshold} "
            f"({checkpoint_threshold_pct:.0%} of {context_window} context window). "
            f"Creating checkpoint (context NOT evicted)"
        )

        # Convert messages to GeneralContentBlock format (full conversion)
        from ii_agent.llm.base import (
            TextPrompt, TextResult, ToolCall as BaseToolCall,
            ToolFormattedResult, ThinkingBlock
        )
        message_lists = []
        for msg in messages:
            content_blocks = []
            for part in msg.parts:
                if hasattr(part, 'text') and part.text:
                    if msg.role == MessageRole.USER:
                        content_blocks.append(TextPrompt(text=part.text))
                    elif msg.role == MessageRole.ASSISTANT:
                        content_blocks.append(TextResult(text=part.text))
                elif hasattr(part, 'tool_calls') and part.tool_calls:
                    for tool_call in part.tool_calls:
                        content_blocks.append(BaseToolCall(
                            tool_name=tool_call.name,
                            tool_input=tool_call.input
                        ))
                elif hasattr(part, 'tool_name') and hasattr(part, 'tool_output'):
                    content_blocks.append(ToolFormattedResult(
                        tool_name=part.tool_name,
                        tool_output=part.tool_output
                    ))

            if content_blocks:
                message_lists.append(content_blocks)

        # Create checkpoint system and generate microkernel BEFORE checkpoint
        checkpoint_system = cls.get_checkpoint_system()
        microkernel = checkpoint_system._generate_microkernel(message_lists)

        # Create checkpoint with microkernel (context NOT evicted)
        slab_id = await checkpoint_system.create_checkpoint(
            message_lists, microkernel=microkernel
        )

        logger.info(
            f"Created checkpoint {slab_id} with microkernel "
            f"({len(microkernel.get('tasks', []))} tasks, "
            f"{len(microkernel.get('goals', []))} goals, "
            f"{len(microkernel.get('important_breadcrumbs', []))} breadcrumbs)"
        )
        return slab_id

    @classmethod
    def reduce_message_tokens(cls, messages: List[Message]) -> List[Message]:
        """
        Reduce message list if total tokens >= 90% of 128k context window.
        Removes oldest messages until reaching a user message with remaining tokens < threshold.

        Args:
            messages: List of messages to potentially reduce (must be in chronological order)

        Returns:
            Reduced list of messages starting from a user message (or original if under threshold)
        """
        MAX_CONTEXT = 128_000
        REDUCTION_THRESHOLD = int(MAX_CONTEXT * 0.9)  # 115,200 tokens

        # Calculate total tokens
        total_tokens = sum(msg.tokens or 0 for msg in messages)

        # If under threshold, return original list
        if total_tokens < REDUCTION_THRESHOLD:
            logger.debug(
                f"Messages under threshold: {total_tokens}/{REDUCTION_THRESHOLD} tokens"
            )
            return messages

        logger.info(
            f"Reducing messages: {total_tokens} tokens >= {REDUCTION_THRESHOLD} threshold"
        )

        # Remove messages from beginning until we hit a user message and are under threshold
        current_tokens = total_tokens
        start_index = 0

        for i, msg in enumerate(messages):
            # Subtract current message tokens
            current_tokens -= msg.tokens or 0

            # Check if this is a user message AND we're now under threshold
            if msg.role == MessageRole.USER and current_tokens < REDUCTION_THRESHOLD:
                start_index = i
                break

        if start_index >= len(messages):
            return messages

        # Return messages starting from the found user message
        reduced_messages = messages[start_index:]

        final_tokens = sum(msg.tokens or 0 for msg in reduced_messages)
        logger.info(
            f"Reduced from {len(messages)} to {len(reduced_messages)} messages "
            f"({total_tokens} -> {final_tokens} tokens)"
        )

        return reduced_messages
