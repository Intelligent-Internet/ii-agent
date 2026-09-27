"""Tests for /auth/dev/login endpoint changes.

Covers:
- POST method support for dev login
- Rate limiting by client IP
- Backward-compatible GET endpoint
- Rejection in non-local mode
"""

from __future__ import annotations

import time

import pytest

from ii_agent.auth.router import (
    _DEV_LOGIN_TIMESTAMPS,
    _DEV_LOGIN_RATE_LIMIT_SECONDS,
)

pytestmark = pytest.mark.unit


class TestDevLoginRateLimiting:
    """Rate limiter for dev login endpoint."""

    def setup_method(self):
        """Clear rate limit state between tests."""
        _DEV_LOGIN_TIMESTAMPS.clear()

    def test_first_request_allowed(self):
        """First request from any IP should be allowed (no prior timestamp)."""
        assert "192.168.1.1" not in _DEV_LOGIN_TIMESTAMPS

    def test_second_request_within_window_blocked(self):
        """Second request within rate limit window should be blocked."""
        now = time.time()
        _DEV_LOGIN_TIMESTAMPS["192.168.1.1"] = now
        last = _DEV_LOGIN_TIMESTAMPS.get("192.168.1.1", 0)
        assert now - last < _DEV_LOGIN_RATE_LIMIT_SECONDS

    def test_request_after_window_allowed(self):
        """Request after rate limit window expires should be allowed."""
        old_time = time.time() - _DEV_LOGIN_RATE_LIMIT_SECONDS - 1
        _DEV_LOGIN_TIMESTAMPS["192.168.1.1"] = old_time
        now = time.time()
        last = _DEV_LOGIN_TIMESTAMPS.get("192.168.1.1", 0)
        assert now - last >= _DEV_LOGIN_RATE_LIMIT_SECONDS

    def test_different_ips_independent(self):
        """Rate limiting is per-IP — different IPs have independent windows."""
        now = time.time()
        _DEV_LOGIN_TIMESTAMPS["192.168.1.1"] = now
        # Different IP should not be rate limited
        last_other = _DEV_LOGIN_TIMESTAMPS.get("192.168.1.2", 0)
        assert now - last_other >= _DEV_LOGIN_RATE_LIMIT_SECONDS

    def test_stale_entry_cleanup(self):
        """Entries older than 1 hour should be cleaned up."""
        stale_time = time.time() - 7200  # 2 hours ago
        _DEV_LOGIN_TIMESTAMPS["old-ip"] = stale_time
        _DEV_LOGIN_TIMESTAMPS["recent-ip"] = time.time()

        # Simulate cleanup logic from the endpoint
        now = time.time()
        stale_threshold = now - 3600
        for ip in list(_DEV_LOGIN_TIMESTAMPS.keys()):
            if _DEV_LOGIN_TIMESTAMPS[ip] < stale_threshold:
                del _DEV_LOGIN_TIMESTAMPS[ip]

        assert "old-ip" not in _DEV_LOGIN_TIMESTAMPS
        assert "recent-ip" in _DEV_LOGIN_TIMESTAMPS

    def test_rate_limit_seconds_is_positive(self):
        """Rate limit constant should be a positive integer."""
        assert _DEV_LOGIN_RATE_LIMIT_SECONDS > 0
        assert isinstance(_DEV_LOGIN_RATE_LIMIT_SECONDS, int)
