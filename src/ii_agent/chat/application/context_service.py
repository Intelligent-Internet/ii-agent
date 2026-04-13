"""Context window management for chat sessions."""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ii_agent.chat.types import (
    Message,
    TextContent,
    MessageRole,
    CouncilMemberOutput,
    CouncilSynthesis,
)
from ii_agent.chat.messages.service import MessageService
from ii_agent.chat.messages.models import ChatSummary
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.chat.llm import LLMProviderFactory
from ii_agent.chat.prompts.context_prompts import PREVIOUS_SUMMARY, SUMMARY_PROMPT

logger = logging.getLogger(__name__)


# Model context window limits (in tokens)
CONTEXT_WINDOWS = {
    # OpenAI Models - https://platform.openai.com/docs/models/gpt-5
    "gpt-5": 200000,
    # Anthropic Models
    "claude-opus-4-5@20251101": 200000,
    "claude-sonnet-4-5@20250929": 200000,
    "claude-sonnet-4@20250514": 200000,
    # Google Models
    "gemini/gemini-3-pro-preview": 200000,
    # Default fallback
    "__default__": 128000,
}


class ContextWindowManager:
    """Enhanced context manager with summarization."""

    SUMMARIZATION_THRESHOLD = 0.90  # Summarize at 90%
    EMERGENCY_THRESHOLD = 0.90  # Emergency compression at 90%

    # ==== PHASE 1: LOAD CONTEXT ====

    @classmethod
    async def load_context_for_llm(
        cls,
        *,
        db_session: AsyncSession,
        session_id: uuid.UUID,
    ) -> List[Message]:
        """
        Load existing context for LLM call.
        """
        # 1. Load active summary
        summary = await cls._get_active_summary(db_session, session_id)

        # 2. Load messages after summary
        if summary:
            messages = await MessageService().list_messages_after_id(
                db_session,
                session_id=session_id,
                after_message_id=summary.end_message_id,
                limit=1000,
            )
        else:
            messages = await MessageService().list_by_session(
                db_session,
                session_id=session_id,
                limit=1000,
            )

        # 3. Build context
        context = []
        if summary:
            summary_msg = Message(
                id=uuid.uuid4(),
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                parts=[
                    TextContent(
                        text=f"""[Conversation summary up to this point]
                        {PREVIOUS_SUMMARY.format(parent_summary_text=summary.summary_text)}
                        """
                    )
                ],
                tokens=summary.summary_tokens,
                created_at=int(summary.created_at.timestamp()),
                updated_at=int(summary.created_at.timestamp()),
            )
            context.append(summary_msg)
        context.extend(messages)

        # Collapse council messages: replace council member outputs with synthesis-only text
        context = cls._collapse_council_messages(context)

        logger.info(f"Loaded context: summary={'Yes' if summary else 'No'}")

        return context

    # ==== PHASE 2: EMERGENCY COMPRESSION (During Tool Loop) ====

    @classmethod
    async def compress_context_if_needed(
        cls,
        *,
        db_session: AsyncSession,
        messages: List[Message],
        session_id: uuid.UUID,
        llm_config: ModelConfig,
        user_id: uuid.UUID,
    ) -> List[Message]:
        """
        Emergency compression during tool execution loop.

        Only called if context grows too large mid-execution.
        """
        max_context = CONTEXT_WINDOWS.get(llm_config.model, CONTEXT_WINDOWS["__default__"])
        threshold = int(max_context * cls.EMERGENCY_THRESHOLD)

        # Calculate total tokens
        total_tokens = sum(msg.tokens or 0 for msg in messages)

        if total_tokens < threshold:
            return messages

        logger.warning(f"Emergency compression: {total_tokens} tokens exceeds {threshold}")

        # Get parent summary
        parent_summary = await cls._get_active_summary(db_session, session_id)

        ### Determine what to summarize
        ## sum_0 + [(u1, a1), (u2, a2)] < threshold        ---> continue
        ## sum_0 + [(u1, a1), (u2, a2), (u3)] > threshold  ---> summarize
        ## => _____  sum_1  ________  + (u3)

        # Find last user message - keep from there onwards
        last_user_idx = cls._find_last_user_message(messages)
        if last_user_idx == -1:
            last_user_idx = len(messages) // 2

        if parent_summary:
            messages_to_summarize = messages[1:last_user_idx]  # Skip summary message at index 0
        else:
            messages_to_summarize = messages[:last_user_idx]

        messages_to_keep = messages[last_user_idx:]

        if not messages_to_summarize:
            return messages

        # Create new summary
        new_summary = await cls.create_chained_summary(
            db_session=db_session,
            session_id=session_id,
            messages=messages_to_summarize,
            parent_summary=parent_summary,
            llm_config=llm_config,
            user_id=user_id,
            summary_authority="native",
        )

        # Build compressed context
        compressed = []

        new_summary_msg = Message(
            id=uuid.uuid4(),
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            parts=[
                TextContent(
                    text=f"[Conversation summary up to this point]\n{new_summary.summary_text}"
                )
            ],
            tokens=new_summary.summary_tokens,
            created_at=int(new_summary.created_at.timestamp()),
            updated_at=int(new_summary.created_at.timestamp()),
        )
        compressed.append(new_summary_msg)
        compressed.extend(messages_to_keep)

        new_total = sum(m.tokens or 0 for m in compressed)
        logger.info(
            f"Compressed: {len(messages)} → {len(compressed)} messages, "
            f"{total_tokens} → {new_total} tokens"
        )

        return compressed

    # ==== PHASE 3: MAIN SUMMARIZATION (After Response) ====

    @classmethod
    async def check_and_summarize_after_response(
        cls,
        *,
        db_session: AsyncSession,
        session_id: uuid.UUID,
        llm_config: ModelConfig,
        user_id: uuid.UUID,
    ) -> None:
        """
        Check and summarize AFTER LLM response completes.

        This is the MAIN summarization checkpoint.
        Called after assistant response is saved.

        Skipped when the per-session compaction lock is held, which
        indicates an A2A-delegated turn is active (the CLI backend
        manages its own context compaction).
        """
        from ii_agent.chat.application.compaction_lock import is_compaction_locked

        if is_compaction_locked(session_id):
            logger.info(
                "Skipping native summarization — A2A turn active for session %s "
                "[event=agent.compaction.skipped, reason=a2a_lock_held]",
                session_id,
            )
            return

        max_context = CONTEXT_WINDOWS.get(llm_config.model, CONTEXT_WINDOWS["__default__"])
        threshold = int(max_context * cls.SUMMARIZATION_THRESHOLD)

        # 1. Load active summary
        active_summary = await cls._get_active_summary(db_session, session_id)

        # 2. Load ALL messages (including newly created ones)
        if active_summary:
            all_messages = await MessageService().list_messages_after_id(
                db_session,
                session_id=session_id,
                after_message_id=active_summary.end_message_id,
                limit=1000,
            )
            summary_tokens = active_summary.summary_tokens
        else:
            all_messages = await MessageService().list_by_session(
                db_session,
                session_id=session_id,
                limit=1000,
            )
            summary_tokens = 0

        # 3. Calculate total tokens
        message_tokens = sum(msg.tokens or 0 for msg in all_messages)
        total_tokens = summary_tokens + message_tokens

        logger.info(
            f"Post-response check: summary={summary_tokens}, "
            f"messages={message_tokens}, total={total_tokens}/{threshold}"
        )

        # 4. Check if summarization needed
        if total_tokens < threshold:
            logger.info("Under threshold, no summarization needed")
            return

        logger.info(f"Threshold exceeded ({total_tokens}/{threshold}), creating summary")

        ### 5. Determine what to summarize
        ## sum_0 + [(u1, a1), (u2, a2)] < threshold             ---> continue
        ## sum_0 + [(u1, a1), (u2, a2), (u3 + a3)] > threshold  ---> summarize
        ## => _____  sum_1  ________  + (u3 + a3)

        # Find last user message - keep from there onwards
        last_user_idx = cls._find_last_user_message(all_messages)
        if last_user_idx == -1:
            last_user_idx = len(all_messages) // 2

        messages_to_summarize = all_messages[:last_user_idx]
        messages_to_keep = all_messages[last_user_idx:]

        if not messages_to_summarize:
            logger.warning("No messages to summarize, skipping summarization")
            return

        # 6. Create new chained summary
        new_summary = await cls.create_chained_summary(
            db_session=db_session,
            session_id=session_id,
            messages=messages_to_summarize,
            parent_summary=active_summary,
            llm_config=llm_config,
            user_id=user_id,
            summary_authority="native",
        )

        logger.info(
            f"Created summary {new_summary.id}: "
            f"compressed {len(messages_to_summarize)} messages, "
            f"{message_tokens} → {new_summary.summary_tokens} tokens, "
            f"kept {len(messages_to_keep)} recent messages"
        )

    # ==== HELPER METHODS ====

    @classmethod
    async def create_chained_summary(
        cls,
        *,
        db_session: AsyncSession,
        session_id: uuid.UUID,
        messages: List[Message],
        parent_summary: Optional[ChatSummary],
        llm_config: ModelConfig,
        user_id: uuid.UUID,
        summary_authority: str = "native",
    ) -> ChatSummary:
        """Create new summary, optionally chaining from parent.

        Parameters
        ----------
        summary_authority:
            Identifier for the compaction system creating this summary.
            Typically ``"native"`` for ii-agent's own summarizer.  Used to
            prevent cross-authority chaining (e.g., native summary chaining
            from an A2A-created summary).
        """

        # Guard: do not chain from a summary created by a different authority.
        if (
            parent_summary is not None
            and parent_summary.summary_authority is not None
            and parent_summary.summary_authority != summary_authority
        ):
            logger.warning(
                "Cross-authority summary chaining prevented: "
                "active summary %s has authority '%s', current authority is '%s'. "
                "Creating standalone summary for session %s.",
                parent_summary.id,
                parent_summary.summary_authority,
                summary_authority,
                session_id,
            )
            parent_summary = None

        # Generate summary text via LLM
        summary_text, summary_tokens = await SummarizationService.generate_summary(
            messages=messages,
            llm_config=llm_config,
            user_id=user_id,
            db_session=db_session,
            parent_summary_text=parent_summary.summary_text if parent_summary else None,
        )

        # Calculate tokens
        original_tokens = sum(msg.tokens or 0 for msg in messages)

        logger.info(f"Original tokens: {original_tokens}")
        logger.info(f"Summary tokens: {summary_tokens}")
        logger.info(f"Summary text: {summary_text}")

        # Create DB record
        summary = ChatSummary(
            id=uuid.uuid4(),
            session_id=session_id,
            summary_text=summary_text,
            end_message_id=messages[-1].id,  # Last message summarized
            original_tokens=original_tokens,
            summary_tokens=summary_tokens,
            compression_ratio=original_tokens / max(summary_tokens, 1),
            model_id=llm_config.setting_id,
            parent_summary_id=parent_summary.id if parent_summary else None,
            summary_authority=summary_authority,
            created_at=datetime.now(timezone.utc),
        )

        db_session.add(summary)
        await db_session.commit()
        await db_session.refresh(summary)

        logger.info(
            f"Created summary: {original_tokens} → {summary_tokens} tokens "
            f"(ratio: {summary.compression_ratio:.1f}x)"
        )

        return summary

    @classmethod
    async def _get_active_summary(
        cls,
        db_session: AsyncSession,
        session_id: uuid.UUID,
    ) -> Optional[ChatSummary]:
        """Get most recent summary (highest end_message_id)."""
        result = await db_session.execute(
            select(ChatSummary)
            .where(ChatSummary.session_id == session_id)
            .order_by(ChatSummary.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @classmethod
    def _collapse_council_messages(cls, messages: List[Message]) -> List[Message]:
        """Collapse council assistant messages to synthesis-only text.

        For messages containing CouncilMemberOutput parts, replace the entire
        message's parts with just the synthesis text (or a placeholder if no
        synthesis is available). This prevents context window explosion from
        N model outputs per council turn.
        """
        collapsed = []
        for msg in messages:
            if msg.role != MessageRole.ASSISTANT:
                collapsed.append(msg)
                continue

            has_council_parts = any(
                isinstance(p, (CouncilMemberOutput, CouncilSynthesis)) for p in msg.parts
            )
            if not has_council_parts:
                collapsed.append(msg)
                continue

            # Extract synthesis content
            synthesis_text = None
            for p in msg.parts:
                if isinstance(p, CouncilSynthesis):
                    synthesis_text = p.content
                    break

            if not synthesis_text:
                synthesis_text = "[Council response - synthesis unavailable]"

            # Estimate tokens for collapsed content (original tokens reflect
            # all N council outputs, not just the synthesis text)
            estimated_tokens = len(synthesis_text) // 4 if synthesis_text else 0

            collapsed_msg = Message(
                id=msg.id,
                role=msg.role,
                session_id=msg.session_id,
                parts=[TextContent(text=synthesis_text)],
                model=msg.model,
                provider=msg.provider,
                created_at=msg.created_at,
                updated_at=msg.updated_at,
                file_ids=msg.file_ids,
                tokens=estimated_tokens,
                tools_enabled=msg.tools_enabled,
                metadata=msg.metadata,
                provider_metadata=msg.provider_metadata,
                finish_reason=msg.finish_reason,
            )
            collapsed.append(collapsed_msg)

        return collapsed

    @classmethod
    def _find_last_user_message(cls, messages: List[Message]) -> int:
        """Find index of last USER message."""
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].role == MessageRole.USER:
                return i
        return -1


#######
## SummarizationService
#######
"""Service for generating conversation summaries using LLM."""


class SummarizationService:
    """Generate LLM-based summaries for chat context."""

    @classmethod
    async def generate_summary(
        cls,
        *,
        messages: List[Message],
        llm_config: ModelConfig,
        user_id: uuid.UUID,
        db_session: AsyncSession,
        parent_summary_text: Optional[str] = None,
    ) -> str:
        """
        Generate LLM summary, optionally chaining from parent summary.

        Args:
            messages: Messages to summarize
            model_id: Model to use for summarization
            user_id: User ID
            db_session: Database session
            parent_summary_text: Text from parent summary (for chaining)

        Returns:
            Summary text
        """

        # Build conversation text
        conversation_text = cls._build_conversation_text(messages)

        # Build prompt with optional parent summary
        previous_summary_section = ""
        if parent_summary_text:
            previous_summary_section = PREVIOUS_SUMMARY.format(
                parent_summary_text=parent_summary_text
            )

        prompt = SUMMARY_PROMPT.format(
            previous_summary_section=previous_summary_section,
            conversation_text=conversation_text,
        )

        provider = LLMProviderFactory.create_provider(llm_config)

        # Generate summary
        summary_message = Message(
            id=uuid.uuid4(),
            role=MessageRole.USER,
            parts=[TextContent(text=prompt)],
            session_id=uuid.UUID(int=0),  # Placeholder, not stored
            created_at=int(datetime.now(timezone.utc).timestamp()),
            updated_at=int(datetime.now(timezone.utc).timestamp()),
        )

        try:
            run_response = await provider.send(
                messages=[summary_message],
                tools=[],
            )

            summary = (
                run_response.content
                if isinstance(run_response.content, str)
                else "".join(getattr(p, "text", str(p)) for p in run_response.content)
            )
            logger.info(
                f"Generated summary for {len(messages)} messages "
                f"({'with' if parent_summary_text else 'without'} parent summary)"
            )
            return summary, run_response.usage.total_tokens

        except Exception as e:
            logger.error(f"Failed to generate summary: {e}", exc_info=True)
            # Fallback: Simple concatenation
            return cls._create_fallback_summary(messages, parent_summary_text)

    @classmethod
    def _build_conversation_text(cls, messages: List[Message]) -> str:
        """
        Build text representation for summarization.

        Focus on USER input and ASSISTANT final responses only.
        Skip: tool calls, tool results, reasoning/thinking, images, etc.
        """
        from ii_agent.chat.types import TextContent

        lines = []
        for msg in messages:
            if msg.role == MessageRole.USER:
                # Extract only text content from user (skip images, files)
                text_parts = [p.text for p in msg.parts if isinstance(p, TextContent)]
                if text_parts:
                    user_text = " ".join(text_parts)
                    line = f"USER: {user_text}"
                    lines.append(line)

            elif msg.role == MessageRole.ASSISTANT:
                # Extract only TextContent (skip ToolCall, ToolResult, ReasoningContent)
                text_parts = [p.text for p in msg.parts if isinstance(p, TextContent)]
                if text_parts:
                    assistant_text = " ".join(text_parts)
                    line = f"ASSISTANT: {assistant_text}"
                    lines.append(line)

        return "\n\n".join(lines)

    @classmethod
    def _create_fallback_summary(
        cls,
        messages: List[Message],
        parent_summary_text: Optional[str] = None,
    ) -> tuple[str, int]:
        """Create simple summary without LLM (fallback on error).

        Returns:
            Tuple of (summary_text, total_tokens)
        """
        # Get last 5 messages
        last_messages = messages[-5:] if len(messages) > 5 else messages

        # Calculate total tokens from last messages
        total_tokens = sum(msg.tokens or 0 for msg in last_messages)

        lines = []

        if parent_summary_text:
            lines.append("=== Previous Summary ===")
            lines.append(parent_summary_text)
            lines.append("")

        lines.append("=== Recent Messages ===")

        for msg in last_messages:
            role = msg.role.value.upper()
            text_part = msg.content()
            if text_part:
                # Take first 100 chars
                content = text_part.text[:100].replace("\n", " ")
                lines.append(f"{role}: {content}")

        return "\n".join(lines), total_tokens
