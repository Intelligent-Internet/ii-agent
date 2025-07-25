"""Session configuration for CLI."""

from typing import Optional
from pydantic import BaseModel

from ii_agent.runtime.model.constants import RuntimeMode


class SessionConfig(BaseModel):
    """Configuration for session management."""

    session_id: str
    mode: RuntimeMode
    session_name: Optional[str] = None
