"""
Unit tests for trace_formatter.py — TraceFormatter, CostReport, format helpers.
"""

import pytest

from ii_skills.shared.trace_formatter import (
    TraceFormatter,
    CostReport,
    LLMUsage,
    format_duration,
    format_bytes,
    format_cost,
    format_percent,
)


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------

class TestFormatDuration:

    def test_milliseconds(self):
        assert format_duration(123) == "123ms"

    def test_milliseconds_fractional(self):
        assert format_duration(45.7) == "46ms"

    def test_seconds(self):
        assert format_duration(1234.5) == "1.23s"

    def test_minutes(self):
        assert format_duration(65000) == "1m 5s"

    def test_hours(self):
        assert format_duration(3661000) == "1h 1m"

    def test_zero(self):
        assert format_duration(0) == "0ms"

    def test_negative(self):
        assert format_duration(-100) == "0ms"

    def test_under_one_second(self):
        assert format_duration(999) == "999ms"

    def test_exactly_one_second(self):
        assert format_duration(1000) == "1.00s"

    def test_exactly_one_minute(self):
        assert format_duration(60000) == "1m 0s"


# ---------------------------------------------------------------------------
# format_bytes
# ---------------------------------------------------------------------------

class TestFormatBytes:

    def test_bytes(self):
        assert format_bytes(512) == "512 B"

    def test_kilobytes(self):
        assert format_bytes(2048) == "2.0 KB"

    def test_megabytes(self):
        assert format_bytes(1258291) == "1.2 MB"

    def test_gigabytes(self):
        result = format_bytes(5368709120)
        assert "5.0 GB" == result

    def test_zero(self):
        assert format_bytes(0) == "0 B"

    def test_negative(self):
        assert format_bytes(-1) == "0 B"


# ---------------------------------------------------------------------------
# format_cost
# ---------------------------------------------------------------------------

class TestFormatCost:

    def test_small_cost(self):
        assert format_cost(0.0034) == "$0.0034"

    def test_medium_cost(self):
        assert format_cost(0.034) == "$0.034"

    def test_large_cost(self):
        assert format_cost(1.5) == "$1.50"

    def test_very_large_cost(self):
        assert format_cost(123.456) == "$123.46"


# ---------------------------------------------------------------------------
# format_percent
# ---------------------------------------------------------------------------

class TestFormatPercent:

    def test_normal(self):
        assert format_percent(3, 10) == "30.0%"

    def test_zero_total(self):
        assert format_percent(3, 0) == "0.0%"

    def test_hundred_percent(self):
        assert format_percent(10, 10) == "100.0%"

    def test_zero_value(self):
        assert format_percent(0, 10) == "0.0%"


# ---------------------------------------------------------------------------
# TraceFormatter.format_run_summary
# ---------------------------------------------------------------------------

class TestFormatRunSummary:

    def test_with_dict(self):
        record = {
            "run_id": "abc123-def456",
            "run_type": "deal_analysis",
            "status": "completed",
            "duration_ms": 5432.1,
            "metrics": {
                "completed_tasks": 8,
                "failed_tasks": 1,
                "total_tasks": 9,
            },
            "events": [{"type": "a"}, {"type": "b"}],
        }
        result = TraceFormatter.format_run_summary(record)
        assert "abc123-def4" in result
        assert "[OK]" in result
        assert "completed" in result
        assert "deal_analysis" in result
        assert "8/9 completed" in result
        assert "1 failed" in result
        assert "Events: 2" in result

    def test_with_error(self):
        record = {
            "run_id": "err-123",
            "run_type": "test",
            "status": "failed",
            "duration_ms": 100,
            "metrics": {},
            "events": [],
            "error": "Something went wrong",
        }
        result = TraceFormatter.format_run_summary(record)
        assert "[FAIL]" in result
        assert "Something went wrong" in result

    def test_cancelled_status(self):
        record = {
            "run_id": "cancel-1",
            "run_type": "test",
            "status": "cancelled",
            "duration_ms": 0,
            "metrics": {},
            "events": [],
        }
        result = TraceFormatter.format_run_summary(record)
        assert "[CANCEL]" in result


# ---------------------------------------------------------------------------
# TraceFormatter.format_tool_table
# ---------------------------------------------------------------------------

class TestFormatToolTable:

    def test_empty(self):
        assert "No tool metrics" in TraceFormatter.format_tool_table({})

    def test_with_metrics(self):
        metrics = {
            "web_search": {
                "total_calls": 10,
                "successful_calls": 9,
                "failed_calls": 1,
                "avg_duration_ms": 234.5,
                "p95_duration_ms": 890.2,
            },
            "file_read": {
                "total_calls": 5,
                "successful_calls": 5,
                "failed_calls": 0,
                "avg_duration_ms": 12.3,
                "p95_duration_ms": 45.6,
            },
        }
        result = TraceFormatter.format_tool_table(metrics)
        assert "Tool" in result
        assert "Calls" in result
        assert "web_search" in result
        assert "file_read" in result
        lines = result.strip().split("\n")
        assert len(lines) == 4  # header + divider + 2 rows


# ---------------------------------------------------------------------------
# TraceFormatter.format_event_timeline
# ---------------------------------------------------------------------------

class TestFormatEventTimeline:

    def test_empty(self):
        assert "No events" in TraceFormatter.format_event_timeline([])

    def test_with_events(self):
        events = [
            {
                "event_type": "workspace_created",
                "timestamp": "2026-01-15T10:00:00+00:00",
                "data": {},
            },
            {
                "event_type": "task_started",
                "timestamp": "2026-01-15T10:00:01.200000+00:00",
                "data": {"task_id": "analyze"},
            },
            {
                "event_type": "task_completed",
                "timestamp": "2026-01-15T10:00:03.500000+00:00",
                "data": {"task_id": "analyze", "duration_ms": 2300},
            },
        ]
        result = TraceFormatter.format_event_timeline(events)
        assert "workspace_created" in result
        assert "task_started" in result
        assert "analyze" in result
        assert "+0ms" in result  # First event


# ---------------------------------------------------------------------------
# TraceFormatter.format_trace_tree
# ---------------------------------------------------------------------------

class TestFormatTraceTree:

    def test_empty(self):
        assert "No sub-agent" in TraceFormatter.format_trace_tree([])

    def test_with_records(self):
        records = [
            {
                "agent_type": "research",
                "task_description": "Find company data",
                "status": "success",
                "duration_ms": 12100,
                "error_message": None,
            },
            {
                "agent_type": "analysis",
                "task_description": "Run LBO model",
                "status": "failed",
                "duration_ms": 33100,
                "error_message": "RuntimeError: bad input",
            },
        ]
        result = TraceFormatter.format_trace_tree(records)
        assert "research" in result
        assert "analysis" in result
        assert "[OK]" in result
        assert "[FAIL]" in result
        assert "RuntimeError" in result


# ---------------------------------------------------------------------------
# CostReport
# ---------------------------------------------------------------------------

class TestCostReport:

    def test_empty_report(self):
        report = CostReport()
        text = report.format_cost_breakdown()
        assert "Total: $0.0000" in text

    def test_from_run_record_with_llm_metrics(self):
        record = {
            "events": [
                {"event_type": "tool_completed", "data": {"tool_name": "web_search"}},
                {"event_type": "tool_completed", "data": {"tool_name": "web_search"}},
                {"event_type": "tool_completed", "data": {"tool_name": "file_read"}},
            ]
        }
        llm_metrics = [
            {
                "model": "claude-opus-4-5",
                "prompt_tokens": 10000,
                "completion_tokens": 2000,
                "cache_read_tokens": 6000,
                "cost": 0.45,
            },
            {
                "model": "claude-sonnet-4-5",
                "prompt_tokens": 2000,
                "completion_tokens": 500,
                "cache_read_tokens": 1500,
                "cost": 0.066,
            },
        ]
        report = CostReport.from_run_record(record, llm_metrics)

        assert report.total_cost == pytest.approx(0.516)
        assert report.total_prompt_tokens == 12000
        assert report.total_completion_tokens == 2500
        assert report.total_cache_tokens == 7500
        assert report.tool_calls["web_search"] == 2
        assert report.tool_calls["file_read"] == 1

        text = report.format_cost_breakdown()
        assert "claude-opus-4-5" in text
        assert "claude-sonnet-4-5" in text
        assert "web_search" in text
        assert "Token Summary:" in text

    def test_format_budget_utilization(self):
        from ii_skills.shared.run_budgets import RunBudgetConfig, BudgetEnforcer

        budget = RunBudgetConfig(
            max_tasks=100,
            max_duration_minutes=30,
            max_api_calls=500,
        )
        enforcer = BudgetEnforcer(budget)
        enforcer.start()
        enforcer.tasks_completed = 15
        enforcer.api_calls = 45

        report = CostReport()
        text = report.format_budget_utilization(enforcer)
        assert "Tasks: 15/100" in text
        assert "API: 45/500" in text
