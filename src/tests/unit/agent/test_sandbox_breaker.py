"""Unit tests for the per-sandbox circuit breaker.

Covers ``record_failure``, ``record_success``, ``should_fail_fast``,
``reset``, and the sliding-window expiry behaviour. The breaker is an
in-process best-effort signal; these tests pin the threshold/window
semantics so future refactors don't silently change them.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ii_agent.agents.sandboxes import breaker


@pytest.fixture(autouse=True)
def _reset_breaker_state():
    """Each test starts with a clean breaker map."""
    breaker.reset()
    yield
    breaker.reset()


def _settings(threshold: int = 3, window: float = 300.0):
    """Build a minimal settings stand-in matching what breaker.* reads."""

    class _Sandbox:
        max_sandbox_restart_failures = threshold
        sandbox_failure_window_seconds = window

    class _S:
        sandbox = _Sandbox()

    return _S()


def test_record_failure_increments_counter():
    with patch.object(breaker, "get_settings", return_value=_settings()):
        assert breaker.record_failure("sb-1") == 1
        assert breaker.record_failure("sb-1") == 2
        assert breaker.record_failure("sb-1") == 3


def test_record_failure_isolated_per_sandbox():
    with patch.object(breaker, "get_settings", return_value=_settings()):
        breaker.record_failure("sb-A")
        breaker.record_failure("sb-A")
        assert breaker.record_failure("sb-B") == 1
        assert breaker.record_failure("sb-A") == 3


def test_record_success_clears_state():
    with patch.object(breaker, "get_settings", return_value=_settings()):
        breaker.record_failure("sb-1")
        breaker.record_failure("sb-1")
        breaker.record_success("sb-1")
        # Counter starts over.
        assert breaker.record_failure("sb-1") == 1


def test_should_fail_fast_false_below_threshold():
    with patch.object(breaker, "get_settings", return_value=_settings(threshold=3)):
        breaker.record_failure("sb-1")
        breaker.record_failure("sb-1")
        assert breaker.should_fail_fast("sb-1") is False


def test_should_fail_fast_true_at_threshold():
    with patch.object(breaker, "get_settings", return_value=_settings(threshold=3)):
        breaker.record_failure("sb-1")
        breaker.record_failure("sb-1")
        breaker.record_failure("sb-1")
        assert breaker.should_fail_fast("sb-1") is True


def test_should_fail_fast_unknown_sandbox():
    with patch.object(breaker, "get_settings", return_value=_settings()):
        assert breaker.should_fail_fast("never-seen") is False


def test_window_expiry_resets_count_on_record_failure():
    """A failure outside the window resets the counter to 1."""
    fake_now = [1000.0]

    def _now():
        return fake_now[0]

    with patch.object(breaker, "get_settings", return_value=_settings(window=60.0)):
        with patch.object(breaker.time, "monotonic", side_effect=_now):
            assert breaker.record_failure("sb-1") == 1
            fake_now[0] = 1030.0
            assert breaker.record_failure("sb-1") == 2
            # Jump past the window — next failure starts a fresh window.
            fake_now[0] = 1200.0
            assert breaker.record_failure("sb-1") == 1


def test_window_expiry_clears_open_breaker_on_check():
    """An open breaker auto-clears once the window elapses."""
    fake_now = [1000.0]

    def _now():
        return fake_now[0]

    with patch.object(breaker, "get_settings", return_value=_settings(threshold=2, window=60.0)):
        with patch.object(breaker.time, "monotonic", side_effect=_now):
            breaker.record_failure("sb-1")
            breaker.record_failure("sb-1")
            assert breaker.should_fail_fast("sb-1") is True
            # Window elapses — should_fail_fast must drop the entry.
            fake_now[0] = 1200.0
            assert breaker.should_fail_fast("sb-1") is False
            # And a fresh failure starts at 1.
            assert breaker.record_failure("sb-1") == 1


def test_reset_clears_all_when_called_without_id():
    with patch.object(breaker, "get_settings", return_value=_settings()):
        breaker.record_failure("sb-A")
        breaker.record_failure("sb-B")
        breaker.reset()
        assert breaker.record_failure("sb-A") == 1
        assert breaker.record_failure("sb-B") == 1


def test_reset_clears_single_sandbox():
    with patch.object(breaker, "get_settings", return_value=_settings()):
        breaker.record_failure("sb-A")
        breaker.record_failure("sb-A")
        breaker.record_failure("sb-B")
        breaker.reset("sb-A")
        # sb-A reset, sb-B preserved.
        assert breaker.record_failure("sb-A") == 1
        assert breaker.record_failure("sb-B") == 2


def test_settings_failure_falls_back_to_safe_defaults():
    """If get_settings() blows up, breaker uses 3-strike / 300s defaults."""

    def _boom():
        raise RuntimeError("settings unavailable")

    with patch.object(breaker, "get_settings", side_effect=_boom):
        # Default threshold is 3 — first two failures should not open.
        breaker.record_failure("sb-1")
        breaker.record_failure("sb-1")
        assert breaker.should_fail_fast("sb-1") is False
        breaker.record_failure("sb-1")
        assert breaker.should_fail_fast("sb-1") is True
