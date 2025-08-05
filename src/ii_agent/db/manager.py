from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, List
import uuid
from pathlib import Path
from sqlalchemy import asc, text, select
from sqlalchemy.orm import selectinload
from ii_agent.core.config.ii_agent_config import config
from ii_agent.db.models import Session, Event
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.core.config.ii_agent_config import II_AGENT_DIR
from ii_agent.core.logger import logger
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession as DBSession


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


run_migrations()

# engine = create_engine(load_ii_agent_config().database_url, connect_args={"check_same_thread": False})
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
engine = create_async_engine(config.database_url, echo=True, future=True)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


@asynccontextmanager
async def get_db() -> AsyncGenerator[DBSession, None]:
    """Get a database session as a context manager.

    Yields:
        A database session that will be automatically committed or rolled back
    """
    async with SessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()


class SessionsTable:
    """Table class for session operations following Open WebUI pattern."""

    async def create_session(
        self,
        session_uuid: uuid.UUID,
        workspace_path: Path,
        device_id: Optional[str] = None,
    ) -> tuple[uuid.UUID, Path]:
        """Create a new session with a UUID-based workspace directory.

        Args:
            session_uuid: The UUID for the session
            workspace_path: The path to the workspace directory
            device_id: Optional device identifier for the session

        Returns:
            A tuple of (session_uuid, workspace_path)
        """
        # Create session in database
        async with get_db() as db:
            db_session = Session(
                id=session_uuid, workspace_dir=str(workspace_path), device_id=device_id
            )
            db.add(db_session)
            await db.flush()  # This will populate the id field

        return session_uuid, workspace_path

    async def get_session_by_workspace(self, workspace_dir: str) -> Optional[Session]:
        """Get a session by its workspace directory.

        Args:
            workspace_dir: The workspace directory path

        Returns:
            The session if found, None otherwise
        """
        async with get_db() as db:
            result = await db.execute(
                select(Session).where(Session.workspace_dir == workspace_dir)
            )
            return result.scalar_one_or_none()

    async def get_session_by_id(self, session_id: uuid.UUID) -> Optional[Session]:
        """Get a session by its UUID.

        Args:
            session_id: The UUID of the session

        Returns:
            The session if found, None otherwise
        """
        async with get_db() as db:
            result = await db.execute(
                select(Session).where(Session.id == str(session_id))
            )
            return result.scalar_one_or_none()

    async def get_session_by_device_id(self, device_id: str) -> Optional[Session]:
        """Get a session by its device ID.

        Args:
            device_id: The device identifier

        Returns:
            The session if found, None otherwise
        """
        async with get_db() as db:
            result = await db.execute(
                select(Session).where(Session.device_id == device_id)
            )
            return result.scalar_one_or_none()

    async def update_session_name(self, session_id: uuid.UUID, name: str) -> None:
        """Update the name of a session.

        Args:
            session_id: The UUID of the session to update
            name: The new name for the session
        """
        async with get_db() as db:
            result = await db.execute(
                select(Session).where(Session.id == str(session_id))
            )
            db_session = result.scalar_one_or_none()
            if db_session:
                db_session.name = name
                await db.flush()

    async def get_sessions_by_device_id(self, device_id: str) -> List[dict]:
        """Get all sessions for a specific device ID, sorted by creation time descending.

        Args:
            device_id: The device identifier to look up sessions for

        Returns:
            A list of session dictionaries with their details, sorted by creation time descending
        """
        async with get_db() as db:
            # Use raw SQL query to get sessions by device_id
            query = text(
                """
            SELECT 
                session.id,
                session.workspace_dir,
                session.created_at,
                session.device_id,
                session.name
            FROM session
            WHERE session.device_id = :device_id
            ORDER BY session.created_at DESC
            """
            )

            # Execute the raw query with parameters
            result = await db.execute(query, {"device_id": device_id})

            # Convert result to a list of dictionaries
            sessions = []
            for row in result:
                session_data = {
                    "id": row.id,
                    "workspace_dir": row.workspace_dir,
                    "created_at": row.created_at,
                    "device_id": row.device_id,
                    "name": row.name or "",
                }
                sessions.append(session_data)

            return sessions


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
        async with get_db() as db:
            db_event = Event(
                session_id=session_id,
                event_type=event.type.value,
                event_payload=event.model_dump(),
            )
            db.add(db_event)
            await db.flush()  # This will populate the id field
            return uuid.UUID(db_event.id)

    async def get_session_events(self, session_id: uuid.UUID) -> list[Event]:
        """Get all events for a session.

        Args:
            session_id: The UUID of the session

        Returns:
            A list of events for the session
        """
        async with get_db() as db:
            result = await db.execute(
                select(Event).where(Event.session_id == str(session_id))
            )
            return result.scalars().all()

    async def delete_session_events(self, session_id: uuid.UUID) -> None:
        """Delete all events for a session.

        Args:
            session_id: The UUID of the session to delete events for
        """
        async with get_db() as db:
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
        async with get_db() as db:
            # Find the last user message event
            result = await db.execute(
                select(Event)
                .where(
                    Event.session_id == str(session_id),
                    Event.event_type == EventType.USER_MESSAGE.value,
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
        async with get_db() as db:
            result = await db.execute(
                select(Event)
                .where(Event.session_id == session_id)
                .order_by(asc(Event.timestamp))
                .options(selectinload(Event.session))
            )
            events = result.scalars().all()

            # Convert events to a list of dictionaries
            event_list = []
            for e in events:
                event_data = {
                    "id": e.id,
                    "session_id": e.session_id,
                    "timestamp": e.timestamp.isoformat(),
                    "event_type": e.event_type,
                    "event_payload": e.event_payload,
                    "workspace_dir": e.session.workspace_dir,
                }
                event_list.append(event_data)

            return event_list


# Create singleton instances following Open WebUI pattern
Sessions = SessionsTable()
Events = EventsTable()
