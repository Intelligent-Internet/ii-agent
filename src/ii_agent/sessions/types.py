"""Session domain enums."""

from enum import StrEnum


class SessionState(StrEnum):
    """Session state values."""

    PENDING = "pending"
    ACTIVE = "active"
    PAUSE = "pause"


class AppKind(StrEnum):
    """Application kind for sessions."""

    AGENT = "agent"
    CHAT = "chat"
    BROWSER_EXTENSION = "browser_extension"
