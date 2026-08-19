from __future__ import annotations

from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest

from ii_agent.chat.application.council_service import CouncilService
from ii_agent.chat.types import (
    CouncilModelConfig,
    CouncilPreferences,
    FinishReason,
    Message,
    MessageRole,
    RunResponseOutput,
    TextContent,
)
from ii_agent.billing.schemas import TokenUsage
from ii_agent.settings.llm import Provider
from ii_agent.core.config.llm_config import LLMConfig

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skip(reason="Pre-existing: test written for unreleased council_service API (llm_configs param)"),
]


_TEST_SESSION_ID = str(uuid4())


def _make_message(session_id: str = _TEST_SESSION_ID) -> Message:
    return Message(
        id=uuid4(),
        role=MessageRole.USER,
        session_id=session_id,
        parts=[TextContent(text="How should we solve this?")],
        created_at=0,
        updated_at=0,
    )


def _make_preferences() -> CouncilPreferences:
    return CouncilPreferences(
        enabled=True,
        council_models=[
            CouncilModelConfig(model_id="member-1"),
            CouncilModelConfig(model_id="member-2"),
        ],
        synthesis_model_id="synth-1",
    )


def _make_llm_configs() -> dict[str, LLMConfig]:
    return {
        "member-1": LLMConfig(model="member-1", provider=Provider.OPENAI),
        "member-2": LLMConfig(model="member-2", provider=Provider.OPENAI),
        "synth-1": LLMConfig(model="synth-1", provider=Provider.OPENAI),
    }


def _make_response(content: str) -> RunResponseOutput:
    return RunResponseOutput(
        content=[TextContent(text=content)],
        usage=TokenUsage(input_tokens=10, output_tokens=5),
        finish_reason=FinishReason.END_TURN,
    )


def _make_client_factory(response_map: dict[str, str]):
    """Return a get_client replacement that produces fake clients keyed by model."""

    def _factory(config: LLMConfig):
        model_id = config.model
        client = AsyncMock()
        if model_id in response_map:
            client.send = AsyncMock(return_value=_make_response(response_map[model_id]))
        else:
            client.send = AsyncMock(return_value=_make_response(""))
        return client

    return _factory


@pytest.mark.asyncio
async def test_stream_council_response_completes_all_models(monkeypatch):
    monkeypatch.setattr(
        "ii_agent.chat.application.council_service.cancel.raise_if_cancelled",
        AsyncMock(return_value=None),
    )

    response_map = {
        "member-1": "Alpha",
        "member-2": "Beta",
        "synth-1": "Combined",
    }

    with patch(
        "ii_agent.chat.application.council_service.get_client",
        side_effect=_make_client_factory(response_map),
    ):
        events = [
            event
            async for event in CouncilService.stream_council_response(
                user_id="user-1",
                messages=[_make_message()],
                user_question="How should we solve this?",
                council_preferences=_make_preferences(),
                llm_configs=_make_llm_configs(),
                model_names={
                    "member-1": "Model One",
                    "member-2": "Model Two",
                    "synth-1": "Synth Model",
                },
                run_id="run-123",
                session_id=_TEST_SESSION_ID,
            )
        ]

    assert any(
        event["type"] == "council_synthesis_complete" and event["content"] == "Combined"
        for event in events
    )

    result_event = next(event for event in events if event["type"] == "council_result")
    assert result_event["member_outputs"] == {
        "member-1": "Alpha",
        "member-2": "Beta",
    }
    assert result_event["synthesis_content"] == "Combined"
    assert result_event["had_error"] is False


@pytest.mark.asyncio
async def test_stream_council_response_handles_member_error(monkeypatch):
    monkeypatch.setattr(
        "ii_agent.chat.application.council_service.cancel.raise_if_cancelled",
        AsyncMock(return_value=None),
    )

    def _error_factory(config: LLMConfig):
        model_id = config.model
        client = AsyncMock()
        if model_id == "member-1":
            client.send = AsyncMock(side_effect=RuntimeError("provider boom"))
        elif model_id == "member-2":
            client.send = AsyncMock(return_value=_make_response("Stable answer"))
        elif model_id == "synth-1":
            client.send = AsyncMock(return_value=_make_response("Summary"))
        else:
            client.send = AsyncMock(return_value=_make_response(""))
        return client

    with patch(
        "ii_agent.chat.application.council_service.get_client",
        side_effect=_error_factory,
    ):
        events = [
            event
            async for event in CouncilService.stream_council_response(
                user_id="user-1",
                messages=[_make_message()],
                user_question="How should we solve this?",
                council_preferences=_make_preferences(),
                llm_configs=_make_llm_configs(),
                model_names={
                    "member-1": "Model One",
                    "member-2": "Model Two",
                    "synth-1": "Synth Model",
                },
                run_id="run-456",
                session_id=_TEST_SESSION_ID,
            )
        ]

    assert any(
        event["type"] == "council_member_error"
        and event["model_id"] == "member-1"
        and event["error"] == "provider boom"
        for event in events
    )

    result_event = next(event for event in events if event["type"] == "council_result")
    assert result_event["member_outputs"] == {"member-2": "Stable answer"}
    assert result_event["synthesis_content"] == "Summary"
    assert result_event["had_error"] is True
