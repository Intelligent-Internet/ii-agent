"""Chat service - thin orchestrator for chat conversations."""

from __future__ import annotations

import logging
import uuid
from typing import AsyncIterator, Dict, Optional, TYPE_CHECKING
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db import get_db_session_local
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.chat.types import (
    BinaryContent,
    CouncilMemberOutput,
    CouncilSynthesis,
    Message,
    TextContent,
    MessageRole,
    EventType,
    FinishReason,
)
from ii_agent.chat.api.schemas import ChatMessageRequest, SessionMetadata
from ii_agent.chat.exceptions import AnthropicImageTooLargeError
from ii_agent.chat.llm import LLMProviderFactory
from ii_agent.chat.messages.service import MessageService
from ii_agent.chat.media.orchestrator import MediaOrchestrator
from ii_agent.chat.application.context_service import ContextWindowManager
from ii_agent.chat.application.file_processing_service import ChatFileProcessor
from ii_agent.chat.application.tool_service import ChatToolService
from ii_agent.chat.application.turn_loop_service import LLMTurnLoopService
from ii_agent.chat.messages.history_service import ChatMessageHistoryService

if TYPE_CHECKING:
    from ii_agent.chat.application.a2a_turn_loop_service import A2AChatTurnLoop
    from ii_agent.realtime.pubsub.asyncio_pubsub import AsyncIOPubSub
from ii_agent.chat.application.council_service import CouncilService, MIN_COUNCIL_MODELS
from ii_agent.billing.exceptions import InsufficientCreditsError
from ii_agent.credits.constants import MINIMUM_REQUIRED_CREDITS
from ii_agent.credits.service import CreditService
from ii_agent.sessions.models import Session
from ii_agent.sessions.repository import SessionRepository
from ii_agent.core.config.settings import get_settings
from ii_agent.core.redis import cancel
from ii_agent.chat.exceptions import ModelNotFoundError
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.title_service import SessionTitleService
from ii_agent.realtime.events.app_events import ModelUsageEvent

if TYPE_CHECKING:
    from ii_agent.core.container import ApplicationContainer

logger = logging.getLogger(__name__)


class ChatService:
    """Thin orchestrator for chat conversations."""

    def __init__(
        self,
        *,
        file_processor: ChatFileProcessor,
        tool_service: ChatToolService,
        llm_loop: LLMTurnLoopService,
        message_history: ChatMessageHistoryService,
        message_service: MessageService,
        session_repo: SessionRepository,
        model_setting_service,
        credit_service: CreditService | None = None,
        container: ApplicationContainer,
        title_service: SessionTitleService,
        a2a_loop: A2AChatTurnLoop | None = None,
        pubsub: AsyncIOPubSub | None = None,
    ) -> None:
        self._file_processor = file_processor
        self._tool_service = tool_service
        self._llm_loop = llm_loop
        self._message_history = message_history
        self._message_service = message_service
        self._session_repo = session_repo
        self._model_setting_service = model_setting_service
        self._credit_service = credit_service
        self._container = container
        self._title_service = title_service
        self._a2a_loop = a2a_loop
        self._pubsub = pubsub

    def _select_turn_loop(
        self,
        *,
        model_config: ModelConfig,
        chat_request: ChatMessageRequest,
    ) -> LLMTurnLoopService:
        """Choose between A2A and direct turn loops.

        Falls back to the direct loop when:
        - No A2A loop configured
        - Council mode is active (uses its own multi-model execution path
          with per-member A2A/direct routing — see ``CouncilService``)
        - BYOK model in cloud deployment (user pays own API bill)
        - Custom/LiteLLM provider (no A2A adapter mapping)
        - Storybook media type (requires Celery streaming path)

        **Local vs cloud BYOK handling:**

        In cloud (multitenant) deployments, BYOK users provide their own
        API keys and expect direct model calls — routing through the
        platform's A2A adapter (e.g. Copilot) would charge the platform's
        subscription instead of the user's key.

        In local/self-hosted deployments (``ENVIRONMENT=local``), there is
        no system/user model distinction — the operator controls all keys
        and explicitly opts into A2A routing via
        ``AGENT_CHAT_INNER_LOOP_MODE=a2a``.  All compatible models route
        through A2A regardless of ``config_type``.
        """
        if self._a2a_loop is None:
            logger.info("turn-loop-select: direct (no A2A loop configured)")
            return self._llm_loop

        # Council uses parallel direct LLM calls — incompatible with A2A
        council = getattr(chat_request, "council_preferences", None)
        if council and getattr(council, "enabled", False):
            logger.info("turn-loop-select: direct (council mode active)")
            return self._llm_loop

        # BYOK users in cloud deployments go direct — the user pays their
        # own API bill and the A2A adapter would use platform credentials.
        # In local mode the operator owns all keys, so BYOK is irrelevant.
        if model_config.is_user_model() and get_settings().environment != "local":
            logger.info("turn-loop-select: direct (BYOK user model, cloud deployment)")
            return self._llm_loop

        # Custom/LiteLLM providers have no A2A adapter mapping
        from ii_agent.settings.llm.types import Provider

        if model_config.provider == Provider.CUSTOM:
            logger.info("turn-loop-select: direct (custom provider)")
            return self._llm_loop

        # Storybook uses Celery streaming — A2A tool bridge can't invoke
        # start_celery_generation(), so storybook.run() returns an error.
        media = getattr(chat_request, "media_preferences", None)
        if media and getattr(media, "type", None) == "storybook":
            logger.info("turn-loop-select: direct (storybook media)")
            return self._llm_loop

        logger.info("turn-loop-select: a2a")
        return self._a2a_loop  # type: ignore[return-value]

    @staticmethod
    def _find_model_info(all_models, model_id: str):
        normalized_model_id = str(model_id)
        return next(
            (
                model
                for model in all_models.models
                if str(getattr(model, "id", "")) == normalized_model_id
                or str(getattr(model, "model_id", "")) == normalized_model_id
            ),
            None,
        )

    async def create_chat_session(
        self, db: AsyncSession, *, user_message: str, user_id: uuid.UUID, model_id: str
    ) -> SessionMetadata:
        session_id = uuid.uuid4()
        created_at = datetime.now(timezone.utc)
        session_name, title_pending = self._title_service.build_initial_title(
            user_message,
            80,
        )

        session = Session(
            id=session_id,
            user_id=user_id,
            name=session_name,
            status="active",
            agent_type="chat",
            app_kind="chat",
            created_at=created_at,
            updated_at=created_at,
            session_metadata=SessionTitleService.set_title_pending(
                None,
                title_pending,
            ),
        )
        session = await self._session_repo.save(db, session)
        await db.commit()

        logger.info(f"Created chat session {session_id} for user {user_id}")

        if title_pending:
            self._title_service.schedule_title_update(
                session_id,
                user_message,
                user_id=user_id,
                app_kind="chat",
            )

        return SessionMetadata(
            session_id=session_id,
            name=session.name,
            title_pending=title_pending,
            status="active",
            agent_type="chat",
            model_id=model_id,
            created_at=created_at.isoformat(),
        )

    async def update_session_name_if_untitled(
        self, db: AsyncSession, *, session_id: uuid.UUID, query: str
    ) -> None:
        session = await self._session_repo.get_by_id(db, session_id)
        if not session:
            return

        if session.name == "Untitled":
            session.name, title_pending = self._title_service.build_initial_title(
                query,
                80,
            )
            session.session_metadata = SessionTitleService.set_title_pending(
                getattr(session, "session_metadata", None),
                title_pending,
            )
            await db.flush()
            if title_pending:
                self._title_service.schedule_title_update(
                    session_id,
                    query,
                    user_id=session.user_id,
                    app_kind=str(getattr(session, "app_kind", "chat") or "chat"),
                )
                logger.info(f"Scheduled background title update for session {session_id}")

    async def validate_session_access(
        self, db: AsyncSession, *, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        session = await self._session_repo.get_by_id(db, session_id)
        if not session or session.user_id != user_id:
            raise SessionNotFoundError("Session not found or access denied")

    async def validate_public_session_access(
        self, db: AsyncSession, *, session_id: uuid.UUID
    ) -> None:
        session = await self._session_repo.get_public_by_id(db, session_id)
        if not session:
            raise SessionNotFoundError("Session not found or not public")

    async def validate_model_for_chat(
        self, db: AsyncSession, *, model_id: str, user_id: uuid.UUID
    ) -> None:
        all_models = await self._model_setting_service.get_all_available_models(
            db,
            user_id=user_id,
        )
        model_info = self._find_model_info(all_models, model_id)
        if not model_info:
            raise ModelNotFoundError(f"Model not found: {model_id}")

    async def get_model_config(
        self, db: AsyncSession, *, model_id: str, user_id: uuid.UUID
    ) -> ModelConfig:
        all_models = await self._model_setting_service.get_all_available_models(
            db,
            user_id=user_id,
        )
        model_info = self._find_model_info(all_models, model_id)

        if model_info is not None:
            try:
                return await self._model_setting_service.resolve_config_by_setting_id(
                    db,
                    setting_id=model_info.id,
                )
            except ValueError:
                logger.warning(
                    "Failed to resolve model config by setting id %s; falling back to model_id",
                    model_info.id,
                )

        return await self._model_setting_service.resolve_system_config(db, model_id=model_id)

    async def _check_credits(
        self, db: AsyncSession, *, user_id: uuid.UUID, model_config: ModelConfig
    ) -> None:
        """Pre-run credit gate. Raises InsufficientCreditsError if balance is too low."""
        if not self._credit_service:
            return
        if model_config.is_user_model():
            return
        if not get_settings().credits.billing_enabled:
            return

        has_credits = await self._credit_service.has_sufficient_credits(
            db, user_id, MINIMUM_REQUIRED_CREDITS
        )
        if not has_credits:
            balance = await self._credit_service.get_balance(db, user_id)
            available = float(balance.credits + balance.bonus_credits) if balance else 0.0
            raise InsufficientCreditsError(
                "Insufficient credits to start chat. Please add more credits.",
                available_credits=available,
                required_credits=float(MINIMUM_REQUIRED_CREDITS),
            )

    async def _publish_council_usage(
        self,
        *,
        usage,
        model_config: ModelConfig,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        run_id: uuid.UUID,
        billing_backend: str = "native",
        provider_reported_cost: float = 0.0,
        premium_requests: int = 0,
    ) -> None:
        """Publish ModelUsageEvent for a single council member or synthesis call."""
        if not self._pubsub:
            return
        if not usage:
            return

        try:
            await self._pubsub.publish(
                ModelUsageEvent(
                    session_id=session_id,
                    user_id=user_id,
                    run_id=run_id,
                    setting_id=model_config.id,
                    model_id=model_config.model_id,
                    provider=model_config.provider,
                    pricing=model_config.pricing,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_write_tokens=usage.cache_write_tokens,
                    reasoning_tokens=usage.reasoning_tokens,
                    is_user_key=model_config.is_user_model(),
                    billing_backend=billing_backend,
                    provider_reported_cost=provider_reported_cost,
                    premium_requests=premium_requests,
                )
            )
        except Exception:
            logger.exception(
                "Failed to publish council usage event (session=%s, model=%s)",
                session_id,
                model_config.model_id,
            )

    async def build_message_history_response(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        limit: int = 50,
        before: Optional[str] = None,
    ):
        """Delegate to message history service."""
        return await self._message_history.build_message_history_response(
            db,
            session_id=session_id,
            limit=limit,
            before=before,
        )

    async def stream_chat_response(
        self, *, chat_request: ChatMessageRequest, user_id: uuid.UUID
    ) -> AsyncIterator[Dict]:
        """Stream chat response with tool execution loop.

        Acquires short-lived DB sessions only for DB operations, never holding
        a connection during LLM streaming or tool I/O.

        Orchestrates: context loading, file processing, tool setup, LLM turn loop.
        """
        session_id = chat_request.session_id
        default_tools = {
            "web_search": True,
            "image_search": True,
            "web_visit": True,
            "code_interpreter": True,
            "file_search": True,
            "generate_image": True,
        }
        tools = {**default_tools, **(chat_request.tools or {})}

        # Phase 0 (prep): media context, load context, create user message, get model config, check credits
        async with get_db_session_local() as db:
            media_context = None
            if chat_request.media_preferences and chat_request.media_preferences.enabled:
                media_context = await MediaOrchestrator.prepare_media_context(
                    db_session=db,
                    session_id=session_id,
                    media_preferences=chat_request.media_preferences,
                    chat_request=chat_request,
                    container=self._container,
                )
                tools[media_context.tool_name] = True
                logger.info(f"[MEDIA] Prepared media context: tool={media_context.tool_name}")

            model_id = chat_request.model_id

            if media_context and media_context.should_clear_context:
                messages = []
                logger.info(f"Media generation (clear context) for session {session_id}")
            else:
                messages = await ContextWindowManager.load_context_for_llm(
                    db_session=db,
                    session_id=session_id,
                )
                logger.info(
                    f"Loaded full context for session {session_id} ({len(messages)} messages)"
                )

            # Build user message content
            display_content = chat_request.content
            llm_content = chat_request.content

            if chat_request.github_repository:
                repo_context = (
                    f"\n\n[The user has selected GitHub repository: {chat_request.github_repository.full_name} "
                    f"(default branch: {chat_request.github_repository.default_branch}). "
                    f"When the user says 'this repository', 'the repository', 'the repo', or similar, "
                    f"they are referring to this GitHub repository. Use the github tool to access it.]"
                )
                llm_content += repo_context

            message_metadata = None
            if media_context:
                message_metadata = {
                    "media": chat_request.media_preferences.model_dump(exclude_none=True)
                }
                llm_content += media_context.tool_hint

            display_text_part = TextContent(text=display_content)
            user_message = await self._message_service.create_message(
                db,
                session_id=chat_request.session_id,
                role=MessageRole.USER,
                parts=[display_text_part],
                model_id=chat_request.model_id,
                file_ids=chat_request.file_ids,
                tools=tools,
                metadata=message_metadata,
            )

            await db.commit()

            model_config = await self.get_model_config(db, model_id=model_id, user_id=user_id)

            # Pre-run credit check
            await self._check_credits(db, user_id=user_id, model_config=model_config)

        run_id = str(user_message.id)
        await cancel.register_run(run_id)
        logger.info(f"Started chat run {run_id} for session {session_id}")

        # Phase 1: Process file uploads
        async with get_db_session_local() as db:
            vector_store = await self._file_processor.process_uploads(
                db,
                user_id=user_id,
                session_id=session_id,
                user_message=user_message,
                llm_content=llm_content,
                display_content=display_content,
            )

        # Build LLM user message with repo context and media parts (pure in-memory)
        media_message_parts = media_context.llm_message_parts if media_context else []

        llm_parts = [user_message.parts[0]]
        for part in user_message.parts:
            if isinstance(part, BinaryContent):
                llm_parts.append(part)

        if media_message_parts:
            llm_parts.extend(media_message_parts)

        llm_user_message = Message(
            id=user_message.id,
            role=user_message.role,
            session_id=user_message.session_id,
            parts=llm_parts,
            model=user_message.model,
            provider=user_message.provider,
            created_at=user_message.created_at,
            updated_at=user_message.updated_at,
            file_ids=user_message.file_ids,
            tokens=user_message.tokens,
            tools_enabled=user_message.tools_enabled,
            metadata=user_message.metadata,
            provider_metadata=user_message.provider_metadata,
            finish_reason=user_message.finish_reason,
        )
        messages.append(llm_user_message)

        # Phase 2: Build tool registry
        async with get_db_session_local() as db:
            tool_registry, tools_to_pass = await self._tool_service.build_tool_registry(
                db,
                user_id=user_id,
                session_id=session_id,
                tools=tools,
                chat_request=chat_request,
                vector_store=vector_store,
                media_context=media_context,
            )

        provider = LLMProviderFactory.create_provider(model_config)
        is_code_interpreter_enabled = bool(tools and tools.get("code_interpreter"))

        # Phase 3: Run LLM turn loop (loop manages its own DB sessions)
        loop = self._select_turn_loop(model_config=model_config, chat_request=chat_request)
        try:
            async for event in loop.run(
                messages=messages,
                provider=provider,
                tool_registry=tool_registry,
                tools_to_pass=tools_to_pass,
                is_code_interpreter_enabled=is_code_interpreter_enabled,
                session_id=session_id,
                user_id=user_id,
                model_id=model_id,
                user_message=user_message,
                run_id=run_id,
                model_config=model_config,
                chat_request=chat_request,
                tool_service=self._tool_service,
            ):
                yield event

            await cancel.cleanup_run(run_id)
            logger.info(f"Completed chat run {run_id} for session {session_id}")

        except (cancel.RunCancelledException, Exception) as e:
            is_cancelled = isinstance(e, cancel.RunCancelledException)

            if is_cancelled:
                logger.info(f"Chat run {run_id} was cancelled for session {session_id}")
            else:
                logger.error(f"Chat streaming error: {e}", exc_info=True)

            async with get_db_session_local() as db:
                await self._message_service.mark_messages_incomplete(
                    db,
                    parent_message_id=user_message.id,
                )
                await db.commit()

            await cancel.cleanup_run(run_id)

            error_text = str(e).lower()
            if isinstance(e, AnthropicImageTooLargeError) or "image exceeds 5 mb" in error_text:
                yield {
                    "type": EventType.ERROR.value,
                    "message": (
                        "Anthropic models cannot process images larger than 5 MB. "
                        "Please switch to another model or upload a smaller image."
                    ),
                    "code": "anthropic_image_too_large",
                }
                return

            if is_cancelled:
                yield {
                    "type": EventType.COMPLETE,
                    "finish_reason": FinishReason.CANCELED,
                }
            else:
                raise

    async def stream_council_chat_response(
        self, *, chat_request: ChatMessageRequest, user_id: uuid.UUID
    ) -> AsyncIterator[Dict]:
        """Stream council response: run multiple LLMs in parallel, then synthesize.

        Acquires short-lived DB sessions only for DB operations, never holding
        a connection during LLM streaming or tool I/O.

        Orchestrates: context loading, file processing, parallel model execution, synthesis.
        """
        council_prefs = chat_request.council_preferences
        if not council_prefs or not council_prefs.enabled:
            raise ValueError("Council preferences must be enabled")

        CouncilService.validate_preferences(council_prefs)

        session_id = chat_request.session_id

        # Prep block: load context, create user message, process file uploads, resolve model configs
        async with get_db_session_local() as db:
            # Load context
            messages = await ContextWindowManager.load_context_for_llm(
                db_session=db,
                session_id=session_id,
            )
            logger.info(
                f"Council: loaded context for session {session_id} ({len(messages)} messages)"
            )

            # Build user message content
            display_content = chat_request.content
            llm_content = chat_request.content

            if chat_request.github_repository:
                repo_context = (
                    f"\n\n[The user has selected GitHub repository: {chat_request.github_repository.full_name} "
                    f"(default branch: {chat_request.github_repository.default_branch}). "
                    f"When the user says 'this repository', 'the repository', 'the repo', or similar, "
                    f"they are referring to this GitHub repository. Use the github tool to access it.]"
                )
                llm_content += repo_context

            display_text_part = TextContent(text=display_content)
            user_message = await self._message_service.create_message(
                db,
                session_id=session_id,
                role=MessageRole.USER,
                parts=[display_text_part],
                model_id=chat_request.model_id,
                file_ids=chat_request.file_ids,
            )

            await db.commit()

            # Process file uploads (provider-neutral with provider=None)
            await self._file_processor.process_uploads(
                db,
                user_id=user_id,
                session_id=session_id,
                user_message=user_message,
                llm_content=llm_content,
                display_content=display_content,
            )

            # Resolve model configs for all council models + synthesis model
            all_model_ids = [m.model_id for m in council_prefs.council_models]
            if council_prefs.synthesis_model_id not in all_model_ids:
                all_model_ids.append(council_prefs.synthesis_model_id)

            model_configs: Dict[str, ModelConfig] = {}
            model_names = {}
            all_models = await self._model_setting_service.get_all_available_models(
                db, user_id=user_id
            )
            failed_models = []
            for mid in all_model_ids:
                try:
                    model_configs[mid] = await self.get_model_config(
                        db, model_id=mid, user_id=user_id
                    )
                    model_info = self._find_model_info(all_models, mid)
                    model_names[mid] = model_info.model if model_info else mid
                except Exception as e:
                    logger.warning(f"Could not resolve config for council model {mid}: {e}")
                    failed_models.append(mid)

            # Pre-run credit check using synthesis model config as representative
            synthesis_config = model_configs.get(council_prefs.synthesis_model_id)
            if synthesis_config:
                await self._check_credits(db, user_id=user_id, model_config=synthesis_config)

        run_id = str(user_message.id)
        await cancel.register_run(run_id)
        logger.info(f"Started council run {run_id} for session {session_id}")

        # Build LLM messages list (pure in-memory)
        # After process_uploads, user_message.parts[0] already contains
        # llm_content (with GitHub repo context) + file info text
        llm_parts = [user_message.parts[0]]
        for part in user_message.parts:
            if isinstance(part, BinaryContent):
                llm_parts.append(part)

        llm_user_message = Message(
            id=user_message.id,
            role=user_message.role,
            session_id=user_message.session_id,
            parts=llm_parts,
            model=user_message.model,
            provider=user_message.provider,
            created_at=user_message.created_at,
            updated_at=user_message.updated_at,
            file_ids=user_message.file_ids,
            tokens=user_message.tokens,
            tools_enabled=user_message.tools_enabled,
            metadata=user_message.metadata,
            provider_metadata=user_message.provider_metadata,
            finish_reason=user_message.finish_reason,
        )
        messages.append(llm_user_message)

        # Fail fast: synthesis model config is required
        if council_prefs.synthesis_model_id not in model_configs:
            await cancel.cleanup_run(run_id)
            raise ValueError(
                f"Synthesis model '{council_prefs.synthesis_model_id}' could not be resolved"
            )

        # Fail fast: need at least 2 council models with valid configs
        valid_council_count = sum(
            1 for m in council_prefs.council_models if m.model_id in model_configs
        )
        if valid_council_count < MIN_COUNCIL_MODELS:
            await cancel.cleanup_run(run_id)
            raise ValueError(
                f"Only {valid_council_count} council models could be resolved, "
                f"need at least {MIN_COUNCIL_MODELS}"
            )

        member_outputs_for_persist = {}
        synthesis_content = ""
        synthesis_model_id = council_prefs.synthesis_model_id

        try:
            # Council runs multiple LLMs in parallel.  Each member
            # independently decides A2A vs direct via the per-model
            # is_cloud_byok check inside CouncilService.
            a2a_client = self._a2a_loop._client if self._a2a_loop is not None else None
            a2a_backend = self._a2a_loop._a2a_backend if self._a2a_loop is not None else "copilot"

            # Council LLM streaming — NO DB connection held
            async for event in CouncilService.stream_council_response(
                user_id=user_id,
                messages=messages,
                user_question=display_content,
                council_preferences=council_prefs,
                model_configs=model_configs,
                model_names=model_names,
                run_id=run_id,
                session_id=session_id,
                a2a_client=a2a_client,
                a2a_backend=a2a_backend,
            ):
                event_type = event.get("type")

                if event_type == "council_result":
                    # Internal metadata event - don't yield to frontend
                    member_outputs_for_persist = event.get("member_outputs", {})
                    synthesis_content = event.get("synthesis_content", "")
                    synthesis_model_id = event.get("synthesis_model_id", synthesis_model_id)
                    continue

                if event_type == "council_synthesis_error":
                    yield event
                    continue

                # Publish billing events for completed member/synthesis calls
                if event_type in ("council_member_complete", "council_synthesis_complete"):
                    event_usage = event.get("usage")
                    event_model_config = event.get("model_config")
                    if event_usage and event_model_config:
                        await self._publish_council_usage(
                            usage=event_usage,
                            model_config=event_model_config,
                            session_id=session_id,
                            user_id=user_id,
                            run_id=uuid.UUID(run_id),
                            billing_backend=event.get("billing_backend", "native"),
                            provider_reported_cost=event.get("provider_reported_cost", 0.0),
                            premium_requests=event.get("premium_requests", 0),
                        )

                # Strip billing-internal fields before yielding to frontend
                _billing_keys = {
                    "usage",
                    "model_config",
                    "billing_backend",
                    "provider_reported_cost",
                    "premium_requests",
                }
                yield {k: v for k, v in event.items() if k not in _billing_keys}

            # Persist assistant message + post-summarization — short-lived DB session
            async with get_db_session_local() as db:
                # Persist assistant message with council parts
                assistant_parts = []
                for mid, content in member_outputs_for_persist.items():
                    assistant_parts.append(
                        CouncilMemberOutput(
                            model_id=mid,
                            model_name=model_names.get(mid, mid),
                            content=content,
                            status="completed",
                        )
                    )

                if synthesis_content:
                    assistant_parts.append(
                        CouncilSynthesis(
                            synthesis_model_id=synthesis_model_id,
                            content=synthesis_content,
                        )
                    )

                # Don't persist an empty assistant message on total failure
                if not assistant_parts:
                    assistant_parts.append(
                        TextContent(text="[Council execution failed - no model produced output]")
                    )

                assistant_message = await self._message_service.create_message(
                    db,
                    session_id=session_id,
                    role=MessageRole.ASSISTANT,
                    parts=assistant_parts,
                    model_id=chat_request.model_id,
                )

                await db.commit()

                # Post-response summarization
                try:
                    model_config = await self.get_model_config(
                        db, model_id=chat_request.model_id, user_id=user_id
                    )
                    await ContextWindowManager.check_and_summarize_after_response(
                        db_session=db,
                        session_id=session_id,
                        llm_config=model_config,
                        user_id=user_id,
                    )
                except Exception as e:
                    logger.warning(f"Post-council summarization failed: {e}")

            await cancel.cleanup_run(run_id)

            yield {
                "type": "complete",
                "message_id": str(assistant_message.id),
                "finish_reason": FinishReason.END_TURN,
            }

            logger.info(f"Completed council run {run_id} for session {session_id}")

        except (cancel.RunCancelledException, Exception) as e:
            is_cancelled = isinstance(e, cancel.RunCancelledException)

            if is_cancelled:
                logger.info(f"Council run {run_id} was cancelled for session {session_id}")
            else:
                logger.error(f"Council streaming error: {e}", exc_info=True)

            async with get_db_session_local() as db:
                await self._message_service.mark_messages_incomplete(
                    db,
                    parent_message_id=user_message.id,
                )
                await db.commit()

            await cancel.cleanup_run(run_id)

            if is_cancelled:
                yield {
                    "type": EventType.COMPLETE,
                    "finish_reason": FinishReason.CANCELED,
                }
            else:
                raise

    async def clear_messages(self, db: AsyncSession, *, session_id: uuid.UUID) -> int:
        return await self._message_history._repo.delete_by_session(db, session_id)

    async def delete_messages_from(
        self, db: AsyncSession, *, session_id: uuid.UUID, message_id: uuid.UUID
    ) -> int:
        """Delete a message and all subsequent messages."""
        deleted = await self._message_history._repo.delete_from_message(db, session_id, message_id)
        await db.commit()
        return deleted

    async def stop_conversation(
        self, db: AsyncSession, *, session_id: uuid.UUID
    ) -> Optional[uuid.UUID]:
        session = await self._session_repo.get_by_id(db, session_id)
        if not session:
            raise SessionNotFoundError("Session not found")

        # Find the last user message whose assistant reply is still incomplete
        running_msg = await self._message_history._repo.find_running_by_session(db, session_id)

        if running_msg and running_msg.parent_message_id:
            run_id = str(running_msg.parent_message_id)
            cancelled = await cancel.cancel_run(run_id)
            if cancelled:
                logger.info(f"Cancelled running chat for session {session_id} (run_id={run_id})")

        last_message = await self._message_history._repo.get_last_by_session(db, session_id)

        return last_message.id if last_message else None
