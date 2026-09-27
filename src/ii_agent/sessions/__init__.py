"""Session lifecycle management domain module.

Services (SessionService, SessionForkService, SessionTitleService) are
accessed via DI from the container — import from their own modules or
use the Dep aliases in sessions/dependencies.py.
"""

from ii_agent.sessions.exceptions import SessionNotFoundError, SessionValidationError
from ii_agent.sessions.models import Session

# Register ORM model with Base.metadata at import time. The hand-written
# migration in 20260427_000008 creates the underlying table, but autogen
# diff and any test fixture that calls Base.metadata.create_all() require
# this side-import (B4 fix; v3.11).
from ii_agent.sessions.purge import db_models as _purge_db_models  # noqa: F401
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
