from contextlib import contextmanager
from typing import Optional, Generator
import uuid
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as DBSession
from ii_agent.db.models import Base, Session, Event
from ii_agent.core.event import EventType, RealtimeEvent


class DatabaseManager:
    """Manager class for database operations."""

    def __init__(self, db_path: str = "events.db"):
        """Initialize the database manager.

        Args:
            db_path: Path to the SQLite database file
        """
        self.engine = create_engine(f"sqlite:///{db_path}")
        self.SessionFactory = sessionmaker(bind=self.engine)

        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)

    @contextmanager
    def get_session(self) -> Generator[DBSession, None, None]:
        """Get a database session as a context manager.

        Yields:
            A database session that will be automatically committed or rolled back
        """
        session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_session(
        self,
        session_uuid: uuid.UUID,
        workspace_path: Path,
        device_id: Optional[str] = None,
    ) -> None:
        """Create a new session with a UUID-based workspace directory.

        Args:
            session_uuid: The UUID for the session
            workspace_path: The path to the workspace directory
            device_id: Optional device identifier for the session

        Returns:
            A tuple of (session_uuid, workspace_path)
        """

        # Create session in database
        with self.get_session() as session:
            db_session = Session(
                id=session_uuid, workspace_dir=str(workspace_path), device_id=device_id
            )
            session.add(db_session)
            session.flush()  # This will populate the id field

        return session_uuid, workspace_path

    def save_event(self, session_id: uuid.UUID, event: RealtimeEvent) -> uuid.UUID:
        """Save an event to the database.

        Args:
            session_id: The UUID of the session this event belongs to
            event: The event to save

        Returns:
            The UUID of the created event
        """
        with self.get_session() as session:
            db_event = Event(
                session_id=session_id,
                event_type=event.type.value,
                event_payload=event.model_dump(),
            )
            session.add(db_event)
            session.flush()  # This will populate the id field
            return uuid.UUID(db_event.id)

    def get_session_events(self, session_id: uuid.UUID) -> list[Event]:
        """Get all events for a session.

        Args:
            session_id: The UUID of the session

        Returns:
            A list of events for the session
        """
        with self.get_session() as session:
            return (
                session.query(Event).filter(Event.session_id == str(session_id)).all()
            )

    def get_session_by_workspace(self, workspace_dir: str) -> Optional[Session]:
        """Get a session by its workspace directory.

        Args:
            workspace_dir: The workspace directory path

        Returns:
            The session if found, None otherwise
        """
        with self.get_session() as session:
            return (
                session.query(Session)
                .filter(Session.workspace_dir == workspace_dir)
                .first()
            )

    def get_session_by_id(self, session_id: uuid.UUID) -> Optional[Session]:
        """Get a session by its UUID.

        Args:
            session_id: The UUID of the session

        Returns:
            The session if found, None otherwise
        """
        with self.get_session() as session:
            return session.query(Session).filter(Session.id == str(session_id)).first()

    def get_session_by_device_id(self, device_id: str) -> Optional[Session]:
        """Get a session by its device ID.

        Args:
            device_id: The device identifier

        Returns:
            The session if found, None otherwise
        """
        with self.get_session() as session:
            return session.query(Session).filter(Session.device_id == device_id).first()

    def delete_session_events(self, session_id: uuid.UUID) -> None:
        """Delete all events for a session.

        Args:
            session_id: The UUID of the session to delete events for
        """
        with self.get_session() as session:
            session.query(Event).filter(Event.session_id == str(session_id)).delete()

    def delete_events_from_last_to_user_message(self, session_id: uuid.UUID) -> None:
        """Delete events from the most recent event backwards to the last user message (inclusive).
        This preserves the conversation history before the last user message.
        Args:
            session_id: The UUID of the session to delete events for
        """
        with self.get_session() as session:
            # Find the last user message event
            last_user_event = (
                session.query(Event)
                .filter(
                    Event.session_id == str(session_id),
                    Event.event_type == EventType.USER_MESSAGE.value
                )
                .order_by(Event.timestamp.desc())
                .first()
            )

            if last_user_event:
                # Delete all events after the last user message (inclusive)
                session.query(Event).filter(
                    Event.session_id == str(session_id),
                    Event.timestamp >= last_user_event.timestamp
                ).delete()
            else:
                # If no user message found, delete all events
                session.query(Event).filter(
                    Event.session_id == str(session_id)
                ).delete()
