"""Session configuration for CLI."""

from pathlib import Path
from typing import List
from pydantic import BaseModel


class SessionConfig(BaseModel):
    """Configuration for session management."""

    session_id: str
    session_name: str

    @property
    def sessions_dir(self) -> Path:
        """Get the sessions directory path."""
        home = Path.home()
        return home / ".ii_agent" / "sessions"

    def get_available_sessions(self) -> List[str]:
        """Get list of available session names from the sessions directory."""
        sessions_dir = self.sessions_dir
        if not sessions_dir.exists():
            return []

        sessions = []
        for session_file in sessions_dir.glob("*.json"):
            sessions.append(session_file.stem)

        return sorted(sessions)

    def session_exists(self, session_name: str) -> bool:
        """Check if a session exists."""
        session_file = self.sessions_dir / f"{session_name}.json"
        return session_file.exists()

    def ensure_sessions_dir(self) -> None:
        """Ensure the sessions directory exists."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
