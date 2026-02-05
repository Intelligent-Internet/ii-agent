"""
Event Telemetry System

Provides run start/end metadata hooks for telemetry without changing behavior.
Follows ralph's DistributionLogger pattern with structured logging and file persistence.

Usage:
    from ii_skills.shared.event_telemetry import TelemetryLogger, RunContext

    logger = TelemetryLogger(output_dir="logs/telemetry")

    async with logger.run_context(
        run_type="deal_analysis",
        metadata={"company": "Acme", "deal_type": "lbo"}
    ) as ctx:
        # Your code here
        ctx.log_event("phase_started", {"phase": "data_collection"})
        ctx.add_metric("api_calls", 5)

    # Run metrics automatically captured on exit
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from uuid import uuid4
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class RunStatus(Enum):
    """Status of a telemetry run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TelemetryEvent:
    """A single telemetry event."""
    event_id: str
    run_id: str
    event_type: str
    timestamp: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunMetrics:
    """Metrics collected during a run."""
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    total_duration_ms: float = 0
    api_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    bytes_processed: int = 0
    custom_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunRecord:
    """Complete record of a telemetry run."""
    run_id: str
    run_type: str
    status: RunStatus
    started_at: str
    ended_at: Optional[str] = None
    duration_ms: Optional[float] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    metrics: RunMetrics = field(default_factory=RunMetrics)
    events: List[TelemetryEvent] = field(default_factory=list)
    error: Optional[str] = None
    error_traceback: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['status'] = self.status.value
        return d


class RunContext:
    """
    Context for a telemetry run.

    Provides methods to log events and metrics during execution.
    Automatically captures start/end times and final status.
    """

    def __init__(
        self,
        run_id: str,
        run_type: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        on_event: Optional[Callable[[TelemetryEvent], None]] = None,
    ):
        self.run_id = run_id
        self.run_type = run_type
        self.user_id = user_id
        self.session_id = session_id
        self.metadata = metadata or {}
        self._on_event = on_event

        self._started_at = datetime.now(timezone.utc)
        self._ended_at: Optional[datetime] = None
        self._status = RunStatus.PENDING
        self._metrics = RunMetrics()
        self._events: List[TelemetryEvent] = []
        self._error: Optional[str] = None
        self._error_traceback: Optional[str] = None

    def log_event(self, event_type: str, data: Optional[Dict[str, Any]] = None):
        """Log a telemetry event."""
        event = TelemetryEvent(
            event_id=str(uuid4()),
            run_id=self.run_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            data=data or {},
        )
        self._events.append(event)

        if self._on_event:
            try:
                self._on_event(event)
            except Exception as e:
                logger.warning(f"Event callback failed: {e}")

    def add_metric(self, key: str, value: Any):
        """Add a custom metric."""
        self._metrics.custom_metrics[key] = value

    def increment_metric(self, key: str, amount: int = 1):
        """Increment a custom metric counter."""
        current = self._metrics.custom_metrics.get(key, 0)
        self._metrics.custom_metrics[key] = current + amount

    def increment_tasks(self, completed: int = 0, failed: int = 0, skipped: int = 0):
        """Increment task counters."""
        self._metrics.completed_tasks += completed
        self._metrics.failed_tasks += failed
        self._metrics.skipped_tasks += skipped
        self._metrics.total_tasks = (
            self._metrics.completed_tasks +
            self._metrics.failed_tasks +
            self._metrics.skipped_tasks
        )

    def increment_api_calls(self, count: int = 1):
        """Increment API call counter."""
        self._metrics.api_calls += count

    def increment_cache(self, hits: int = 0, misses: int = 0):
        """Increment cache hit/miss counters."""
        self._metrics.cache_hits += hits
        self._metrics.cache_misses += misses

    def add_bytes_processed(self, bytes_count: int):
        """Add to bytes processed counter."""
        self._metrics.bytes_processed += bytes_count

    def start(self):
        """Mark run as started."""
        self._status = RunStatus.RUNNING
        self.log_event("run_started", {
            "run_type": self.run_type,
            "user_id": self.user_id,
            "metadata": self.metadata,
        })

    def complete(self):
        """Mark run as completed."""
        self._status = RunStatus.COMPLETED
        self._ended_at = datetime.now(timezone.utc)
        self.log_event("run_completed", {
            "metrics": self._metrics.to_dict(),
        })

    def fail(self, error: str, traceback: Optional[str] = None):
        """Mark run as failed."""
        self._status = RunStatus.FAILED
        self._ended_at = datetime.now(timezone.utc)
        self._error = error
        self._error_traceback = traceback
        self.log_event("run_failed", {
            "error": error,
        })

    def cancel(self):
        """Mark run as cancelled."""
        self._status = RunStatus.CANCELLED
        self._ended_at = datetime.now(timezone.utc)
        self.log_event("run_cancelled", {})

    def to_record(self) -> RunRecord:
        """Convert to a complete run record."""
        duration_ms = None
        if self._ended_at:
            duration_ms = (self._ended_at - self._started_at).total_seconds() * 1000

        self._metrics.total_duration_ms = duration_ms or 0

        return RunRecord(
            run_id=self.run_id,
            run_type=self.run_type,
            status=self._status,
            started_at=self._started_at.isoformat(),
            ended_at=self._ended_at.isoformat() if self._ended_at else None,
            duration_ms=duration_ms,
            user_id=self.user_id,
            session_id=self.session_id,
            metadata=self.metadata,
            metrics=self._metrics,
            events=self._events,
            error=self._error,
            error_traceback=self._error_traceback,
        )


class TelemetryLogger:
    """
    Telemetry logger following ralph's DistributionLogger pattern.

    Provides:
    - Run start/end hooks with metadata capture
    - Event logging during execution
    - Metrics collection
    - File-based persistence for audit trail
    - Optional webhook callbacks
    """

    def __init__(
        self,
        output_dir: Optional[str] = None,
        webhook_url: Optional[str] = None,
        enable_file_logging: bool = True,
        enable_console_logging: bool = False,
    ):
        """
        Initialize telemetry logger.

        Args:
            output_dir: Directory for telemetry files
            webhook_url: Optional webhook for real-time telemetry
            enable_file_logging: Write records to JSON files
            enable_console_logging: Log to console
        """
        self._output_dir = Path(output_dir) if output_dir else Path("logs/telemetry")
        self._webhook_url = webhook_url
        self._enable_file_logging = enable_file_logging
        self._enable_console_logging = enable_console_logging

        # Ensure output directory exists
        if self._enable_file_logging:
            self._output_dir.mkdir(parents=True, exist_ok=True)

        # Active runs
        self._active_runs: Dict[str, RunContext] = {}

        # Event hooks
        self._on_run_start: List[Callable[[RunContext], None]] = []
        self._on_run_end: List[Callable[[RunRecord], None]] = []
        self._on_event: List[Callable[[TelemetryEvent], None]] = []

    def add_run_start_hook(self, hook: Callable[[RunContext], None]):
        """Register a hook called when runs start."""
        self._on_run_start.append(hook)

    def add_run_end_hook(self, hook: Callable[[RunRecord], None]):
        """Register a hook called when runs end."""
        self._on_run_end.append(hook)

    def add_event_hook(self, hook: Callable[[TelemetryEvent], None]):
        """Register a hook called for each event."""
        self._on_event.append(hook)

    def _fire_event(self, event: TelemetryEvent):
        """Fire event to all registered hooks."""
        for hook in self._on_event:
            try:
                hook(event)
            except Exception as e:
                logger.warning(f"Event hook failed: {e}")

    def _fire_run_start(self, ctx: RunContext):
        """Fire run start hooks."""
        for hook in self._on_run_start:
            try:
                hook(ctx)
            except Exception as e:
                logger.warning(f"Run start hook failed: {e}")

    def _fire_run_end(self, record: RunRecord):
        """Fire run end hooks."""
        for hook in self._on_run_end:
            try:
                hook(record)
            except Exception as e:
                logger.warning(f"Run end hook failed: {e}")

    def _log_to_console(self, message: str, level: str = "INFO"):
        """Log message to console."""
        if self._enable_console_logging:
            print(f"[TELEMETRY] [{level}] {message}")

    def _write_record(self, record: RunRecord):
        """Write run record to file."""
        if not self._enable_file_logging:
            return

        try:
            # Create dated subdirectory
            date_dir = self._output_dir / datetime.now().strftime("%Y-%m-%d")
            date_dir.mkdir(parents=True, exist_ok=True)

            # Write record file
            filename = f"{record.run_type}_{record.run_id}.json"
            filepath = date_dir / filename

            with open(filepath, "w") as f:
                json.dump(record.to_dict(), f, indent=2, default=str)

            self._log_to_console(f"Wrote telemetry to {filepath}")

        except Exception as e:
            logger.error(f"Failed to write telemetry: {e}")

    async def _send_webhook(self, event_type: str, data: Dict[str, Any]):
        """Send telemetry to webhook."""
        if not self._webhook_url:
            return

        try:
            import aiohttp

            payload = {
                "event_type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status >= 400:
                        logger.warning(f"Telemetry webhook failed: {response.status}")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Telemetry webhook failed: {e}")

    def create_run(
        self,
        run_type: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> RunContext:
        """
        Create a new run context.

        Args:
            run_type: Type of run (e.g., "deal_analysis", "newsletter")
            user_id: Optional user identifier
            session_id: Optional session identifier
            metadata: Optional metadata dict
            run_id: Optional specific run ID (auto-generated if not provided)

        Returns:
            RunContext for the new run
        """
        run_id = run_id or str(uuid4())

        ctx = RunContext(
            run_id=run_id,
            run_type=run_type,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
            on_event=self._fire_event,
        )

        self._active_runs[run_id] = ctx
        return ctx

    @asynccontextmanager
    async def run_context(
        self,
        run_type: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Async context manager for telemetry runs.

        Automatically captures start/end times and status.

        Usage:
            async with logger.run_context("deal_analysis", metadata={"company": "Acme"}) as ctx:
                ctx.log_event("phase_started", {"phase": "data_collection"})
                # ... do work ...
        """
        ctx = self.create_run(run_type, user_id, session_id, metadata)

        try:
            # Start run
            ctx.start()
            self._fire_run_start(ctx)
            self._log_to_console(f"Run started: {run_type} ({ctx.run_id})")

            # Send webhook
            asyncio.create_task(self._send_webhook("run_started", {
                "run_id": ctx.run_id,
                "run_type": run_type,
                "metadata": metadata,
            }))

            yield ctx

            # Complete run
            ctx.complete()

        except asyncio.CancelledError:
            ctx.cancel()
            raise

        except Exception as e:
            import traceback
            ctx.fail(str(e), traceback.format_exc())
            raise

        finally:
            # Generate record
            record = ctx.to_record()

            # Fire end hooks
            self._fire_run_end(record)

            # Write to file
            self._write_record(record)

            # Log completion
            status = record.status.value
            duration = f" ({record.duration_ms:.0f}ms)" if record.duration_ms else ""
            self._log_to_console(f"Run {status}: {run_type}{duration}")

            # Send webhook
            asyncio.create_task(self._send_webhook("run_ended", {
                "run_id": record.run_id,
                "run_type": record.run_type,
                "status": status,
                "duration_ms": record.duration_ms,
                "metrics": record.metrics.to_dict(),
            }))

            # Cleanup
            self._active_runs.pop(ctx.run_id, None)

    def get_active_runs(self) -> Dict[str, RunContext]:
        """Get all currently active runs."""
        return dict(self._active_runs)

    def get_recent_records(
        self,
        run_type: Optional[str] = None,
        limit: int = 100,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Get recent telemetry records from files.

        Args:
            run_type: Filter by run type
            limit: Maximum records to return
            days: Number of days to look back

        Returns:
            List of run records as dicts
        """
        if not self._enable_file_logging:
            return []

        records = []
        today = datetime.now()

        for day_offset in range(days):
            date = today - timedelta(days=day_offset)
            date_dir = self._output_dir / date.strftime("%Y-%m-%d")

            if not date_dir.exists():
                continue

            for filepath in sorted(date_dir.glob("*.json"), reverse=True):
                if len(records) >= limit:
                    break

                try:
                    with open(filepath) as f:
                        record = json.load(f)

                    if run_type and record.get("run_type") != run_type:
                        continue

                    records.append(record)
                except Exception as e:
                    logger.warning(f"Failed to read telemetry file: {e}")

        return records[:limit]


# Singleton for convenience
_default_logger: Optional[TelemetryLogger] = None


def get_telemetry_logger() -> TelemetryLogger:
    """Get the default telemetry logger instance."""
    global _default_logger
    if _default_logger is None:
        _default_logger = TelemetryLogger()
    return _default_logger


def set_telemetry_logger(logger_instance: TelemetryLogger):
    """Set the default telemetry logger instance."""
    global _default_logger
    _default_logger = logger_instance


# Import for get_recent_records
from datetime import timedelta
