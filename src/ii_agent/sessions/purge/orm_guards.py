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

from typing import Any

from sqlalchemy import event, text
from sqlalchemy.orm.mapper import Mapper

from ii_agent.core.logger import logger
from ii_agent.sessions.models import Session as SessionModel
from ii_agent.sessions.purge.exceptions import PurgeBlockedError


_REGISTERED: bool = False


def _before_insert_session(
    mapper: Mapper[SessionModel],  # noqa: ARG001 — required by event signature
    connection: Any,
    target: SessionModel,
) -> None:
    """Synchronous SQLAlchemy ``before_insert`` listener.

    Runs inside the active transaction. If ``users.is_purging=true`` for
    the row's user, abort the INSERT by raising ``PurgeBlockedError``.

    The listener honours an opt-out via the connection's
    ``execution_options(skip_purge_guard=True)`` — reserved for trusted
    internal paths (none in production code today).
    """
    # Bypass for trusted internal paths (admin scripts, future migrations).
    try:
        exec_opts = connection.get_execution_options()
    except Exception:
        exec_opts = {}
    if exec_opts.get("skip_purge_guard"):
        return

    user_id = getattr(target, "user_id", None)
    if user_id is None:
        # Pre-existing NOT NULL constraint will reject; let it surface.
        return

    row = connection.execute(
        text("SELECT is_purging FROM users WHERE id = :uid"),
        {"uid": user_id},
    ).first()
    if row is None:
        # FK constraint will reject the insert; let it surface.
        return
    if bool(row[0]):
        logger.warning(
            "ORM guard blocked Session insert for user_id={} "
            "(is_purging=true). I3/I8/I14 defence-in-depth fired.",
            user_id,
        )
        raise PurgeBlockedError(f"cannot create Session: user {user_id} is_purging=true")


def register_purge_guards() -> None:
    """Install the ``before_insert`` listener on ``Session``.

    Idempotent: subsequent calls are no-ops. Called from app startup
    (``app/lifespan.py``) immediately after the SQLAlchemy engine is
    initialised and BEFORE any router is wired.
    """
    global _REGISTERED
    if _REGISTERED:
        return
    event.listen(SessionModel, "before_insert", _before_insert_session)
    _REGISTERED = True
    logger.info("Registered ORM purge guard (before_insert on Session)")


__all__ = ["register_purge_guards"]
