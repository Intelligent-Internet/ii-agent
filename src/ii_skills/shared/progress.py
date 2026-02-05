"""
Live Progress Reporter — real-time terminal updates during multi-phase execution.

Provides transparent feedback while the agent works through a case study:
- Phase start/complete with numbered progress
- Key metric updates (IRR, MOIC, etc.) as they're computed
- File creation notifications with full paths
- Timing information

Designed to be hooked into TaskGraphExecutor or used standalone.

Usage:
    from ii_skills.shared.progress import ProgressReporter

    reporter = ProgressReporter(total_phases=5, case_name="Acme Corp LBO")
    reporter.phase_start("Building Operating Model")
    reporter.metric("EBITDA Y5", "$28.4M")
    reporter.file_created("output/cases/.../02_models/acme_lbo.xlsx", "LBO Model")
    reporter.phase_complete("Operating Model", {"revenue_y5": 142.0, "ebitda_y5": 28.4})
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from rich.console import Console
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


# ---------------------------------------------------------------------------
# ProgressEvent — structured log of progress events
# ---------------------------------------------------------------------------

@dataclass
class ProgressEvent:
    """A single progress event."""
    event_type: str  # phase_start, phase_complete, metric, file, message, error
    label: str
    detail: str = ""
    timestamp: str = ""
    elapsed_ms: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# ProgressReporter
# ---------------------------------------------------------------------------

class ProgressReporter:
    """
    Real-time progress reporter for terminal output.

    Emits formatted status lines as work progresses.
    Can be used with or without rich library.
    """

    def __init__(
        self,
        total_phases: int = 0,
        case_name: str = "",
        use_color: bool = True,
        quiet: bool = False,
    ):
        """
        Args:
            total_phases: Total number of phases expected (for X/N display).
            case_name: Deal/case name for context.
            use_color: Use rich formatting if available.
            quiet: If True, suppress all output (events still logged).
        """
        self.total_phases = total_phases
        self.case_name = case_name
        self._use_color = use_color and HAS_RICH
        self._quiet = quiet
        self._console = Console() if HAS_RICH else None

        self._current_phase: int = 0
        self._start_time: float = time.monotonic()
        self._phase_start_time: float = 0.0
        self._events: List[ProgressEvent] = []

    # --- Public API ---

    def case_start(self, case_name: str = "", total_phases: int = 0) -> None:
        """Signal the start of a case study."""
        if case_name:
            self.case_name = case_name
        if total_phases:
            self.total_phases = total_phases
        self._start_time = time.monotonic()

        event = ProgressEvent(
            event_type="case_start",
            label=self.case_name or "Case Study",
            detail=f"{self.total_phases} phases" if self.total_phases else "",
        )
        self._events.append(event)
        self._emit_line(f"[START] {self.case_name}", style="bold blue")

    def phase_start(self, phase_name: str) -> None:
        """Signal the start of a new phase."""
        self._current_phase += 1
        self._phase_start_time = time.monotonic()

        progress = f"[{self._current_phase}/{self.total_phases}]" if self.total_phases else f"[{self._current_phase}]"

        event = ProgressEvent(
            event_type="phase_start",
            label=phase_name,
            detail=progress,
        )
        self._events.append(event)
        self._emit_line(f"{progress} {phase_name}...", style="bold cyan")

    def phase_complete(self, phase_name: str, summary: Optional[Dict[str, Any]] = None) -> None:
        """Signal the completion of a phase with optional summary metrics."""
        elapsed = (time.monotonic() - self._phase_start_time) * 1000 if self._phase_start_time else 0

        detail_parts = [f"{_format_duration(elapsed)}"]
        if summary:
            for key, value in summary.items():
                if isinstance(value, float):
                    detail_parts.append(f"{key}: {value:,.1f}")
                else:
                    detail_parts.append(f"{key}: {value}")

        detail = " | ".join(detail_parts)

        event = ProgressEvent(
            event_type="phase_complete",
            label=phase_name,
            detail=detail,
            elapsed_ms=elapsed,
        )
        self._events.append(event)
        self._emit_line(f"  [OK] {phase_name} ({detail})", style="green")

    def metric(self, label: str, value: str) -> None:
        """Report a key metric as it's computed."""
        event = ProgressEvent(
            event_type="metric",
            label=label,
            detail=value,
        )
        self._events.append(event)
        self._emit_line(f"  >> {label}: {value}", style="yellow")

    def file_created(self, path: str, description: str = "") -> None:
        """Notify that a file was created."""
        event = ProgressEvent(
            event_type="file",
            label=description or "File created",
            detail=path,
        )
        self._events.append(event)
        desc = f" ({description})" if description else ""
        self._emit_line(f"  [FILE] {path}{desc}", style="dim")

    def message(self, text: str) -> None:
        """Emit a general status message."""
        event = ProgressEvent(event_type="message", label=text)
        self._events.append(event)
        self._emit_line(f"  {text}", style=None)

    def error(self, text: str) -> None:
        """Emit an error message."""
        event = ProgressEvent(event_type="error", label=text)
        self._events.append(event)
        self._emit_line(f"  [ERROR] {text}", style="bold red")

    def case_complete(self, summary: Optional[Dict[str, Any]] = None) -> None:
        """Signal the case study is complete."""
        total_elapsed = (time.monotonic() - self._start_time) * 1000

        event = ProgressEvent(
            event_type="case_complete",
            label=self.case_name or "Case Study",
            detail=f"Total: {_format_duration(total_elapsed)}",
            elapsed_ms=total_elapsed,
        )
        self._events.append(event)

        line = f"[DONE] {self.case_name} - {_format_duration(total_elapsed)}"
        if summary:
            extras = [f"{k}: {v}" for k, v in summary.items()]
            line += f" | {' | '.join(extras)}"

        self._emit_line(line, style="bold green")

    # --- Summary ---

    def get_timeline(self) -> str:
        """Get a formatted timeline of all events."""
        if not self._events:
            return "  No progress events recorded."

        lines = ["  Progress Timeline", f"  {'─' * 60}"]
        for ev in self._events:
            prefix = {
                "case_start": "[START]",
                "phase_start": "  >>>",
                "phase_complete": "  [OK]",
                "metric": "   >>",
                "file": " [FILE]",
                "message": "     ",
                "error": "[ERROR]",
                "case_complete": " [DONE]",
            }.get(ev.event_type, "     ")

            detail = f" - {ev.detail}" if ev.detail else ""
            lines.append(f"  {ev.timestamp} {prefix} {ev.label}{detail}")

        return "\n".join(lines)

    @property
    def events(self) -> List[ProgressEvent]:
        """Access raw event list."""
        return self._events.copy()

    @property
    def elapsed_seconds(self) -> float:
        """Total elapsed time in seconds."""
        return time.monotonic() - self._start_time

    # --- Internal ---

    def _emit_line(self, text: str, style: Optional[str] = None) -> None:
        """Print a line to the console."""
        if self._quiet:
            return

        if self._use_color and self._console and style:
            self._console.print(text, style=style)
        else:
            print(text)


# ---------------------------------------------------------------------------
# TaskGraphExecutor integration callback
# ---------------------------------------------------------------------------

class ProgressCallbacks:
    """
    TaskGraphCallbacks-compatible adapter for ProgressReporter.

    Hooks into TaskGraphExecutor to emit progress automatically.

    Usage:
        from ii_skills.shared.progress import ProgressReporter, ProgressCallbacks
        from ii_skills.shared.task_graph import TaskGraphExecutor

        reporter = ProgressReporter(total_phases=3, case_name="Acme LBO")
        callbacks = ProgressCallbacks(reporter)
        executor = TaskGraphExecutor(graph=graph, callbacks=callbacks)
    """

    def __init__(self, reporter: ProgressReporter):
        self.reporter = reporter

    async def on_phase_start(self, phase_id: str, **kwargs) -> None:
        self.reporter.phase_start(phase_id)

    async def on_phase_complete(self, phase_id: str, **kwargs) -> None:
        self.reporter.phase_complete(phase_id, kwargs.get("summary"))

    async def on_task_start(self, task_id: str, **kwargs) -> None:
        self.reporter.message(f"Running: {task_id}")

    async def on_task_complete(self, task_id: str, result: Any = None, **kwargs) -> None:
        if isinstance(result, dict):
            # Extract any notable metrics
            for key in ("irr", "moic", "total_return", "npv"):
                if key in result:
                    val = result[key]
                    if isinstance(val, float):
                        self.reporter.metric(key.upper(), f"{val:.2f}")

    async def on_task_failed(self, task_id: str, error: str = "", **kwargs) -> None:
        self.reporter.error(f"Task failed: {task_id} - {error}")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _format_duration(ms: float) -> str:
    """Format milliseconds to human-readable duration."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    elif ms < 60000:
        return f"{ms / 1000:.1f}s"
    else:
        minutes = int(ms // 60000)
        seconds = int((ms % 60000) // 1000)
        return f"{minutes}m {seconds}s"
