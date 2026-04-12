"""Tests for ii_agent.users.schemas — UserPublic.serialize_period_end."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock


class TestUserPublicSerializePeriodEnd:
    def _make_schema(self, **kwargs):
        from ii_agent.users.schemas import UserPublic

        base = dict(
            id="user-1",
            email="test@example.com",
            role="user",
            first_name="Test",
            last_name="User",
        )
        return UserPublic(**{**base, **kwargs})

    def test_serialize_period_end_with_datetime(self):
        """Branch [26, 27]: value is datetime → return isoformat."""
        schema = self._make_schema()
        dt = datetime.now(timezone.utc)
        info = MagicMock()
        result = schema.serialize_period_end(dt, info)
        assert isinstance(result, str)
        assert "T" in result  # ISO format

    def test_serialize_period_end_with_none(self):
        """Branch [26, 28]: value is None → return value (None)."""
        schema = self._make_schema()
        info = MagicMock()
        result = schema.serialize_period_end(None, info)
        assert result is None

    def test_serialize_period_end_with_string(self):
        """Branch [26, 28]: value is str → returned as-is."""
        schema = self._make_schema()
        info = MagicMock()
        result = schema.serialize_period_end("2024-01-01", info)
        assert result == "2024-01-01"
