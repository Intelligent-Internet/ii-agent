"""Phase (b) — provider cleanup. No DB transaction held across HTTP I/O.

Design: docs/design-docs/session-lifecycle-and-data-custody.md §4.5.

This module provides:
  - ``LeakedResource`` — value type representing one upstream resource that
    failed to delete.
  - ``run_provider_cleanup`` — phase-(b) entrypoint. Heartbeats the claim,
    invokes per-provider cleanup hooks, classifies failures, and either
    raises ``TransientProviderError`` (for retry next sweep) or writes
    rows to ``purge_dead_letter`` and raises ``ExhaustedRetriesError``.
  - ``register_cleanup_hook`` — extension point. PR-F / PR-G follow-ups
    will register concrete hooks (OpenAI files / containers / vector
    stores; GCS blobs; Composio profiles). Today this module ships with
    NO hooks registered, so phase (b) is a no-op for grace-purge of
    sessions whose providers are not yet hooked. That is INTENTIONAL —
    landing the orchestration without the upstream calls allows the
    purge driver to ship dark while provider plumbing is reviewed
    separately.

Concurrency contract:
  - Caller (``session_purge.purge_one_session``) MUST NOT hold a DB
    transaction while this function runs. The function opens its own
    short-lived txs to read provider IDs and to write dead-letter rows.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import get_settings
from ii_agent.core.db.base import get_db_session_local
from ii_agent.core.logger import logger

from .claim import heartbeat_claim
from .exceptions import ExhaustedRetriesError, TransientProviderError


@dataclass(frozen=True)
class LeakedResource:
    """One upstream resource that failed deletion past the retry budget."""

    provider: str
    """Upstream system identifier. E.g. 'openai', 'gcs'."""

    resource_kind: str
    """Provider-specific resource type. E.g. 'file', 'container'."""

    resource_id: str
    """The leaked upstream ID — what the operator must DELETE manually."""

    error_message: str
    """Last-attempt error, truncated to 4 KB."""

    transient: bool
    """True if the LAST attempt was a transient failure (5xx/timeout/429)."""


class CleanupHookResult(Protocol):
    """Return value of a cleanup hook.

    A hook attempts to delete every upstream resource for one session.
    It returns the list of leaked resources (empty on full success) and
    classifies each as transient or permanent so the caller can decide
    between retry-next-sweep and dead-letter.
    """

    leaked: list[LeakedResource]


@dataclass
class _HookOutcome:
    leaked: list[LeakedResource]


CleanupHook = Callable[[uuid.UUID, uuid.UUID], Awaitable[_HookOutcome]]
"""Hook signature: (session_id, user_id) -> _HookOutcome.

Hooks MUST NOT hold an open DB tx across HTTP calls. Hooks MAY open
short read-only txs via ``get_db_session_local()`` to look up provider IDs.
"""


_HOOKS: list[tuple[str, CleanupHook]] = []


def register_cleanup_hook(name: str, hook: CleanupHook) -> None:
    """Register a phase-(b) hook. Idempotent on (name); re-registering replaces."""
    global _HOOKS
    _HOOKS = [(n, h) for n, h in _HOOKS if n != name] + [(name, hook)]


def _registered_hook_names() -> list[str]:
    return [n for n, _ in _HOOKS]


async def _heartbeat_loop(
    session_id: uuid.UUID,
    stop: asyncio.Event,
) -> None:
    """Background task that heartbeats the claim every interval.

    Opens its own short-lived DB session per heartbeat — the main phase-(b)
    flow holds no tx, so we cannot share one.
    """
    interval = get_settings().sessions.heartbeat_interval_seconds
    try:
        while not stop.is_set():
            try:
                async with get_db_session_local() as db:
                    await heartbeat_claim(db, session_id)
                    await db.commit()
            except Exception as exc:  # pragma: no cover — defensive
                logger.warning(
                    "purge phase (b) heartbeat failed for {}: {}",
                    session_id,
                    exc,
                )
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        return


_INSERT_DEAD_LETTER_SQL = text(
    """
    INSERT INTO purge_dead_letter
        (session_id, user_id, provider, resource_kind, resource_id, error_message)
    VALUES
        (:session_id, :user_id, :provider, :resource_kind, :resource_id, :error_message)
    """
)


async def _persist_dead_letter(
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    leaked: list[LeakedResource],
) -> int:
    """Persist leaked resources to ``purge_dead_letter``. Own short tx."""
    if not leaked:
        return 0
    async with get_db_session_local() as db:
        for r in leaked:
            await db.execute(
                _INSERT_DEAD_LETTER_SQL,
                {
                    "session_id": str(session_id),
                    "user_id": str(user_id),
                    "provider": r.provider,
                    "resource_kind": r.resource_kind,
                    "resource_id": r.resource_id[:512],
                    "error_message": r.error_message[:4096],
                },
            )
        await db.commit()
    return len(leaked)


async def run_provider_cleanup(
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    current_attempts: int,
) -> int:
    """Phase (b). Run all registered cleanup hooks.

    Args:
        session_id: target session.
        user_id: target user (for dead-letter triage).
        current_attempts: ``sessions.purge_attempts`` AFTER phase (a)'s
            increment. Used to decide transient (retry) vs exhausted
            (dead-letter).

    Returns:
        Number of leaked resources written to ``purge_dead_letter`` (zero
        on full success).

    Raises:
        TransientProviderError: at least one hook reported transient
            failures AND we have retries left. Caller should release the
            claim and let the next sweep retry.
        ExhaustedRetriesError: hooks reported permanent failures OR retries
            exhausted. Dead-letter rows have already been written before
            this exception is raised (so on raise, ``leaked_resources`` are
            already operator-visible).

    Concurrency:
        - No open DB tx held across hooks.
        - Heartbeats the claim every ``heartbeat_interval_seconds`` via a
          background task.

    No-op behaviour:
        If no hooks are registered, returns 0 immediately (full success).
        This is the default state until PR-F/PR-G register concrete hooks.
    """
    if not get_settings().sessions.provider_cleanup_enabled:
        return 0
    if not _HOOKS:
        # No upstream providers wired yet — phase (b) is a no-op.
        return 0

    cfg = get_settings().sessions
    stop = asyncio.Event()
    hb_task = asyncio.create_task(_heartbeat_loop(session_id, stop))
    started = time.monotonic()
    aggregated: list[LeakedResource] = []
    try:
        for name, hook in _HOOKS:
            try:
                outcome = await hook(session_id, user_id)
            except Exception as exc:
                # A hook must not raise — coding bug. Treat as transient.
                logger.exception(
                    "purge phase (b) hook {!r} raised unexpectedly for session {}",
                    name,
                    session_id,
                )
                aggregated.append(
                    LeakedResource(
                        provider=name,
                        resource_kind="unknown",
                        resource_id="hook-raised",
                        error_message=f"{type(exc).__name__}: {exc}",
                        transient=True,
                    )
                )
                continue
            aggregated.extend(outcome.leaked)
    finally:
        stop.set()
        try:
            await asyncio.wait_for(hb_task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            hb_task.cancel()

    elapsed = time.monotonic() - started
    if not aggregated:
        logger.debug(
            "purge phase (b) clean for session {} ({:.2f}s, hooks={})",
            session_id,
            elapsed,
            _registered_hook_names(),
        )
        return 0

    transient_seen = any(r.transient for r in aggregated)
    retries_left = current_attempts < cfg.purge_max_attempts

    if transient_seen and retries_left:
        # Some failures could still resolve; let next sweep retry.
        # Do NOT write dead-letter yet — the row is still recoverable.
        raise TransientProviderError(
            f"phase (b) for {session_id}: {len(aggregated)} resources transiently failed "
            f"(attempt {current_attempts}/{cfg.purge_max_attempts})"
        )

    # Either all failures are permanent, or we have exhausted retries.
    written = await _persist_dead_letter(session_id=session_id, user_id=user_id, leaked=aggregated)
    raise ExhaustedRetriesError(
        f"phase (b) for {session_id}: {written} leaked resources persisted to "
        "purge_dead_letter; session row will NOT be deleted",
        dead_letter_count=written,
    )


async def _read_provider_ids_example(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> list[str]:
    """Reference implementation for hooks. Not used directly.

    Hooks should follow this pattern:
        1. Open a short tx; SELECT provider IDs; close the tx.
        2. With NO open tx, issue HTTP DELETEs.
        3. Classify each failure as transient (5xx/429/timeout/connection)
           vs permanent (4xx other than 404; 404 = success).
        4. Return _HookOutcome with leaked resources.
    """
    # No-op reference. Real hooks live in chat/providers/ and integrations/.
    _ = (db, session_id)
    return []
