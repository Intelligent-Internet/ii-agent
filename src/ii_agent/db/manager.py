from contextlib import contextmanager
from typing import Optional, Generator, List
import uuid
from pathlib import Path
from sqlalchemy import create_engine, asc, text
from sqlalchemy.orm import sessionmaker, Session as DBSession
from ii_agent.db.models import Base, Session, Event
from ii_agent.core.event import EventType, RealtimeEvent


# Database setup
DATABASE_URL = "sqlite:///db/events.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

# Create tables if they don't exist
Base.metadata.create_all(engine)


@contextmanager
def get_db() -> Generator[DBSession, None, None]:
    """Get a database session as a context manager.

    Yields:
        A database session that will be automatically committed or rolled back
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class SessionsTable:
    """Table class for session operations following Open WebUI pattern."""

    def create_session(
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
        with get_db() as db:
            db_session = Session(
                id=session_uuid, workspace_dir=str(workspace_path), device_id=device_id
            )
            db.add(db_session)
            db.flush()  # This will populate the id field

        return session_uuid, workspace_path

    def get_session_by_workspace(self, workspace_dir: str) -> Optional[Session]:
        """Get a session by its workspace directory.

        Args:
            workspace_dir: The workspace directory path

        Returns:
            The session if found, None otherwise
        """
        with get_db() as db:
            return (
                db.query(Session)
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
        with get_db() as db:
            return db.query(Session).filter(Session.id == str(session_id)).first()

    def get_session_by_device_id(self, device_id: str) -> Optional[Session]:
        """Get a session by its device ID.

        Args:
            device_id: The device identifier

        Returns:
            The session if found, None otherwise
        """
        with get_db() as db:
            return db.query(Session).filter(Session.device_id == device_id).first()

    def update_session_name(self, session_id: uuid.UUID, name: str) -> None:
        """Update the name of a session.

        Args:
            session_id: The UUID of the session to update
            name: The new name for the session
        """
        with get_db() as db:
            db_session = db.query(Session).filter(Session.id == str(session_id)).first()
            if db_session:
                db_session.name = name
                db.flush()

    def get_sessions_by_device_id(self, device_id: str) -> List[dict]:
        """Get all sessions for a specific device ID, sorted by creation time descending.
        
        Args:
            device_id: The device identifier to look up sessions for

        Returns:
            A list of session dictionaries with their details, sorted by creation time descending
        """
        with get_db() as db:
            # Use raw SQL query to get sessions by device_id
            query = text("""
            SELECT 
                session.id,
                session.workspace_dir,
                session.created_at,
                session.device_id,
                session.name
            FROM session
            WHERE session.device_id = :device_id
            ORDER BY session.created_at DESC
            """)

            # Execute the raw query with parameters
            result = db.execute(query, {"device_id": device_id})

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

    def save_event(self, session_id: uuid.UUID, event: RealtimeEvent) -> uuid.UUID:
        """Save an event to the database.

        Args:
            session_id: The UUID of the session this event belongs to
            event: The event to save

        Returns:
            The UUID of the created event
        """
        with get_db() as db:
            db_event = Event(
                session_id=session_id,
                event_type=event.type.value,
                event_payload=event.model_dump(),
            )
            db.add(db_event)
            db.flush()  # This will populate the id field
            return uuid.UUID(db_event.id)

    def get_session_events(self, session_id: uuid.UUID) -> list[Event]:
        """Get all events for a session.

        Args:
            session_id: The UUID of the session

        Returns:
            A list of events for the session
        """
        with get_db() as db:
            return (
                db.query(Event).filter(Event.session_id == str(session_id)).all()
            )

    def delete_session_events(self, session_id: uuid.UUID) -> None:
        """Delete all events for a session.

        Args:
            session_id: The UUID of the session to delete events for
        """
        with get_db() as db:
            db.query(Event).filter(Event.session_id == str(session_id)).delete()

    def delete_events_from_last_to_user_message(self, session_id: uuid.UUID) -> None:
        """Delete events from the most recent event backwards to the last user message (inclusive).
        This preserves the conversation history before the last user message.
        
        Args:
            session_id: The UUID of the session to delete events for
        """
        with get_db() as db:
            # Find the last user message event
            last_user_event = (
                db.query(Event)
                .filter(
                    Event.session_id == str(session_id),
                    Event.event_type == EventType.USER_MESSAGE.value,
                )
                .order_by(Event.timestamp.desc())
                .first()
            )

            if last_user_event:
                # Delete all events after the last user message (inclusive)
                db.query(Event).filter(
                    Event.session_id == str(session_id),
                    Event.timestamp >= last_user_event.timestamp,
                ).delete()
            else:
                # If no user message found, delete all events
                db.query(Event).filter(
                    Event.session_id == str(session_id)
                ).delete()

    def get_session_events_with_details(self, session_id: str) -> List[dict]:
        """Get all events for a specific session ID with session details, sorted by timestamp ascending.

        Args:
            session_id: The session identifier to look up events for

        Returns:
            A list of event dictionaries with their details, sorted by timestamp ascending
        """
        with get_db() as db:
            events = (
                db.query(Event)
                .filter(Event.session_id == session_id)
                .order_by(asc(Event.timestamp))
                .all()
            )

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
