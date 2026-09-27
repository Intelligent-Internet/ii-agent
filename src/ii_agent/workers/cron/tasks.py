"""
Scheduled tasks for cleaning up stale agent run tasks.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from ii_agent.realtime.events.app_events import AgentResponseInterruptedEvent
from ii_agent.realtime.events.models import ApplicationEvent
from ii_agent.realtime.events.repository import EventRepository
from ii_agent.core.db import get_db_session_local
from ii_agent.tasks.models import RunTask, TaskLog
from ii_agent.tasks.types import RunStatus
from ii_agent.chat.messages.models import ChatMessage
from ii_agent.core.logger import logger


# ──────────────────────────────────────────────────────────────────────────────
# Host-environment detection for misfire tuning.
#
# APScheduler's AsyncIOScheduler schedules wake-ups against the asyncio event
# loop's clock, which is derived from CLOCK_MONOTONIC. On a hypervisor guest
# whose host suspends (laptops running WSL2, Hyper-V, VirtualBox, qemu/KVM
# laptops, etc.) the guest's CLOCK_MONOTONIC freezes for the duration of the
# host sleep. When the host thaws, every job that was scheduled to fire during
# the suspend window is reported as "missed by N minutes" and — with the
# default ``misfire_grace_time=1s`` — silently dropped. Long-period jobs
# (e.g. the daily lifecycle-invariants probe) can be skipped for a full day
# every time the developer closes the laptop lid.
#
# Bare-metal Linux servers do not suspend, so the production-grade defaults
# would be fine there. To avoid one-environment-fits-all compromises we tune
# misfire_grace_time and coalesce based on detected host class:
#
#   • bare-metal → tight grace (60 s) — surface real scheduler stalls fast
#   • virtualised → generous grace (1 h) + coalesce — tolerate suspend gaps
#
# Detection is best-effort: inside a container ``/proc/cpuinfo`` exposes the
# ``hypervisor`` CPU flag whenever the host CPU is virtualised, which is the
# precise condition we care about (a paused vCPU stops the monotonic clock).
# WSL2 is additionally probed via ``/proc/version`` to be explicit in logs.
# Operators can force a class via ``IIA_CRON_HOST_CLASS=bare|vm`` if the
# heuristic guesses wrong (e.g. running on a hypervisor server that genuinely
# never suspends).
# ──────────────────────────────────────────────────────────────────────────────


def _detect_host_class() -> tuple[str, str]:
    """Return ``(host_class, reason)`` where host_class is "bare" or "vm"."""
    override = os.environ.get("IIA_CRON_HOST_CLASS", "").strip().lower()
    if override in {"bare", "vm"}:
        return override, f"forced by IIA_CRON_HOST_CLASS={override}"

    # WSL2 → always treat as VM (host is a Hyper-V guest that suspends with
    # the Windows host).
    try:
        version = Path("/proc/version").read_text(errors="ignore").lower()
    except OSError:
        version = ""
    if "microsoft" in version or "wsl" in version:
        return "vm", "WSL2 detected via /proc/version"

    # Generic hypervisor guest detection. The ``hypervisor`` flag in
    # /proc/cpuinfo is set by KVM/Hyper-V/VMware/Xen/etc. when the CPU is
    # virtualised, regardless of whether we are inside a container.
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text(errors="ignore")
    except OSError:
        cpuinfo = ""
    for line in cpuinfo.splitlines():
        if line.startswith("flags") and " hypervisor" in f" {line} ":
            return "vm", "hypervisor flag in /proc/cpuinfo"

    return "bare", "no virtualisation indicators detected"


_HOST_CLASS, _HOST_CLASS_REASON = _detect_host_class()

# Job-defaults tuning per host class. ``coalesce`` collapses a backlog of
# missed fires (caused by host suspend) into a single catch-up run rather
# than firing N times in quick succession when the clock thaws.
if _HOST_CLASS == "vm":
    _JOB_DEFAULTS = {
        "coalesce": True,
        "misfire_grace_time": 3600,  # 1 h — tolerate typical laptop sleep
        "max_instances": 1,
    }
else:
    _JOB_DEFAULTS = {
        "coalesce": True,
        "misfire_grace_time": 60,  # 60 s — bare metal should never miss
        "max_instances": 1,
    }


# Initialize the scheduler with environment-aware misfire tolerance.
scheduler = AsyncIOScheduler(job_defaults=_JOB_DEFAULTS)


def _coerce_uuid(value: object) -> uuid.UUID:
    """Normalize UUID-like values returned by async drivers."""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


async def cleanup_long_running_tasks():
    """
    Clean up RunTasks that have been running for more than 45 minutes.
    Marks them as failed and emits an interrupted event instead of deleting.
    """
    try:
        # Calculate the cutoff time (45 minutes ago)
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=45)
        total_processed = 0
        batch_size = 20
        max_processed = 100

        logger.info(f"Starting cleanup of RunTasks older than {cutoff_time}")

        async with get_db_session_local() as db:
            while total_processed < max_processed:
                # Select tasks older than 45 minutes with FOR UPDATE SKIP LOCKED
                # This ensures we don't block on locked rows and prevents concurrent updates
                # Only select tasks that are currently in RUNNING status
                stmt = (
                    select(RunTask)
                    .where(
                        RunTask.created_at < cutoff_time,
                        RunTask.status == RunStatus.RUNNING,
                    )
                    .order_by(RunTask.created_at.desc())
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )

                result = await db.execute(stmt)
                tasks = result.scalars().all()

                if not tasks:
                    logger.info("No more stale RunTasks found")
                    break

                batch_count = 0

                event_repo = EventRepository()
                for task in tasks:
                    session_id = _coerce_uuid(task.session_id)
                    run_id = _coerce_uuid(task.id)

                    task.status = RunStatus.FAILED
                    task.error_message = "Agent run task timed out during cron cleanup."
                    task.updated_at = datetime.now(timezone.utc)
                    db.add(TaskLog(task_id=run_id, status=RunStatus.FAILED))

                    event = AgentResponseInterruptedEvent(
                        session_id=session_id,
                        run_id=run_id,
                        content={
                            "message": "Agent run task was interrupted by system cleanup due to timeout.",
                            "run_id": str(run_id),
                            "run_status": RunStatus.FAILED,
                        },
                    )
                    await event_repo.save(
                        db,
                        ApplicationEvent(
                            id=event.id,
                            event_type=event.name,
                            event_group=event.group,
                            session_id=session_id,
                            run_id=run_id,
                            user_id=event.user_id,
                            content=event.content,
                        ),
                    )
                    batch_count += 1

                # Commit all updates in one transaction
                await db.commit()

                total_processed += batch_count
                logger.info(
                    f"Marked {batch_count} stale RunTasks as failed due to timeout. "
                    f"Total processed: {total_processed}/{max_processed}"
                )

                if batch_count < batch_size:
                    break

                if total_processed >= max_processed:
                    logger.info(
                        f"Reached max processed limit ({max_processed}). "
                        "Remaining tasks will be processed in next run."
                    )
                    break

        logger.info(
            f"Cleanup completed. Total RunTasks marked as failed due to timeout: {total_processed}"
        )

    except Exception as e:
        logger.opt(exception=True).error(f"Error during RunTask cleanup: {e}")
        # Don't re-raise - we want the scheduler to continue running


async def cleanup_long_running_chat_messages():
    """
    Clean up incomplete assistant ChatMessages older than 45 minutes.
    Marks them as finished (is_finished=True) so they don't block future operations.
    """
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=45)
        total_processed = 0
        batch_size = 20
        max_processed = 100

        logger.info(f"Starting cleanup of incomplete ChatMessages older than {cutoff_time}")

        async with get_db_session_local() as db:
            while total_processed < max_processed:
                stmt = (
                    select(ChatMessage)
                    .where(
                        ChatMessage.created_at < cutoff_time,
                        ChatMessage.role == "assistant",
                        ChatMessage.is_finished == False,  # noqa: E712
                    )
                    .order_by(ChatMessage.created_at.desc())
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )

                result = await db.execute(stmt)
                messages = result.scalars().all()

                if not messages:
                    logger.info("No more stale incomplete ChatMessages found")
                    break

                batch_count = len(messages)

                for msg in messages:
                    msg.is_finished = True
                    msg.finish_reason = "timeout"
                    msg.updated_at = datetime.now(timezone.utc)

                await db.commit()

                total_processed += batch_count
                logger.info(
                    f"Marked {batch_count} stale ChatMessages as finished. "
                    f"Total processed: {total_processed}/{max_processed}"
                )

                if batch_count < batch_size:
                    break

                if total_processed >= max_processed:
                    logger.info(
                        f"Reached max processed limit ({max_processed}). "
                        "Remaining messages will be processed in next run."
                    )
                    break

        logger.info(f"Chat message cleanup completed. Total marked as finished: {total_processed}")

    except Exception as e:
        logger.opt(exception=True).error(f"Error during ChatMessage cleanup: {e}")


async def run_purge_invariants_check():
    """Nightly §2.3 lifecycle-invariants probe.

    Runs every ``check_I*`` in :data:`invariants.DB_CHECKABLE` against
    the primary database and logs the report. Any FAIL or ERROR
    outcome is logged at ERROR level (so the alerting pipeline keyed
    on ``INVARIANT FAIL`` / ``INVARIANT ERROR`` substrings pages an
    operator). Schema-enforced invariants (Tier 1) are not executed
    here — they are checked atomically at write time by the database.
    Structural invariants (Tier 3) are pinned by named tests and not
    executed by this runner.

    The job swallows its own exceptions because APScheduler's default
    behaviour on an unhandled error is to suppress the next firing —
    we want the invariant probe to keep running even if a single
    pass blew up on a transient DB hiccup.
    """
    try:
        from ii_agent.sessions.purge.check_runner import run_all_invariants

        async with get_db_session_local() as db:
            report = await run_all_invariants(db)
        logger.info("purge invariants: {}", report.summary())
        if report.failed or report.errored:
            # The check_runner already logged the offending rows at ERROR.
            # This bubbles a single concise summary the alert rule keys on.
            logger.error(
                "INVARIANT REPORT non-pass: failed={} errored={} skipped={} elapsed={:.2f}s",
                len(report.failed),
                len(report.errored),
                len(report.skipped),
                report.total_elapsed_seconds,
            )
    except Exception as e:
        logger.opt(exception=True).error(f"Error running purge invariants: {e}")


def start_scheduler():
    """
    Start the scheduler and add all periodic jobs.
    """
    try:
        # ── Run / chat cleanup ────────────────────────────────────────────
        scheduler.add_job(
            cleanup_long_running_tasks,
            trigger=IntervalTrigger(minutes=40),
            id="cleanup_stale_agent_run_tasks",
            name="Cleanup stale RunTasks (older than 45 mins)",
            replace_existing=True,
            max_instances=1,
        )

        scheduler.add_job(
            cleanup_long_running_chat_messages,
            trigger=IntervalTrigger(minutes=40),
            id="cleanup_stale_chat_messages",
            name="Cleanup stale incomplete ChatMessages (older than 45 mins)",
            replace_existing=True,
            max_instances=1,
        )

        # ── Lifecycle invariants probe ────────────────────────────────────
        # Daily probe of every DB-checkable invariant. Schema-enforced
        # invariants are policed at write time; this catches anything that
        # bypasses the ORM or drifts via raw SQL.
        #
        # Misfire tuning rationale:
        #   - On a 24 h interval, a missed fire = the system goes a full day
        #     without an integrity scan. We want to be very forgiving about
        #     when the catch-up run actually executes.
        #   - On a VM/laptop, the host can suspend for >1 h (overnight,
        #     weekend), so we override the default grace to 6 h here and
        #     keep coalesce=True so an extended outage produces exactly one
        #     catch-up run, not a flood.
        #   - On bare metal we still relax the default 60 s grace to 30 min
        #     for this job so a transient event-loop stall doesn't drop the
        #     daily run on the floor.
        _invariants_grace = 6 * 3600 if _HOST_CLASS == "vm" else 1800
        scheduler.add_job(
            run_purge_invariants_check,
            trigger=IntervalTrigger(hours=24),
            id="run_purge_invariants_check",
            name="Run §2.3 lifecycle-invariants probe (DB_CHECKABLE tier)",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=_invariants_grace,
            coalesce=True,
        )

        # ── Billing recovery (temporarily disabled) ───────────────────────
        # from ii_agent.workers.cron.billing_recovery import (
        #     alert_settlement_failures,
        #     expire_stale_reservations,
        #     retry_shortfall_settlement_failures,
        # )
        #
        # scheduler.add_job(
        #     expire_stale_reservations,
        #     trigger=IntervalTrigger(minutes=15),
        #     id="expire_stale_reservations",
        #     name="Release stale credit reservation holds",
        #     replace_existing=True,
        #     max_instances=1,
        # )
        #
        # scheduler.add_job(
        #     retry_shortfall_settlement_failures,
        #     trigger=IntervalTrigger(minutes=5),
        #     id="retry_shortfall_settlement_failures",
        #     name="Retry replayable shortfall settlement failures",
        #     replace_existing=True,
        #     max_instances=1,
        # )
        #
        # scheduler.add_job(
        #     alert_settlement_failures,
        #     trigger=IntervalTrigger(minutes=5),
        #     id="alert_settlement_failures",
        #     name="Log reservations stuck in settlement_failed",
        #     replace_existing=True,
        #     max_instances=1,
        # )

        # Start the scheduler
        scheduler.start()
        logger.info(
            "Scheduler started with {} jobs (host_class={}, reason={}, "
            "default_misfire_grace_time={}s, coalesce={})",
            len(scheduler.get_jobs()),
            _HOST_CLASS,
            _HOST_CLASS_REASON,
            _JOB_DEFAULTS["misfire_grace_time"],
            _JOB_DEFAULTS["coalesce"],
        )

    except Exception as e:
        logger.opt(exception=True).error(f"Error starting scheduler: {e}")
        raise


def shutdown_scheduler():
    """
    Shutdown the scheduler gracefully.
    """
    try:
        if scheduler.running:
            scheduler.shutdown(wait=True)
            logger.info("Scheduler shutdown successfully")
    except Exception as e:
        logger.opt(exception=True).error(f"Error shutting down scheduler: {e}")
