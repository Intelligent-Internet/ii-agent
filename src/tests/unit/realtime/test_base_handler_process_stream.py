from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agents.runs.agent import (
    RunCancelledEvent,
    RunCompletedEvent,
    RunPausedEvent,
)
from ii_agent.realtime.handlers.base import BaseCommandHandler, CommandType
from ii_agent.realtime.handlers.plan import PlanHandler
from ii_agent.realtime.handlers.query import UserQueryHandler
from ii_agent.realtime.schemas import PlanCommandContent, QueryCommandContent
from ii_agent.tasks.types import RunStatus


pytestmark = pytest.mark.unit


class _StubHandler(BaseCommandHandler):
    def get_command_type(self) -> CommandType:
        return CommandType.PING

    async def handle(self, content, session_info) -> None:
        return None


class _CapturingPubSub:
    def __init__(self) -> None:
        self.publish = AsyncMock()


def _make_handler():
    pubsub = _CapturingPubSub()
    container = MagicMock()
    container.run_task_service = MagicMock()
    container.run_task_service.transition_status = AsyncMock()
    return _StubHandler(pubsub=pubsub, container=container), pubsub, container


def _make_session_info():
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        api_version="v1",
    )


@asynccontextmanager
async def _db_cm():
    yield AsyncMock()


async def _stream(*events):
    for event in events:
        yield event


@pytest.mark.asyncio
@pytest.mark.parametrize("command_type", [QueryCommandContent, PlanCommandContent])
async def test_project_recall_preflight_attaches_or_clarifies(command_type):
    handler, pubsub, container = _make_handler()
    container.file_service.recall_for_turn = AsyncMock()
    container.event_service.save_event = AsyncMock()
    session_info = _make_session_info()
    command = command_type(text="show earlier image")
    recalled_id = str(uuid.uuid4())
    handler.create_user_message_event = AsyncMock(return_value=(MagicMock(name="user_event"), None))

    with patch("ii_agent.realtime.handlers.base.get_db_session_local", side_effect=_db_cm):
        container.file_service.recall_for_turn.return_value = ([recalled_id], None)
        assert await handler.prepare_recalled_files(command, session_info)
        assert command.files == [recalled_id]
        assert not pubsub.publish.await_count

        command.files = []
        container.file_service.recall_for_turn.return_value = ([], "Which file?")
        assert not await handler.prepare_recalled_files(command, session_info)

    assert [call.args[0].name for call in pubsub.publish.await_args_list][1:] == [
        "agent.response",
        "agent.stream.complete",
        "agent.complete",
    ]
    assert pubsub.publish.await_args_list[1].args[0].content["text"] == "Which file?"
    assert pubsub.publish.await_args_list[-1].args[0].content["run_status"] == RunStatus.COMPLETED
    container.event_service.save_event.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_type", "command_type", "run_method"),
    [
        (UserQueryHandler, QueryCommandContent, "_handle_query"),
        (PlanHandler, PlanCommandContent, "_handle_plan"),
    ],
)
async def test_project_handlers_stop_before_run_on_recall_ambiguity(
    handler_type, command_type, run_method
):
    handler = handler_type(pubsub=_CapturingPubSub(), container=MagicMock())
    session_info = _make_session_info()
    handler.validate_and_update_session = AsyncMock(return_value=(True, session_info, MagicMock()))
    handler.prepare_recalled_files = AsyncMock(return_value=False)
    setattr(handler, run_method, AsyncMock())

    await handler.handle(command_type(text="show earlier image"), session_info)

    handler.prepare_recalled_files.assert_awaited_once()
    getattr(handler, run_method).assert_not_awaited()


class TestProcessAgentEventStream:
    @pytest.mark.asyncio
    async def test_cancelled_run_stays_cancelled(self):
        handler, pubsub, container = _make_handler()
        session_info = _make_session_info()
        run_id = uuid.uuid4()

        event = RunCancelledEvent(
            session_id=str(session_info.id),
            agent_id="agent-1",
            agent_name="II-Agent",
            run_id=str(run_id),
            model="test-model",
            reason="User cancelled",
        )

        with patch(
            "ii_agent.realtime.handlers.base.get_db_session_local",
            return_value=_db_cm(),
        ):
            final_status = await handler.process_agent_event_stream(
                _stream(event),
                session_info,
                run_id=run_id,
            )

        assert final_status == RunStatus.CANCELLED
        container.run_task_service.transition_status.assert_awaited_once()
        assert (
            container.run_task_service.transition_status.await_args.kwargs["to_status"]
            == RunStatus.CANCELLED
        )
        published_names = [call.args[0].name for call in pubsub.publish.await_args_list]
        assert "agent.response.interrupted" in published_names

    @pytest.mark.asyncio
    async def test_paused_run_stays_paused(self):
        handler, _pubsub, container = _make_handler()
        session_info = _make_session_info()
        run_id = uuid.uuid4()

        event = RunPausedEvent(
            session_id=str(session_info.id),
            agent_id="agent-1",
            agent_name="II-Agent",
            run_id=str(run_id),
            model="test-model",
            content="Awaiting confirmation",
        )

        with patch(
            "ii_agent.realtime.handlers.base.get_db_session_local",
            return_value=_db_cm(),
        ):
            final_status = await handler.process_agent_event_stream(
                _stream(event),
                session_info,
                run_id=run_id,
            )

        assert final_status == RunStatus.PAUSED
        container.run_task_service.transition_status.assert_awaited_once()
        assert (
            container.run_task_service.transition_status.await_args.kwargs["to_status"]
            == RunStatus.PAUSED
        )

    @pytest.mark.asyncio
    async def test_completed_run_without_run_output_stays_completed(self):
        handler, _pubsub, container = _make_handler()
        session_info = _make_session_info()
        run_id = uuid.uuid4()

        event = RunCompletedEvent(
            session_id=str(session_info.id),
            agent_id="agent-1",
            agent_name="II-Agent",
            run_id=str(run_id),
            model="test-model",
            status=RunStatus.COMPLETED,
        )

        with patch(
            "ii_agent.realtime.handlers.base.get_db_session_local",
            return_value=_db_cm(),
        ):
            final_status = await handler.process_agent_event_stream(
                _stream(event),
                session_info,
                run_id=run_id,
            )

        assert final_status == RunStatus.COMPLETED
        container.run_task_service.transition_status.assert_awaited_once()
        assert (
            container.run_task_service.transition_status.await_args.kwargs["to_status"]
            == RunStatus.COMPLETED
        )
