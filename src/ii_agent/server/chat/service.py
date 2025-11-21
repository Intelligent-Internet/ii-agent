"""Chat service with LiteLLM integration."""

import logging
import uuid
from typing import AsyncIterator, Dict, List, Optional, Tuple, TYPE_CHECKING, Any
from datetime import datetime, timezone

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.db.chat import ChatMessage
from ii_agent.db.models import Session
from ii_agent.db.manager import APIKeys
from ii_agent.db.agent import AgentRunTask, RunStatus
from ii_agent.metrics.models import ModelPricing, LLMMetrics, TokenUsage
from ii_agent.server.chat.context_manager import ContextWindowManager
from ii_agent.storage import ContextModeManager
from ii_agent.server.chat.llm import LLMProviderFactory
from ii_agent.server.chat.message_service import MessageService
from ii_agent.server.chat.models import (
    ChatMessageRequest,
    RunResponseOutput,
    SessionMetadata,
    ErrorTextContent,
    ToolCall,
    ToolResult,
    TextContent,
    MessageRole,
    EventType,
    FinishReason,
)
from ii_agent.server.chat.tools import (
    WebSearchTool,
    ImageSearchTool,
    WebVisitTool,
    FileSearchTool,
    ToolCallInput,
)
from ii_agent.server.chat.tools.recall_context import RecallContextTool
from ii_agent.server.chat.tools.microcontext_subroutine import MicrocontextSubroutineTool
from ii_agent.server.credits.service import (
    has_sufficient_credits,
    deduct_user_credits,
)
from ii_agent.server.llm_settings.service import (
    get_user_llm_config,
    get_system_llm_config,
    get_all_available_models,
)
from ii_agent.server.vectordb import openai_vector_store
from ii_agent.server.chat import cancel

if TYPE_CHECKING:
    from ii_agent.server.chat.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ChatService:
    """Service for managing chat conversations."""

    _context_mode_manager: ContextModeManager = ContextModeManager()

    @staticmethod
    def _truncate_session_name(query: str, max_length: int = 50) -> str:
        """
        Truncate query to reasonable length for session name.

        Args:
            query: User query text
            max_length: Maximum length for session name (default: 50)

        Returns:
            Truncated session name with ellipsis if needed
        """
        truncated = query[:max_length].strip()
        if len(query) > max_length:
            truncated += "..."
        return truncated

    @classmethod
    async def create_chat_session(
        cls, *, db_session: AsyncSession, user_message: str, user_id: str, model_id: str
    ) -> SessionMetadata:
        """
        Create a new chat session.

        Args:
            db_session: Database session
            user_id: User ID who owns the session
            model_id: LLM model ID for this session

        Returns:
            SessionMetadata: Session metadata with id, name, created_at, etc.
        """
        session_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        # Truncate query to reasonable length using helper method
        session_name = cls._truncate_session_name(user_message)

        session = Session(
            id=session_id,
            user_id=user_id,
            name=session_name,
            status="active",
            agent_type="chat",
            created_at=created_at,
            updated_at=created_at,
        )
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        logger.info(f"Created chat session {session_id} for user {user_id}")

        return SessionMetadata(
            session_id=session_id,
            name=session.name,
            status="active",
            agent_type="chat",
            model_id=model_id,
            created_at=created_at.isoformat(),
        )

    @classmethod
    async def update_session_name_if_untitled(
        cls, *, db_session: AsyncSession, session_id: str, query: str
    ) -> None:
        """
        Update session name with first user query if session name is 'Untitled'.

        Args:
            db_session: Database session
            session_id: Session ID to update
            query: User query to use as session name
        """
        # Get the session
        result = await db_session.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            return

        # Only update if name is "Untitled"
        if session.name == "Untitled":
            # Truncate query to reasonable length using helper method
            new_name = cls._truncate_session_name(query)

            await db_session.execute(
                update(Session)
                .where(Session.id == session_id)
                .values(name=new_name, updated_at=datetime.now(timezone.utc))
            )
            await db_session.commit()
            logger.info(f"Updated session {session_id} name to: {new_name}")

    @classmethod
    async def validate_session_access(
        cls, *, db_session: AsyncSession, session_id: str, user_id: str
    ) -> None:
        """
        Validate that user has access to session.

        Args:
            db_session: Database session
            session_id: Session ID to validate
            user_id: User ID to check access for

        Raises:
            ValueError: If session not found or access denied
        """
        result = await db_session.execute(
            select(Session).where(
                Session.id == session_id,
                Session.user_id == user_id,
            )
        )
        session = result.scalar_one_or_none()

        if not session:
            raise ValueError("Session not found or access denied")

    @classmethod
    async def validate_public_session_access(
        cls, *, db_session: AsyncSession, session_id: str
    ) -> None:
        """
        Validate that the session is public and accessible without authentication.

        Args:
            db_session: Database session
            session_id: Session ID to validate

        Raises:
            ValueError: If session not found, not public, or deleted
        """
        result = await db_session.execute(
            select(Session).where(
                Session.id == session_id,
                Session.is_public.is_(True),
                Session.deleted_at.is_(None),
            )
        )
        session = result.scalar_one_or_none()

        if not session:
            raise ValueError("Session not found or not public")

    @classmethod
    async def check_sufficient_credits(
        cls, *, db_session: AsyncSession, user_id: str
    ) -> bool:
        """
        Check if user has sufficient credits.

        Args:
            db_session: Database session
            user_id: User ID to check

        Returns:
            True if user has sufficient credits, False otherwise
        """
        return await has_sufficient_credits(
            db_session=db_session,
            user_id=user_id,
            amount=0.01,  # Minimum credit threshold
        )

    @classmethod
    async def validate_model_for_chat(
        cls, *, db_session: AsyncSession, model_id: str, user_id: str
    ) -> None:
        """
        Validate that the model exists and is available for chat.

        Supports: OpenAI, Gemini, and other LiteLLM-compatible models.

        Args:
            db_session: Database session
            model_id: Model ID to validate
            user_id: User ID

        Raises:
            ValueError: If model is not found
        """
        # Get all available models
        # TODO: Optimize this
        all_models = await get_all_available_models(
            user_id=user_id, db_session=db_session
        )

        # Find the requested model
        model_info = next((m for m in all_models.models if m.id == model_id), None)

        if not model_info:
            raise ValueError(f"Model not found: {model_id}")

        # Model exists and is available for chat
        # LiteLLM handles the API differences automatically

    @classmethod
    async def get_llm_config(
        cls, *, db_session: AsyncSession, model_id: str, user_id: str
    ) -> LLMConfig:
        """
        Get LLM config for a model (from user settings or system config).

        Args:
            db_session: Database session
            model_id: Model ID
            user_id: User ID

        Returns:
            LLMConfig

        Raises:
            ValueError: If model not found
        """
        # Try to get from user settings first
        try:
            return await get_user_llm_config(
                model_id=model_id,
                user_id=user_id,
                db_session=db_session,
            )
        except ValueError:
            # Fall back to system config
            return get_system_llm_config(model_id=model_id)

    @classmethod
    async def stream_chat_response(
        cls, *, db_session: AsyncSession, chat_request: ChatMessageRequest, user_id: str
    ) -> AsyncIterator[Dict]:
        """
        Stream chat response using new architecture with tool execution loop.

        Args:
            tools: Optional dict of tool names to enabled status.
                   Example: {"web_search": True, "image_search": False}
                   If None, no tools are enabled.

        This implements an outer loop that:
        1. Calls LLM with current message history (and enabled tools)
        2. Streams LLM response to frontend
        3. If finish_reason == "tool_use", executes tools locally
        4. Streams tool results to frontend
        5. Adds tool results to message history
        6. Loops back to step 1 with updated history
        7. Exits when finish_reason != "tool_use"
        """
        session_id = str(chat_request.session_id)
        tools = {
            "web_search": True,
            "image_search": True,
            "web_visit": True,
            "code_interpreter": True,
            "file_search": True,
        }
        model_id = chat_request.model_id

        # Record model usage and trigger cliff benchmark if threshold met
        # This runs in background and doesn't block the chat
        from ii_agent.server.chat.context_manager import ContextWindowManager
        benchmark = ContextWindowManager.get_cliff_benchmark()
        benchmark.record_usage(model_id)
        asyncio.create_task(benchmark.run_background_tests(model_id, self._llm_call_simple))

        # Get session for context window check
        result = await db_session.execute(
            select(Session).where(Session.id == session_id, Session.user_id == user_id)
        )
        session = result.scalar_one()

        # Check if summarization is needed
        await ContextWindowManager.check_and_summarize(
            db_session=db_session, session=session, model_id=model_id
        )

        # Get conversation history with summary filtering
        messages = await ContextWindowManager.get_messages_with_summary(
            db_session=db_session,
            session_id=session_id,
            summary_message_id=session.summary_message_id,
        )

        # Check if should dump and generate tiles (at 33% context threshold)
        dump_result = await ContextWindowManager.dump_and_tile_if_needed(
            messages=messages,
            model_id=model_id,
        )
        if dump_result:
            logger.info(
                f"Dumped context at 33%: slab {dump_result.get('current_slab_id')}, "
                f"{len(dump_result.get('tiles_generated', []))} tiles, "
                f"{len(dump_result.get('retained_breadcrumbs', []))} breadcrumbs retained"
            )

        # Create user message with TextContent part
        user_text_part = TextContent(text=chat_request.content)
        user_message = await MessageService.create_message(
            db_session=db_session,
            session_id=str(chat_request.session_id),
            role=MessageRole.USER,
            parts=[user_text_part],
            model_id=chat_request.model_id,
            file_ids=chat_request.file_ids,
            tools=tools,
        )

        # Create AgentRunTask to track this chat run
        agent_task = await AgentRunTask.create(
            db=db_session,
            session_id=uuid.UUID(session_id),
            user_message_id=user_message.id,
            status=RunStatus.RUNNING,
        )
        await db_session.commit()

        # Use task ID as run_id for cancellation tracking
        run_id = str(agent_task.id)
        await cancel.register_run(run_id)

        logger.info(f"Started chat run {run_id} for session {session_id}")

        vector_store = await openai_vector_store.retrieve(
            user_id=user_id, session_id=session_id
        )
        if user_message.file_ids:
            vs_files = await openai_vector_store.add_files_batch(
                user_id=user_id,
                session_id=session_id,
                file_ids=user_message.file_ids,
            )
            logger.info(f"Added files: {len(vs_files)} to vector stores")

            # Append file upload information to user message
            if vs_files:
                file_info_lines = ["Files uploaded:"]
                for file_obj in vs_files:
                    file_info_lines.append(
                        f"- Name: {file_obj.file_name}, content type: {file_obj.content_type}, bytes: {file_obj.bytes}"
                    )

                user_text = user_message.parts[0].text
                file_info_text = user_text + "\n\n" + "\n".join(file_info_lines)
                user_message.parts = [TextContent(text=file_info_text)]

        # Add to messages list
        messages.append(user_message)

        # Get LLM config and create provider
        llm_config = await cls.get_llm_config(
            db_session=db_session, model_id=model_id, user_id=user_id
        )
        provider = LLMProviderFactory.create_provider(llm_config)

        # Get code interpreter flag from tools
        is_code_interpreter_enabled = bool(tools and tools.get("code_interpreter"))

        # Initialize tools if requested
        tool_registry = {}
        tools_to_pass: List[Dict[str, Any]] = []

        if tools and any(tools.values()):  # If tools dict provided and any enabled
            config = IIAgentConfig()

            # Get user's active API key using existing helper
            user_api_key = await APIKeys.get_active_api_key_for_user(user_id)
            if not user_api_key:
                logger.error(f"No active API key found for user {user_id}")
                raise ValueError(
                    "User API key not found. Please configure API key in settings."
                )

            # Instantiate tool instances (fresh per request)
            all_search_tools: List[BaseTool] = [
                WebSearchTool(config.tool_server_url, user_api_key, session_id),
                ImageSearchTool(config.tool_server_url, user_api_key, session_id),
                WebVisitTool(config.tool_server_url, user_api_key, session_id),
            ]
            if vector_store:
                (
                    all_search_tools.append(
                        FileSearchTool(
                            session_id=session_id,
                            user_id=user_id,
                            vector_store_id=vector_store.provider_store_id,
                        )
                    ),
                )

            # Filter to only enabled tools (excluding built-in code interpreter when container in use)
            enabled_tools: List[BaseTool] = [
                tool for tool in all_search_tools if tools.get(tool.name, False)
            ]

            # Add context management tools (always available, not user-toggleable)
            context_tools: List[BaseTool] = [
                RecallContextTool(),
                MicrocontextSubroutineTool(),
            ]
            enabled_tools.extend(context_tools)

            if not enabled_tools:
                logger.warning(f"No tools enabled in request: {tools}")
            else:
                logger.info(f"Enabled tools: {[t.name for t in enabled_tools]}")

            # Create registry: tool_name -> BaseTool instance (for execution)
            tool_registry = {tool.name: tool for tool in enabled_tools}

            # Convert tool info to OpenAI function format (standard interchange format)
            for tool in enabled_tools:
                tool_info = tool.info()
                tools_to_pass.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool_info.name,
                            "description": tool_info.description,
                            "parameters": tool_info.parameters,
                        },
                    }
                )
        try:
            # ============================================================
            # REACT LOOP FSM - This pattern can be matched by REPL
            # ============================================================
            # States: WAITING_FOR_LLM -> (TOOL_USE | COMPLETE)
            #         TOOL_USE -> EXECUTING_TOOLS -> WAITING_FOR_LLM
            #         COMPLETE -> EXIT
            # ============================================================
            while True:
                # [PRESENTATION] Cancellation check (web-specific)
                await cancel.raise_if_cancelled(run_id)

                # [BUSINESS LOGIC] Token management (model-aware reduction)
                messages = ContextWindowManager.reduce_message_tokens(messages, model_id=model_id)

                # [FSM STATE] WAITING_FOR_LLM
                run_response: RunResponseOutput = None
                file_parts = []

                # [FSM TRANSITION] Call LLM
                async for event in provider.stream(
                    messages=messages,
                    tools=tools_to_pass,
                    is_code_interpreter_enabled=is_code_interpreter_enabled,
                    session_id=session_id,
                ):
                    if event.type == EventType.COMPLETE:
                        # [FSM] Store response for state transition decision
                        run_response = event.response
                    else:
                        # [PRESENTATION] Yield SSE events to web UI
                        sse_event = event.to_sse_event()
                        if sse_event is not None:
                            yield sse_event

                # [PRESENTATION] Yield usage metrics to web UI
                if run_response:
                    yield {
                        "type": "usage",
                        "usage": {
                            "input_tokens": run_response.usage.prompt_tokens,
                            "output_tokens": run_response.usage.completion_tokens,
                            "cache_creation_tokens": run_response.usage.cache_write_tokens,
                            "cache_read_tokens": run_response.usage.cache_read_tokens,
                        },
                    }

                if run_response.files:
                    file_parts.extend(run_response.files)

                # [PRESENTATION] Cancellation check (web-specific)
                await cancel.raise_if_cancelled(run_id)

                # [PERSISTENCE] Save assistant message to DB
                assistant_message = await MessageService.create_message(
                    db_session=db_session,
                    session_id=session_id,
                    role=MessageRole.ASSISTANT,
                    parts=run_response.content,
                    model_id=model_id,
                    parent_message_id=user_message.id,
                    usage=run_response.usage,
                    file_ids=[f["id"] for f in file_parts],
                    provider_metadata=run_response.provider_metadata,
                    finish_reason=run_response.finish_reason.value
                    if run_response.finish_reason
                    else None,
                )

                # [PRESENTATION] Cancellation check (web-specific)
                await cancel.raise_if_cancelled(run_id)

                # [FSM STATE UPDATE] Add message to conversation history
                messages.append(assistant_message)

                # [CONTEXT MANAGEMENT] Check if checkpoint needed (at model-specific threshold)
                checkpoint_id = await ContextWindowManager.create_checkpoint_if_needed(
                    messages=messages,
                    model_id=model_id,
                )
                if checkpoint_id:
                    # Retrieve microkernel from checkpoint metadata
                    checkpoint_system = ContextWindowManager.get_checkpoint_system()
                    microkernel = checkpoint_system.checkpoint_metadata.get(
                        checkpoint_id, {}
                    ).get("microkernel", {})

                    logger.info(
                        f"Created checkpoint {checkpoint_id} at threshold "
                        f"(context NOT evicted, indexed for recall). "
                        f"Microkernel: {len(microkernel.get('tasks', []))} tasks, "
                        f"{len(microkernel.get('goals', []))} goals"
                    )

                    # Transition to SUSPENDED mode with microkernel
                    mode_status = cls._context_mode_manager.transition_to_suspended(
                        checkpoint_id, microkernel
                    )
                    logger.info(f"Context mode transition: {mode_status}")

                # [FSM STATE TRANSITION] Decide next state based on finish_reason
                if run_response.finish_reason == FinishReason.TOOL_USE:
                    # [FSM STATE] TOOL_USE -> EXECUTING_TOOLS

                    # [FSM] Extract tool calls from response
                    tool_calls_to_execute = [
                        part
                        for part in run_response.content
                        if isinstance(part, ToolCall) and not part.provider_executed
                    ]

                    # [FSM] Execute tools and collect results
                    tool_result_parts = []

                    for tool_call in tool_calls_to_execute:
                        # [FSM] Execute tool
                        tool_result = await cls._execute_tool(
                            tool_call_id=tool_call.id,
                            tool_name=tool_call.name,
                            tool_input=tool_call.input,
                            tool_registry=tool_registry,
                        )

                        # [PRESENTATION] Yield tool result to web UI
                        yield {
                            "type": "tool_result",
                            "tool_call_id": tool_result.tool_call_id,
                            "name": tool_result.name,
                            "output": tool_result.output.model_dump(),
                        }

                        # [FSM] Collect tool results
                        tool_result_parts.append(tool_result)

                    # [PERSISTENCE] Save tool results to DB
                    tool_results_message = await MessageService.create_message(
                        db_session=db_session,
                        session_id=session_id,
                        role=MessageRole.TOOL,
                        parts=tool_result_parts,
                        parent_message_id=user_message.id,
                        model_id=chat_request.model_id,
                    )

                    # [FSM STATE UPDATE] Add tool results to conversation history
                    messages.append(tool_results_message)

                    # [PERSISTENCE] Commit transaction
                    await db_session.commit()

                    # [FSM TRANSITION] EXECUTING_TOOLS -> WAITING_FOR_LLM (loop back)
                    continue

                else:
                    # [FSM STATE] COMPLETE (terminal state)

                    # [BUSINESS LOGIC] Deduct credits for usage
                    await cls._deduct_credits_for_llm_usage(
                        db_session=db_session,
                        user_id=user_id,
                        session_id=session_id,
                        model_id=model_id,
                        usage=run_response.usage,
                    )

                    # [PERSISTENCE] Commit credits deduction
                    await db_session.commit()

                    # [PERSISTENCE] Update run task status
                    await db_session.refresh(agent_task)
                    agent_task.status = RunStatus.COMPLETED
                    await db_session.commit()

                    # [PRESENTATION] Send completion event to web UI
                    yield {
                        "type": "complete",
                        "message_id": assistant_message.id,
                        "finish_reason": run_response.finish_reason.value,
                        "files": file_parts,
                    }

                    # [PRESENTATION] Cleanup web-specific tracking
                    await cancel.cleanup_run(run_id)
                    logger.info(f"Completed chat run {run_id} for session {session_id}")

                    # [FSM TRANSITION] EXIT loop (terminal state reached)
                    break

        except (cancel.RunCancelledException, Exception) as e:
            is_cancelled = isinstance(e, cancel.RunCancelledException)

            # Log appropriate message
            if is_cancelled:
                logger.info(f"Chat run {run_id} was cancelled for session {session_id}")
            else:
                logger.error(f"Chat streaming error: {e}", exc_info=True)

            # Update AgentRunTask status
            # Refresh to avoid StaleDataError
            await db_session.refresh(agent_task)
            agent_task.status = RunStatus.ABORTED if is_cancelled else RunStatus.FAILED
            await db_session.commit()

            # Common cleanup: mark messages incomplete and cleanup run tracking
            await MessageService.mark_messages_incomplete(
                db_session=db_session,
                parent_message_id=user_message.id,
            )
            await cancel.cleanup_run(run_id)

            # Handle specific case
            if is_cancelled:
                # Send cancellation event to frontend
                yield {
                    "type": EventType.COMPLETE,
                    "finish_reason": FinishReason.CANCELED,
                }
            else:
                # Re-raise for other exceptions
                raise

    @classmethod
    async def get_message_history(
        cls,
        *,
        db_session: AsyncSession,
        session_id: str,
        limit: int = 50,
        before: Optional[str] = None,
    ) -> Tuple[List[ChatMessage], bool]:
        """
        Get message history with pagination.

        Args:
            db_session: Database session
            session_id: Session ID
            limit: Maximum number of messages to return
            before: Message ID to get messages before

        Returns:
            Tuple of (list of messages, has_more flag)
        """

        query = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit + 1)
        )

        if before:
            # Get messages before a specific message ID
            before_msg = await db_session.get(ChatMessage, before)
            if before_msg:
                query = query.where(ChatMessage.created_at < before_msg.created_at)

        result = await db_session.execute(query)
        messages = list(result.scalars().all())

        # Check if there are more messages
        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]

        # Reverse to get chronological order
        messages.reverse()

        return messages, has_more

    @classmethod
    async def clear_messages(cls, *, db_session: AsyncSession, session_id: str) -> int:
        """
        Clear all messages in a session.

        Args:
            db_session: Database session
            session_id: Session ID

        Returns:
            Number of messages deleted
        """

        result = await db_session.execute(
            delete(ChatMessage).where(ChatMessage.session_id == session_id)
        )
        await db_session.commit()

        return result.rowcount

    @classmethod
    async def stop_conversation(
        cls, *, db_session: AsyncSession, session_id: str
    ) -> Optional[str]:
        """
        Stop a conversation by cancelling the running chat and updating session status to 'pause'.

        Args:
            db_session: Database session
            session_id: Session ID

        Returns:
            Last message ID if conversation has messages, None otherwise

        Raises:
            ValueError: If session not found
        """
        # Get the session
        result = await db_session.execute(
            select(Session).where(Session.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            raise ValueError("Session not found")

        # Find and cancel running AgentRunTask (if any)
        running_task = await AgentRunTask.find_last_by_session_id_and_status(
            db=db_session,
            session_id=uuid.UUID(session_id),
            status=RunStatus.RUNNING.value,
        )

        if running_task:
            # Cancel the running chat using task ID
            task_id = str(running_task.id)
            cancelled = await cancel.cancel_run(task_id)
            if cancelled:
                # Refresh to get latest state before updating
                await db_session.refresh(running_task)
                if running_task.status == RunStatus.RUNNING:
                    running_task.status = RunStatus.ABORTED
                    logger.info(
                        f"Cancelled running chat task {task_id} for session {session_id}"
                    )
                else:
                    logger.info(
                        f"Task {task_id} already finished with status {running_task.status}, skipping abort"
                    )

        # Get last message ID
        last_msg_result = await db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(1)
        )
        last_message = last_msg_result.scalar_one_or_none()

        await db_session.commit()


        return str(last_message.id) if last_message else None

    @classmethod
    async def _get_conversation_history(
        cls, *, db_session: AsyncSession, session_id: str, limit: int
    ) -> List[ChatMessage]:
        """
        Get recent conversation history.

        Args:
            db_session: Database session
            session_id: Session ID
            limit: Maximum number of messages to return

        Returns:
            List of chat messages in chronological order
        """

        result = await db_session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())
        messages.reverse()  # Chronological order

        return messages

    @classmethod
    async def _deduct_credits_for_llm_usage(
        cls,
        *,
        db_session: AsyncSession,
        user_id: str,
        session_id: str,
        model_id: str,
        usage: "TokenUsage",
    ) -> None:
        """
        Deduct credits for LLM usage if using system-provided model.

        Skips credit deduction for user-provided models.

        Args:
            db_session: Database session
            user_id: User ID
            session_id: Session ID
            model_id: Model ID
            usage: Token usage from provider (provider_interface.TokenUsage)
        """
        # Check if model is user-provided (skip credit deduction for user models)
        llm_config = await cls.get_llm_config(
            db_session=db_session, user_id=user_id, model_id=model_id
        )

        if llm_config.is_user_model():
            logger.info(f"Skipped credit deduction for user-provided model {model_id}")
            return

        usage.model_name = llm_config.model
        # Create LLMMetrics and calculate credits
        llm_metrics = LLMMetrics(
            token_usage=usage,
            session_id=session_id,
        )

        # Calculate cost using pricing model
        pricing = ModelPricing.get_default_pricing(llm_config.model)
        cost = llm_metrics.calculate_credits(pricing)

        # Deduct credits
        await deduct_user_credits(
            db_session=db_session,
            user_id=user_id,
            amount=cost,
            description=f"Chat message - {model_id} - session {session_id}",
        )

        logger.info(
            f"Deducted {cost:.6f} credits for system model {model_id} "
            f"(prompt: {usage.prompt_tokens}, "
            f"completion: {usage.completion_tokens}, "
            f"cache_read: {usage.cache_read_tokens}, "
            f"cache_write: {usage.cache_write_tokens})"
        )

    @classmethod
    async def _update_session_tokens(
        cls, *, db_session: AsyncSession, session_id: str, usage: "TokenUsage"
    ) -> None:
        """Update session token counts."""
        await db_session.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(
                prompt_tokens=Session.prompt_tokens + usage.prompt_tokens,
                completion_tokens=Session.completion_tokens + usage.completion_tokens,
            )
        )

    @classmethod
    async def _execute_tool(
        cls,
        *,
        tool_call_id: str,
        tool_name: str,
        tool_input: str,
        tool_registry: Dict[str, "BaseTool"],
    ) -> "ToolResult":
        """
        Execute a search tool using the simple tool interface.

        This method:
        1. Looks up tool in registry
        2. Calls tool.run(ToolCall)
        3. Converts ToolResponse to ToolResult ContentPart
        4. Returns for direct addition to message parts

        Args:
            tool_call_id: ID of the tool call (for linking result to call)
            tool_name: Name of the tool to execute
            tool_input: JSON string of tool parameters
            tool_registry: Dictionary mapping tool names to BaseTool instances

        Returns:
            ToolResult ContentPart ready to be added to message
        """
        try:
            # Look up tool in registry
            tool = tool_registry.get(tool_name)
            if not tool:
                logger.error(f"Tool '{tool_name}' not found in registry")
                return ToolResult(
                    tool_call_id=tool_call_id,
                    name=tool_name,
                    output=ErrorTextContent(
                        value=f"Unknown tool: {tool_name}",
                    ),
                )

            # Execute tool
            tool_response = await tool.run(
                ToolCallInput(
                    id=tool_call_id,
                    name=tool_name,
                    input=tool_input,
                )
            )

            # Convert ToolResponse to ToolResult ContentPart
            return ToolResult(
                tool_call_id=tool_call_id,
                name=tool_name,
                output=tool_response.output,
            )

        except Exception as e:
            logger.error(f"Tool execution error for '{tool_name}': {e}", exc_info=True)
            return ToolResult(
                tool_call_id=tool_call_id,
                name=tool_name,
                output=ErrorTextContent(
                    value=f"Unexpected error executing tool: {str(e)}",
                ),
            )

    @staticmethod
    async def _llm_call_simple(prompt: str) -> str:
        """
        Simple LLM call interface for cliff benchmarking.

        Uses LiteLLM for model-agnostic calls. This is intentionally simple
        for benchmark purposes - no streaming, no tool use, just completion.

        Args:
            prompt: The prompt text

        Returns:
            Model response text

        Raises:
            Exception: If LLM call fails
        """
        try:
            import litellm

            # Use a fast model for benchmarking
            # TODO: Make this configurable based on available API keys
            model = "gpt-4o-mini"  # Fast and cheap for benchmarking

            response = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                timeout=60.0,
            )

            return response.choices[0].message.content or ""

        except Exception as e:
            logger.error(f"Simple LLM call failed: {e}")
            raise
