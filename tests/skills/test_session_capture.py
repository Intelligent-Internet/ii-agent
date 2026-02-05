"""
Unit tests for session_capture.py — SessionRecord, CapturedToolCall.
"""

import json
import pytest
from pathlib import Path

from ii_skills.shared.session_capture import SessionRecord, CapturedToolCall


# ---------------------------------------------------------------------------
# CapturedToolCall
# ---------------------------------------------------------------------------

class TestCapturedToolCall:

    def test_creation(self):
        call = CapturedToolCall(
            sequence_index=0,
            tool_name="skill_ib_toolkit",
            tool_input={"action": "analyze"},
            tool_output={"result": "ok"},
            duration_ms=123.4,
        )
        assert call.sequence_index == 0
        assert call.tool_name == "skill_ib_toolkit"
        assert call.is_error is False

    def test_to_dict(self):
        call = CapturedToolCall(
            sequence_index=1,
            tool_name="test",
            tool_input={"a": 1},
            tool_output={"b": 2},
            duration_ms=50,
            is_error=True,
        )
        d = call.to_dict()
        assert d["sequence_index"] == 1
        assert d["is_error"] is True
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# SessionRecord
# ---------------------------------------------------------------------------

class TestSessionRecord:

    def test_creation(self):
        record = SessionRecord(
            run_id="abc-123",
            skill_name="ib_toolkit",
            action="quick_lbo_analysis",
            user_params={"ebitda": 50},
        )
        assert record.run_id == "abc-123"
        assert record.skill_name == "ib_toolkit"
        assert record.started_at != ""
        assert record.completed_at is None
        assert record.tool_calls == []

    def test_add_tool_call(self):
        record = SessionRecord(run_id="r1", skill_name="s1", action="a1")
        call = record.add_tool_call(
            tool_name="web_search",
            tool_input={"query": "test"},
            tool_output={"results": []},
            duration_ms=200,
        )
        assert call.sequence_index == 0
        assert len(record.tool_calls) == 1

        call2 = record.add_tool_call(
            tool_name="file_read",
            tool_input={"path": "/test"},
            tool_output={"content": "..."},
            duration_ms=50,
        )
        assert call2.sequence_index == 1
        assert len(record.tool_calls) == 2

    def test_complete(self):
        record = SessionRecord(run_id="r1", skill_name="s1", action="a1")
        record.complete(final_output={"irr": 0.25})
        assert record.completed_at is not None
        assert record.final_output == {"irr": 0.25}

    def test_complete_with_output_files(self, tmp_path):
        record = SessionRecord(run_id="r1", skill_name="s1", action="a1")

        # Create a test file
        test_file = tmp_path / "output.xlsx"
        test_file.write_bytes(b"fake excel data")

        record.complete(
            final_output={"output_path": str(test_file)},
            output_files={"output.xlsx": str(test_file)},
        )

        assert "output.xlsx" in record.output_checksums
        assert len(record.output_checksums["output.xlsx"]) == 64  # SHA-256 hex

    def test_tool_sequence_hash_deterministic(self):
        record1 = SessionRecord(run_id="r1", skill_name="s1", action="a1")
        record1.add_tool_call("t1", {"a": 1}, {"b": 2}, 100)
        record1.add_tool_call("t2", {"c": 3}, {"d": 4}, 200)

        record2 = SessionRecord(run_id="r2", skill_name="s1", action="a1")
        record2.add_tool_call("t1", {"a": 1}, {"b": 2}, 150)  # Different duration
        record2.add_tool_call("t2", {"c": 3}, {"d": 4}, 250)

        # Same tool names + inputs -> same hash (duration ignored)
        assert record1.tool_sequence_hash() == record2.tool_sequence_hash()

    def test_tool_sequence_hash_differs_on_input_change(self):
        record1 = SessionRecord(run_id="r1", skill_name="s1", action="a1")
        record1.add_tool_call("t1", {"a": 1}, {}, 100)

        record2 = SessionRecord(run_id="r2", skill_name="s1", action="a1")
        record2.add_tool_call("t1", {"a": 2}, {}, 100)  # Different input

        assert record1.tool_sequence_hash() != record2.tool_sequence_hash()

    def test_params_hash_deterministic(self):
        record1 = SessionRecord(
            run_id="r1", skill_name="s1", action="a1",
            user_params={"ebitda": 50, "multiple": 8},
        )
        record2 = SessionRecord(
            run_id="r2", skill_name="s1", action="a1",
            user_params={"multiple": 8, "ebitda": 50},  # Different order
        )
        assert record1.params_hash() == record2.params_hash()

    def test_to_dict(self):
        record = SessionRecord(
            run_id="r1", skill_name="s1", action="a1",
            user_params={"x": 1},
        )
        record.add_tool_call("t1", {"a": 1}, {"b": 2}, 100)
        record.complete(final_output={"result": "ok"})

        d = record.to_dict()
        assert d["run_id"] == "r1"
        assert d["skill_name"] == "s1"
        assert len(d["tool_calls"]) == 1
        assert "tool_sequence_hash" in d
        assert "params_hash" in d

    def test_save_and_load(self, tmp_path):
        record = SessionRecord(
            run_id="save-test",
            skill_name="ib_toolkit",
            action="quick_lbo",
            user_params={"ebitda": 50},
        )
        record.add_tool_call("web_search", {"q": "test"}, {"r": []}, 200)
        record.complete(final_output={"irr": 0.25})

        filepath = tmp_path / "session.json"
        record.save(filepath)
        assert filepath.exists()

        loaded = SessionRecord.load(filepath)
        assert loaded.run_id == "save-test"
        assert loaded.skill_name == "ib_toolkit"
        assert len(loaded.tool_calls) == 1
        assert loaded.tool_calls[0].tool_name == "web_search"
        assert loaded.final_output == {"irr": 0.25}

    def test_save_creates_parent_dirs(self, tmp_path):
        record = SessionRecord(run_id="r1", skill_name="s1", action="a1")
        filepath = tmp_path / "deep" / "nested" / "session.json"
        record.save(filepath)
        assert filepath.exists()
