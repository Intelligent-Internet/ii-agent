"""Pre-warmed sandbox pool manager.

Maintains a configurable pool of N pre-booted Docker sandbox containers
ready to be claimed by incoming sessions. Eliminates the ~90s cold-start
of `start-services.sh` from the user-visible session start latency.

Design summary
--------------

* Each pool slot has a stable integer id in ``[0, N)``.
* On startup, *every* missing slot is created in parallel.
* Each row carries a ``retire_at`` timestamp computed from the slot index:

    stagger    = max_age / N
    bootstrap  = now + max_age - (slot * stagger)   # initial fill only
    replace    = now + max_age                      # subsequent cycles

  This keeps slot retirements offset by ``stagger`` seconds permanently,
  so the pool never empties simultaneously.

* When a slot is claimed (or retired), a replacement for the *same slot*
  is scheduled for creation as soon as possible. Slot identity carries
  the modulo offset across cycles.

Only active when ``provider == 'docker'`` AND ``local_mode`` AND
``prewarm_pool_size > 0``. E2B has its own internal warm pool.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import event

from ii_agent.agents.sandboxes.base import Sandbox
from ii_agent.agents.sandboxes.exceptions import SandboxCreationError
from ii_agent.agents.sandboxes.host_monitor import HostHealthState, get_host_state
from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.repository import SandboxRepository
from ii_agent.agents.sandboxes.types import (
    PoolState,
    SandboxProviderType,
    SandboxStatus,
)
from ii_agent.core.config.settings import Settings
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger


# Type alias for the provider-create callable. Real wiring uses
# DockerSandbox.create; tests inject a mock.
ProviderCreateFn = Callable[[uuid.UUID, str], Awaitable[Sandbox]]


# How long an AVAILABLE pool row may sit in status=INITIALIZING before it
# is presumed orphaned by a crashed previous backend run and reaped.
# Container provisioning normally takes 90-110 s, so 10 minutes leaves a
# comfortable safety margin against legitimate slow boots while still
# unblocking the slot well before the next user-facing claim attempt.
_STUCK_INITIALIZING_THRESHOLD = timedelta(minutes=10)


class SandboxPoolManager:
    """Manages the pre-warmed sandbox pool lifecycle.

    Thread/task-safe via a single ``_creating`` set guarded by
    ``_create_lock`` to prevent duplicate creations for the same slot.
    """

    POOL_SESSION_PLACEHOLDER = "__pool__"

    def __init__(
        self,
        sandbox_repo: SandboxRepository,
        config: Settings,
        provider_create_fn: ProviderCreateFn,
    ) -> None:
        self._sandbox_repo = sandbox_repo
        self._config = config
        self._provider_create_fn = provider_create_fn
        self._create_lock = asyncio.Lock()
        self._creating: set[int] = set()

    # ── Public configuration accessors ───────────────────────────────────

    @property
    def pool_size(self) -> int:
        return int(self._config.sandbox.prewarm_pool_size)

    @property
    def max_age_seconds(self) -> int:
        return int(self._config.sandbox.prewarm_max_age_seconds)

    @property
    def stagger_seconds(self) -> int:
        """Per-slot retirement offset: ``max_age / pool_size``."""
        n = self.pool_size
        if n <= 0:
            return 0
        return self.max_age_seconds // n

    @property
    def enabled(self) -> bool:
        cfg = self._config.sandbox
        return self.pool_size > 0 and cfg.provider == "docker" and bool(cfg.local_mode)

    # ── Slot enumeration / retirement schedule ───────────────────────────

    def compute_bootstrap_retire_at(
        self,
        slot: int,
        *,
        now: Optional[datetime] = None,
    ) -> datetime:
        """First-fill formula: ``now + max_age - (slot * stagger)``.

        Slot 0 gets the full max_age lifetime; higher slots get progressively
        shorter first-cycle lifetimes so their first retirements are spread
        across the max_age window. After replacement they get full max_age.
        """
        anchor = now or datetime.now(timezone.utc)
        offset = slot * self.stagger_seconds
        # Guard against degenerate config (pool_size > max_age).
        retire_seconds = max(self.max_age_seconds - offset, 60)
        return anchor + timedelta(seconds=retire_seconds)

    def compute_replacement_retire_at(
        self,
        *,
        now: Optional[datetime] = None,
    ) -> datetime:
        """Replacement-cycle formula: ``now + max_age`` (full lifetime)."""
        anchor = now or datetime.now(timezone.utc)
        return anchor + timedelta(seconds=self.max_age_seconds)

    # ── Bootstrap & replenish ────────────────────────────────────────────

    async def bootstrap(self) -> None:
        """Ensure all N slots have a live container at startup.

        Inspects existing pool rows; for each slot in ``[0, N)`` without a
        live AVAILABLE/CLAIMED row, schedules a create using the bootstrap
        retire_at formula. Creates all missing slots in parallel.

        Respects the integrated host monitor: if state is WARN or worse
        at startup, bootstrap is deferred — the cleanup loop's
        :meth:`ensure_full` will pick up the slack once the host
        recovers.
        """
        if not self.enabled:
            return

        host_state = get_host_state()
        if host_state >= HostHealthState.WARN:
            logger.warning(
                f"Sandbox pool bootstrap deferred: host_state={host_state.name} "
                f"— pool will fill from the cleanup loop once host recovers"
            )
            return

        # Reap rows wedged in INITIALIZING by a previous backend crash
        # *before* enumerating live slots, otherwise those zombies are
        # counted as occupied and we never recreate the slot.
        await self.reap_stuck_initializing()

        existing_slots = await self._existing_live_slots()
        missing = [s for s in range(self.pool_size) if s not in existing_slots]

        if not missing:
            logger.info(f"Sandbox pool bootstrap: all {self.pool_size} slots already populated")
            return

        logger.info(
            f"Sandbox pool bootstrap: {len(missing)} slot(s) missing ({missing}) — creating in parallel"
        )

        # Fire all creates in parallel; failures are logged per-slot.
        await asyncio.gather(
            *(self._create_slot_async(slot, is_bootstrap=True) for slot in missing),
            return_exceptions=True,
        )

    async def ensure_full(self) -> None:
        """Cleanup-loop entry point: create any missing slots ASAP.

        Replacement creates use the full ``max_age`` retire_at since the
        slot's modulo offset is preserved by *when* this slot last cycled,
        not by the formula.

        Skipped when the host monitor reports WARN or worse so we don't
        burn high-order page blocks while the host is already
        fragmented. The slot will be filled on a later sweep once the
        host returns to OK/WATCH.
        """
        if not self.enabled:
            return

        host_state = get_host_state()
        if host_state >= HostHealthState.WARN:
            logger.info(f"Sandbox pool ensure_full skipped: host_state={host_state.name}")
            return

        # Same guard as bootstrap: reap stuck rows so they don't mask
        # the missing-slot detection below.
        await self.reap_stuck_initializing()

        existing_slots = await self._existing_live_slots()
        missing = [s for s in range(self.pool_size) if s not in existing_slots]
        if not missing:
            return

        logger.info(f"Sandbox pool ensure_full: replenishing slot(s) {missing}")
        for slot in missing:
            # Fire-and-forget; concurrent creates are de-duped via _creating.
            asyncio.create_task(self._create_slot_async(slot, is_bootstrap=False))

    async def shrink_excess(self) -> int:
        """Mark RETIRING any AVAILABLE rows whose slot index is out of range.

        Triggered when ``prewarm_pool_size`` is reduced at runtime.
        Returns the number of rows marked.
        """
        if self.pool_size < 0:
            return 0

        marked = 0
        async with get_db_session_local() as db:
            rows = await self._sandbox_repo.list_active_pool_rows(db)
            for row in rows:
                if (
                    row.pool_slot is not None
                    and row.pool_slot >= self.pool_size
                    and row.pool_state == PoolState.AVAILABLE
                ):
                    row.pool_state = PoolState.RETIRING
                    marked += 1
            if marked:
                await db.commit()
        return marked

    # ── Claim ────────────────────────────────────────────────────────────

    async def claim(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Optional[AgentSandbox]:
        """Atomically claim the oldest AVAILABLE pool row for a session.

        Returns the claimed row (with ``pool_state=CLAIMED``,
        ``session_id=session_id``, ``claimed_at=now``, ``pool_slot=None``)
        or None when the pool is empty. Triggers replenishment of the
        freed slot via the slot index returned alongside the row by the
        repository (the row's own ``pool_slot`` is cleared on claim so
        the long-lived CLAIMED row does not block future ensure_full
        cycles for that slot).

        Replenishment is wired to fire from a SQLAlchemy ``after_commit``
        hook on the caller's session rather than immediately. Audit item
        #6 in ``docs/design-docs/sandbox-pool-claim-mcp-handoff-audit.md``:
        the historical race where a rolled-back claim left a duplicate
        replenished row on the slot is now structurally impossible because
        the trigger never fires until the caller's transaction is durable.
        Fire-and-forget is preserved (the replenish task is created from
        within the after-commit listener, which itself runs synchronously
        inside ``await db.commit()`` on the same loop).
        """
        if not self.enabled:
            return None

        row, claimed_slot = await self._sandbox_repo.claim_oldest_available(db, session_id)
        if row is None:
            return None

        logger.info(
            f"Sandbox pool claim: row={row.id} slot={claimed_slot} session={session_id} — scheduling post-commit replenish"
        )

        # Schedule replacement for the same slot via an after_commit hook
        # so it cannot fire if the caller rolls back. Captured by closure.
        if claimed_slot is not None:
            self._schedule_replenish_after_commit(db, claimed_slot)

        return row

    def _schedule_replenish_after_commit(
        self,
        db: AsyncSession,
        claimed_slot: int,
    ) -> None:
        """Register a one-shot ``after_commit`` listener that schedules replenish.

        The listener runs synchronously inside the greenlet-driven
        ``await db.commit()`` so ``asyncio.get_running_loop()`` is safe.
        We use ``once=True`` to auto-deregister; otherwise repeat claims
        on the same session would stack listeners.
        """
        pool_self = self
        slot = claimed_slot

        def _on_after_commit(_session: Any) -> None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop (e.g. some unit tests using sync sessions).
                # Fall back to the legacy immediate-schedule pattern so the
                # slot still gets refilled.
                logger.debug(
                    f"Pool replenish (slot={slot}): no running loop in after_commit; "
                    "falling back to direct asyncio.create_task"
                )
                try:
                    asyncio.create_task(pool_self._create_slot_async(slot, is_bootstrap=False))
                except RuntimeError:
                    logger.warning(f"Pool replenish (slot={slot}): cannot schedule — no event loop")
                return

            loop.create_task(pool_self._create_slot_async(slot, is_bootstrap=False))

        event.listen(db.sync_session, "after_commit", _on_after_commit, once=True)

    # ── Dedupe ───────────────────────────────────────────────────────────

    async def dedupe_available_slots(self) -> int:
        """Mark duplicate AVAILABLE rows per slot as RETIRING (keep newest).

        Defensive sweep against the historical race where ``claim`` scheduled
        a replenish before its caller's transaction was durable: if the caller
        rolled back, the original claim was undone but the replenished row
        remained, leaving multiple AVAILABLE rows on the same slot.

        The deployed commit-immediately-after-claim fix prevents new
        occurrences, but this sweep cleans up any pre-existing leaks and
        guards against unanticipated future races. The dropped containers
        are then reaped by the existing RETIRING -> orphan/zombie cleanup
        chain. Keeps the newest row on each slot since it carries the latest
        ``retire_at`` deadline.

        Returns the number of rows marked RETIRING.
        """
        if not self.enabled:
            return 0

        marked = 0
        async with get_db_session_local() as db:
            rows = await self._sandbox_repo.list_active_pool_rows(db)
            by_slot: dict[int, list[AgentSandbox]] = {}
            for row in rows:
                if row.pool_state == PoolState.AVAILABLE and row.pool_slot is not None:
                    by_slot.setdefault(row.pool_slot, []).append(row)
            for slot, slot_rows in by_slot.items():
                if len(slot_rows) <= 1:
                    continue
                slot_rows.sort(key=lambda r: r.created_at, reverse=True)
                for stale in slot_rows[1:]:
                    stale.pool_state = PoolState.RETIRING
                    marked += 1
                    logger.warning(
                        f"Sandbox pool dedupe: slot={slot} has {len(slot_rows)} AVAILABLE "
                        f"rows; marking duplicate row={stale.id} (created={stale.created_at}) "
                        "as RETIRING"
                    )
            if marked:
                await db.commit()
        return marked

    # ── Retirement ───────────────────────────────────────────────────────

    async def validate_available_slots(self) -> int:
        """Retire AVAILABLE slot rows whose Docker container is missing or dead.

        Prevents the "standby slot backed by a dead container" failure mode:
        after a Docker restart the row still reports ``status=running,
        pool_state=available`` but ``containers.get`` returns 404, so the
        next claimer receives a broken sandbox. Marking the row RETIRING
        triggers the existing cleanup chain to reap the row and lets
        ``ensure_full`` provision a replacement on the same slot.

        Also performs a fast HTTP ``/health`` probe of the sandbox MCP
        server (port from ``settings.mcp.port``) using the **container
        IP** so a wedged MCP process inside a healthy container is also
        caught here \u2014 historically these would be silently handed to
        sessions and only surface as ``Client failed to connect`` later.
        See docs/design-docs/sandbox-pool-claim-mcp-handoff-audit.md.
        """
        if not self.enabled:
            return 0

        try:
            from ii_agent.agents.sandboxes.docker import DockerSandbox
            from ii_agent.agents.sandboxes.executor import docker_call
        except Exception:
            return 0

        try:
            client = DockerSandbox._get_docker_client()
        except Exception:
            return 0

        # Lightweight HTTP probe of the in-container MCP /health endpoint.
        # Bounded total budget per sandbox so a slow probe cannot wedge
        # the cleanup loop. Failures here should NOT be fatal \u2014 the
        # network/probe itself can hiccup; we only count *consistent*
        # unhealthy containers (caught on a second sweep) toward
        # retirement to avoid flapping rows under transient load.
        try:
            import httpx  # noqa: F401  (only imported when feature used)

            _httpx_available = True
        except Exception:
            _httpx_available = False

        marked = 0
        async with get_db_session_local() as db:
            rows = await self._sandbox_repo.list_active_pool_rows(db)
            to_retire: list[AgentSandbox] = []
            for row in rows:
                if row.pool_state != PoolState.AVAILABLE:
                    continue
                pid = row.provider_sandbox_id
                if not pid:
                    # INITIALIZING rows haven't reached provider yet; skip.
                    continue
                try:
                    container = await docker_call(client.containers.get, pid, timeout=5)
                    await docker_call(container.reload, timeout=5)
                except Exception:
                    to_retire.append(row)
                    continue
                status = getattr(container, "status", "")
                if status not in ("running", "created", "restarting"):
                    to_retire.append(row)
                    continue

                # Container is up; check the MCP /health endpoint via the
                # container IP. We do this *only* if httpx is importable
                # and the container has an IP \u2014 fall closed (don't
                # retire) on any infra issue with the probe itself.
                if not _httpx_available:
                    continue
                try:
                    import httpx as _httpx

                    container_ip = self._extract_container_ip(container)
                    if not container_ip:
                        continue
                    url = f"http://{container_ip}:{self._config.mcp.port}/health"
                    async with _httpx.AsyncClient(timeout=1.0) as http_client:
                        resp = await http_client.get(url)
                    if resp.status_code >= 400:
                        logger.warning(
                            f"Sandbox pool validate: row={row.id} container {pid} healthy "
                            f"but MCP /health returned {resp.status_code}; retiring."
                        )
                        to_retire.append(row)
                except Exception as e:
                    # A single failed probe is not retire-worthy: the
                    # cleanup loop runs every 60s and a transient blip
                    # shouldn't shrink the pool. Just log at DEBUG.
                    logger.debug(
                        f"Sandbox pool validate: MCP /health probe failed for "
                        f"row={row.id} container {pid}: {e}"
                    )

            for row in to_retire:
                row.pool_state = PoolState.RETIRING
                marked += 1
                logger.warning(
                    f"Sandbox pool validate: retiring slot={row.pool_slot} row={row.id} "
                    "(container missing, not running, or MCP unhealthy)"
                )
            if marked:
                await db.commit()

        return marked

    @staticmethod
    def _extract_container_ip(container) -> str | None:
        """Best-effort extraction of the bridge-network IP for a container.

        Returns ``None`` when the inspect payload doesn't expose an IP
        we can use (e.g. host network, or pre-attach state). The
        ``Networks`` map under ``NetworkSettings`` is the post-Docker
        17.06 layout; we tolerate both the legacy top-level ``IPAddress``
        and the per-network entries.
        """
        try:
            attrs = getattr(container, "attrs", None) or {}
            ns = attrs.get("NetworkSettings", {}) or {}
            networks = ns.get("Networks") or {}
            for net in networks.values():
                ip = (net or {}).get("IPAddress")
                if ip:
                    return ip
            ip = ns.get("IPAddress")
            if ip:
                return ip
        except Exception:
            pass
        return None

    # ── Retirement legacy marker ─────────────────────────────────────────

    async def mark_due_for_retirement(self) -> int:
        """Mark AVAILABLE rows past ``retire_at`` as RETIRING.

        Called every cleanup sweep. Does NOT kill containers — the cleanup
        loop's existing orphan/zombie sweeps handle that. Returns the
        number of rows marked.
        """
        if not self.enabled:
            return 0

        marked = 0
        async with get_db_session_local() as db:
            rows = await self._sandbox_repo.list_due_for_retirement(db)
            for row in rows:
                row.pool_state = PoolState.RETIRING
                marked += 1
                logger.info(
                    f"Sandbox pool retire: row={row.id} slot={row.pool_slot} retire_at={row.retire_at}"
                )
            if marked:
                await db.commit()
        return marked

    # ── Internal helpers ─────────────────────────────────────────────────

    async def reap_stuck_initializing(self) -> int:
        """Mark DELETED any AVAILABLE pool rows wedged in INITIALIZING.

        Failure mode this exists to recover from: a previous backend run
        inserted a pool row at the start of :meth:`_do_create_slot`
        (status=INITIALIZING, pool_state=AVAILABLE) and then crashed
        before reaching either the container-create call or the
        post-create status=RUNNING update. The row survives the restart
        and:

          * :meth:`_existing_live_slots` (pre-fix) treated it as a live
            slot purely on ``pool_state == AVAILABLE``, so bootstrap
            logged "all slots already populated" and never recreated.
          * Orphan cleanup explicitly skips AVAILABLE pool rows.
          * The Docker-zombie sweep needs a ``provider_sandbox_id`` to
            compare against; these rows usually have none.
          * Stale-pause needs a ``session_id``; pool rows have none.

        The row is therefore stuck forever and the slot stays empty
        even though the DB claims it's full. This sweep closes that
        loop by marking the wedged row DELETED so the next
        :meth:`ensure_full` cycle (or the in-flight bootstrap) can
        recreate the slot from scratch. If the row carried a
        ``provider_sandbox_id`` (i.e. crashed *between* container create
        and the status update) the orphaned container is reaped on the
        next pass of the existing Docker-zombie sweep, which keys on
        active DB rows — once we mark this one DELETED, that container
        becomes a zombie by definition.

        Returns the number of rows reaped.
        """
        if not self.enabled:
            return 0

        cutoff = datetime.now(timezone.utc) - _STUCK_INITIALIZING_THRESHOLD
        reaped = 0
        async with get_db_session_local() as db:
            rows = await self._sandbox_repo.list_active_pool_rows(db)
            for row in rows:
                if row.pool_state != PoolState.AVAILABLE:
                    continue
                if row.status != SandboxStatus.INITIALIZING:
                    continue
                if row.created_at is None or row.created_at > cutoff:
                    continue
                row.status = SandboxStatus.DELETED
                reaped += 1
                logger.warning(
                    f"Sandbox pool reap: slot={row.pool_slot} row={row.id} "
                    f"stuck INITIALIZING since {row.created_at} "
                    f"(provider_sandbox_id={row.provider_sandbox_id or 'none'}) "
                    "— marking DELETED so the slot can be recreated"
                )
            if reaped:
                await db.commit()
        return reaped

    async def _existing_live_slots(self) -> set[int]:
        """Return slot indices currently held by a *credible* live row.

        A slot is "live" when its row is one of:

          * ``pool_state == AVAILABLE`` AND ``status == RUNNING`` — fully
            provisioned, ready for claim.
          * ``pool_state == AVAILABLE`` AND ``status == INITIALIZING``
            AND younger than :data:`_STUCK_INITIALIZING_THRESHOLD` — a
            create currently in flight.
          * ``pool_state == CLAIMED`` (any status) — handed to a session;
            its lifetime is owned by that session, not us.
          * ``pool_state == RETIRING`` (any status) — the cleanup loop
            owns its teardown; we don't recreate its slot until the row
            disappears.

        Older AVAILABLE+INITIALIZING rows are explicitly *not* counted
        as live: they are presumed orphaned by a crashed previous
        backend run and reaped by :meth:`reap_stuck_initializing`. This
        is the central guard against the historical "phantom standby"
        bug where 2 INITIALIZING rows survived a crash and made the
        pool look full forever despite zero containers existing.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - _STUCK_INITIALIZING_THRESHOLD
        async with get_db_session_local() as db:
            rows = await self._sandbox_repo.list_active_pool_rows(db)
            live: set[int] = set()
            for row in rows:
                if row.pool_slot is None:
                    continue
                if row.pool_state == PoolState.AVAILABLE:
                    if row.status == SandboxStatus.RUNNING:
                        live.add(row.pool_slot)
                    elif (
                        row.status == SandboxStatus.INITIALIZING
                        and row.created_at is not None
                        and row.created_at > cutoff
                    ):
                        # Provisioning in flight — slot is taken until
                        # the create finishes or reap_stuck_initializing
                        # decides it's wedged.
                        live.add(row.pool_slot)
                elif row.pool_state in (PoolState.CLAIMED, PoolState.RETIRING):
                    live.add(row.pool_slot)
            return live

    async def snapshot(self) -> dict[str, Any]:
        """Return a JSON-friendly snapshot of pool occupancy and health.

        Used by the ``/health/sandbox-pool`` endpoint and by
        ``platform_checks_pool.sh``. Exposes:

          * ``configured`` — target pool size from settings.
          * ``ready`` — count of AVAILABLE+RUNNING rows (claimable now).
          * ``initializing`` — count of AVAILABLE+INITIALIZING rows.
          * ``initializing_age_max_seconds`` — oldest INITIALIZING row age.
          * ``stuck_initializing`` — count of INITIALIZING rows older than
            :data:`_STUCK_INITIALIZING_THRESHOLD` (i.e. reap candidates).
          * ``claimed`` — count of CLAIMED rows (in-flight sessions).
          * ``retiring`` — count of RETIRING rows (cleanup loop owns).
          * ``stuck_threshold_seconds`` — the reap threshold in seconds.
          * ``enabled`` — whether the pool is enabled in this process.

        Never raises: callers must always get a usable shape so the
        health endpoint and shell scripts can render even on degraded
        DB conditions.
        """
        snap: dict[str, Any] = {
            "enabled": self.enabled,
            "configured": self.pool_size,
            "ready": 0,
            "initializing": 0,
            "initializing_age_max_seconds": None,
            "stuck_initializing": 0,
            "claimed": 0,
            "retiring": 0,
            "stuck_threshold_seconds": int(_STUCK_INITIALIZING_THRESHOLD.total_seconds()),
        }
        if not self.enabled:
            return snap

        now = datetime.now(timezone.utc)
        cutoff = now - _STUCK_INITIALIZING_THRESHOLD
        max_init_age: float | None = None
        try:
            async with get_db_session_local() as db:
                rows = await self._sandbox_repo.list_active_pool_rows(db)
                for row in rows:
                    if row.pool_state == PoolState.AVAILABLE:
                        if row.status == SandboxStatus.RUNNING:
                            snap["ready"] += 1
                        elif row.status == SandboxStatus.INITIALIZING:
                            snap["initializing"] += 1
                            if row.created_at is not None:
                                age = (now - row.created_at).total_seconds()
                                if max_init_age is None or age > max_init_age:
                                    max_init_age = age
                                if row.created_at <= cutoff:
                                    snap["stuck_initializing"] += 1
                    elif row.pool_state == PoolState.CLAIMED:
                        snap["claimed"] += 1
                    elif row.pool_state == PoolState.RETIRING:
                        snap["retiring"] += 1
        except Exception:
            logger.exception("Sandbox pool snapshot failed (returning partial)")
        if max_init_age is not None:
            snap["initializing_age_max_seconds"] = int(max_init_age)
        return snap

    async def _create_slot_async(self, slot: int, *, is_bootstrap: bool) -> None:
        """Create a new pool container for ``slot``.

        Idempotent: if another task is already creating ``slot``, returns
        immediately. Catches all exceptions and logs them — pool failures
        must never propagate to the request path.
        """
        async with self._create_lock:
            if slot in self._creating:
                logger.debug(f"Sandbox pool: slot {slot} create already in flight, skipping")
                return
            self._creating.add(slot)

        try:
            await self._do_create_slot(slot, is_bootstrap=is_bootstrap)
        except Exception:
            logger.exception(
                f"Sandbox pool: failed to create slot {slot} (is_bootstrap={is_bootstrap})"
            )
        finally:
            async with self._create_lock:
                self._creating.discard(slot)

    async def _do_create_slot(self, slot: int, *, is_bootstrap: bool) -> None:
        # 1. Insert the row first so we can recover even if container create
        #    crashes mid-flight.
        async with get_db_session_local() as db:
            now = datetime.now(timezone.utc)
            retire_at = (
                self.compute_bootstrap_retire_at(slot, now=now)
                if is_bootstrap
                else self.compute_replacement_retire_at(now=now)
            )
            row = AgentSandbox(
                session_id=None,
                provider=SandboxProviderType.DOCKER,
                status=SandboxStatus.INITIALIZING,
                pool_state=PoolState.AVAILABLE,
                pool_slot=slot,
                retire_at=retire_at,
            )
            row = await self._sandbox_repo.save(db, row)
            row_id = row.id
            await db.commit()

        logger.info(
            f"Sandbox pool: creating container for slot {slot} (row={row_id}, retire_at={retire_at})"
        )

        # 2. Provision the container. This is the slow part (~90-110s).
        try:
            sandbox_mgr = await self._provider_create_fn(
                row_id,
                self.POOL_SESSION_PLACEHOLDER,
            )
        except SandboxCreationError as exc:
            logger.error(
                f"Sandbox pool: provider create failed for slot {slot} row {row_id}: {exc}"
            )
            # Mark the row DELETED so future bootstrap/ensure_full retries it.
            async with get_db_session_local() as db:
                await self._sandbox_repo.update_status(db, row_id, SandboxStatus.DELETED)
                await db.commit()
            return

        # 3. Persist provider state.
        async with get_db_session_local() as db:
            await self._sandbox_repo.update_provider_info(
                db,
                row_id,
                status=SandboxStatus.RUNNING,
                provider_sandbox_id=sandbox_mgr.provider_sandbox_id,
                expired_at=sandbox_mgr.expired_at,
                provider_data=sandbox_mgr.metadata,
            )
            await db.commit()

        logger.info(
            f"Sandbox pool: slot {slot} ready (row={row_id}, container={sandbox_mgr.provider_sandbox_id})"
        )
