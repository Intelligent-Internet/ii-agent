import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, List
import uuid
import ssl
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from sqlalchemy import asc, select, desc, func, delete, update
from sqlalchemy import exc
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.orm import selectinload
from ii_agent.db.agent import AgentRunTask, RunStatus
from ii_agent.core.config.ii_agent_config import config
from ii_agent.db.models import (
    Session,
    Event,
    FileUpload,
    APIKey,
    LLMSetting,
    User,
    Project,
)
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.core.config.ii_agent_config import II_AGENT_DIR
from ii_agent.core.logger import logger
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession


def run_migrations():
    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config(II_AGENT_DIR / "alembic.ini")
        migrations_path = II_AGENT_DIR / "migrations"
        alembic_cfg.set_main_option("script_location", str(migrations_path))

        command.upgrade(alembic_cfg, "head")

    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        raise


async def seed_admin_llm_settings():
    """Seed LLM settings for admin user with system models from LLM_CONFIGS."""

    # Get LLM_CONFIGS from environment
    llm_configs_str = os.getenv("LLM_CONFIGS")
    if not llm_configs_str:
        logger.info(
            "LLM_CONFIGS environment variable not set, skipping admin LLM settings seeding"
        )
        return

    try:
        llm_configs = json.loads(llm_configs_str)
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing LLM_CONFIGS: {e}")
        return

    async with SessionLocal() as db_session:
        try:
            # Check if admin user exists, create if not
            admin_user = (
                await db_session.execute(
                    select(User).filter(User.email == "admin@ii.inc")
                )
            ).scalar_one_or_none()

            if not admin_user:
                # Create admin user
                admin_user = User(
                    id="admin",
                    email="admin@ii.inc",
                    first_name="Admin",
                    last_name="User",
                    role="admin",
                    is_active=True,
                    email_verified=True,
                    credits=1000.0,  # Give admin user initial credits
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db_session.add(admin_user)
                await db_session.flush()
                logger.info("Created admin user with ID 'admin'")
            else:
                logger.info(f"Admin user already exists with ID: {admin_user.id}")

            # Ensure admin user has an API key for tool server access
            # Check by specific ID first (for idempotent upsert behavior)
            admin_api_key_id = "admin-api-key"
            existing_api_key = (
                await db_session.execute(
                    select(APIKey).where(APIKey.id == admin_api_key_id)
                )
            ).scalar_one_or_none()

            if not existing_api_key:
                # Create API key for admin user
                admin_api_key = APIKey(
                    id=admin_api_key_id,
                    user_id=admin_user.id,
                    api_key=f"dev-local-api-key-{admin_user.id}",
                    is_active=True,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db_session.add(admin_api_key)
                await db_session.flush()
                logger.info("Created API key for admin user")
            elif not existing_api_key.is_active:
                # Reactivate if it was deactivated
                existing_api_key.is_active = True
                existing_api_key.updated_at = datetime.now(timezone.utc)
                logger.info("Reactivated API key for admin user")
            else:
                logger.info("Admin user already has an active API key")

            # Get existing admin LLM settings to check what already exists
            existing_settings_result = await db_session.execute(
                select(LLMSetting).where(LLMSetting.user_id == admin_user.id)
            )
            existing_settings = existing_settings_result.scalars().all()

            # Create a dict of existing settings by ID for quick lookup
            existing_settings_dict = {
                setting.id: setting for setting in existing_settings
            }
            logger.info(
                f"Found {len(existing_settings_dict)} existing admin LLM settings"
            )

            # Seed/Update LLM settings for each model in LLM_CONFIGS
            added_count = 0
            updated_count = 0
            for model_id, config_data in llm_configs.items():
                # Encrypt API key if provided, otherwise save 'empty'
                encrypted_api_key = "empty"
                if config_data.get("api_key"):
                    from ii_agent.server.utils.encryption import encryption_manager

                    encrypted_api_key = encryption_manager.encrypt(
                        config_data["api_key"]
                    )

                # Check if this model_id already exists
                if model_id in existing_settings_dict:
                    # Update existing setting
                    existing_setting = existing_settings_dict[model_id]
                    existing_setting.model = config_data["model"]
                    existing_setting.api_type = config_data["api_type"]
                    existing_setting.encrypted_api_key = encrypted_api_key
                    existing_setting.base_url = config_data.get("base_url")
                    existing_setting.max_retries = config_data.get("max_retries", 10)
                    existing_setting.max_message_chars = config_data.get(
                        "max_message_chars", 30000
                    )
                    existing_setting.temperature = config_data.get("temperature", 0.0)
                    existing_setting.thinking_tokens = config_data.get(
                        "thinking_tokens"
                    )
                    existing_setting.is_active = True
                    existing_setting.updated_at = datetime.now(timezone.utc)
                    existing_setting.llm_metadata = {
                        "vertex_region": config_data.get("vertex_region"),
                        "vertex_project_id": config_data.get("vertex_project_id"),
                        "azure_endpoint": config_data.get("azure_endpoint"),
                        "azure_api_version": config_data.get("azure_api_version"),
                        "cot_model": config_data.get("cot_model", False),
                        "enable_extended_context": config_data.get("enable_extended_context", False),
                        "source_config_id": model_id,  # Track which config this came from
                    }
                    updated_count += 1
                    logger.info(
                        f"Updated LLM setting for model: {config_data['model']} (ID: {existing_setting.id})"
                    )
                else:
                    # Create new LLM setting
                    llm_setting = LLMSetting(
                        id=model_id,
                        user_id=admin_user.id,
                        model=config_data["model"],
                        api_type=config_data["api_type"],
                        encrypted_api_key=encrypted_api_key,
                        base_url=config_data.get("base_url"),
                        max_retries=config_data.get("max_retries", 10),
                        max_message_chars=config_data.get("max_message_chars", 30000),
                        temperature=config_data.get("temperature", 0.0),
                        thinking_tokens=config_data.get("thinking_tokens"),
                        is_active=True,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                        llm_metadata={
                            "vertex_region": config_data.get("vertex_region"),
                            "vertex_project_id": config_data.get("vertex_project_id"),
                            "azure_endpoint": config_data.get("azure_endpoint"),
                            "azure_api_version": config_data.get("azure_api_version"),
                            "cot_model": config_data.get("cot_model", False),
                            "enable_extended_context": config_data.get("enable_extended_context", False),
                            "source_config_id": model_id,  # Track which config this came from
                        },
                    )

                    db_session.add(llm_setting)
                    added_count += 1
                    logger.info(
                        f"Created LLM setting for model: {config_data['model']} (ID: {llm_setting.id})"
                    )

            if added_count > 0 or updated_count > 0:
                logger.info(
                    f"Added {added_count} new and updated {updated_count} existing admin LLM settings"
                )
            else:
                logger.info("No admin LLM settings changes needed")

            await db_session.commit()
            logger.info("Successfully seeded admin LLM settings")
        except Exception:
            await db_session.rollback()
            raise


# Flag to track if seeding has been done
_seeding_done = False


async def ensure_admin_llm_settings_seeded():
    """Ensure admin LLM settings are seeded (run once)."""
    global _seeding_done
    if not _seeding_done:
        try:
            await seed_admin_llm_settings()
            _seeding_done = True
        except Exception as e:
            logger.error(f"Error seeding admin LLM settings: {e}")


def _init_admin_settings():
    """Initialize admin settings on module load."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(ensure_admin_llm_settings_seeded())
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    except Exception as e:
        from ii_agent.core.logger import logger

        logger.error(f"Failed to seed admin LLM settings during initialization: {e}")


run_migrations()

# Parse the database URL to handle SSL parameters for asyncpg
database_url = config.database_url
connect_args = {}

if "+asyncpg" in database_url:
    # Parse the URL to extract SSL parameters
    parsed = urlparse(database_url)
    if parsed.query:
        query_params = parse_qs(parsed.query)

        # Remove SSL-related parameters from the URL
        clean_params = []
        for key, values in query_params.items():
            if key not in ["sslmode", "channel_binding", "ssl"]:
                for value in values:
                    clean_params.append(f"{key}={value}")

        # Reconstruct the URL without SSL parameters
        clean_query = "&".join(clean_params) if clean_params else ""
        database_url = database_url.split("?")[0]
        if clean_query:
            database_url += "?" + clean_query

        # Add encoding parameters for proper Unicode handling
        encoding_params = "client_encoding=utf8"
        if "?" in database_url:
            database_url += "&" + encoding_params
        else:
            database_url += "?" + encoding_params

        # Configure SSL for asyncpg based on sslmode parameter
        if "sslmode" in query_params:
            sslmode = query_params["sslmode"][0]
            if sslmode in ["require", "verify-ca", "verify-full"]:
                # Create SSL context
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                connect_args["ssl"] = ssl_context

engine = create_async_engine(
    database_url,
    echo=False,
    future=True,
    connect_args=connect_args,
    pool_size=20,
    max_overflow=0,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=30,
)
SessionLocal = async_sessionmaker(
    bind=engine, expire_on_commit=False, autocommit=False, autoflush=False
)


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session as a context manager.

    Yields:
        A database session that will be automatically committed or rolled back
    """
    async with SessionLocal() as db:
        try:
            yield db
        except exc.SQLAlchemyError as db_exc:
            await db.rollback()
            logger.error(f"Database session rollback due to exception, {db_exc}")
            raise


@asynccontextmanager
async def get_db_session_local() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session as a context manager.

    Yields:
        A database session that will be automatically committed or rolled back
    """
    async with SessionLocal() as db:
        try:
            yield db
            await db.commit()
        except exc.SQLAlchemyError as db_exc:
            await db.rollback()
            logger.error(
                f"Exception during local session, rolling back, error: {db_exc}"
            )
            raise


class SessionsTable:
    """Table class for session operations following Open WebUI pattern."""

    async def create_session(
        self,
        session_uuid: uuid.UUID,
        user_id: str,
        agent_state_path: str,
        name: Optional[str] = None,
    ) -> Session:
        """Create a new session with a UUID-based workspace directory.

        Args:
            session_uuid: The UUID for the session
            user_id: The ID of the user creating the session
            title: Optional title for the session

        Returns:
            A tuple of (session_uuid, workspace_path)
        """
        # Create session in database
        async with get_db_session_local() as db:
            session = Session(
                id=str(session_uuid),
                user_id=user_id,
                name=name,
                status="active",
                agent_state_path=agent_state_path,
            )
            db.add(session)
            await db.flush()  # This will populate the id field
            await db.refresh(session)

        return session


    async def update_sandbox_id(self, session_uuid: uuid.UUID, sandbox_id: str):
        """Update the sandbox ID for a session.

        Args:
            session_uuid: The UUID of the session
            sandbox_id: The sandbox ID
        """
        async with get_db_session_local() as db:
            db_session = await db.execute(
                select(Session).where(Session.id == str(session_uuid))
            )
            db_session = db_session.scalar_one_or_none()
            if db_session:
                db_session.sandbox_id = sandbox_id
                await db.flush()

    async def get_session_by_workspace(self, workspace_dir: str) -> Optional[Session]:
        """Get a session by its workspace directory.

        Args:
            workspace_dir: The workspace directory path

        Returns:
            The session if found, None otherwise
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(Session).where(Session.workspace_dir == workspace_dir)
            )
            return result.scalar_one_or_none()

    async def session_has_sandbox(self, session_id: uuid.UUID) -> bool:
        """Check if a sandbox ID exists in the database.

        Args:
            session_id: The session ID to check

        Returns:
            True if the sandbox ID exists, False otherwise
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(Session).where(Session.id == str(session_id))
            )
            session = result.scalar_one_or_none()
            return session is not None and session.sandbox_id is not None

    async def has_active_session_for_sandbox(self, sandbox_id: str) -> bool:
        """Check if there is an active (non-deleted) session for a sandbox.

        Args:
            sandbox_id: The sandbox ID to check

        Returns:
            True if an active session exists for this sandbox, False otherwise
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(Session).where(
                    Session.sandbox_id == sandbox_id,
                    Session.deleted_at.is_(None)  # Only non-deleted sessions
                )
            )
            session = result.scalar_one_or_none()
            return session is not None

    async def find_session_by_id(
        self, *, db: AsyncSession, session_id: uuid.UUID
    ) -> Optional[Session]:
        """Get a session by its UUID.

        Args:
            session_id: The UUID of the session

        Returns:
            The session if found, None otherwise
        """
        result = await db.execute(select(Session).where(Session.id == str(session_id)))
        return result.scalar_one_or_none()

    async def get_session_by_id(self, session_id: uuid.UUID) -> Optional[Session]:
        """Get a session by its UUID.

        Args:
            session_id: The UUID of the session

        Returns:
            The session if found, None otherwise
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(Session).where(Session.id == str(session_id))
            )
            return result.scalar_one_or_none()

    async def update_session_name(self, session_id: uuid.UUID, name: str) -> None:
        """Update the name of a session.

        Args:
            session_id: The UUID of the session to update
            name: The new name for the session
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(Session).where(Session.id == str(session_id))
            )
            db_session = result.scalar_one_or_none()
            if db_session:
                db_session.name = name
                await db.flush()

    async def update_session_agent_type(
        self, session_id: uuid.UUID, agent_type: str
    ) -> None:
        """Update the agent type of a session.

        Args:
            session_id: The UUID of the session to update
            agent_type: The new agent type for the session
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(Session).where(Session.id == str(session_id))
            )
            db_session = result.scalar_one_or_none()
            if db_session:
                db_session.agent_type = agent_type
                await db.flush()

    async def update_session_llm_setting_id(
        self, session_id: uuid.UUID, llm_setting_id: Optional[str]
    ) -> None:
        """Update the LLM setting ID of a session.

        Args:
            session_id: The UUID of the session to update
            llm_setting_id: The LLM setting ID to associate with the session, or None to clear it
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(Session).where(Session.id == str(session_id))
            )
            db_session = result.scalar_one_or_none()
            if db_session:
                db_session.llm_setting_id = llm_setting_id
                await db.flush()

    async def get_session_llm_setting_id(self, session_id: uuid.UUID) -> Optional[str]:
        """Get the LLM setting ID for a session.

        Args:
            session_id: The UUID of the session

        Returns:
            The LLM setting ID if set, None otherwise
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(Session.llm_setting_id).where(Session.id == str(session_id))
            )
            return result.scalar_one_or_none()

    async def get_user_sessions(
        self,
        user_id: str,
        search_term: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        public_only: Optional[bool] = False,
    ) -> tuple[List[dict], int]:
        """Get sessions for a user with optional search and pagination.

        Args:
            user_id: The ID of the user
            search_term: Optional search term to filter sessions by name
            page: Page number for pagination (1-indexed)
            per_page: Number of items per page

        Returns:
            A tuple of (list of session dictionaries, total count)
        """
        async with get_db_session_local() as db:
            query = select(Session).where(
                Session.user_id == user_id, Session.deleted_at.is_(None)
            )

            if public_only:
                query = query.where(Session.is_public)

            if search_term:
                query = query.where(Session.name.ilike(f"%{search_term}%"))

            # Get total count
            count_query = (
                select(func.count())
                .select_from(Session)
                .where(Session.user_id == user_id, Session.deleted_at.is_(None))
            )
            if public_only:
                count_query = count_query.where(Session.is_public)
            if search_term:
                count_query = count_query.where(Session.name.ilike(f"%{search_term}%"))

            count_result = await db.execute(count_query)
            total = count_result.scalar()

            # Apply pagination
            offset = (page - 1) * per_page
            query = (
                query.order_by(desc(Session.created_at)).limit(per_page).offset(offset)
            )

            result = await db.execute(query)
            sessions = result.scalars().all()

            return [
                {
                    "id": str(session.id),
                    "user_id": session.user_id,
                    "name": session.name,
                    "status": session.status,
                    "sandbox_id": session.sandbox_id,
                    "workspace_dir": f"/workspace/{session.id}",
                    "is_public": session.is_public,
                    "public_url": session.public_url,
                    "token_usage": None,
                    "settings": None,
                    "agent_type": session.agent_type,
                    "created_at": (
                        session.created_at.isoformat() if session.created_at else None
                    ),
                    "updated_at": (
                        session.updated_at.isoformat() if session.updated_at else None
                    ),
                    "last_message_at": (
                        session.last_message_at.isoformat()
                        if session.last_message_at
                        else None
                    ),
                }
                for session in sessions
            ], total

    async def get_session_details(
        self, session_id: str, user_id: str
    ) -> Optional[dict]:
        """Get detailed information for a specific session.

        Args:
            session_id: The ID of the session
            user_id: The ID of the user (for authorization)

        Returns:
            A dictionary with session details if found and user has access, None otherwise
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(Session).where(
                    Session.id == session_id,
                    Session.user_id == user_id,
                    Session.deleted_at.is_(None),
                )
            )
            session = result.scalar_one_or_none()

            if not session:
                return None

            return {
                "id": str(session.id),
                "user_id": session.user_id,
                "name": session.name,
                "status": session.status,
                "sandbox_id": session.sandbox_id,
                "workspace_dir": f"/workspace/{session.id}",
                "is_public": session.is_public,
                "public_url": session.public_url,
                "token_usage": None,
                "settings": None,
                "agent_type": session.agent_type,
                "created_at": (
                    session.created_at.isoformat() if session.created_at else None
                ),
                "updated_at": (
                    session.updated_at.isoformat() if session.updated_at else None
                ),
                "last_message_at": (
                    session.last_message_at.isoformat()
                    if session.last_message_at
                    else None
                ),
            }

    async def soft_delete_session(self, session_id: str, user_id: str) -> None:
        """Soft delete a session by setting its deleted_at timestamp.

        Args:
            session_id: The ID of the session to delete
            user_id: The ID of the user (for authorization)

        Raises:
            Exception: If session not found or user lacks access
        """
        from datetime import datetime, timezone

        async with get_db_session_local() as db:
            result = await db.execute(
                select(Session).where(
                    Session.id == session_id,
                    Session.user_id == user_id,
                    Session.deleted_at.is_(None),
                )
            )
            session = result.scalar_one_or_none()

            if not session:
                raise Exception(f"Session {session_id} not found or already deleted")

            session.deleted_at = datetime.now(timezone.utc)
            await db.flush()

    async def set_session_public(
        self, session_id: str, user_id: str, is_public: bool
    ) -> bool:
        """Set the public status of a session.

        Args:
            session_id: The ID of the session
            user_id: The ID of the user (for authorization)
            is_public: Whether the session should be public

        Returns:
            True if the update was successful, False if session not found

        Raises:
            Exception: If user lacks access
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(Session).where(
                    Session.id == session_id,
                    Session.user_id == user_id,
                    Session.deleted_at.is_(None),
                )
            )
            session = result.scalar_one_or_none()

            if not session:
                return False

            session.is_public = is_public
            await db.flush()
            return True

    async def get_public_session_details(self, session_id: str) -> Optional[dict]:
        """Get detailed information for a public session.

        Args:
            session_id: The ID of the session

        Returns:
            A dictionary with session details if found and session is public, None otherwise
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(Session).where(
                    Session.id == session_id,
                    Session.is_public,
                    Session.deleted_at.is_(None),
                )
            )
            session = result.scalar_one_or_none()

            if not session:
                return None

            return {
                "id": str(session.id),
                "user_id": session.user_id,
                "name": session.name,
                "status": session.status,
                "sandbox_id": session.sandbox_id,
                "workspace_dir": f"/workspace/{session.id}",
                "is_public": session.is_public,
                "public_url": session.public_url,
                "token_usage": None,
                "settings": None,
                "agent_type": session.agent_type,
                "created_at": (
                    session.created_at.isoformat() if session.created_at else None
                ),
                "updated_at": (
                    session.updated_at.isoformat() if session.updated_at else None
                ),
                "last_message_at": (
                    session.last_message_at.isoformat()
                    if session.last_message_at
                    else None
                ),
            }

    async def get_sessions_with_running_status(self) -> List[Session]:
        """Get all sessions that have active running status.

        Returns:
            List of Session objects with running status
        """
        async with get_db_session_local() as db:
            # Join Session with SessionStatus to find sessions with running status
            result = await db.execute(
                select(Session)
                .join(
                    AgentRunTask,
                    Session.id == AgentRunTask.session_id,
                )
                .where(
                    AgentRunTask.status == RunStatus.RUNNING,
                    Session.deleted_at.is_(None),
                )
            )
            return result.scalars().all()

    async def get_session_running_status(
        self, session_id: str
    ) -> Optional[AgentRunTask]:
        """Get the running status for a specific session.

        Args:
            session_id: The ID of the session

        Returns:
            SessionStatus object if found and running, None otherwise
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(AgentRunTask).where(
                    AgentRunTask.session_id == session_id,
                    AgentRunTask.status == RunStatus.RUNNING,
                )
            )
            return result.scalar_one_or_none()


class ProjectsTable:
    """Table helper for project CRUD operations."""

    async def create_or_update_project(
        self,
        *,
        session_id: str,
        project_name: str,
        framework: str | None = None,
        project_path: str | None = None,
        description: str | None = None,
    ) -> dict | None:
        async with get_db_session_local() as db:
            session_result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = session_result.scalar_one_or_none()
            if not session:
                logger.warning(
                    "Unable to persist project metadata because session %s was not found",
                    session_id,
                )
                return None

            user_id = session.user_id

            existing_result = await db.execute(
                select(Project)
                .where(Project.user_id == user_id)
                .where(Project.name == project_name)
                .where(Project.deleted_at.is_(None))
            )
            project = existing_result.scalar_one_or_none()

            if project:
                project.framework = framework
                project.project_path = project_path
                project.session_id = session_id
                project.description = description or project.description
            else:
                project = Project(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    session_id=session_id,
                    name=project_name,
                    description=description,
                    framework=framework,
                    project_path=project_path,
                )
                db.add(project)

            await db.flush()
            await db.refresh(project)

            return self.serialize_project(project)

    def serialize_project(self, project: Project) -> dict:
        return {
            "id": project.id,
            "user_id": project.user_id,
            "session_id": project.session_id,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "current_build_status": project.current_build_status,
            "framework": project.framework,
            "project_path": project.project_path,
            "database": project.database_json,
            "storage": project.storage_json,
            "secrets": project.secrets_json,
            "current_production_deployment_id": project.current_production_deployment_id,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        }


class EventsTable:
    """Table class for event operations following Open WebUI pattern."""

    async def save_event(
        self, session_id: uuid.UUID, event: RealtimeEvent
    ) -> uuid.UUID:
        """Save an event to the database.

        Args:
            session_id: The UUID of the session this event belongs to
            event: The event to save

        Returns:
            The UUID of the created event
        """
        # Use event timestamp if provided, otherwise use current time
        event_timestamp = (
            datetime.fromtimestamp(event.timestamp, tz=timezone.utc)
            if hasattr(event, "timestamp") and event.timestamp
            else datetime.now(timezone.utc)
        )

        async with get_db_session_local() as db:
            db_event = Event(
                id=str(event.id),
                session_id=str(session_id),
                run_id=event.run_id,
                type=event.type.value,
                content=event.content,
                created_at=event_timestamp,  # Use the event's timestamp
            )
            db.add(db_event)
            await db.flush()  # This will populate the id field
            await db.refresh(db_event)
        return uuid.UUID(db_event.id)

    async def save_event_db_session(
        self, db: AsyncSession, session_id: uuid.UUID, event: RealtimeEvent
    ) -> Event:
        """Save an event to the database.

        Args:
            session_id: The UUID of the session this event belongs to
            event: The event to save

        Returns:
            The UUID of the created event
        """
        # Use event timestamp if provided, otherwise use current time
        event_timestamp = (
            datetime.fromtimestamp(event.timestamp, tz=timezone.utc)
            if hasattr(event, "timestamp") and event.timestamp
            else datetime.now(timezone.utc)
        )

        db_event = Event(
            id=str(event.id),
            session_id=str(session_id),
            run_id=event.run_id,
            type=event.type.value,
            content=event.content,
            created_at=event_timestamp,  # Use the event's timestamp
        )
        db.add(db_event)
        await db.flush()  # This will populate the id field
        await db.refresh(db_event)
        return db_event

    async def get_session_events(self, session_id: uuid.UUID) -> list[Event]:
        """Get all events for a session.

        Args:
            session_id: The UUID of the session

        Returns:
            A list of events for the session
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(Event).where(Event.session_id == str(session_id))
            )
            return result.scalars().all()

    async def delete_session_events(self, session_id: uuid.UUID) -> None:
        """Delete all events for a session.

        Args:
            session_id: The UUID of the session to delete events for
        """
        async with get_db_session_local() as db:
            await db.execute(select(Event).where(Event.session_id == str(session_id)))
            # For delete operations, we need to fetch and delete each item
            result = await db.execute(
                select(Event).where(Event.session_id == str(session_id))
            )
            for event in result.scalars():
                await db.delete(event)

    async def delete_events_from_last_to_user_message(
        self, session_id: uuid.UUID
    ) -> None:
        """Delete events from the most recent event backwards to the last user message (inclusive).
        This preserves the conversation history before the last user message.

        Args:
            session_id: The UUID of the session to delete events for
        """
        async with get_db_session_local() as db:
            # Find the last user message event
            result = await db.execute(
                select(Event)
                .where(
                    Event.session_id == str(session_id),
                    Event.type == EventType.USER_MESSAGE.value,
                )
                .order_by(Event.timestamp.desc())
            )
            last_user_event = result.scalar_one_or_none()

            if last_user_event:
                # Delete all events after the last user message (inclusive)
                result = await db.execute(
                    select(Event).where(
                        Event.session_id == str(session_id),
                        Event.timestamp >= last_user_event.timestamp,
                    )
                )
                for event in result.scalars():
                    await db.delete(event)
            else:
                # If no user message found, delete all events
                result = await db.execute(
                    select(Event).where(Event.session_id == str(session_id))
                )
                for event in result.scalars():
                    await db.delete(event)

    async def get_session_events_with_details(self, session_id: str) -> List[dict]:
        """Get all events for a specific session ID with session details, sorted by timestamp ascending.

        Args:
            session_id: The session identifier to look up events for

        Returns:
            A list of event dictionaries with their details, sorted by timestamp ascending
        """
        ignored_events = [
            EventType.STATUS_UPDATE.value,
            EventType.SYSTEM.value,
            EventType.ERROR.value,
            EventType.PONG.value,
            EventType.CONNECTION_ESTABLISHED.value,
            EventType.WORKSPACE_INFO.value,
            EventType.AGENT_INITIALIZED.value,
            EventType.SANDBOX_STATUS.value,
        ]

        async with get_db_session_local() as db:
            result = await db.execute(
                select(Event)
                .where(Event.session_id == session_id)
                .where(Event.type.not_in(ignored_events))
                .order_by(asc(Event.created_at))
            )
            events = result.scalars().all()

            # Convert events to a list of dictionaries
            event_list = []
            for e in events:
                event_data = {
                    "id": e.id,
                    "session_id": e.session_id,
                    "created_at": e.created_at.isoformat(),
                    "type": e.type,
                    "content": e.content,
                    "workspace_dir": f"/workspace/{e.session_id}",
                }
                event_list.append(event_data)

            return event_list


class FileTable:
    async def get_file_by_id(self, file_id: str):
        async with get_db_session_local() as db:
            result = await db.execute(
                select(FileUpload).where(FileUpload.id == file_id)
            )
            return result.scalar_one_or_none()

    async def get_files_by_session_id(self, session_id: str):
        async with get_db_session_local() as db:
            result = await db.execute(
                select(FileUpload).where(FileUpload.session_id == session_id)
            )
            return result.scalars().all()

    async def update_session_id(self, file_id: str, session_id: str):
        async with get_db_session_local() as db:
            result = await db.execute(
                select(FileUpload).where(FileUpload.id == file_id)
            )
            file = result.scalar_one_or_none()
            if file:
                file.session_id = session_id
                await db.flush()
                return True
            return False

    async def create_file(
        self,
        file_id: str,
        file_name: str,
        file_size: int,
        storage_path: str,
        content_type: str,
        session_id: str,
    ):
        async with get_db_session_local() as db:
            # get the user id from the session id
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()
            if session:
                user_id = session.user_id
            else:
                raise ValueError(f"Session {session_id} not found")

            db_file = FileUpload(
                id=file_id,
                file_name=file_name,
                file_size=file_size,
                storage_path=storage_path,
                content_type=content_type,
                session_id=session_id,
                user_id=user_id,
            )
            db.add(db_file)
            await db.flush()
            return db_file


class APIKeysTable:
    async def get_active_api_key_for_user(self, user_id: str) -> Optional[str]:
        """Get the active API key for a user.

        Args:
            user_id: The ID of the user

        Returns:
            The API key string if found and active, None otherwise
        """
        async with get_db_session_local() as db:
            result = await db.execute(
                select(APIKey)
                .where(APIKey.user_id == user_id, APIKey.is_active)
                .order_by(desc(APIKey.created_at))
            )
            api_key_obj = result.scalar_one_or_none()
            return api_key_obj.api_key if api_key_obj else None


# Create singleton instances following Open WebUI pattern
Sessions = SessionsTable()
Events = EventsTable()
Files = FileTable()
APIKeys = APIKeysTable()
Projects = ProjectsTable()
