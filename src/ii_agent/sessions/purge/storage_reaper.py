"""Storage reaper (§4.6) — orphaned-asset cleanup.

After session deletion, ``user_assets`` (FileAsset) rows whose only
``session_assets`` link is gone become orphans. The reaper runs as its own
cleanup-loop stage, INDEPENDENT of session purge, and handles any orphan
source (manual asset deletion, failed uploads, etc.).

Design: docs/design-docs/session-lifecycle-and-data-custody.md §4.6.

Two-step upload races (Adversarial v3.5):
    UserAsset is sometimes inserted BEFORE its SessionAsset link in the
    upload pipeline. Reaping during that window destroys legitimate
    uploads. Defence: ``storage_reaper_min_age_seconds`` (default 1h).
    Only assets older than the buffer AND with no link AND not is_public
    are eligible.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import get_settings
from ii_agent.core.db.base import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.files.models import FileAsset, SessionAsset


async def _select_orphans(db: AsyncSession, *, batch_size: int, min_age_s: int) -> list[FileAsset]:
    """Phase 1 — single read to enumerate orphan candidates.

    Filter:
      - No SessionAsset link
      - Not public (public links may be referenced from outside our DB)
      - Older than ``min_age_s`` (avoid two-step upload race)
    """
    stmt = (
        select(FileAsset)
        .where(
            ~exists().where(SessionAsset.asset_id == FileAsset.id),
            FileAsset.is_public.is_(False),
            FileAsset.created_at < func.now() - timedelta(seconds=min_age_s),
        )
        .limit(batch_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def reap_orphaned_user_assets() -> int:
    """Delete orphaned ``user_assets`` rows + their backing storage objects.

    Returns:
        The number of FileAsset rows actually deleted (storage delete + DB delete
        both succeeded).

    Concurrency:
        Per-asset: we issue the storage DELETE OUTSIDE the DB transaction, then
        DELETE the row in its own short tx. If the storage DELETE fails, the row
        stays so the next sweep retries. Storage 404 is treated as success.

        Multiple workers running this concurrently: each worker reads its own
        candidate set; a row picked by two workers is a no-op for the second
        (already deleted). DELETE is idempotent.

    Failure handling:
        - Storage 404 ⇒ treated as success (already gone).
        - Storage transient error ⇒ logged, row left in place, next sweep retries.
        - DB error after successful storage DELETE ⇒ orphaned blob is recreatable,
          but row will be re-picked next sweep (storage DELETE is idempotent).
    """
    cfg = get_settings().sessions
    if not cfg.storage_reaper_enabled:
        return 0

    deleted = 0
    batch_size = cfg.storage_reaper_batch_size
    min_age_s = cfg.storage_reaper_min_age_seconds

    # Phase 1 — enumerate. Single short tx.
    async with get_db_session_local() as db:
        orphans = await _select_orphans(db, batch_size=batch_size, min_age_s=min_age_s)

    if not orphans:
        return 0

    # Phase 2 — per-asset: storage DELETE (no tx held), then DB DELETE.
    # Resolve storage at call time so import remains cheap.
    from ii_agent.core.container import get_app_container

    storage = get_app_container().storage_service

    for asset in orphans:
        try:
            await storage.delete(asset.storage_path)
        except Exception as exc:
            # Conservative: log + skip. Next sweep retries.
            logger.warning(
                "storage reaper: storage DELETE failed for {} ({}): {} — will retry next sweep",
                asset.id,
                asset.storage_path,
                exc,
            )
            continue

        # DB delete in own short tx.
        try:
            async with get_db_session_local() as db_del:
                await db_del.execute(delete(FileAsset).where(FileAsset.id == asset.id))
                await db_del.commit()
        except Exception:  # pragma: no cover — defensive
            logger.exception(
                "storage reaper: DB DELETE failed for {} after storage DELETE — "
                "blob is gone but row remains; next sweep will re-attempt",
                asset.id,
            )
            continue
        deleted += 1

    if deleted:
        logger.info("storage reaper: reaped {} orphaned user_assets", deleted)
    return deleted
