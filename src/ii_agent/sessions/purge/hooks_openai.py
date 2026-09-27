"""Phase (b) cleanup hook for OpenAI per-session resources.

Issues HTTP DELETEs against the OpenAI API for every
``chat_provider_containers`` and ``chat_provider_files`` row with
``provider='openai'`` that points at this session.  Returns a
``LeakedResource`` for any deletion that did not succeed; the caller
(``providers.run_provider_cleanup``) classifies and either retries
or dead-letters.

Activation: opt-in via ``SESSIONS_OPENAI_PROVIDER_CLEANUP_ENABLED=true``
(see ``core.config.sessions.SessionsSettings``) and registered from
``app.lifespan`` step 4c.  Defaults OFF so this code ships dark until
ops flip the flag during the pre-flip canary (gate #4 in §0.0).

Concurrency contract: hook follows the §4.5 rules — opens its own
short read-only DB tx to fetch provider IDs, then runs HTTP DELETEs
with NO open tx.

Failure classification:
    - HTTP 404 → success (resource already gone).
    - HTTP 408 / 425 / 429 / 5xx / connection-error / timeout → transient.
    - All other 4xx → permanent.
    - Any unexpected exception → transient (so we retry).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from sqlalchemy import text

from ii_agent.core.config.settings import get_settings
from ii_agent.core.db.base import get_db_session_local
from ii_agent.core.logger import logger

from .providers import CleanupHook, LeakedResource, _HookOutcome, register_cleanup_hook


_PROVIDER_NAME = "openai"

# (table, column-mapping for SELECT, resource_kind, delete-method-path)
# SELECTs only the IDs we need; keep the read tx tiny.
_CONTAINERS_SQL = text(
    """
    SELECT container_id
    FROM chat_provider_containers
    WHERE session_id = :session_id AND provider = :provider
    """
)

_FILES_SQL = text(
    """
    SELECT provider_file_id
    FROM chat_provider_files
    WHERE session_id = :session_id AND provider = :provider
    """
)


def _classify(exc: BaseException) -> tuple[bool, int | None]:
    """Return ``(transient, status_code)``.

    Imports the OpenAI exception types lazily so this module remains
    importable even when ``openai`` is not installed (e.g. minimal
    test environments).  Any unexpected error type is treated as
    transient.
    """
    try:
        import openai
    except ImportError:
        return True, None

    if isinstance(exc, openai.NotFoundError):
        return False, 404  # 404 means "already gone" — handled by caller as success
    status = getattr(exc, "status_code", None)
    if isinstance(exc, openai.APIStatusError):
        if status in (408, 425, 429) or (status is not None and 500 <= status < 600):
            return True, status
        return False, status
    if isinstance(
        exc,
        (openai.APITimeoutError, openai.APIConnectionError),
    ):
        return True, None
    # Unknown exception → treat as transient so we retry.
    return True, status


def _build_client() -> Any | None:
    """Instantiate ``AsyncOpenAI`` from environment.  Returns None on failure.

    Uses ``OPENAI_API_KEY``; honours ``OPENAI_BASE_URL`` if set.  The
    hook stays best-effort: a missing key means we cannot DELETE, so
    every attempted DELETE is reported as a leaked resource and the
    caller dead-letters appropriately.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        import openai
    except ImportError:
        return None
    base_url = os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    return openai.AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=1)


async def _read_ids(session_id: uuid.UUID) -> tuple[list[str], list[str]]:
    """Open a tiny read-only tx; return (container_ids, file_ids)."""
    async with get_db_session_local() as db:
        c_rows = (
            await db.execute(
                _CONTAINERS_SQL, {"session_id": str(session_id), "provider": _PROVIDER_NAME}
            )
        ).all()
        f_rows = (
            await db.execute(
                _FILES_SQL, {"session_id": str(session_id), "provider": _PROVIDER_NAME}
            )
        ).all()
    return ([r[0] for r in c_rows if r[0]], [r[0] for r in f_rows if r[0]])


async def _delete_one(
    *,
    client: Any,
    resource_kind: str,
    resource_id: str,
) -> LeakedResource | None:
    """Attempt one HTTP DELETE.  Returns LeakedResource on failure (None on success)."""
    try:
        if resource_kind == "container":
            await client.containers.delete(resource_id)
        elif resource_kind == "file":
            await client.files.delete(resource_id)
        else:  # pragma: no cover — guarded by caller
            raise ValueError(f"unknown resource_kind: {resource_kind}")
        return None
    except Exception as exc:  # noqa: BLE001 — classified below
        transient, status = _classify(exc)
        if status == 404:
            # Already gone: treat as success.
            return None
        return LeakedResource(
            provider=_PROVIDER_NAME,
            resource_kind=resource_kind,
            resource_id=resource_id,
            error_message=f"{type(exc).__name__}: {exc}"[:4000],
            transient=transient,
        )


async def openai_cleanup_hook(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> _HookOutcome:
    """Phase-(b) hook entry point.  Conforms to ``providers.CleanupHook``."""
    _ = user_id  # not used by this hook (resources are session-scoped)
    container_ids, file_ids = await _read_ids(session_id)
    if not container_ids and not file_ids:
        return _HookOutcome(leaked=[])

    client = _build_client()
    if client is None:
        # No client available — every resource is leaked.  Mark all
        # transient so a future sweep with a key configured can retry.
        leaked: list[LeakedResource] = [
            LeakedResource(
                provider=_PROVIDER_NAME,
                resource_kind=kind,
                resource_id=rid,
                error_message="OPENAI_API_KEY not configured or openai SDK unavailable",
                transient=True,
            )
            for kind, ids in (("container", container_ids), ("file", file_ids))
            for rid in ids
        ]
        logger.warning(
            "openai cleanup hook fired for session {} but client unavailable; {} leaked",
            session_id,
            len(leaked),
        )
        return _HookOutcome(leaked=leaked)

    leaked = []
    try:
        for cid in container_ids:
            r = await _delete_one(client=client, resource_kind="container", resource_id=cid)
            if r is not None:
                leaked.append(r)
        for fid in file_ids:
            r = await _delete_one(client=client, resource_kind="file", resource_id=fid)
            if r is not None:
                leaked.append(r)
    finally:
        # AsyncOpenAI exposes aclose() / close() — call if available.
        close = getattr(client, "close", None)
        if callable(close):
            try:
                maybe = close()
                if hasattr(maybe, "__await__"):
                    await maybe
            except Exception:  # pragma: no cover — best-effort
                pass

    return _HookOutcome(leaked=leaked)


def maybe_register_openai_hook() -> bool:
    """Register the OpenAI hook iff the feature flag is set.

    Returns True if registration happened.  Idempotent: re-registering
    replaces the prior hook (see ``register_cleanup_hook``).
    """
    if not get_settings().sessions.openai_provider_cleanup_enabled:
        return False
    hook: CleanupHook = openai_cleanup_hook
    register_cleanup_hook(_PROVIDER_NAME, hook)
    logger.info("Registered OpenAI phase-(b) cleanup hook for session purge")
    return True
