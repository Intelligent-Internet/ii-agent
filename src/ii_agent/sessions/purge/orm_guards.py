"""ORM-level defence-in-depth guards (Adversarial v3.9 #5).

The runtime FastAPI dependency ``NotPurgingDep`` only protects HTTP traffic
that goes through the session-creation endpoints. Direct ORM inserts —
admin scripts, migrations, future Celery tasks, test fixtures, anything
that constructs a ``Session`` and calls ``db.add(...)`` — bypass that
dependency entirely. If such code runs while the owning user has
``is_purging=true``, a session can land in the database AFTER
``purge_user_account`` has finished its scan (I3 violation, GDPR Art. 17
re-emergence).

This module installs a SQLAlchemy ``before_insert`` event listener on
``Session`` that re-reads ``users.is_purging`` for the row's ``user_id``
under the same transaction and aborts the INSERT if the flag is set.

Contract:
    1. Listener is registered exactly once at app startup
       (``app/lifespan.py`` calls ``register_purge_guards()``).
    2. Listener fires inside the caller's transaction — it does NOT open
       a new session. A simple ``SELECT users.is_purging FROM users
       WHERE id = :user_id`` against the active connection is sufficient.
    3. On ``is_purging=true`` it raises ``PurgeBlockedError`` which
       propagates up through ``db.flush()`` / ``db.commit()`` and rolls
       the offending tx back. The originating call site logs and surfaces
       the failure; never silently swallow.
    4. The listener is bypassable ONLY by passing
       ``Session.__table__.insert().execution_options(skip_purge_guard=True)``
       — reserved for the orphan-cleanup loop's internal bookkeeping. Any
       new bypass requires invariant review.

Invariants preserved: I3, I8, I14 (defence-in-depth).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def register_purge_guards() -> None:
    """Install the ``before_insert`` listener on ``Session``.

    Idempotent: subsequent calls are no-ops. Called from app startup
    (``app/lifespan.py``) immediately after the SQLAlchemy engine is
    initialised and BEFORE any router is wired.

    Raises:
        RuntimeError: called before ``Session.metadata`` is bound to an
            engine (programming error — startup ordering bug).
    """
    raise NotImplementedError


__all__ = ["register_purge_guards"]
