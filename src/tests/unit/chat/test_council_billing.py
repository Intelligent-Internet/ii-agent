"""Unit tests for council mode billing integration.

Tests cover:
- CouncilService: usage + model_config propagation in events
- ChatService._publish_council_usage: billing event publishing
- ChatService.stream_council_chat_response: credit pre-check + per-event billing
- Guard layers: billing disabled, BYOK (is_user_key), no pubsub
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.billing.schemas import TokenUsage
from ii_agent.chat.application.chat_service import ChatService
from ii_agent.chat.application.council_service import CouncilService
from ii_agent.chat.types import (
    CouncilPreferences,
    CouncilModelConfig,
    Message,
    MessageRole,
    TextContent,
)
from ii_agent.realtime.events.app_events import ModelUsageEvent
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.settings.llm.types import ConfigType, Provider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER = uuid.uuid4()
_SESSION = uuid.uuid4()
_RUN = uuid.uuid4()
_SETTING = uuid.uuid4()


def _make_model_config(
    *,
    model_id: str = "claude-sonnet-4-20250514",
    provider: Provider = Provider.ANTHROPIC,
    config_type: ConfigType = ConfigType.SYSTEM,
    setting_id: uuid.UUID | None = None,
) -> ModelConfig:
    return ModelConfig(
        id=setting_id or uuid.uuid4(),
        model_id=model_id,
        provider=provider,
        pricing=None,
        config_type=config_type,
    )


def _make_token_usage(
    *,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> TokenUsage:
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def _make_council_preferences(
    *,
    model_ids: list[str] | None = None,
    synthesis_model_id: str = "claude-sonnet-4-20250514",
) -> CouncilPreferences:
    ids = model_ids or ["model-a", "model-b"]
    return CouncilPreferences(
        enabled=True,
        council_models=[CouncilModelConfig(model_id=mid) for mid in ids],
        synthesis_model_id=synthesis_model_id,
    )


def _make_messages() -> list[Message]:
    import time

    now = int(time.time())
    return [
        Message(
            id=uuid.uuid4(),
            role=MessageRole.USER,
            parts=[TextContent(text="Hello")],
            session_id=_SESSION,
            created_at=now,
            updated_at=now,
        )
    ]


def _make_chat_service(*, pubsub=None, credit_service=None) -> ChatService:
    """Build a ChatService with mocked dependencies."""
    container = MagicMock()
    container.config = MagicMock()
    return ChatService(
        file_processor=MagicMock(),
        tool_service=MagicMock(),
        llm_loop=MagicMock(),
        message_history=MagicMock(),
        message_service=MagicMock(),
        session_repo=MagicMock(),
        model_setting_service=MagicMock(),
        credit_service=credit_service,
        container=container,
        title_service=MagicMock(),
        a2a_loop=None,
        pubsub=pubsub,
    )


def _make_fake_message() -> SimpleNamespace:
    """Build a fake message object returned by create_message."""
    import time

    now = int(time.time())
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=MessageRole.USER,
        session_id=_SESSION,
        parts=[TextContent(text="test")],
        model=None,
        provider=None,
        created_at=now,
        updated_at=now,
        file_ids=None,
        tokens=None,
        tools_enabled=None,
        metadata=None,
        provider_metadata=None,
        finish_reason=None,
    )


def _make_all_models_response():
    """Build a fake response for get_all_available_models (needs .models attr)."""
    return SimpleNamespace(models=[])


# ---------------------------------------------------------------------------
# CouncilService: usage propagation in events
# ---------------------------------------------------------------------------


class TestCouncilServiceUsagePropagation:
    """Verify that CouncilService propagates usage + model_config in events."""

    @pytest.mark.asyncio
    async def test_member_complete_event_includes_usage_and_config(self):
        """council_member_complete events must include usage and model_config."""
        config_a = _make_model_config(model_id="model-a")
        config_b = _make_model_config(model_id="model-b")
        synthesis_config = _make_model_config(model_id="synth")

        usage_a = _make_token_usage(input_tokens=10, output_tokens=5)
        usage_b = _make_token_usage(input_tokens=20, output_tokens=10)
        usage_synth = _make_token_usage(input_tokens=50, output_tokens=30)

        response_a = SimpleNamespace(content=[TextContent(text="Answer A")], usage=usage_a)
        response_b = SimpleNamespace(content=[TextContent(text="Answer B")], usage=usage_b)
        response_synth = SimpleNamespace(content=[TextContent(text="Synthesis")], usage=usage_synth)

        # Patch get_client to return mocks that return our controlled responses
        def mock_get_client(config):
            client = MagicMock()

            async def send(messages):
                if config.model_id == "model-a":
                    return response_a
                elif config.model_id == "model-b":
                    return response_b
                else:
                    return response_synth

            client.send = send
            return client

        prefs = _make_council_preferences(
            model_ids=["model-a", "model-b"], synthesis_model_id="synth"
        )

        with (
            patch(
                "ii_agent.chat.application.council_service.get_client",
                side_effect=mock_get_client,
            ),
            patch(
                "ii_agent.chat.application.council_service.cancel.raise_if_cancelled",
                new_callable=AsyncMock,
            ),
        ):
            events: list[dict] = []
            async for event in CouncilService.stream_council_response(
                user_id=_USER,
                messages=_make_messages(),
                user_question="Hello",
                council_preferences=prefs,
                model_configs={
                    "model-a": config_a,
                    "model-b": config_b,
                    "synth": synthesis_config,
                },
                model_names={"model-a": "Model A", "model-b": "Model B", "synth": "Synth"},
                run_id=str(_RUN),
                session_id=_SESSION,
            ):
                events.append(event)

        # Check member_complete events
        member_completes = [e for e in events if e["type"] == "council_member_complete"]
        assert len(member_completes) == 2

        for event in member_completes:
            assert "usage" in event, f"Missing 'usage' in {event['type']} for {event['model_id']}"
            assert "model_config" in event, f"Missing 'model_config' in {event['type']}"
            assert isinstance(event["usage"], TokenUsage)
            assert isinstance(event["model_config"], ModelConfig)

        # Check specific usage values
        event_a = next(e for e in member_completes if e["model_id"] == "model-a")
        assert event_a["usage"].input_tokens == 10
        assert event_a["usage"].output_tokens == 5
        assert event_a["model_config"].model_id == "model-a"

        event_b = next(e for e in member_completes if e["model_id"] == "model-b")
        assert event_b["usage"].input_tokens == 20
        assert event_b["usage"].output_tokens == 10

        # Check synthesis_complete event
        synth_completes = [e for e in events if e["type"] == "council_synthesis_complete"]
        assert len(synth_completes) == 1
        synth_event = synth_completes[0]
        assert "usage" in synth_event
        assert "model_config" in synth_event
        assert synth_event["usage"].input_tokens == 50
        assert synth_event["usage"].output_tokens == 30
        assert synth_event["model_config"].model_id == "synth"

    @pytest.mark.asyncio
    async def test_member_error_does_not_include_usage(self):
        """council_member_error events should NOT include usage/model_config."""
        config = _make_model_config(model_id="failing-model")

        def mock_get_client(cfg):
            client = MagicMock()

            async def send(messages):
                raise RuntimeError("LLM exploded")

            client.send = send
            return client

        prefs = _make_council_preferences(
            model_ids=["failing-model", "failing-model-2"],
            synthesis_model_id="synth",
        )

        with (
            patch(
                "ii_agent.chat.application.council_service.get_client",
                side_effect=mock_get_client,
            ),
            patch(
                "ii_agent.chat.application.council_service.cancel.raise_if_cancelled",
                new_callable=AsyncMock,
            ),
        ):
            events = []
            async for event in CouncilService.stream_council_response(
                user_id=_USER,
                messages=_make_messages(),
                user_question="test",
                council_preferences=prefs,
                model_configs={
                    "failing-model": config,
                    "failing-model-2": _make_model_config(model_id="failing-model-2"),
                    "synth": _make_model_config(model_id="synth"),
                },
                model_names={},
                run_id=str(_RUN),
                session_id=_SESSION,
            ):
                events.append(event)

        error_events = [e for e in events if e["type"] == "council_member_error"]
        assert len(error_events) == 2
        for event in error_events:
            assert "usage" not in event
            assert "model_config" not in event


# ---------------------------------------------------------------------------
# ChatService._publish_council_usage
# ---------------------------------------------------------------------------


class TestPublishCouncilUsage:
    """Test the _publish_council_usage billing event publisher."""

    @pytest.mark.asyncio
    async def test_publishes_model_usage_event(self):
        """Should publish a ModelUsageEvent with correct fields."""
        pubsub = MagicMock()
        published: list = []
        pubsub.publish = AsyncMock(side_effect=published.append)

        svc = _make_chat_service(pubsub=pubsub)
        config = _make_model_config(model_id="claude-test")
        usage = _make_token_usage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=10,
            cache_write_tokens=5,
            reasoning_tokens=3,
        )

        session_id = uuid.uuid4()
        user_id = uuid.uuid4()
        run_id = uuid.uuid4()

        await svc._publish_council_usage(
            usage=usage,
            model_config=config,
            session_id=session_id,
            user_id=user_id,
            run_id=run_id,
        )

        assert len(published) == 1
        event = published[0]
        assert isinstance(event, ModelUsageEvent)
        assert event.session_id == session_id
        assert event.user_id == user_id
        assert event.run_id == run_id
        assert event.model_id == "claude-test"
        assert event.input_tokens == 100
        assert event.output_tokens == 50
        assert event.cache_read_tokens == 10
        assert event.cache_write_tokens == 5
        assert event.reasoning_tokens == 3
        assert event.billing_backend == "native"
        assert event.is_user_key is False

    @pytest.mark.asyncio
    async def test_marks_user_key_for_byok_config(self):
        """Should set is_user_key=True when model_config is user-provided."""
        pubsub = MagicMock()
        published: list = []
        pubsub.publish = AsyncMock(side_effect=published.append)

        svc = _make_chat_service(pubsub=pubsub)
        config = _make_model_config(config_type=ConfigType.USER)
        usage = _make_token_usage()

        await svc._publish_council_usage(
            usage=usage,
            model_config=config,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
        )

        assert published[0].is_user_key is True

    @pytest.mark.asyncio
    async def test_does_nothing_when_pubsub_is_none(self):
        """Should not raise when pubsub is None."""
        svc = _make_chat_service(pubsub=None)
        config = _make_model_config()
        usage = _make_token_usage()

        # Should not raise
        await svc._publish_council_usage(
            usage=usage,
            model_config=config,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
        )

    @pytest.mark.asyncio
    async def test_does_nothing_when_usage_is_none(self):
        """Should not publish when usage is None."""
        pubsub = MagicMock()
        pubsub.publish = AsyncMock()

        svc = _make_chat_service(pubsub=pubsub)
        config = _make_model_config()

        await svc._publish_council_usage(
            usage=None,
            model_config=config,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
        )

        pubsub.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_swallows_pubsub_exception(self):
        """Should log but not propagate pubsub errors."""
        pubsub = MagicMock()
        pubsub.publish = AsyncMock(side_effect=RuntimeError("pubsub broken"))

        svc = _make_chat_service(pubsub=pubsub)
        config = _make_model_config()
        usage = _make_token_usage()

        # Should not raise
        await svc._publish_council_usage(
            usage=usage,
            model_config=config,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
        )


# ---------------------------------------------------------------------------
# ChatService.stream_council_chat_response: billing integration
# ---------------------------------------------------------------------------


class TestCouncilChatResponseBilling:
    """Test that stream_council_chat_response runs credit pre-check and publishes billing events."""

    def _make_chat_request(self) -> SimpleNamespace:
        """Build a minimal chat request for council mode."""
        return SimpleNamespace(
            session_id=_SESSION,
            content="What is the meaning of life?",
            model_id="claude-sonnet-4-20250514",
            file_ids=None,
            github_repository=None,
            council_preferences=_make_council_preferences(),
            media_preferences=None,
            tools=None,
        )

    @pytest.mark.asyncio
    async def test_credit_precheck_runs_before_council(self):
        """stream_council_chat_response should call _check_credits before launching council."""
        pubsub = MagicMock()
        pubsub.publish = AsyncMock()
        credit_service = MagicMock()
        credit_service.has_sufficient_credits = AsyncMock(return_value=True)

        svc = _make_chat_service(pubsub=pubsub, credit_service=credit_service)

        # Mock all the DB operations
        config_a = _make_model_config(model_id="model-a")
        config_b = _make_model_config(model_id="model-b")
        synth_config = _make_model_config(model_id="claude-sonnet-4-20250514")

        svc._check_credits = AsyncMock()
        svc.get_model_config = AsyncMock(
            side_effect=lambda db, model_id, user_id: {
                "model-a": config_a,
                "model-b": config_b,
                "claude-sonnet-4-20250514": synth_config,
            }[model_id]
        )
        svc._model_setting_service = MagicMock()
        svc._model_setting_service.get_all_available_models = AsyncMock(
            return_value=_make_all_models_response()
        )

        svc._message_service.create_message = AsyncMock(return_value=_make_fake_message())
        svc._file_processor.process_uploads = AsyncMock(return_value=None)

        # Mock council service to yield minimal events
        council_events = [
            {
                "type": "council_member_complete",
                "model_id": "model-a",
                "model_name": "Model A",
                "content": "Answer A",
                "usage": _make_token_usage(),
                "model_config": config_a,
            },
            {
                "type": "council_member_complete",
                "model_id": "model-b",
                "model_name": "Model B",
                "content": "Answer B",
                "usage": _make_token_usage(),
                "model_config": config_b,
            },
            {
                "type": "council_synthesis_complete",
                "model_id": "claude-sonnet-4-20250514",
                "content": "Synthesis",
                "usage": _make_token_usage(),
                "model_config": synth_config,
            },
            {
                "type": "council_result",
                "member_outputs": {"model-a": "Answer A", "model-b": "Answer B"},
                "synthesis_content": "Synthesis",
                "synthesis_model_id": "claude-sonnet-4-20250514",
                "model_names": {},
                "had_error": False,
            },
        ]

        async def mock_council_stream(**kwargs):
            for event in council_events:
                yield event

        chat_request = self._make_chat_request()

        with (
            patch("ii_agent.chat.application.chat_service.get_db_session_local") as mock_db_ctx,
            patch("ii_agent.chat.application.chat_service.ContextWindowManager") as mock_ctx,
            patch(
                "ii_agent.chat.application.chat_service.CouncilService.stream_council_response",
                side_effect=mock_council_stream,
            ),
            patch(
                "ii_agent.chat.application.chat_service.cancel.register_run",
                new_callable=AsyncMock,
            ),
            patch(
                "ii_agent.chat.application.chat_service.cancel.cleanup_run",
                new_callable=AsyncMock,
            ),
        ):
            # Mock the DB context manager
            mock_db = MagicMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.commit = AsyncMock()
            mock_db_ctx.return_value = mock_db

            mock_ctx.load_context_for_llm = AsyncMock(return_value=[])
            mock_ctx.check_and_summarize_after_response = AsyncMock()

            events_received = []
            async for event in svc.stream_council_chat_response(
                chat_request=chat_request, user_id=_USER
            ):
                events_received.append(event)

            # Credit pre-check was called
            svc._check_credits.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_billing_events_published_for_each_member(self):
        """Should publish a ModelUsageEvent for each council member + synthesis."""
        pubsub = MagicMock()
        published: list = []
        pubsub.publish = AsyncMock(side_effect=published.append)
        credit_service = MagicMock()
        credit_service.has_sufficient_credits = AsyncMock(return_value=True)

        svc = _make_chat_service(pubsub=pubsub, credit_service=credit_service)

        config_a = _make_model_config(model_id="model-a")
        config_b = _make_model_config(model_id="model-b")
        synth_config = _make_model_config(model_id="claude-sonnet-4-20250514")

        svc._check_credits = AsyncMock()
        svc.get_model_config = AsyncMock(
            side_effect=lambda db, model_id, user_id: {
                "model-a": config_a,
                "model-b": config_b,
                "claude-sonnet-4-20250514": synth_config,
            }[model_id]
        )
        svc._model_setting_service = MagicMock()
        svc._model_setting_service.get_all_available_models = AsyncMock(
            return_value=_make_all_models_response()
        )

        svc._message_service.create_message = AsyncMock(return_value=_make_fake_message())
        svc._file_processor.process_uploads = AsyncMock(return_value=None)

        usage_a = _make_token_usage(input_tokens=10, output_tokens=5)
        usage_b = _make_token_usage(input_tokens=20, output_tokens=10)
        usage_synth = _make_token_usage(input_tokens=50, output_tokens=30)

        council_events = [
            {
                "type": "council_member_complete",
                "model_id": "model-a",
                "model_name": "Model A",
                "content": "Answer A",
                "usage": usage_a,
                "model_config": config_a,
            },
            {
                "type": "council_member_complete",
                "model_id": "model-b",
                "model_name": "Model B",
                "content": "Answer B",
                "usage": usage_b,
                "model_config": config_b,
            },
            {
                "type": "council_synthesis_complete",
                "model_id": "claude-sonnet-4-20250514",
                "content": "Synthesis",
                "usage": usage_synth,
                "model_config": synth_config,
            },
            {
                "type": "council_result",
                "member_outputs": {"model-a": "Answer A", "model-b": "Answer B"},
                "synthesis_content": "Synthesis",
                "synthesis_model_id": "claude-sonnet-4-20250514",
                "model_names": {},
                "had_error": False,
            },
        ]

        async def mock_council_stream(**kwargs):
            for event in council_events:
                yield event

        chat_request = self._make_chat_request()

        with (
            patch("ii_agent.chat.application.chat_service.get_db_session_local") as mock_db_ctx,
            patch("ii_agent.chat.application.chat_service.ContextWindowManager") as mock_ctx,
            patch(
                "ii_agent.chat.application.chat_service.CouncilService.stream_council_response",
                side_effect=mock_council_stream,
            ),
            patch(
                "ii_agent.chat.application.chat_service.cancel.register_run",
                new_callable=AsyncMock,
            ),
            patch(
                "ii_agent.chat.application.chat_service.cancel.cleanup_run",
                new_callable=AsyncMock,
            ),
        ):
            mock_db = MagicMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.commit = AsyncMock()
            mock_db_ctx.return_value = mock_db

            mock_ctx.load_context_for_llm = AsyncMock(return_value=[])
            mock_ctx.check_and_summarize_after_response = AsyncMock()

            events_received = []
            async for event in svc.stream_council_chat_response(
                chat_request=chat_request, user_id=_USER
            ):
                events_received.append(event)

        # 3 ModelUsageEvents: 2 members + 1 synthesis
        assert len(published) == 3
        for event in published:
            assert isinstance(event, ModelUsageEvent)

        # Verify token counts match
        model_ids_published = [e.model_id for e in published]
        assert "model-a" in model_ids_published
        assert "model-b" in model_ids_published
        assert "claude-sonnet-4-20250514" in model_ids_published

        evt_a = next(e for e in published if e.model_id == "model-a")
        assert evt_a.input_tokens == 10
        assert evt_a.output_tokens == 5

        evt_synth = next(e for e in published if e.model_id == "claude-sonnet-4-20250514")
        assert evt_synth.input_tokens == 50
        assert evt_synth.output_tokens == 30

    @pytest.mark.asyncio
    async def test_no_billing_when_pubsub_is_none(self):
        """Council billing should be gracefully skipped with no pubsub."""
        svc = _make_chat_service(pubsub=None)

        config_a = _make_model_config(model_id="model-a")
        config_b = _make_model_config(model_id="model-b")
        synth_config = _make_model_config(model_id="claude-sonnet-4-20250514")

        svc._check_credits = AsyncMock()
        svc.get_model_config = AsyncMock(
            side_effect=lambda db, model_id, user_id: {
                "model-a": config_a,
                "model-b": config_b,
                "claude-sonnet-4-20250514": synth_config,
            }[model_id]
        )
        svc._model_setting_service = MagicMock()
        svc._model_setting_service.get_all_available_models = AsyncMock(
            return_value=_make_all_models_response()
        )

        svc._message_service.create_message = AsyncMock(return_value=_make_fake_message())
        svc._file_processor.process_uploads = AsyncMock(return_value=None)

        council_events = [
            {
                "type": "council_member_complete",
                "model_id": "model-a",
                "model_name": "Model A",
                "content": "Answer A",
                "usage": _make_token_usage(),
                "model_config": config_a,
            },
            {
                "type": "council_result",
                "member_outputs": {"model-a": "Answer A"},
                "synthesis_content": "",
                "synthesis_model_id": "claude-sonnet-4-20250514",
                "model_names": {},
                "had_error": False,
            },
        ]

        async def mock_council_stream(**kwargs):
            for event in council_events:
                yield event

        with (
            patch("ii_agent.chat.application.chat_service.get_db_session_local") as mock_db_ctx,
            patch("ii_agent.chat.application.chat_service.ContextWindowManager") as mock_ctx,
            patch(
                "ii_agent.chat.application.chat_service.CouncilService.stream_council_response",
                side_effect=mock_council_stream,
            ),
            patch(
                "ii_agent.chat.application.chat_service.cancel.register_run",
                new_callable=AsyncMock,
            ),
            patch(
                "ii_agent.chat.application.chat_service.cancel.cleanup_run",
                new_callable=AsyncMock,
            ),
        ):
            mock_db = MagicMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.commit = AsyncMock()
            mock_db_ctx.return_value = mock_db

            mock_ctx.load_context_for_llm = AsyncMock(return_value=[])
            mock_ctx.check_and_summarize_after_response = AsyncMock()

            # Should complete without error even with no pubsub
            events_received = []
            async for event in svc.stream_council_chat_response(
                chat_request=self._make_chat_request(), user_id=_USER
            ):
                events_received.append(event)

        # If we got here without error, pubsub=None is handled gracefully
        assert any(e.get("type") == "complete" for e in events_received)

    @pytest.mark.asyncio
    async def test_no_billing_for_events_without_usage(self):
        """Events without usage data (e.g., starts/errors) should not trigger billing."""
        pubsub = MagicMock()
        pubsub.publish = AsyncMock()

        svc = _make_chat_service(pubsub=pubsub)

        config = _make_model_config(model_id="model-a")
        synth_config = _make_model_config(model_id="claude-sonnet-4-20250514")

        svc._check_credits = AsyncMock()
        svc.get_model_config = AsyncMock(
            side_effect=lambda db, model_id, user_id: {
                "model-a": config,
                "model-b": _make_model_config(model_id="model-b"),
                "claude-sonnet-4-20250514": synth_config,
            }[model_id]
        )
        svc._model_setting_service = MagicMock()
        svc._model_setting_service.get_all_available_models = AsyncMock(
            return_value=_make_all_models_response()
        )

        svc._message_service.create_message = AsyncMock(return_value=_make_fake_message())
        svc._file_processor.process_uploads = AsyncMock(return_value=None)

        # Events that should NOT trigger billing
        council_events = [
            {"type": "council_member_start", "model_id": "model-a", "model_name": "A"},
            {
                "type": "council_member_error",
                "model_id": "model-b",
                "model_name": "B",
                "error": "timeout",
            },
            {
                "type": "council_synthesis_start",
                "model_id": "claude-sonnet-4-20250514",
            },
            {
                "type": "council_synthesis_complete",
                "model_id": "claude-sonnet-4-20250514",
                "content": "Synthesis",
                # No usage, no model_config → should not bill
            },
            {
                "type": "council_result",
                "member_outputs": {},
                "synthesis_content": "Synthesis",
                "synthesis_model_id": "claude-sonnet-4-20250514",
                "model_names": {},
                "had_error": True,
            },
        ]

        async def mock_council_stream(**kwargs):
            for event in council_events:
                yield event

        with (
            patch("ii_agent.chat.application.chat_service.get_db_session_local") as mock_db_ctx,
            patch("ii_agent.chat.application.chat_service.ContextWindowManager") as mock_ctx,
            patch(
                "ii_agent.chat.application.chat_service.CouncilService.stream_council_response",
                side_effect=mock_council_stream,
            ),
            patch(
                "ii_agent.chat.application.chat_service.cancel.register_run",
                new_callable=AsyncMock,
            ),
            patch(
                "ii_agent.chat.application.chat_service.cancel.cleanup_run",
                new_callable=AsyncMock,
            ),
        ):
            mock_db = MagicMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.commit = AsyncMock()
            mock_db_ctx.return_value = mock_db

            mock_ctx.load_context_for_llm = AsyncMock(return_value=[])
            mock_ctx.check_and_summarize_after_response = AsyncMock()

            events_received = []
            async for event in svc.stream_council_chat_response(
                chat_request=self._make_chat_request(), user_id=_USER
            ):
                events_received.append(event)

        # No billing events should have been published
        pubsub.publish.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 2: A2A Council Billing
# ---------------------------------------------------------------------------


class TestPublishCouncilUsageA2AParams:
    """Test _publish_council_usage with A2A billing parameters."""

    @pytest.mark.asyncio
    async def test_publishes_a2a_billing_backend(self):
        """Should pass billing_backend to ModelUsageEvent for A2A members."""
        pubsub = MagicMock()
        published: list = []
        pubsub.publish = AsyncMock(side_effect=published.append)

        svc = _make_chat_service(pubsub=pubsub)
        config = _make_model_config(model_id="gpt-4o")
        usage = _make_token_usage(input_tokens=100, output_tokens=50)

        await svc._publish_council_usage(
            usage=usage,
            model_config=config,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            billing_backend="a2a:copilot",
        )

        assert len(published) == 1
        event = published[0]
        assert isinstance(event, ModelUsageEvent)
        assert event.billing_backend == "a2a:copilot"

    @pytest.mark.asyncio
    async def test_publishes_provider_reported_cost_and_premium_requests(self):
        """Should pass provider_reported_cost and premium_requests for A2A members."""
        pubsub = MagicMock()
        published: list = []
        pubsub.publish = AsyncMock(side_effect=published.append)

        svc = _make_chat_service(pubsub=pubsub)
        config = _make_model_config(model_id="gpt-4o")
        usage = _make_token_usage(input_tokens=100, output_tokens=50)

        await svc._publish_council_usage(
            usage=usage,
            model_config=config,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            billing_backend="a2a:copilot",
            provider_reported_cost=0.08,
            premium_requests=2,
        )

        assert len(published) == 1
        event = published[0]
        assert event.billing_backend == "a2a:copilot"
        assert event.provider_reported_cost == 0.08
        assert event.premium_requests == 2

    @pytest.mark.asyncio
    async def test_defaults_to_native_billing_backend(self):
        """Without explicit billing_backend, should default to 'native'."""
        pubsub = MagicMock()
        published: list = []
        pubsub.publish = AsyncMock(side_effect=published.append)

        svc = _make_chat_service(pubsub=pubsub)
        config = _make_model_config()
        usage = _make_token_usage()

        await svc._publish_council_usage(
            usage=usage,
            model_config=config,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
        )

        assert published[0].billing_backend == "native"
        assert published[0].provider_reported_cost == 0.0
        assert published[0].premium_requests == 0


class TestCouncilServiceA2ARouting:
    """Test CouncilService A2A member routing."""

    @pytest.mark.asyncio
    async def test_a2a_member_events_include_billing_backend(self):
        """A2A members should emit billing_backend='a2a:{backend}' in events."""
        from ii_agent.integrations.a2a.as_client import A2AStreamEvent

        config_a = _make_model_config(model_id="model-a")
        config_b = _make_model_config(model_id="model-b")
        synthesis_config = _make_model_config(model_id="synth")

        # Mock A2A client that returns content + usage via streaming
        a2a_client = AsyncMock()

        async def mock_astream(*, messages, context_id, metadata):
            yield A2AStreamEvent(
                event_type="assistant.message_delta",
                data={"delta": "A2A answer"},
            )
            yield A2AStreamEvent(
                event_type="assistant.usage",
                data={
                    "input_tokens": 15,
                    "output_tokens": 8,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "reasoning_tokens": 0,
                    "cost": 0.04,
                    "premium_requests": 1,
                },
            )

        a2a_client.astream = mock_astream

        prefs = _make_council_preferences(
            model_ids=["model-a", "model-b"], synthesis_model_id="synth"
        )

        with patch(
            "ii_agent.chat.application.council_service.cancel.raise_if_cancelled",
            new_callable=AsyncMock,
        ):
            events: list[dict] = []
            async for event in CouncilService.stream_council_response(
                user_id=_USER,
                messages=_make_messages(),
                user_question="Hello",
                council_preferences=prefs,
                model_configs={
                    "model-a": config_a,
                    "model-b": config_b,
                    "synth": synthesis_config,
                },
                model_names={"model-a": "A", "model-b": "B", "synth": "Synth"},
                run_id=str(_RUN),
                session_id=_SESSION,
                a2a_client=a2a_client,
                a2a_backend="copilot",
            ):
                events.append(event)

        member_completes = [e for e in events if e["type"] == "council_member_complete"]
        assert len(member_completes) == 2

        for event in member_completes:
            assert event["billing_backend"] == "a2a:copilot"
            assert event["provider_reported_cost"] == 0.04
            assert event["premium_requests"] == 1
            assert event["content"] == "A2A answer"
            assert isinstance(event["usage"], TokenUsage)
            assert event["usage"].input_tokens == 15
            assert event["usage"].output_tokens == 8

        # Synthesis should also be A2A
        synth_completes = [e for e in events if e["type"] == "council_synthesis_complete"]
        assert len(synth_completes) == 1
        assert synth_completes[0]["billing_backend"] == "a2a:copilot"

    @pytest.mark.asyncio
    async def test_byok_member_uses_direct_path_even_with_a2a(self):
        """BYOK members should use direct path with billing_backend='native' in cloud."""
        from ii_agent.integrations.a2a.as_client import A2AStreamEvent

        config_byok = _make_model_config(model_id="model-byok", config_type=ConfigType.USER)
        config_system = _make_model_config(model_id="model-system", config_type=ConfigType.SYSTEM)
        synthesis_config = _make_model_config(model_id="synth")

        # BYOK response (direct)
        byok_usage = _make_token_usage(input_tokens=30, output_tokens=20)
        byok_response = SimpleNamespace(content=[TextContent(text="BYOK answer")], usage=byok_usage)

        # Mock get_client for BYOK and synthesis
        def mock_get_client(config):
            client = MagicMock()

            async def send(messages):
                if config.model_id == "model-byok":
                    return byok_response
                # synthesis
                return SimpleNamespace(
                    content=[TextContent(text="Synthesis")],
                    usage=_make_token_usage(input_tokens=50, output_tokens=30),
                )

            client.send = send
            return client

        # A2A client for system models
        a2a_client = AsyncMock()

        async def mock_astream(*, messages, context_id, metadata):
            yield A2AStreamEvent(
                event_type="assistant.message_delta",
                data={"delta": "System A2A answer"},
            )
            yield A2AStreamEvent(
                event_type="assistant.usage",
                data={
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cost": 0.02,
                    "premium_requests": 1,
                },
            )

        a2a_client.astream = mock_astream

        prefs = _make_council_preferences(
            model_ids=["model-byok", "model-system"], synthesis_model_id="synth"
        )

        mock_settings = MagicMock()
        mock_settings.environment = "production"

        with (
            patch(
                "ii_agent.chat.application.council_service.get_client",
                side_effect=mock_get_client,
            ),
            patch(
                "ii_agent.chat.application.council_service.cancel.raise_if_cancelled",
                new_callable=AsyncMock,
            ),
            patch(
                "ii_agent.chat.application.council_service.get_settings",
                return_value=mock_settings,
            ),
        ):
            events: list[dict] = []
            async for event in CouncilService.stream_council_response(
                user_id=_USER,
                messages=_make_messages(),
                user_question="Hello",
                council_preferences=prefs,
                model_configs={
                    "model-byok": config_byok,
                    "model-system": config_system,
                    "synth": synthesis_config,
                },
                model_names={},
                run_id=str(_RUN),
                session_id=_SESSION,
                a2a_client=a2a_client,
                a2a_backend="copilot",
            ):
                events.append(event)

        member_completes = [e for e in events if e["type"] == "council_member_complete"]
        assert len(member_completes) == 2

        # BYOK member should have billing_backend="native"
        byok_event = next(e for e in member_completes if e["model_id"] == "model-byok")
        assert byok_event["billing_backend"] == "native"
        assert byok_event["content"] == "BYOK answer"
        assert "provider_reported_cost" not in byok_event

        # System member should have billing_backend="a2a:copilot"
        system_event = next(e for e in member_completes if e["model_id"] == "model-system")
        assert system_event["billing_backend"] == "a2a:copilot"
        assert system_event["content"] == "System A2A answer"
        assert system_event["provider_reported_cost"] == 0.02
        assert system_event["premium_requests"] == 1

    @pytest.mark.asyncio
    async def test_direct_path_when_no_a2a_client(self):
        """Without a2a_client, all members use direct path with 'native' billing."""
        config_a = _make_model_config(model_id="model-a")
        config_b = _make_model_config(model_id="model-b")
        synth_config = _make_model_config(model_id="synth")

        usage = _make_token_usage(input_tokens=10, output_tokens=5)

        def mock_get_client(config):
            client = MagicMock()

            async def send(messages):
                return SimpleNamespace(content=[TextContent(text="Direct answer")], usage=usage)

            client.send = send
            return client

        prefs = _make_council_preferences(
            model_ids=["model-a", "model-b"], synthesis_model_id="synth"
        )

        with (
            patch(
                "ii_agent.chat.application.council_service.get_client",
                side_effect=mock_get_client,
            ),
            patch(
                "ii_agent.chat.application.council_service.cancel.raise_if_cancelled",
                new_callable=AsyncMock,
            ),
        ):
            events: list[dict] = []
            async for event in CouncilService.stream_council_response(
                user_id=_USER,
                messages=_make_messages(),
                user_question="Hello",
                council_preferences=prefs,
                model_configs={
                    "model-a": config_a,
                    "model-b": config_b,
                    "synth": synth_config,
                },
                model_names={},
                run_id=str(_RUN),
                session_id=_SESSION,
                # No a2a_client — all direct
            ):
                events.append(event)

        member_completes = [e for e in events if e["type"] == "council_member_complete"]
        assert len(member_completes) == 2
        for event in member_completes:
            assert event["billing_backend"] == "native"
            assert "provider_reported_cost" not in event

        synth_completes = [e for e in events if e["type"] == "council_synthesis_complete"]
        assert len(synth_completes) == 1
        assert synth_completes[0]["billing_backend"] == "native"

    @pytest.mark.asyncio
    async def test_a2a_rate_limit_falls_back_to_direct_path(self):
        """Rate-limited A2A council members should fall back to native inference."""
        from ii_agent.integrations.a2a.as_client import A2AStreamEvent

        config_a = _make_model_config(model_id="model-a")
        config_b = _make_model_config(model_id="model-b")
        synth_config = _make_model_config(model_id="synth")
        usage = _make_token_usage(input_tokens=10, output_tokens=5)

        a2a_client = AsyncMock()

        async def mock_astream(*, messages, context_id, metadata):
            yield A2AStreamEvent(
                event_type="session.error",
                data={"message": "rate limit exceeded"},
            )

        a2a_client.astream = mock_astream

        def mock_get_client(config):
            client = MagicMock()

            async def send(messages):
                return SimpleNamespace(
                    content=[TextContent(text=f"Direct answer for {config.model_id}")],
                    usage=usage,
                )

            client.send = send
            return client

        prefs = _make_council_preferences(
            model_ids=["model-a", "model-b"], synthesis_model_id="synth"
        )

        with (
            patch(
                "ii_agent.chat.application.council_service.get_client",
                side_effect=mock_get_client,
            ),
            patch(
                "ii_agent.chat.application.council_service.cancel.raise_if_cancelled",
                new_callable=AsyncMock,
            ),
        ):
            events: list[dict] = []
            async for event in CouncilService.stream_council_response(
                user_id=_USER,
                messages=_make_messages(),
                user_question="Hello",
                council_preferences=prefs,
                model_configs={
                    "model-a": config_a,
                    "model-b": config_b,
                    "synth": synth_config,
                },
                model_names={},
                run_id=str(_RUN),
                session_id=_SESSION,
                a2a_client=a2a_client,
                a2a_backend="copilot",
            ):
                events.append(event)

        member_completes = [e for e in events if e["type"] == "council_member_complete"]
        assert len(member_completes) == 2
        assert all(e["billing_backend"] == "native" for e in member_completes)

        synth_completes = [e for e in events if e["type"] == "council_synthesis_complete"]
        assert len(synth_completes) == 1
        assert synth_completes[0]["billing_backend"] == "native"


class TestCouncilChatResponseA2ABillingPassthrough:
    """Test that stream_council_chat_response passes A2A billing fields through."""

    def _make_chat_request(self) -> SimpleNamespace:
        return SimpleNamespace(
            session_id=_SESSION,
            content="What is the meaning of life?",
            model_id="claude-sonnet-4-20250514",
            file_ids=None,
            github_repository=None,
            council_preferences=_make_council_preferences(),
            media_preferences=None,
            tools=None,
        )

    @pytest.mark.asyncio
    async def test_a2a_billing_fields_published_and_stripped(self):
        """A2A billing fields should be published in ModelUsageEvent and stripped from frontend events."""
        pubsub = MagicMock()
        published: list = []
        pubsub.publish = AsyncMock(side_effect=published.append)

        svc = _make_chat_service(pubsub=pubsub, credit_service=MagicMock())

        config_a = _make_model_config(model_id="model-a")
        config_b = _make_model_config(model_id="model-b")
        synth_config = _make_model_config(model_id="claude-sonnet-4-20250514")

        svc._check_credits = AsyncMock()
        svc.get_model_config = AsyncMock(
            side_effect=lambda db, model_id, user_id: {
                "model-a": config_a,
                "model-b": config_b,
                "claude-sonnet-4-20250514": synth_config,
            }[model_id]
        )
        svc._model_setting_service = MagicMock()
        svc._model_setting_service.get_all_available_models = AsyncMock(
            return_value=_make_all_models_response()
        )
        svc._message_service.create_message = AsyncMock(return_value=_make_fake_message())
        svc._file_processor.process_uploads = AsyncMock(return_value=None)

        council_events = [
            {
                "type": "council_member_complete",
                "model_id": "model-a",
                "model_name": "Model A",
                "content": "Answer A",
                "usage": _make_token_usage(input_tokens=10, output_tokens=5),
                "model_config": config_a,
                "billing_backend": "a2a:copilot",
                "provider_reported_cost": 0.04,
                "premium_requests": 1,
            },
            {
                "type": "council_member_complete",
                "model_id": "model-b",
                "model_name": "Model B",
                "content": "Answer B",
                "usage": _make_token_usage(input_tokens=20, output_tokens=10),
                "model_config": config_b,
                "billing_backend": "native",
            },
            {
                "type": "council_synthesis_complete",
                "model_id": "claude-sonnet-4-20250514",
                "content": "Synthesis",
                "usage": _make_token_usage(input_tokens=50, output_tokens=30),
                "model_config": synth_config,
                "billing_backend": "a2a:copilot",
                "provider_reported_cost": 0.08,
                "premium_requests": 2,
            },
            {
                "type": "council_result",
                "member_outputs": {"model-a": "Answer A", "model-b": "Answer B"},
                "synthesis_content": "Synthesis",
                "synthesis_model_id": "claude-sonnet-4-20250514",
                "model_names": {},
                "had_error": False,
            },
        ]

        async def mock_council_stream(**kwargs):
            for event in council_events:
                yield event

        with (
            patch("ii_agent.chat.application.chat_service.get_db_session_local") as mock_db_ctx,
            patch("ii_agent.chat.application.chat_service.ContextWindowManager") as mock_ctx,
            patch(
                "ii_agent.chat.application.chat_service.CouncilService.stream_council_response",
                side_effect=mock_council_stream,
            ),
            patch(
                "ii_agent.chat.application.chat_service.cancel.register_run",
                new_callable=AsyncMock,
            ),
            patch(
                "ii_agent.chat.application.chat_service.cancel.cleanup_run",
                new_callable=AsyncMock,
            ),
        ):
            mock_db = MagicMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=False)
            mock_db.commit = AsyncMock()
            mock_db_ctx.return_value = mock_db

            mock_ctx.load_context_for_llm = AsyncMock(return_value=[])
            mock_ctx.check_and_summarize_after_response = AsyncMock()

            events_received = []
            async for event in svc.stream_council_chat_response(
                chat_request=self._make_chat_request(), user_id=_USER
            ):
                events_received.append(event)

        # 3 billing events published
        assert len(published) == 3

        # Verify A2A member has a2a billing backend
        evt_a = next(e for e in published if e.model_id == "model-a")
        assert evt_a.billing_backend == "a2a:copilot"
        assert evt_a.provider_reported_cost == 0.04
        assert evt_a.premium_requests == 1

        # Verify native member has native billing backend
        evt_b = next(e for e in published if e.model_id == "model-b")
        assert evt_b.billing_backend == "native"
        assert evt_b.provider_reported_cost == 0.0
        assert evt_b.premium_requests == 0

        # Verify synthesis has a2a billing backend
        evt_synth = next(e for e in published if e.model_id == "claude-sonnet-4-20250514")
        assert evt_synth.billing_backend == "a2a:copilot"
        assert evt_synth.provider_reported_cost == 0.08
        assert evt_synth.premium_requests == 2

        # Verify billing fields are stripped from frontend events
        frontend_events = [
            e
            for e in events_received
            if e.get("type") in ("council_member_complete", "council_synthesis_complete")
        ]
        for event in frontend_events:
            assert "usage" not in event
            assert "model_config" not in event
            assert "billing_backend" not in event
            assert "provider_reported_cost" not in event
            assert "premium_requests" not in event
