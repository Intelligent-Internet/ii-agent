"""Service layer for sessions domain - business logic only."""

from __future__ import annotations

import uuid
import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, List

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.tasks.service import RunTaskService

from ii_agent.credits.constants import MINIMUM_REQUIRED_CREDITS
from ii_agent.realtime.events.models import ApplicationEvent
from ii_agent.realtime.events.repository import EventRepository
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.models import Session
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.schemas import SessionEventDetail, SessionInfo, ValidatedSessionResult
from ii_agent.sessions.title_service import SessionTitleService
from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.core.redis.cache import EntityCache
from ii_agent.core.storage.providers.base import StorageProvider

if TYPE_CHECKING:
    from ii_agent.agents.sandboxes.repository import SandboxRepository
    from ii_agent.credits.service import CreditService
    from ii_agent.files.service import FileService
    from ii_agent.settings.llm.service import ModelSettingService

logger = logging.getLogger(__name__)


class SessionService:
    """Service for managing chat sessions - business logic layer."""

    KEY_PATTERN = "session:{session_id}"

    def __init__(
        self,
        *,
        session_repo: SessionRepository,
        event_repo: EventRepository,
        run_task_service: RunTaskService,
        file_store: StorageProvider,
        file_service: FileService,
        sandbox_repo: SandboxRepository,
        cache: EntityCache,
        config: Settings,
    ) -> None:
        self._config = config
        self._session_repo = session_repo
        self._event_repo = event_repo
        self._run_task_service = run_task_service
        self._file_store = file_store
        self._file_service = file_service
        self._sandbox_repo = sandbox_repo
        self._cache = cache

    # ==================== Session CRUD ====================

    async def create_session(
        self,
        db: AsyncSession,
        session_uuid: uuid.UUID,
        user_id: uuid.UUID,
        api_version: str = "v0",
        name: Optional[str] = None,
    ) -> SessionInfo:
        """Create a new session with a UUID-based workspace directory."""
        session = Session(
            id=session_uuid,
            user_id=user_id,
            name=name,
            status="active",
            api_version=api_version,
        )
        saved = await self._session_repo.save(db, session)
        return self._build_session_info(saved, api_version=api_version)

    async def get_session_by_id(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> Optional[SessionInfo]:
        """Get a session by its UUID with project loaded."""
        session = await self._session_repo.get_by_id_with_project(db, session_id)
        if session is None:
            return None
        return self._build_session_info(session)

    async def get_session_details(
        self, db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[SessionInfo]:
        """Get detailed information for a specific session."""
        session = await self._session_repo.get_by_id_and_user(db, session_id, user_id)
        if not session:
            return None
        return self._build_session_info(session)

    async def get_public_session_details(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> Optional[SessionInfo]:
        """Get detailed information for a public session."""
        session = await self._session_repo.get_public_by_id(db, session_id)
        if not session:
            return None
        return self._build_session_info(session, include_project=False)

    # ==================== Session Updates ====================

    async def _evict_session_cache(self, session_id: uuid.UUID) -> None:
        """Evict a session from the cache."""
        await self._cache.evict(self.KEY_PATTERN.format(session_id=str(session_id)))

    async def update_session_fields(
        self, db: AsyncSession, session_id: uuid.UUID, **fields
    ) -> None:
        """Update one or more fields on a session by keyword argument."""
        session = await self._session_repo.get_by_id(db, session_id)
        if session:
            for key, value in fields.items():
                setattr(session, key, value)
            await self._session_repo.update(db, session)
            await self._evict_session_cache(session_id)

    async def update_session_title_state(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        *,
        name: Optional[str],
        title_pending: bool,
    ) -> None:
        """Update session name and its title-pending flag together."""
        session = await self._session_repo.get_by_id(db, session_id)
        if not session:
            return
        session.name = name
        session.session_metadata = SessionTitleService.set_title_pending(
            session.session_metadata,
            title_pending,
        )
        await self._session_repo.update(db, session)
        await self._evict_session_cache(session_id)

    async def update_session_name(self, db: AsyncSession, session_id: uuid.UUID, name: str) -> None:
        """Update session name and clear the title-pending flag."""
        await self.update_session_title_state(db, session_id, name=name, title_pending=False)

    async def get_user_sessions(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        search_term: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        public_only: Optional[bool] = False,
        session_type: Optional[str] = None,
    ) -> tuple[List[SessionInfo], int]:
        """Get sessions for a user with optional search and pagination."""
        sessions, total = await self._session_repo.get_user_sessions(
            db,
            user_id=user_id,
            search_term=search_term,
            page=page,
            per_page=per_page,
            public_only=public_only,
            session_type=session_type,
        )
        return [self._build_session_info(s) for s in sessions], total

    # ==================== Session State ====================

    async def _cancel_active_run(self, db: AsyncSession, session_id: uuid.UUID) -> None:
        """Cancel any active run for the session via Redis + task status transition."""
        active_task = await self._run_task_service.find_active_by_session(db, session_id)
        if active_task is None:
            return
        from ii_agent.core.redis.cancel import cancel_run
        from ii_agent.tasks.types import RunStatus

        cancelled = await cancel_run(str(active_task.id))
        await self._run_task_service.transition_status(
            db,
            task_id=active_task.id,
            to_status=RunStatus.CANCELLED,
            error_message="Session deleted",
        )
        logger.info(
            "Cancelled active run %s for deleted session %s (redis_signal=%s)",
            active_task.id,
            session_id,
            cancelled,
        )

    async def _publish_session_deleted_event(
        self, db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Persist a SessionDeletedEvent for observability."""
        event = ApplicationEvent(
            session_id=session_id,
            user_id=user_id,
            event_type="session.deleted",
            event_group="session",
            content={"session_id": str(session_id), "user_id": str(user_id)},
        )
        await self._event_repo.save(db, event)

    async def soft_delete_session(
        self, db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Soft delete a session with full resource cleanup.

        1. Cancel any active run (Redis signal + task status transition).
        2. Mark session as deleted (soft delete).
        3. Publish a ``session.deleted`` event for observability.
        4. Evict session from cache.

        Sandbox containers are cleaned up asynchronously by the orphan-cleanup
        background loop, which checks ``is_deleted`` and removes containers
        after the configured grace period.
        """
        session = await self._session_repo.get_by_id_and_user(db, session_id, user_id)
        if not session:
            raise SessionNotFoundError(f"Session {session_id} not found or already deleted")

        # Cancel active runs before marking deleted
        await self._cancel_active_run(db, session_id)

        session.is_deleted = True
        await self._session_repo.update(db, session)

        await self._publish_session_deleted_event(db, session_id, user_id)
        await self._evict_session_cache(session_id)

        logger.info("Soft-deleted session %s for user %s", session_id, user_id)

    async def schedule_deletion(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        delete_after: datetime,
    ) -> None:
        """Schedule a session for automatic deletion at a future time.

        Sets ``delete_after`` on the session.  The orphan-cleanup background
        loop will soft-delete the session once this timestamp is in the past,
        which in turn triggers sandbox container cleanup.
        """
        session = await self._session_repo.get_by_id_and_user(db, session_id, user_id)
        if not session:
            raise SessionNotFoundError(f"Session {session_id} not found or already deleted")

        if delete_after.tzinfo is None:
            delete_after = delete_after.replace(tzinfo=timezone.utc)

        session.delete_after = delete_after
        await self._session_repo.update(db, session)
        logger.info("Scheduled session %s for deletion at %s", session_id, delete_after.isoformat())

    async def bulk_soft_delete_sessions(
        self, db: AsyncSession, session_ids: list[uuid.UUID], user_id: uuid.UUID
    ) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
        """Bulk soft delete sessions with full resource cleanup.

        Cancels active runs and publishes events for each session.

        Returns:
            Tuple of (deleted_ids, failed_ids).
        """
        sessions = await self._session_repo.get_non_deleted_by_ids_and_user(
            db, session_ids, user_id
        )
        deleted_ids: list[uuid.UUID] = []
        for session in sessions:
            # Cancel active runs before marking deleted
            await self._cancel_active_run(db, session.id)

            session.is_deleted = True
            deleted_ids.append(session.id)

            await self._publish_session_deleted_event(db, session.id, user_id)
            await self._evict_session_cache(session.id)

        await db.flush()

        found_ids = set(deleted_ids)
        failed_ids = [sid for sid in session_ids if sid not in found_ids]

        logger.info(
            "Bulk soft-deleted %d sessions for user %s (failed=%d)",
            len(deleted_ids),
            user_id,
            len(failed_ids),
        )
        return deleted_ids, failed_ids

    async def set_session_public(
        self, db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID, is_public: bool
    ) -> bool:
        """Set the public status of a session."""
        session = await self._session_repo.get_by_id_and_user(db, session_id, user_id)
        if not session:
            return False
        session.is_public = is_public
        await self._session_repo.update(db, session)
        return True

    async def get_session_running_status(self, db: AsyncSession, session_id: uuid.UUID):
        """Get the running status for a specific session."""
        return await self._run_task_service.find_active_by_session(db, session_id)

    # ==================== Events ====================

    async def get_session_events_with_details(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> List[SessionEventDetail]:
        """Get all events for a session with signed URLs for file results."""
        ignored_events = [
            "agent.status.update",
            "system.notification",
            "system.error",
            "system.pong",
            "connection.established",
            "connection.workspace_info",
            "agent.initialized",
            "sandbox.status_changed",
        ]
        events = await self._event_repo.get_by_session_filtered(
            db, session_id, excluded_types=ignored_events
        )

        event_list: List[SessionEventDetail] = []
        for e in events:
            content = e.content

            # Generate signed URL for file_url type tool results
            if e.event_type == "agent.tool.result":
                tool_result = content.get("result", {})
                if isinstance(tool_result, dict) and tool_result.get("type") == "file_url":
                    content = deepcopy(content)
                    tool_result = content["result"]
                    signed_url = await self._get_signed_tool_result_url(
                        db,
                        session_id=session_id,
                        tool_result=tool_result,
                    )
                    if signed_url:
                        tool_result["url"] = signed_url

            event_list.append(
                SessionEventDetail(
                    id=e.id,
                    session_id=e.session_id,
                    created_at=e.created_at.isoformat(),
                    type=e.event_type,
                    content=content,
                    workspace_dir=f"/workspace/{e.session_id}",
                    run_id=e.run_id,
                )
            )

        return event_list

    async def _get_signed_tool_result_url(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        tool_result: dict,
    ) -> str | None:
        storage_path = tool_result.get("file_storage_path")
        if not storage_path:
            return tool_result.get("url")

        try:
            return await self._file_service.resolve_signed_url_by_path(db, storage_path)
        except FileNotFoundError:
            logger.warning(
                "Session %s tool result file missing at %s; falling back to stored URL",
                session_id,
                storage_path,
            )
            return tool_result.get("url")

    # ==================== Plan ====================

    async def update_session_plan(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        summary: str,
        milestones: List[dict],
    ) -> None:
        """Update the session's stored plan (summary + milestones).

        Raises:
            SessionNotFoundError: If session not found or access denied.
        """
        session = await self._session_repo.get_by_id_and_user(db, session_id, user_id)
        if not session:
            raise SessionNotFoundError(f"Session {session_id} not found or access denied")

        plan_data = {"summary": summary, "milestones": milestones}
        for milestone in plan_data["milestones"]:
            if milestone.get("details") is None:
                milestone["details"] = ""
            if milestone.get("dependencies") is None:
                milestone["dependencies"] = []

        session.session_metadata = {
            **(session.session_metadata or {}),
            "plan": plan_data,
        }
        await self._session_repo.update(db, session)

        # Update or create the plan event
        plan_event_content = {
            "summary": plan_data["summary"],
            "milestones": plan_data["milestones"],
            "is_update": True,
        }
        existing_plan_event = await self._event_repo.get_latest_by_type(
            db, session_id, "plan.milestone.generated"
        )
        if existing_plan_event:
            existing_plan_event.content = plan_event_content
            await db.flush()
        else:
            event = ApplicationEvent(
                session_id=session_id,
                event_type="plan.milestone.generated",
                content=plan_event_content,
            )
            await self._event_repo.save(db, event)

    # ==================== High-level Business Logic ====================

    async def find_session_by_id(
        self, db: AsyncSession, session_uuid: uuid.UUID
    ) -> Optional[SessionInfo]:
        """Find session by ID and return SessionInfo."""
        return await self.get_session_by_id(db, session_uuid)

    async def create_new_session(
        self,
        db: AsyncSession,
        session_uuid: uuid.UUID,
        user_id: uuid.UUID,
        api_version: str = "v0",
    ) -> SessionInfo:
        """Create a new session and return SessionInfo."""
        return await self.create_session(
            db,
            session_uuid=session_uuid,
            user_id=user_id,
            api_version=api_version,
        )

    async def get_or_create_session(
        self,
        db: AsyncSession,
        session_uuid: Optional[uuid.UUID],
        user_id: uuid.UUID,
        api_version: str = "v0",
    ) -> SessionInfo:
        """Get existing session or create a new one."""
        if session_uuid:
            session = await self.find_session_by_id(db, session_uuid)
            if not session:
                raise SessionNotFoundError(f"Session {session_uuid} not found")
            # Upgrade api_version when re-joining with a newer version
            if session.api_version != api_version and api_version == "v1":
                await self._session_repo.update_api_version(db, session_uuid, api_version)
                session = SessionInfo(**{**session.model_dump(), "api_version": api_version})
        else:
            session = await self.create_new_session(db, uuid.uuid4(), user_id, api_version)
        return session

    async def ensure_session_exists(
        self,
        db: AsyncSession,
        session_uuid: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> Optional[uuid.UUID]:
        """Ensure a database session exists for the given session ID."""
        existing_session = await self.get_session_by_id(db, session_uuid)
        if existing_session:
            logger.info(
                f"Found existing session {session_uuid} for user {existing_session.user_id}"
            )
            return existing_session.user_id
        else:
            if not user_id:
                from ii_agent.core.exceptions import ValidationError

                raise ValidationError("Cannot create session without authenticated user_id")

            await self.create_session(
                db,
                session_uuid=session_uuid,
                user_id=user_id,
                name=None,
            )

            logger.info(f"Created new session {session_uuid} for user {user_id}")
            return user_id

    # ==================== Run Validation ====================

    async def validate_and_prepare_for_run(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        source: str | None,
        model_id: str | None,
        text: str | None,
        agent_type: str | None,
        credit_service: CreditService,
        model_setting_service: ModelSettingService,
    ) -> ValidatedSessionResult:
        """Validate a session for an agent run, backfill defaults, and check credits.

        1. Fetches the ORM session (returns error if not found).
        2. Resolves model config via ``model_setting_service.resolve_model_config()``.
        3. Backfills missing ``name``, ``agent_type``, ``model_setting_id`` on the ORM object.
        4. Checks the user has sufficient credits (skipped for user-provided keys).

        Returns a ``ValidatedSessionResult`` with the refreshed ``SessionInfo`` and
        ``ModelConfig``.  The caller is responsible for emitting error events based
        on ``result.error_code``.
        """
        session = await self._session_repo.get_by_id_with_project(db, session_id)
        if not session:
            return ValidatedSessionResult(is_valid=False, error_code="session_not_found")

        session_info = self._build_session_info(session)

        model_config = await model_setting_service.resolve_model_config(
            db,
            session=session_info,
            source=source,
            model_id=model_id,
        )

        # Backfill missing fields directly on the ORM object
        dirty = False
        if not session.name and text:
            session.name = text.strip()[:100]
            dirty = True
        if session.agent_type is None and agent_type is not None:
            session.agent_type = agent_type
            dirty = True
        if not session.model_setting_id:
            session.model_setting_id = model_config.id
            dirty = True

        if dirty:
            await db.flush()
            await self._evict_session_cache(session_id)
            session_info = self._build_session_info(session)

        # Credit check
        if not model_config.is_user_model() and get_settings().credits.billing_enabled:
            has_credits = await credit_service.has_sufficient_credits(
                db,
                user_id=user_id,
                required=MINIMUM_REQUIRED_CREDITS,
            )
            if not has_credits:
                return ValidatedSessionResult(
                    is_valid=False,
                    session_info=session_info,
                    llm_config=model_config,
                    error_code="insufficient_credits",
                )

        return ValidatedSessionResult(
            is_valid=True,
            session_info=session_info,
            llm_config=model_config,
        )

    # ==================== Helpers ====================

    @staticmethod
    def _build_session_info(
        session: Session,
        *,
        include_project: bool = True,
        api_version: Optional[str] = None,
    ) -> SessionInfo:
        """Build a SessionInfo DTO from a Session model."""
        project_id: Optional[uuid.UUID] = None
        if include_project and "project" not in sa_inspect(session).unloaded:
            project_id = session.project.id if session.project else None
        return SessionInfo(
            id=session.id,
            user_id=session.user_id,
            name=session.name,
            status=session.status,
            agent_type=str(session.agent_type) if session.agent_type is not None else None,
            app_kind=session.app_kind,
            created_at=session.created_at.isoformat() if session.created_at else "",
            updated_at=session.updated_at.isoformat() if session.updated_at else None,
            last_message_at=session.last_message_at.isoformat()
            if session.last_message_at
            else None,
            workspace_dir=session.get_workspace_dir(),
            is_public=session.is_public,
            public_url=session.public_url,
            token_usage=None,
            settings=None,
            project_id=project_id,
            api_version=api_version or session.api_version,
            title_pending=SessionTitleService.is_title_pending(session.session_metadata),
            model_setting_id=session.model_setting_id,
            session_metadata=session.session_metadata,
            delete_after=session.delete_after.isoformat() if session.delete_after else None,
        )
