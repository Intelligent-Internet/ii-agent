"""Cleanup-loop stage entry point — drives ``purge_one_session`` (§4.1).

Slots into ``agents/sandboxes/orphan_cleanup.py`` between
``_pause_stale_sandboxes`` and ``_cleanup_docker_zombies``.

Two responsibilities per cycle:

  0. **Backfill** — for newly-soft-deleted rows with ``purge_after IS NULL``,
     compute the deadline based on ``custody`` (standard / ephemeral) and
     write it. One bulk UPDATE; no per-row work.

  1. **Drain loop** — repeatedly call ``purge_one_session`` until either:
        - the queue is empty (SKIPPED_NOT_ELIGIBLE on ``session_id=None``),
        - the wall-clock budget ``purge_max_seconds_per_loop`` is exhausted,
        - or an outcome that suggests we should stop iterating (currently
          only SKIPPED_NOT_ELIGIBLE; everything else continues).

Returns the count of sessions PURGED in this stage (for logging).
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from ii_agent.core.config.settings import get_settings
from ii_agent.core.db.base import get_db_session_local
from ii_agent.core.logger import logger

from .session_purge import purge_one_session
from .storage_reaper import reap_orphaned_user_assets
from .types import PurgeOutcome, PurgeTrigger


# Bulk backfill: branch on custody. Use server-side now() + interval.
_BACKFILL_PURGE_AFTER_SQL = text(
    """
    UPDATE sessions
       SET purge_after = CASE
           WHEN custody = 'ephemeral'
             THEN now() + make_interval(secs => :ephemeral_grace)
           ELSE now() + make_interval(secs => :standard_grace)
       END
     WHERE is_deleted = true
       AND purge_after IS NULL
       AND custody != 'legal_hold'
    """
)


async def cleanup_loop_stage_purge_sessions() -> int:
    """Run one cycle of the §4.1 purge driver. Returns sessions PURGED."""
    cfg = get_settings().sessions
    if not cfg.purge_enabled:
        return 0

    # Step 0 — backfill purge_after. One short tx.
    try:
        async with get_db_session_local() as db:
            await db.execute(
                _BACKFILL_PURGE_AFTER_SQL,
                {
                    "standard_grace": cfg.purge_grace_period_seconds,
                    "ephemeral_grace": cfg.ephemeral_purge_grace_period_seconds,
                },
            )
            await db.commit()
    except Exception:  # pragma: no cover — defensive
        logger.exception("purge stage: purge_after backfill failed; continuing")

    # Step 1 — drain loop with wall-clock budget.
    deadline = asyncio.get_running_loop().time() + cfg.purge_max_seconds_per_loop
    purged = 0
    deferred = 0
    dead_lettered = 0

    while asyncio.get_running_loop().time() < deadline:
        try:
            async with get_db_session_local() as db:
                result = await purge_one_session(
                    session_id=None,
                    trigger=PurgeTrigger.GRACE_EXPIRED,
                    db=db,
                )
        except Exception:  # pragma: no cover — defensive
            logger.exception("purge stage: purge_one_session raised — breaking loop")
            break

        if result.outcome == PurgeOutcome.PURGED:
            purged += 1
        elif result.outcome == PurgeOutcome.DEFERRED_TRANSIENT:
            deferred += 1
        elif result.outcome == PurgeOutcome.DEAD_LETTERED:
            dead_lettered += 1
        elif result.outcome == PurgeOutcome.SKIPPED_NOT_ELIGIBLE:
            # Queue is empty for this cycle.
            break
        # SKIPPED_RACED, SKIPPED_RESTORED, ALREADY_PURGED — keep iterating
        # within the wall-clock budget; another session may be available.

    if purged or deferred or dead_lettered:
        logger.info(
            "purge stage: purged={} deferred={} dead_lettered={}",
            purged,
            deferred,
            dead_lettered,
        )
    return purged


async def cleanup_loop_stage_storage_reaper() -> int:
    """§4.6 storage reaper as a cleanup-loop stage. Returns assets reaped."""
    try:
        return await reap_orphaned_user_assets()
    except Exception:  # pragma: no cover — defensive
        logger.exception("storage reaper stage failed")
        return 0
