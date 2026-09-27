"""Lazy MCP-handshake retry for runtime tool factories.

Background
----------
``SandboxService._configure_mcp`` runs as a fire-and-forget background
task at the end of ``init_sandbox``. With bounded retry it covers
99%+ of cases, but a permanently-wedged container or a misconfigured
network can still leave a sandbox with ``mcp_configured=False`` for
the entire session lifetime.

This helper lets runtime MCP-tool factories (``UserMCPTool``,
``MCPTool``, ``ComposioMCPTool``) trigger a *bounded* fresh handshake
on demand, throttled by a per-sandbox cooldown so a wedged container
isn't hammered on every tool invocation.

Design contract
---------------
- Read-only fast path: when ``mcp_configured`` is already ``True``,
  this function is a single async DB round-trip (~1 ms).
- The retry path runs at most once per
  ``SandboxService._MCP_LAZY_RETRY_COOLDOWN_S``.
- Failures are non-fatal: if the retry doesn't succeed, we log and
  return so the tool's existing error path runs (and produces a
  visible error to the user), instead of silently calling a broken
  endpoint.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ii_agent.core.container import get_app_container
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger


async def ensure_mcp_configured(sandbox_id: str | uuid.UUID, user_id: str | uuid.UUID) -> bool:
    """Ensure the given sandbox has had a successful MCP configure pass.

    Returns ``True`` when the sandbox is (or became) configured, ``False``
    when a retry was attempted and failed (or the sandbox row is gone).
    Always returns ``True`` for sandboxes that don't have a record (e.g.
    bare E2B test paths) so we never block a tool invocation on this
    check.

    See ``docs/design-docs/sandbox-pool-claim-mcp-handoff-audit.md``
    for the full design and 19 corner cases.
    """
    try:
        sb_uuid = sandbox_id if isinstance(sandbox_id, uuid.UUID) else uuid.UUID(str(sandbox_id))
    except (ValueError, AttributeError):
        # Non-UUID sandbox id: legacy/test path. Skip the check.
        return True

    container = get_app_container()
    sandbox_svc = container.sandbox_service

    async with get_db_session_local() as db:
        record = await sandbox_svc._sandbox_repo.get_by_id(db, sb_uuid)
        if record is None:
            return True
        if record.mcp_configured:
            return True

        cooldown = sandbox_svc._MCP_LAZY_RETRY_COOLDOWN_S
        last = record.mcp_configure_attempted_at
        if last is not None:
            elapsed = (datetime.now(timezone.utc) - last).total_seconds()
            if elapsed < cooldown:
                logger.debug(
                    f"MCP lazy-retry skipped for sandbox {sb_uuid}: cooldown "
                    f"({elapsed:.1f}s < {cooldown}s)"
                )
                return False

    # Outside the read-only DB session, attach to the provider and run a
    # fresh configure pass. We deliberately use ``_configure_mcp_background``
    # so the existing wall-clock timeout, retry envelope, and durable-flag
    # persistence all apply uniformly.
    logger.info(f"MCP lazy-retry: configuring sandbox {sb_uuid} on demand")
    try:
        record = None
        async with get_db_session_local() as db:
            record = await sandbox_svc._sandbox_repo.get_by_id(db, sb_uuid)
        if record is None or not record.provider_sandbox_id:
            return False
        sandbox_mgr = await sandbox_svc._connect_provider(record)
    except Exception as e:
        logger.warning(f"MCP lazy-retry attach failed for sandbox {sb_uuid}: {e}")
        return False

    user_uuid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
    await sandbox_svc._configure_mcp_background(sandbox_mgr, user_uuid, str(sb_uuid))

    # Re-read the flag to report back to the caller.
    async with get_db_session_local() as db:
        record = await sandbox_svc._sandbox_repo.get_by_id(db, sb_uuid)
        return bool(record and record.mcp_configured)
