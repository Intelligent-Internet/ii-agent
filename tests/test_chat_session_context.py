import asyncio
from unittest.mock import AsyncMock, Mock, patch
import pytest

from ii_agent.server.socket.chat_session import ChatSessionContext
from ii_agent.server.models.sessions import SessionInfo
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.event_stream import EventStream
from ii_agent.core.event import EventType, RealtimeEvent


class DummyController:
    def __init__(self):
        self.state = Mock()
        self.run_agent_async = AsyncMock(return_value=Mock(is_error=False))
        self.cancel = Mock()
        self.count_tokens = Mock(return_value=1000)


@pytest.mark.asyncio
async def test_chat_session_context_integrates_context_manager(tmp_path):
    # Setup
    wc = Mock()
    file_store = Mock()
    cfg = Mock(spec=IIAgentConfig)
    session_info = SessionInfo(id="test-session", user_id="user1", name="Test")
    llm_config = Mock()
    llm_config.model_id = "gpt-4-turbo"

    controller = DummyController()
    event_stream = EventStream()

    chat_session = ChatSessionContext(
        workspace_manager=wc,
        file_store=file_store,
        config=cfg,
        session_info=session_info,
        llm_config=llm_config,
        agent_controller=controller,
        event_stream=event_stream,
    )

    # Mock ContextWindowManager functions to ensure they are invoked in arun
    with patch(
        "ii_agent.server.chat.context_manager.ContextWindowManager.create_checkpoint_if_needed",
        new=AsyncMock(return_value=None),
    ) as ck:
        with patch(
            "ii_agent.server.chat.context_manager.ContextWindowManager.dump_and_tile_if_needed",
            new=AsyncMock(return_value=None),
        ) as tg:
            with patch(
                "ii_agent.server.chat.context_manager.ContextWindowManager.check_and_summarize",
                new=AsyncMock(return_value=None),
            ) as cs:
                with patch(
                    "ii_agent.server.chat.message_service.MessageService.list_by_session",
                    new=AsyncMock(return_value=[]),
                ) as msg_list:
                    with patch(
                        "ii_agent.db.manager.Sessions.find_session_by_id",
                        new=AsyncMock(return_value=Mock(id=session_info.id, prompt_tokens=0, completion_tokens=0)),
                    ) as sess_find:
                        from ii_agent.server.models.messages import QueryContentInternal
                        query = QueryContentInternal(text="Hello world", resume=False)

                # Run
                await chat_session.arun(query)

                # Assertions: the mock methods should have been called after run
                assert ck.called
                assert tg.called
                assert cs.called
