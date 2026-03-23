"""Tests for QueryHandler._process_query() task status classification.

Covers the bug where a failed agent run (is_error=True from chat_session.arun)
was being classified as RunStatus.COMPLETED instead of RunStatus.FAILED.
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ii_agent.db.agent import RunStatus
from ii_tool.tools.base import ToolResult


class TestProcessQueryStatusMapping:
    """Tests that _process_query correctly maps ToolResult flags to RunStatus.

    We patch _handle_file_upload, _init_chat_session, _send_error_event, and
    the DB layer so that _process_query exercises only its status-mapping logic.
    """

    @pytest.mark.asyncio
    async def test_successful_run_yields_completed(self):
        """A normal (non-error, non-interrupted) result → RunStatus.COMPLETED."""
        status = await self._run_process_query(
            ToolResult(llm_content="done", is_error=False, is_interrupted=False)
        )
        assert status == RunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_error_run_yields_failed(self):
        """An error result (is_error=True) → RunStatus.FAILED."""
        status = await self._run_process_query(
            ToolResult(llm_content=[], is_error=True)
        )
        assert status == RunStatus.FAILED

    @pytest.mark.asyncio
    async def test_interrupted_run_yields_aborted(self):
        """An interrupted result (is_interrupted=True) → RunStatus.ABORTED."""
        status = await self._run_process_query(
            ToolResult(llm_content="interrupted", is_interrupted=True)
        )
        assert status == RunStatus.ABORTED

    @pytest.mark.asyncio
    async def test_exception_during_processing_yields_failed(self):
        """An unhandled exception during processing → RunStatus.FAILED."""
        status = await self._run_process_query(side_effect=RuntimeError("LLM exploded"))
        assert status == RunStatus.FAILED

    @pytest.mark.asyncio
    async def test_none_is_error_treated_as_success(self):
        """is_error=None (the default) should be treated as success."""
        status = await self._run_process_query(
            ToolResult(llm_content="all ok")  # is_error defaults to None
        )
        assert status == RunStatus.COMPLETED

    # --- helper ---

    async def _run_process_query(
        self,
        tool_result: ToolResult | None = None,
        *,
        side_effect: Exception | None = None,
    ) -> RunStatus:
        """Run _process_query and return the RunStatus it computed.

        We intercept AgentRunService.update_task_status to capture the
        status without needing a real database.
        """
        from ii_agent.server.socket.command.query_handler import UserQueryHandler

        event_stream = MagicMock()
        event_stream.publish = AsyncMock()
        handler = UserQueryHandler(event_stream)

        session_info = MagicMock()
        session_info.id = uuid.uuid4()

        running_task = MagicMock()
        running_task.id = uuid.uuid4()

        sandbox = MagicMock()

        query_command = MagicMock()
        query_command.text = "test"
        query_command.resume = False
        query_command.files = []

        # Patch file handling and session init
        handler._handle_file_upload = AsyncMock(return_value=([], []))
        chat_session = MagicMock()
        if side_effect:
            chat_session.arun = AsyncMock(side_effect=side_effect)
        else:
            chat_session.arun = AsyncMock(return_value=tool_result)
        handler._init_chat_session = AsyncMock(return_value=chat_session)
        handler._send_error_event = AsyncMock()

        # Capture the status passed to update_task_status
        captured = {}

        async def fake_update(db, task_id, status):
            captured["status"] = status
            result = MagicMock()
            result.id = task_id
            result.status = status
            return result

        mock_db = MagicMock()
        mock_db.commit = AsyncMock()

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "ii_agent.server.socket.command.query_handler.get_db_session_local",
            return_value=mock_ctx,
        ), patch(
            "ii_agent.server.socket.command.query_handler.AgentRunService.update_task_status",
            side_effect=fake_update,
        ):
            await handler._process_query(
                query_command, session_info, running_task, sandbox
            )

        return captured["status"]
