"""Per-session compaction lock to prevent concurrent summarization.

When an A2A-delegated turn is active, the CLI backend may be performing its
own context compaction.  Running ii-agent's native summarization concurrently
could produce conflicting summaries.  This module provides a shared lock
registry that the A2A inner loop acquires during delegated turns and that
``ContextWindowManager.check_and_summarize_after_response`` checks before
starting native summarization.

Usage::

    # In A2A inner loop — acquire during delegated turn:
    async with compaction_lock(session_id):
        async for event in client.astream(...):
            yield event

    # In ContextWindowManager — skip if lock is held:
    if is_compaction_locked(session_id):
        logger.info("Skipping summarization — A2A turn active for session %s", session_id)
        return
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

_locks: dict[uuid.UUID, asyncio.Lock] = {}


def _get_lock(session_id: uuid.UUID) -> asyncio.Lock:
    """Return (and lazily create) the per-session compaction lock."""
    lock = _locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[session_id] = lock
    return lock


@asynccontextmanager
async def compaction_lock(session_id: uuid.UUID) -> AsyncIterator[None]:
    """Async context manager that holds the compaction lock for *session_id*."""
    lock = _get_lock(session_id)
    async with lock:
        yield


def is_compaction_locked(session_id: uuid.UUID) -> bool:
    """Return ``True`` if the compaction lock is currently held for *session_id*."""
    lock = _locks.get(session_id)
    if lock is None:
        return False
    return lock.locked()


def remove_session_lock(session_id: uuid.UUID) -> None:
    """Remove the lock entry for a deleted session to prevent unbounded growth."""
    _locks.pop(session_id, None)
