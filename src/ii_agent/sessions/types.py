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


class SessionCustody(StrEnum):
    """Retention custody — drives purge eligibility (§3.5, §4.1).

    - STANDARD     — normal retention (purge_grace_period_seconds applies).
    - EPHEMERAL    — short retention (ephemeral_purge_grace_period_seconds applies).
    - LEGAL_HOLD   — purge BLOCKED until operator clears the hold (I1, I3).
    """

    STANDARD = "standard"
    EPHEMERAL = "ephemeral"
    LEGAL_HOLD = "legal_hold"
