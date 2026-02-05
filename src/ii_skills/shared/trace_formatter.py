"""
Operator UX — Human-readable formatting for telemetry, traces, and cost reports.

Consumes RunRecord, ToolMetrics, SubAgentTracer, and BudgetEnforcer data
to produce compact, scannable text summaries. Pure stdlib — no external deps.

Usage:
    from ii_skills.shared.trace_formatter import TraceFormatter, CostReport

    formatter = TraceFormatter()
    print(formatter.format_run_summary(run_record))
    print(formatter.format_tool_table(tool_metrics.get_summary()))
    print(CostReport.from_run_record(record, llm_metrics).format_cost_breakdown())
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_duration(ms: float) -> str:
    """Format milliseconds into a human-readable duration.

    Examples:
        123.4  -> "123ms"
        1234.5 -> "1.23s"
        65432  -> "1m 5s"
        3661000 -> "1h 1m"
    """
    if ms < 0:
        return "0ms"
    if ms < 1000:
        return f"{ms:.0f}ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours}h {remaining_minutes}m"


def format_bytes(n: int) -> str:
    """Format byte count into human-readable size.

    Examples:
        512       -> "512 B"
        1258291   -> "1.2 MB"
        5368709120 -> "5.0 GB"
    """
    if n < 0:
        return "0 B"
    if n < 1024:
        return f"{n} B"
    units = ["KB", "MB", "GB", "TB"]
    value = float(n)
    for unit in units:
        value /= 1024
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} TB"


def format_cost(credits: float) -> str:
    """Format a dollar cost value.

    Examples:
        0.034  -> "$0.034"
        1.5    -> "$1.50"
        123.456 -> "$123.46"
    """
    if credits < 0.01:
        return f"${credits:.4f}"
    if credits < 1.0:
        return f"${credits:.3f}"
    return f"${credits:.2f}"


def format_percent(value: float, total: float) -> str:
    """Format a fraction as a percentage.

    Examples:
        (3, 10) -> "30.0%"
        (0, 0)  -> "0.0%"
    """
    if total == 0:
        return "0.0%"
    return f"{(value / total) * 100:.1f}%"


def _pad_right(text: str, width: int) -> str:
    """Right-pad text to width."""
    return text + " " * max(0, width - len(text))


def _pad_left(text: str, width: int) -> str:
    """Left-pad text to width."""
    return " " * max(0, width - len(text)) + text


# ---------------------------------------------------------------------------
# TraceFormatter
# ---------------------------------------------------------------------------

class TraceFormatter:
    """Formats telemetry data into human-readable text.

    Consumes:
    - RunRecord (from event_telemetry.py)
    - Dict[str, ToolMetricsSummary] (from tool_metrics.py)
    - List[TelemetryEvent] (from event_telemetry.py)
    - List[SubAgentRecord] (from subagent_tracing.py)
    """

    @staticmethod
    def format_run_summary(run_record) -> str:
        """Format a compact 5-line run summary.

        Args:
            run_record: A RunRecord instance or dict with matching keys.

        Returns:
            Multi-line string summary.
        """
        if hasattr(run_record, "to_dict"):
            r = run_record.to_dict()
        elif isinstance(run_record, dict):
            r = run_record
        else:
            return f"[TraceFormatter] Unsupported type: {type(run_record)}"

        status = r.get("status", "unknown")
        run_id = r.get("run_id", "?")
        run_type = r.get("run_type", "?")
        duration_ms = r.get("duration_ms") or 0
        metrics = r.get("metrics", {})

        completed = metrics.get("completed_tasks", 0)
        failed = metrics.get("failed_tasks", 0)
        total = metrics.get("total_tasks", 0)
        events_count = len(r.get("events", []))

        status_icon = {
            "completed": "[OK]",
            "failed": "[FAIL]",
            "cancelled": "[CANCEL]",
            "running": "[RUN]",
        }.get(status, f"[{status.upper()}]")

        lines = [
            f"Run: {run_id[:12]}  {status_icon} {status}",
            f"Type: {run_type}  Duration: {format_duration(duration_ms)}",
            f"Tasks: {completed}/{total} completed, {failed} failed",
            f"Events: {events_count}",
        ]

        error = r.get("error")
        if error:
            lines.append(f"Error: {error[:120]}")

        return "\n".join(lines)

    @staticmethod
    def format_tool_table(metrics: Dict[str, Any]) -> str:
        """Format tool metrics as an aligned ASCII table.

        Args:
            metrics: Dict mapping tool_name to ToolMetricsSummary (or dict).

        Returns:
            ASCII table string.
        """
        if not metrics:
            return "No tool metrics recorded."

        # Normalize to dicts
        rows = []
        for name, summary in metrics.items():
            s = summary.to_dict() if hasattr(summary, "to_dict") else summary
            rows.append({
                "tool": name,
                "calls": s.get("total_calls", 0),
                "avg": format_duration(s.get("avg_duration_ms", 0)),
                "p95": format_duration(s.get("p95_duration_ms", 0)),
                "errors": s.get("failed_calls", 0),
                "rate": format_percent(
                    s.get("successful_calls", 0),
                    s.get("total_calls", 1),
                ),
            })

        # Column widths
        headers = ["Tool", "Calls", "Avg", "P95", "Errors", "Rate"]
        col_widths = [len(h) for h in headers]
        for row in rows:
            col_widths[0] = max(col_widths[0], len(row["tool"]))
            col_widths[1] = max(col_widths[1], len(str(row["calls"])))
            col_widths[2] = max(col_widths[2], len(row["avg"]))
            col_widths[3] = max(col_widths[3], len(row["p95"]))
            col_widths[4] = max(col_widths[4], len(str(row["errors"])))
            col_widths[5] = max(col_widths[5], len(row["rate"]))

        # Build table
        sep = "  "
        header_line = sep.join(
            _pad_right(h, col_widths[i]) for i, h in enumerate(headers)
        )
        divider = sep.join("-" * w for w in col_widths)

        lines = [header_line, divider]
        for row in rows:
            line = sep.join([
                _pad_right(row["tool"], col_widths[0]),
                _pad_left(str(row["calls"]), col_widths[1]),
                _pad_left(row["avg"], col_widths[2]),
                _pad_left(row["p95"], col_widths[3]),
                _pad_left(str(row["errors"]), col_widths[4]),
                _pad_left(row["rate"], col_widths[5]),
            ])
            lines.append(line)

        return "\n".join(lines)

    @staticmethod
    def format_event_timeline(events: List[Any]) -> str:
        """Format events as a chronological timeline.

        Args:
            events: List of TelemetryEvent instances or dicts.

        Returns:
            Timeline string with relative timestamps.
        """
        if not events:
            return "No events recorded."

        # Normalize
        normalized = []
        for e in events:
            if hasattr(e, "to_dict"):
                normalized.append(e.to_dict())
            elif isinstance(e, dict):
                normalized.append(e)

        if not normalized:
            return "No events recorded."

        # Parse first timestamp as base
        first_ts = normalized[0].get("timestamp", "")
        try:
            base_time = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            base_time = None

        lines = []
        for evt in normalized:
            event_type = evt.get("event_type", "?")
            ts_str = evt.get("timestamp", "")
            data = evt.get("data", {})

            # Compute offset
            offset_str = "+?.?s"
            if base_time:
                try:
                    evt_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    offset_ms = (evt_time - base_time).total_seconds() * 1000
                    offset_str = f"+{format_duration(offset_ms)}"
                except (ValueError, AttributeError):
                    pass

            # Build detail suffix
            detail = ""
            if "phase" in data:
                detail = f": {data['phase']}"
            elif "task_id" in data:
                detail = f": {data['task_id']}"
            elif "error" in data:
                detail = f" - {str(data['error'])[:60]}"
            elif "duration_ms" in data:
                detail = f" ({format_duration(data['duration_ms'])})"

            lines.append(f"  {_pad_right(offset_str, 10)} {event_type}{detail}")

        return "\n".join(lines)

    @staticmethod
    def format_trace_tree(records: List[Any]) -> str:
        """Format sub-agent records as an ASCII tree.

        Args:
            records: List of SubAgentRecord instances or dicts.

        Returns:
            ASCII tree string.
        """
        if not records:
            return "No sub-agent traces."

        lines = []
        total = len(records)
        for i, rec in enumerate(records):
            r = rec.to_dict() if hasattr(rec, "to_dict") else rec if isinstance(rec, dict) else {}

            agent_type = r.get("agent_type", "?")
            task_desc = r.get("task_description", "")
            status = r.get("status", "unknown")
            duration_ms = r.get("duration_ms")
            error = r.get("error_message")

            # Status icon
            status_str = status.value if hasattr(status, "value") else str(status)
            icon = {"success": "OK", "failed": "FAIL", "running": "...", "cancelled": "X"}.get(
                status_str.lower(), status_str.upper()
            )

            # Duration
            dur_str = f" ({format_duration(duration_ms)})" if duration_ms else ""

            # Tree connector
            is_last = i == total - 1
            connector = "+-" if is_last else "|-"

            label = f"{agent_type}: {task_desc[:50]}" if task_desc else agent_type
            line = f"  {connector} {label}{dur_str} [{icon}]"

            if error:
                continuation = "   " if is_last else "|  "
                line += f"\n  {continuation}   Error: {error[:80]}"

            lines.append(line)

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CostReport
# ---------------------------------------------------------------------------

@dataclass
class LLMUsage:
    """Aggregated LLM token usage for cost reporting."""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    cost: float = 0.0


@dataclass
class CostReport:
    """Aggregated cost report for a run.

    Built from RunRecord + optional LLM metrics.
    """
    total_cost: float = 0.0
    llm_usage: List[LLMUsage] = field(default_factory=list)
    tool_calls: Dict[str, int] = field(default_factory=dict)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cache_tokens: int = 0

    @classmethod
    def from_run_record(
        cls,
        record,
        llm_metrics: Optional[List[Dict[str, Any]]] = None,
    ) -> "CostReport":
        """Build a CostReport from a RunRecord and optional LLM metrics.

        Args:
            record: RunRecord instance or dict.
            llm_metrics: Optional list of per-model usage dicts with keys:
                model, prompt_tokens, completion_tokens, cache_read_tokens, cost

        Returns:
            CostReport instance.
        """
        report = cls()

        if llm_metrics:
            for m in llm_metrics:
                usage = LLMUsage(
                    model=m.get("model", "unknown"),
                    prompt_tokens=m.get("prompt_tokens", 0),
                    completion_tokens=m.get("completion_tokens", 0),
                    cache_read_tokens=m.get("cache_read_tokens", 0),
                    cost=m.get("cost", 0.0),
                )
                report.llm_usage.append(usage)
                report.total_cost += usage.cost
                report.total_prompt_tokens += usage.prompt_tokens
                report.total_completion_tokens += usage.completion_tokens
                report.total_cache_tokens += usage.cache_read_tokens

        # Extract tool call counts from record events
        r = record.to_dict() if hasattr(record, "to_dict") else record if isinstance(record, dict) else {}
        for evt in r.get("events", []):
            if evt.get("event_type") in ("tool_completed", "tool_call"):
                tool_name = evt.get("data", {}).get("tool_name", "unknown")
                report.tool_calls[tool_name] = report.tool_calls.get(tool_name, 0) + 1

        return report

    def format_cost_breakdown(self) -> str:
        """Format a human-readable cost breakdown.

        Returns:
            Multi-line cost report string.
        """
        lines = []

        # Model costs
        if self.llm_usage:
            lines.append("Model Costs:")
            for usage in sorted(self.llm_usage, key=lambda u: u.cost, reverse=True):
                pct = format_percent(usage.cost, self.total_cost) if self.total_cost > 0 else "0.0%"
                lines.append(f"  {_pad_right(usage.model, 24)} {format_cost(usage.cost)}  ({pct})")

        # Token summary
        total_tokens = self.total_prompt_tokens + self.total_completion_tokens
        if total_tokens > 0:
            cache_total = self.total_cache_tokens + (self.total_prompt_tokens - self.total_cache_tokens)
            cache_rate = format_percent(self.total_cache_tokens, cache_total) if cache_total > 0 else "0.0%"
            lines.append("Token Summary:")
            lines.append(
                f"  Prompt: {self.total_prompt_tokens:,}  "
                f"Completion: {self.total_completion_tokens:,}  "
                f"Cache: {self.total_cache_tokens:,} ({cache_rate} hit rate)"
            )

        # Tool calls
        if self.tool_calls:
            lines.append("Tool Calls:")
            for name, count in sorted(self.tool_calls.items()):
                lines.append(f"  {_pad_right(name, 24)} {count} calls")

        # Total
        lines.append(f"Total: {format_cost(self.total_cost)}")

        return "\n".join(lines)

    def format_budget_utilization(self, enforcer) -> str:
        """Format budget utilization from a BudgetEnforcer.

        Args:
            enforcer: BudgetEnforcer instance.

        Returns:
            Single-line budget utilization string.
        """
        status = enforcer.get_status()
        budget = enforcer.budget

        parts = []

        tasks_done = status.get("tasks_completed", 0) + status.get("tasks_failed", 0)
        if budget.max_tasks is not None:
            parts.append(f"Tasks: {tasks_done}/{budget.max_tasks} ({format_percent(tasks_done, budget.max_tasks)})")
        else:
            parts.append(f"Tasks: {tasks_done}")

        elapsed = status.get("elapsed_minutes", 0)
        if budget.max_duration_minutes is not None:
            parts.append(
                f"Duration: {elapsed:.1f}/{budget.max_duration_minutes} min "
                f"({format_percent(elapsed, budget.max_duration_minutes)})"
            )
        else:
            parts.append(f"Duration: {elapsed:.1f} min")

        api_calls = status.get("api_calls", 0)
        if budget.max_api_calls is not None:
            parts.append(
                f"API: {api_calls}/{budget.max_api_calls} "
                f"({format_percent(api_calls, budget.max_api_calls)})"
            )
        else:
            parts.append(f"API: {api_calls}")

        return "  ".join(parts)
