"""Session lifecycle management domain module.

Services (SessionService, SessionForkService, SessionTitleService) are
accessed via DI from the container — import from their own modules or
use the Dep aliases in sessions/dependencies.py.
"""

from ii_agent.sessions.exceptions import SessionNotFoundError, SessionValidationError
from ii_agent.sessions.models import Session
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.schemas import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    ForkContext,
    ForkSessionRequest,
    ForkSessionResponse,
    ForkType,
    SandboxMode,
    ScheduleDeleteRequest,
    SessionCreate,
    SessionFile,
    SessionInfo,
    SessionMilestoneUpdate,
    SessionPlan,
    SessionPlanUpdate,
    SessionResponse,
    SessionStats,
    SessionUpdate,
    ValidatedSessionResult,
)
from ii_agent.sessions.types import AppKind, SessionState

__all__ = [
    # Exceptions
    "SessionNotFoundError",
    "SessionValidationError",
    # Models
    "Session",
    # Repository
    "SessionRepository",
    # Schemas
    "BulkDeleteRequest",
    "BulkDeleteResponse",
    "ForkContext",
    "ForkSessionRequest",
    "ForkSessionResponse",
    "ForkType",
    "SandboxMode",
    "ScheduleDeleteRequest",
    "SessionCreate",
    "SessionFile",
    "SessionInfo",
    "SessionMilestoneUpdate",
    "SessionPlan",
    "SessionPlanUpdate",
    "SessionResponse",
    "SessionStats",
    "SessionUpdate",
    "ValidatedSessionResult",
    # Types
    "AppKind",
    "SessionState",
]
