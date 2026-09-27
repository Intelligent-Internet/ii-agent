"""Tests for ii_agent.realtime.pubsub — singleton management (get/set/reset/shutdown)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock


class TestPubSubSingleton:
    def setup_method(self):
        import ii_agent.realtime.pubsub as ps

        ps._default_pubsub = None  # start fresh

    def teardown_method(self):
        import ii_agent.realtime.pubsub as ps

        ps._default_pubsub = None

    def test_get_pubsub_creates_when_none(self):
        """Lines 21-23: creates AsyncIOPubSub when _default_pubsub is None."""
        from ii_agent.realtime.pubsub import get_pubsub, AsyncIOPubSub

        result = get_pubsub()
        assert isinstance(result, AsyncIOPubSub)

    def test_get_pubsub_returns_same_instance(self):
        """Line 21: branch [21, 23] — returns existing instance."""
        from ii_agent.realtime.pubsub import get_pubsub

        first = get_pubsub()
        second = get_pubsub()
        assert first is second

    def test_reset_pubsub(self):
        """Line 29: sets _default_pubsub to None."""
        import ii_agent.realtime.pubsub as ps
        from ii_agent.realtime.pubsub import get_pubsub, reset_pubsub

        get_pubsub()  # create instance
        assert ps._default_pubsub is not None
        reset_pubsub()
        assert ps._default_pubsub is None

    def test_shutdown_pubsub_when_none(self):
        """Branch [35, -32]: _default_pubsub is None, shutdown is no-op."""
        from ii_agent.realtime.pubsub import shutdown_pubsub
        import ii_agent.realtime.pubsub as ps

        ps._default_pubsub = None
        asyncio.run(shutdown_pubsub())
        assert ps._default_pubsub is None

    def test_shutdown_pubsub_stops_instance(self):
        """Lines 35-37: stops and resets existing instance."""
        from ii_agent.realtime.pubsub import shutdown_pubsub, set_pubsub
        import ii_agent.realtime.pubsub as ps

        mock_ps = AsyncMock()
        set_pubsub(mock_ps)
        asyncio.run(shutdown_pubsub())
        mock_ps.stop.assert_called_once()
        assert ps._default_pubsub is None

    def test_set_pubsub(self):
        """Line 43: sets the singleton to the given instance."""
        from ii_agent.realtime.pubsub import set_pubsub, get_pubsub
        import ii_agent.realtime.pubsub as ps

        mock_ps = MagicMock()
        set_pubsub(mock_ps)
        assert ps._default_pubsub is mock_ps
        assert get_pubsub() is mock_ps
