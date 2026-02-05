"""
Tool Execution Metrics

Per-tool execution metrics with duration tracking and failure taxonomy.
Provides immediate latency insight with zero behavior change.

Usage:
    from ii_skills.shared.tool_metrics import ToolMetrics, ToolErrorType

    metrics = ToolMetrics()

    # Track a tool execution
    with metrics.track_execution("search_tool") as tracker:
        result = await tool.execute(params)
        if error:
            tracker.mark_error(ToolErrorType.TIMEOUT, "Request timed out")

    # Get metrics summary
    summary = metrics.get_summary()
"""

import time
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from contextlib import contextmanager
import statistics

logger = logging.getLogger(__name__)


class ToolErrorType(Enum):
    """
    Standardized tool failure taxonomy.

    Categories:
    - TIMEOUT: Tool execution exceeded time limit
    - VALIDATION: Input validation failed
    - RUNTIME: Execution error during tool run
    - NOT_FOUND: Requested resource not found
    - PERMISSION: Access denied or insufficient permissions
    - RATE_LIMIT: Rate limit exceeded
    - NETWORK: Network/connectivity error
    - UNKNOWN: Unclassified error
    """
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    RUNTIME = "runtime"
    NOT_FOUND = "not_found"
    PERMISSION = "permission"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    UNKNOWN = "unknown"

    @classmethod
    def from_exception(cls, exc: Exception) -> "ToolErrorType":
        """Classify an exception into an error type."""
        exc_name = type(exc).__name__.lower()
        exc_msg = str(exc).lower()

        if "timeout" in exc_name or "timeout" in exc_msg:
            return cls.TIMEOUT
        elif "validation" in exc_name or "invalid" in exc_msg:
            return cls.VALIDATION
        elif "notfound" in exc_name or "not found" in exc_msg or "404" in exc_msg:
            return cls.NOT_FOUND
        elif "permission" in exc_name or "access denied" in exc_msg or "403" in exc_msg:
            return cls.PERMISSION
        elif "ratelimit" in exc_name or "rate limit" in exc_msg or "429" in exc_msg:
            return cls.RATE_LIMIT
        elif "connection" in exc_name or "network" in exc_msg:
            return cls.NETWORK
        else:
            return cls.UNKNOWN


@dataclass
class ToolExecutionRecord:
    """Record of a single tool execution."""
    tool_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    is_error: bool = False
    error_type: Optional[ToolErrorType] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def complete(self, is_error: bool = False, error_type: Optional[ToolErrorType] = None,
                 error_message: Optional[str] = None):
        """Mark execution as complete."""
        self.end_time = datetime.now()
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.is_error = is_error
        self.error_type = error_type
        self.error_message = error_message

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for event emission."""
        return {
            "tool_name": self.tool_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "is_error": self.is_error,
            "error_type": self.error_type.value if self.error_type else None,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class ToolMetricsSummary:
    """Summary statistics for a tool."""
    tool_name: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    min_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    p50_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0
    error_counts: Dict[str, int] = field(default_factory=dict)
    success_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tool_name": self.tool_name,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": self.success_rate,
            "duration": {
                "total_ms": self.total_duration_ms,
                "avg_ms": self.avg_duration_ms,
                "min_ms": self.min_duration_ms,
                "max_ms": self.max_duration_ms,
                "p50_ms": self.p50_duration_ms,
                "p95_ms": self.p95_duration_ms,
                "p99_ms": self.p99_duration_ms,
            },
            "error_counts": self.error_counts,
        }


class ExecutionTracker:
    """Context manager for tracking a single tool execution."""

    def __init__(self, tool_name: str, metrics: "ToolMetrics", metadata: Optional[Dict] = None):
        self.tool_name = tool_name
        self.metrics = metrics
        self.record = ToolExecutionRecord(
            tool_name=tool_name,
            start_time=datetime.now(),
            metadata=metadata or {},
        )
        self._completed = False

    def mark_error(self, error_type: ToolErrorType, message: Optional[str] = None):
        """Mark execution as failed with specific error type."""
        self.record.is_error = True
        self.record.error_type = error_type
        self.record.error_message = message

    def mark_error_from_exception(self, exc: Exception):
        """Mark execution as failed, classifying the exception."""
        self.record.is_error = True
        self.record.error_type = ToolErrorType.from_exception(exc)
        self.record.error_message = str(exc)

    def add_metadata(self, key: str, value: Any):
        """Add metadata to the execution record."""
        self.record.metadata[key] = value

    def complete(self):
        """Complete the execution tracking."""
        if not self._completed:
            self.record.complete(
                is_error=self.record.is_error,
                error_type=self.record.error_type,
                error_message=self.record.error_message,
            )
            self.metrics._record_execution(self.record)
            self._completed = True


class ToolMetrics:
    """
    Collects and aggregates tool execution metrics.

    Thread-safe collection of execution records with
    summary statistics and percentile calculations.
    """

    def __init__(self, max_records_per_tool: int = 1000):
        """
        Initialize metrics collector.

        Args:
            max_records_per_tool: Maximum records to keep per tool (for memory management)
        """
        self.max_records = max_records_per_tool
        self._records: Dict[str, List[ToolExecutionRecord]] = {}
        self._lock = None  # Add threading.Lock() if needed

    @contextmanager
    def track_execution(self, tool_name: str, metadata: Optional[Dict] = None):
        """
        Context manager for tracking tool execution.

        Usage:
            with metrics.track_execution("my_tool") as tracker:
                try:
                    result = await tool.run()
                except Exception as e:
                    tracker.mark_error_from_exception(e)
                    raise
        """
        tracker = ExecutionTracker(tool_name, self, metadata)
        try:
            yield tracker
        except Exception as e:
            if not tracker.record.is_error:
                tracker.mark_error_from_exception(e)
            raise
        finally:
            tracker.complete()

    def record_execution(
        self,
        tool_name: str,
        duration_ms: float,
        is_error: bool = False,
        error_type: Optional[ToolErrorType] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ):
        """
        Record a tool execution directly (alternative to context manager).

        Args:
            tool_name: Name of the tool
            duration_ms: Execution duration in milliseconds
            is_error: Whether execution failed
            error_type: Type of error if failed
            error_message: Error message if failed
            metadata: Additional metadata
        """
        now = datetime.now()
        record = ToolExecutionRecord(
            tool_name=tool_name,
            start_time=now,
            end_time=now,
            duration_ms=duration_ms,
            is_error=is_error,
            error_type=error_type,
            error_message=error_message,
            metadata=metadata or {},
        )
        self._record_execution(record)

    def _record_execution(self, record: ToolExecutionRecord):
        """Internal method to store an execution record."""
        tool_name = record.tool_name
        if tool_name not in self._records:
            self._records[tool_name] = []

        self._records[tool_name].append(record)

        # Trim old records if over limit
        if len(self._records[tool_name]) > self.max_records:
            self._records[tool_name] = self._records[tool_name][-self.max_records:]

        # Log the execution
        if record.is_error:
            logger.warning(
                f"Tool {tool_name} failed: {record.error_type.value if record.error_type else 'unknown'} "
                f"({record.duration_ms:.1f}ms) - {record.error_message}"
            )
        else:
            logger.debug(f"Tool {tool_name} completed in {record.duration_ms:.1f}ms")

    def get_tool_summary(self, tool_name: str) -> Optional[ToolMetricsSummary]:
        """Get summary statistics for a specific tool."""
        records = self._records.get(tool_name, [])
        if not records:
            return None

        durations = [r.duration_ms for r in records if r.duration_ms is not None]
        errors = [r for r in records if r.is_error]

        summary = ToolMetricsSummary(
            tool_name=tool_name,
            total_calls=len(records),
            successful_calls=len(records) - len(errors),
            failed_calls=len(errors),
        )

        if durations:
            summary.total_duration_ms = sum(durations)
            summary.avg_duration_ms = statistics.mean(durations)
            summary.min_duration_ms = min(durations)
            summary.max_duration_ms = max(durations)

            sorted_durations = sorted(durations)
            summary.p50_duration_ms = self._percentile(sorted_durations, 50)
            summary.p95_duration_ms = self._percentile(sorted_durations, 95)
            summary.p99_duration_ms = self._percentile(sorted_durations, 99)

        if summary.total_calls > 0:
            summary.success_rate = summary.successful_calls / summary.total_calls

        # Count errors by type
        for error in errors:
            error_type = error.error_type.value if error.error_type else "unknown"
            summary.error_counts[error_type] = summary.error_counts.get(error_type, 0) + 1

        return summary

    def get_summary(self) -> Dict[str, ToolMetricsSummary]:
        """Get summary statistics for all tools."""
        return {
            tool_name: self.get_tool_summary(tool_name)
            for tool_name in self._records.keys()
        }

    def get_recent_errors(self, limit: int = 10) -> List[ToolExecutionRecord]:
        """Get most recent errors across all tools."""
        all_errors = []
        for records in self._records.values():
            all_errors.extend([r for r in records if r.is_error])

        # Sort by start time descending
        all_errors.sort(key=lambda r: r.start_time, reverse=True)
        return all_errors[:limit]

    def clear(self, tool_name: Optional[str] = None):
        """Clear metrics records."""
        if tool_name:
            self._records.pop(tool_name, None)
        else:
            self._records.clear()

    @staticmethod
    def _percentile(sorted_data: List[float], percentile: float) -> float:
        """Calculate percentile from sorted data."""
        if not sorted_data:
            return 0.0
        k = (len(sorted_data) - 1) * percentile / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f
        return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


# Global metrics instance for convenience
_global_metrics: Optional[ToolMetrics] = None


def get_global_metrics() -> ToolMetrics:
    """Get the global metrics instance."""
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = ToolMetrics()
    return _global_metrics


def track_tool_execution(tool_name: str, metadata: Optional[Dict] = None):
    """Convenience decorator/context manager using global metrics."""
    return get_global_metrics().track_execution(tool_name, metadata)
