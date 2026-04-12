"""Tests for ii_agent.workers.cron.jobs.extend_sandbox_timeout.SandboxTimeoutExtender."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.workers.cron.jobs.extend_sandbox_timeout import (
    BATCH_SIZE,
    TIMEOUT_EXTENSION_SECONDS,
    SandboxTimeoutExtender,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_extender(sandbox_service=None) -> SandboxTimeoutExtender:
    svc = sandbox_service or AsyncMock()
    return SandboxTimeoutExtender(sandbox_service=svc)


def _make_session(session_id=None) -> MagicMock:
    import uuid

    s = MagicMock()
    s.id = session_id or uuid.uuid4()
    return s


# ---------------------------------------------------------------------------
# SandboxTimeoutExtender.extend_sandbox_timeout
# ---------------------------------------------------------------------------


class TestExtendSandboxTimeout:
    @pytest.mark.asyncio
    async def test_returns_true_on_success(self):
        db = AsyncMock()
        sandbox = AsyncMock()
        sandbox.set_timeout = AsyncMock()

        sandbox_service = AsyncMock()
        sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=sandbox)

        extender = _make_extender(sandbox_service)
        session = _make_session()

        result = await extender.extend_sandbox_timeout(db, session)

        assert result is True
        sandbox.set_timeout.assert_awaited_once_with(TIMEOUT_EXTENSION_SECONDS)

    @pytest.mark.asyncio
    async def test_returns_false_when_no_sandbox_found(self):
        db = AsyncMock()
        sandbox_service = AsyncMock()
        sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=None)

        extender = _make_extender(sandbox_service)
        session = _make_session()

        result = await extender.extend_sandbox_timeout(db, session)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        db = AsyncMock()
        sandbox_service = AsyncMock()
        sandbox_service.get_sandbox_by_session_id = AsyncMock(
            side_effect=Exception("connection error")
        )

        extender = _make_extender(sandbox_service)
        session = _make_session()

        result = await extender.extend_sandbox_timeout(db, session)

        assert result is False

    @pytest.mark.asyncio
    async def test_custom_timeout_passed_through(self):
        db = AsyncMock()
        sandbox = AsyncMock()
        sandbox.set_timeout = AsyncMock()

        sandbox_service = AsyncMock()
        sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=sandbox)

        extender = _make_extender(sandbox_service)
        session = _make_session()

        await extender.extend_sandbox_timeout(db, session, timeout_seconds=3600)

        sandbox.set_timeout.assert_awaited_once_with(3600)


# ---------------------------------------------------------------------------
# SandboxTimeoutExtender.process_batch
# ---------------------------------------------------------------------------


class TestProcessBatch:
    @pytest.mark.asyncio
    async def test_all_succeed(self):
        db = AsyncMock()
        sandbox = AsyncMock()
        sandbox.set_timeout = AsyncMock()

        sandbox_service = AsyncMock()
        sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=sandbox)

        extender = _make_extender(sandbox_service)
        sessions = [_make_session() for _ in range(3)]

        success, failure = await extender.process_batch(db, sessions)

        assert success == 3
        assert failure == 0

    @pytest.mark.asyncio
    async def test_all_fail(self):
        db = AsyncMock()
        sandbox_service = AsyncMock()
        sandbox_service.get_sandbox_by_session_id = AsyncMock(return_value=None)

        extender = _make_extender(sandbox_service)
        sessions = [_make_session() for _ in range(2)]

        success, failure = await extender.process_batch(db, sessions)

        assert success == 0
        assert failure == 2

    @pytest.mark.asyncio
    async def test_mixed_results(self):
        db = AsyncMock()

        sandbox = AsyncMock()
        sandbox.set_timeout = AsyncMock()

        calls = [sandbox, None, sandbox]

        sandbox_service = AsyncMock()
        sandbox_service.get_sandbox_by_session_id = AsyncMock(side_effect=calls)

        extender = _make_extender(sandbox_service)
        sessions = [_make_session() for _ in range(3)]

        success, failure = await extender.process_batch(db, sessions)

        assert success == 2
        assert failure == 1

    @pytest.mark.asyncio
    async def test_empty_session_list(self):
        db = AsyncMock()
        extender = _make_extender()

        success, failure = await extender.process_batch(db, [])

        assert success == 0
        assert failure == 0


# ---------------------------------------------------------------------------
# SandboxTimeoutExtender.run
# ---------------------------------------------------------------------------


class TestRunJob:
    @pytest.mark.asyncio
    async def test_returns_success_when_no_sessions(self):
        extender = _make_extender()
        extender.get_permanent_sessions = AsyncMock(return_value=[])

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        import ii_agent.workers.cron.jobs.extend_sandbox_timeout as mod

        import unittest.mock as mock

        with mock.patch.object(mod, "get_db_session_local", return_value=mock_db):
            result = await extender.run()

        assert result["status"] == "success"
        assert result["total_sessions"] == 0
        assert result["successful"] == 0
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_returns_partial_when_some_fail(self):
        sessions = [_make_session(), _make_session()]
        extender = _make_extender()
        extender.get_permanent_sessions = AsyncMock(return_value=sessions)
        extender.process_batch = AsyncMock(return_value=(1, 1))

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        import ii_agent.workers.cron.jobs.extend_sandbox_timeout as mod
        import unittest.mock as mock

        with mock.patch.object(mod, "get_db_session_local", return_value=mock_db):
            result = await extender.run()

        assert result["status"] == "partial"
        assert result["successful"] == 1
        assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_returns_success_when_all_succeed(self):
        sessions = [_make_session()]
        extender = _make_extender()
        extender.get_permanent_sessions = AsyncMock(return_value=sessions)
        extender.process_batch = AsyncMock(return_value=(1, 0))

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        import ii_agent.workers.cron.jobs.extend_sandbox_timeout as mod
        import unittest.mock as mock

        with mock.patch.object(mod, "get_db_session_local", return_value=mock_db):
            result = await extender.run()

        assert result["status"] == "success"
        assert result["successful"] == 1
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_raises_on_unexpected_error(self):
        extender = _make_extender()
        extender.get_permanent_sessions = AsyncMock(side_effect=Exception("DB crash"))

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        import ii_agent.workers.cron.jobs.extend_sandbox_timeout as mod
        import unittest.mock as mock

        with (
            mock.patch.object(mod, "get_db_session_local", return_value=mock_db),
            pytest.raises(Exception, match="DB crash"),
        ):
            await extender.run()

    @pytest.mark.asyncio
    async def test_includes_duration_in_result(self):
        extender = _make_extender()
        extender.get_permanent_sessions = AsyncMock(return_value=[])

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)

        import ii_agent.workers.cron.jobs.extend_sandbox_timeout as mod
        import unittest.mock as mock

        with mock.patch.object(mod, "get_db_session_local", return_value=mock_db):
            result = await extender.run()

        assert "duration_seconds" in result
        assert isinstance(result["duration_seconds"], float)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_timeout_extension_seconds(self):
        assert TIMEOUT_EXTENSION_SECONDS == 7200

    def test_batch_size(self):
        assert BATCH_SIZE == 10
