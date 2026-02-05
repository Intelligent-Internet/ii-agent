"""
Unit tests for regression.py — BaselineSnapshot, RegressionRunner, DiffReport.
"""

import json
import pytest
from pathlib import Path

from ii_skills.shared.regression import (
    BaselineSnapshot,
    RegressionRunner,
    DiffReport,
)
from ii_skills.shared.session_capture import SessionRecord


# ---------------------------------------------------------------------------
# BaselineSnapshot
# ---------------------------------------------------------------------------

class TestBaselineSnapshot:

    def test_defaults(self):
        bs = BaselineSnapshot()
        assert bs.baseline_id != ""
        assert bs.created_at != ""
        assert bs.skill_name == ""

    def test_to_dict(self):
        bs = BaselineSnapshot(
            skill_name="ib_toolkit",
            action="quick_lbo",
            params_hash="abc123",
        )
        d = bs.to_dict()
        assert d["skill_name"] == "ib_toolkit"
        assert d["params_hash"] == "abc123"

    def test_roundtrip(self):
        bs = BaselineSnapshot(
            skill_name="test",
            action="act",
            params_hash="hash1",
            tool_sequence_hash="hash2",
            output_checksums={"file.xlsx": "checksum1"},
        )
        d = bs.to_dict()
        restored = BaselineSnapshot.from_dict(d)
        assert restored.skill_name == "test"
        assert restored.output_checksums == {"file.xlsx": "checksum1"}


# ---------------------------------------------------------------------------
# DiffReport
# ---------------------------------------------------------------------------

class TestDiffReport:

    def test_no_regression(self):
        report = DiffReport(
            baseline_id="base-1",
            current_run_id="run-1",
            params_match=True,
            tool_sequence_match=True,
            output_match=True,
            regression_detected=False,
        )
        text = report.format()
        assert "NO" in text  # Regression detected: NO

    def test_regression_detected(self):
        report = DiffReport(
            baseline_id="base-1",
            current_run_id="run-1",
            params_match=True,
            tool_sequence_match=False,
            output_match=False,
            tool_sequence_diff=["[0] tool: web_search -> file_read"],
            output_diffs={"file.xlsx": "changed"},
            regression_detected=True,
        )
        text = report.format()
        assert "YES" in text  # Regression detected: YES
        assert "web_search" in text
        assert "changed" in text

    def test_to_dict(self):
        report = DiffReport(baseline_id="b", current_run_id="r")
        d = report.to_dict()
        assert d["baseline_id"] == "b"
        assert d["current_run_id"] == "r"


# ---------------------------------------------------------------------------
# RegressionRunner
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_baselines_dir(tmp_path):
    return tmp_path / "baselines"


@pytest.fixture
def runner(tmp_baselines_dir):
    return RegressionRunner(baselines_dir=str(tmp_baselines_dir))


def _make_session(run_id="run-1", skill="ib_toolkit", action="quick_lbo", params=None):
    """Helper to create a test SessionRecord."""
    record = SessionRecord(
        run_id=run_id,
        skill_name=skill,
        action=action,
        user_params=params or {"ebitda": 50, "multiple": 8},
    )
    record.add_tool_call("web_search", {"q": "test"}, {"r": []}, 200)
    record.add_tool_call("file_write", {"path": "out.xlsx"}, {"ok": True}, 500)
    record.complete(final_output={"irr": 0.25})
    return record


class TestRegressionRunner:

    def test_save_baseline(self, runner, tmp_baselines_dir):
        session = _make_session()
        baseline = runner.save_baseline(session)

        assert baseline.skill_name == "ib_toolkit"
        assert baseline.action == "quick_lbo"
        assert baseline.params_hash == session.params_hash()
        assert baseline.tool_sequence_hash == session.tool_sequence_hash()

        # Files should exist
        baseline_dir = tmp_baselines_dir / "ib_toolkit" / "quick_lbo"
        assert baseline_dir.exists()
        files = list(baseline_dir.glob("*.json"))
        assert len(files) == 2  # baseline + session

    def test_load_baseline(self, runner):
        session = _make_session()
        saved = runner.save_baseline(session)

        loaded = runner.load_baseline("ib_toolkit", "quick_lbo")
        assert loaded is not None
        assert loaded.baseline_id == saved.baseline_id
        assert loaded.params_hash == saved.params_hash

    def test_load_baseline_by_id(self, runner):
        session = _make_session()
        saved = runner.save_baseline(session)

        loaded = runner.load_baseline("ib_toolkit", "quick_lbo", saved.baseline_id)
        assert loaded is not None
        assert loaded.baseline_id == saved.baseline_id

    def test_load_baseline_not_found(self, runner):
        assert runner.load_baseline("nonexistent", "action") is None

    def test_compare_identical(self, runner):
        session = _make_session()
        baseline = runner.save_baseline(session)

        # Same session should match
        report = runner.compare(session, baseline)
        assert report.params_match is True
        assert report.tool_sequence_match is True
        assert report.regression_detected is False

    def test_compare_different_tool_sequence(self, runner):
        session1 = _make_session(run_id="r1")
        baseline = runner.save_baseline(session1)

        # Create session with different tool calls
        session2 = SessionRecord(
            run_id="r2",
            skill_name="ib_toolkit",
            action="quick_lbo",
            user_params={"ebitda": 50, "multiple": 8},
        )
        session2.add_tool_call("different_tool", {"q": "test"}, {"r": []}, 200)
        session2.complete(final_output={"irr": 0.30})

        report = runner.compare(session2, baseline)
        assert report.tool_sequence_match is False
        assert report.regression_detected is True
        assert len(report.tool_sequence_diff) > 0

    def test_compare_different_params(self, runner):
        session1 = _make_session(run_id="r1")
        baseline = runner.save_baseline(session1)

        # Create session with different params
        session2 = _make_session(run_id="r2", params={"ebitda": 100, "multiple": 10})
        report = runner.compare(session2, baseline)
        assert report.params_match is False

    def test_compare_output_checksums(self, runner, tmp_path):
        # Session with output checksums
        session1 = SessionRecord(
            run_id="r1", skill_name="ib_toolkit", action="quick_lbo",
            user_params={"ebitda": 50},
        )
        session1.add_tool_call("t1", {}, {}, 100)
        # Create a file for checksum
        f1 = tmp_path / "out1.xlsx"
        f1.write_bytes(b"content1")
        session1.complete(
            final_output={"ok": True},
            output_files={"out.xlsx": str(f1)},
        )
        baseline = runner.save_baseline(session1)

        # Session with different output
        session2 = SessionRecord(
            run_id="r2", skill_name="ib_toolkit", action="quick_lbo",
            user_params={"ebitda": 50},
        )
        session2.add_tool_call("t1", {}, {}, 100)
        f2 = tmp_path / "out2.xlsx"
        f2.write_bytes(b"different content")
        session2.complete(
            final_output={"ok": True},
            output_files={"out.xlsx": str(f2)},
        )

        report = runner.compare(session2, baseline)
        assert report.output_match is False
        assert report.output_diffs["out.xlsx"] == "changed"
        assert report.regression_detected is True

    def test_list_baselines(self, runner):
        _make_and_save = lambda skill, action: runner.save_baseline(
            _make_session(skill=skill, action=action)
        )
        _make_and_save("ib_toolkit", "quick_lbo")
        _make_and_save("ib_toolkit", "full_lbo")
        _make_and_save("networth", "run")

        all_baselines = runner.list_baselines()
        assert len(all_baselines) == 3

        ib_baselines = runner.list_baselines(skill_name="ib_toolkit")
        assert len(ib_baselines) == 2

    def test_run_regression_suite(self, runner):
        session1 = _make_session(run_id="r1")
        runner.save_baseline(session1)

        # Run same session again
        session2 = _make_session(run_id="r2")

        reports = runner.run_regression_suite([session2])
        assert len(reports) == 1
        assert reports[0].regression_detected is False

    def test_run_regression_suite_no_baseline(self, runner):
        session = _make_session(skill="unknown_skill", action="unknown_action")
        reports = runner.run_regression_suite([session])
        assert len(reports) == 0  # No baseline to compare against
