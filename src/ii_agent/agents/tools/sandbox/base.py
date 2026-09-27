"""Base class for sandbox-dependent tools.

Provides lazy sandbox initialization via :meth:`_ensure_sandbox` which is
called automatically in :meth:`on_tool_start`.  The sandbox is provisioned
on first use (when any sandbox tool fires) and cached on the agent for
subsequent calls.
"""

from __future__ import annotations

import uuid as _uuid
from typing import TYPE_CHECKING, Any, Dict, Optional

from ii_agent.agents.tools.base import BaseAgentTool
from ii_agent.core.container import get_app_container
from ii_agent.core.db.base import get_db_session_local
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.agents.agent import IIAgent
    from ii_agent.agents.sandboxes.service import SandboxService
    from ii_agent.agents.tools.function import FunctionCall


class BaseSandboxTool(BaseAgentTool):
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool
    display_name: str
    metadata: Optional[Dict[str, Any]] = None
    requires_sandbox: bool = True
    sandbox: Any = None

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        """Pre-hook: ensure sandbox exists, then expose it to the tool."""
        await self._ensure_sandbox(agent, fc)
        self.sandbox = agent.sandbox

    async def _ensure_sandbox(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        """Lazily initialize the sandbox if not already running.

        Uses double-checked locking with the agent's internal lock to ensure
        exactly one sandbox is created even when multiple tools fire concurrently.
        Sets the sandbox on the agent and captures SandboxInfo on the FunctionCall.
        """
        if agent.sandbox is not None:
            fc.sandbox = await agent.sandbox.get_info()
            return

        async with agent._internal_lock:
            # Re-check after acquiring the lock (double-checked locking)
            if agent.sandbox is not None:
                fc.sandbox = await agent.sandbox.get_info()
                return

            logger.info(f"Lazily initializing sandbox for session={agent.session_id}")
            sandbox_service = get_app_container().sandbox_service
            async with get_db_session_local() as db:
                sandbox = await sandbox_service.init_sandbox(
                    db,
                    session_id=_uuid.UUID(agent.session_id),
                    user_id=_uuid.UUID(agent.user_id),
                )

            agent.sandbox = sandbox
            agent._sandbox_was_initialized = True
            fc.sandbox = await sandbox.get_info()

    def get_sandbox_service(self) -> "SandboxService":
        return get_app_container().sandbox_service

    def get_session_id(self) -> _uuid.UUID:
        if self.sandbox is None:
            raise RuntimeError(
                "Sandbox not available — initialization likely failed. "
                "Check backend logs for sandbox errors."
            )
        return _uuid.UUID(self.sandbox.session_id)
