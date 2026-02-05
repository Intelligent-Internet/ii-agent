"""
Unit tests for progress.py — ProgressReporter, ProgressCallbacks, ProgressEvent.
"""

import time
import pytest

from ii_skills.shared.progress import (
    ProgressReporter,
    ProgressCallbacks,
    ProgressEvent,
    _format_duration,
)


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------

class TestFormatDuration:

    def test_milliseconds(self):
        assert _format_duration(500) == "500ms"

    def test_seconds(self):
        assert _format_duration(2500) == "2.5s"

    def test_minutes(self):
        assert _format_duration(125000) == "2m 5s"

    def test_zero(self):
        assert _format_duration(0) == "0ms"


# ---------------------------------------------------------------------------
# ProgressEvent
# ---------------------------------------------------------------------------

class TestProgressEvent:

    def test_creation(self):
        ev = ProgressEvent(event_type="metric", label="IRR", detail="22.4%")
        assert ev.event_type == "metric"
        assert ev.label == "IRR"
        assert ev.detail == "22.4%"
        assert ev.timestamp != ""

    def test_auto_timestamp(self):
        ev = ProgressEvent(event_type="test", label="test")
        assert len(ev.timestamp) == 8  # HH:MM:SS


# ---------------------------------------------------------------------------
# ProgressReporter
# ---------------------------------------------------------------------------

class TestProgressReporter:

    def test_creation(self):
        reporter = ProgressReporter(total_phases=5, case_name="Acme LBO")
        assert reporter.total_phases == 5
        assert reporter.case_name == "Acme LBO"

    def test_case_start(self):
        reporter = ProgressReporter(quiet=True)
        reporter.case_start("Test Case", total_phases=3)
        assert reporter.case_name == "Test Case"
        assert reporter.total_phases == 3
        assert len(reporter.events) == 1
        assert reporter.events[0].event_type == "case_start"

    def test_phase_lifecycle(self):
        reporter = ProgressReporter(total_phases=3, quiet=True)
        reporter.phase_start("Build Model")
        reporter.phase_complete("Build Model", {"irr": 22.4})

        assert len(reporter.events) == 2
        assert reporter.events[0].event_type == "phase_start"
        assert reporter.events[1].event_type == "phase_complete"
        assert "22.4" in reporter.events[1].detail

    def test_phase_numbering(self):
        reporter = ProgressReporter(total_phases=3, quiet=True)
        reporter.phase_start("Phase A")
        reporter.phase_start("Phase B")
        reporter.phase_start("Phase C")

        assert reporter._current_phase == 3
        assert "[1/3]" in reporter.events[0].detail
        assert "[2/3]" in reporter.events[1].detail
        assert "[3/3]" in reporter.events[2].detail

    def test_metric(self):
        reporter = ProgressReporter(quiet=True)
        reporter.metric("MOIC", "2.5x")
        assert len(reporter.events) == 1
        assert reporter.events[0].event_type == "metric"
        assert reporter.events[0].label == "MOIC"
        assert reporter.events[0].detail == "2.5x"

    def test_file_created(self):
        reporter = ProgressReporter(quiet=True)
        reporter.file_created("/output/cases/test/model.xlsx", "LBO Model")
        assert reporter.events[0].event_type == "file"
        assert reporter.events[0].detail == "/output/cases/test/model.xlsx"

    def test_message(self):
        reporter = ProgressReporter(quiet=True)
        reporter.message("Processing data...")
        assert reporter.events[0].event_type == "message"
        assert reporter.events[0].label == "Processing data..."

    def test_error(self):
        reporter = ProgressReporter(quiet=True)
        reporter.error("Connection failed")
        assert reporter.events[0].event_type == "error"

    def test_case_complete(self):
        reporter = ProgressReporter(case_name="Test", quiet=True)
        reporter.case_complete({"moic": "2.5x", "irr": "22%"})
        ev = reporter.events[0]
        assert ev.event_type == "case_complete"
        assert ev.elapsed_ms > 0

    def test_elapsed_seconds(self):
        reporter = ProgressReporter(quiet=True)
        time.sleep(0.01)
        assert reporter.elapsed_seconds >= 0.01

    def test_get_timeline(self):
        reporter = ProgressReporter(total_phases=2, case_name="Timeline Test", quiet=True)
        reporter.case_start()
        reporter.phase_start("Phase 1")
        reporter.metric("Revenue Y5", "$142M")
        reporter.phase_complete("Phase 1")
        reporter.phase_start("Phase 2")
        reporter.file_created("/path/to/model.xlsx", "LBO Model")
        reporter.phase_complete("Phase 2")
        reporter.case_complete()

        timeline = reporter.get_timeline()
        assert "Progress Timeline" in timeline
        assert "[START]" in timeline
        assert "[OK]" in timeline
        assert "[DONE]" in timeline
        assert "[FILE]" in timeline

    def test_get_timeline_empty(self):
        reporter = ProgressReporter(quiet=True)
        timeline = reporter.get_timeline()
        assert "No progress events" in timeline

    def test_full_workflow(self):
        """End-to-end workflow test."""
        reporter = ProgressReporter(total_phases=3, case_name="Acme LBO", quiet=True)

        reporter.case_start()
        reporter.phase_start("Assumptions & Sources")
        reporter.metric("Entry EV", "$160M")
        reporter.metric("Equity Check", "$55.2M")
        reporter.phase_complete("Assumptions & Sources", {"entry_ev": 160.0})

        reporter.phase_start("Operating Model")
        reporter.metric("Revenue Y5", "$131.1M")
        reporter.metric("EBITDA Y5", "$28.8M")
        reporter.phase_complete("Operating Model", {"ebitda_y5": 28.8})

        reporter.phase_start("Returns & Sensitivity")
        reporter.metric("MOIC", "2.45x")
        reporter.metric("IRR", "19.6%")
        reporter.file_created("/output/cases/acme/02_models/lbo.xlsx", "LBO Model")
        reporter.phase_complete("Returns & Sensitivity")

        reporter.case_complete({"moic": "2.45x", "irr": "19.6%"})

        assert len(reporter.events) == 15
        timeline = reporter.get_timeline()
        assert "Acme LBO" in timeline or "case_start" in timeline.lower()


# ---------------------------------------------------------------------------
# ProgressCallbacks (TaskGraphExecutor integration)
# ---------------------------------------------------------------------------

class TestProgressCallbacks:

    @pytest.mark.asyncio
    async def test_on_phase_start(self):
        reporter = ProgressReporter(total_phases=2, quiet=True)
        callbacks = ProgressCallbacks(reporter)

        await callbacks.on_phase_start("build_model")
        assert len(reporter.events) == 1
        assert reporter.events[0].label == "build_model"

    @pytest.mark.asyncio
    async def test_on_phase_complete(self):
        reporter = ProgressReporter(quiet=True)
        callbacks = ProgressCallbacks(reporter)

        reporter.phase_start("test")
        await callbacks.on_phase_complete("test", summary={"irr": 0.22})
        assert len(reporter.events) == 2

    @pytest.mark.asyncio
    async def test_on_task_complete_extracts_metrics(self):
        reporter = ProgressReporter(quiet=True)
        callbacks = ProgressCallbacks(reporter)

        await callbacks.on_task_complete("calc_returns", result={"irr": 0.22, "moic": 2.5})
        # Should extract IRR and MOIC as metric events
        metric_events = [e for e in reporter.events if e.event_type == "metric"]
        assert len(metric_events) == 2

    @pytest.mark.asyncio
    async def test_on_task_failed(self):
        reporter = ProgressReporter(quiet=True)
        callbacks = ProgressCallbacks(reporter)

        await callbacks.on_task_failed("broken_task", error="Something went wrong")
        assert len(reporter.events) == 1
        assert reporter.events[0].event_type == "error"
        assert "broken_task" in reporter.events[0].label
