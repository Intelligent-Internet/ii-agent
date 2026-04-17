"""Tests for council_service fallback edge cases.

Covers:
- P3: _should_fallback_to_direct() error marker coverage
- P2: Council synthesis A2A fallback to direct
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.billing.schemas import TokenUsage
from ii_agent.chat.application.council_service import (
    CouncilService,
    _should_fallback_to_direct,
)
from ii_agent.chat.types import (
    CouncilPreferences,
    CouncilModelConfig,
    Message,
    MessageRole,
    TextContent,
)
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.settings.llm.types import ConfigType, Provider

pytestmark = pytest.mark.unit

_USER = uuid.uuid4()
_SESSION = uuid.uuid4()
_RUN = uuid.uuid4()


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_council_billing.py)
# ---------------------------------------------------------------------------


def _make_model_config(
    *,
    model_id: str = "claude-sonnet-4-20250514",
    provider: Provider = Provider.ANTHROPIC,
    config_type: ConfigType = ConfigType.SYSTEM,
) -> ModelConfig:
    return ModelConfig(
        id=uuid.uuid4(),
        model_id=model_id,
        provider=provider,
        pricing=None,
        config_type=config_type,
    )


def _make_token_usage() -> TokenUsage:
    return TokenUsage(input_tokens=10, output_tokens=5)


def _make_council_preferences(
    *,
    model_ids: list[str] | None = None,
    synthesis_model_id: str = "synth",
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


# ===================================================================
# P3: _should_fallback_to_direct — all error markers
# ===================================================================


class TestShouldFallbackToDirect:
    """Parametric tests for every error marker in _should_fallback_to_direct."""

    @pytest.mark.parametrize(
        "error_msg",
        [
            "Execution failed: Error: Failed to list models: 400",
            "Failed to list models: 500",
            "Connection refused",
            "Connection reset by peer",
            "connect ECONNREFUSED 127.0.0.1:3000",
            "Request timeout after 30 seconds",
            "rate limit exceeded",
            "HTTP 429 Too Many Requests",
            "temporary unavailable",
            "Service Unavailable",
            "Server overloaded",
        ],
        ids=[
            "execution_failed",
            "failed_to_list",
            "connection_refused",
            "connection_reset",
            "connect_econnrefused",
            "timeout",
            "rate_limit",
            "http_429",
            "temporary",
            "unavailable",
            "overloaded",
        ],
    )
    def test_should_fallback_on_retriable_error(self, error_msg: str):
        exc = RuntimeError(error_msg)
        assert _should_fallback_to_direct(exc) is True

    @pytest.mark.parametrize(
        "error_msg",
        [
            "Content policy violation",
            "Invalid API key provided",
            "Model not found: gpt-5",
            "Authentication failed",
            "Permission denied",
            "Malformed request body",
        ],
        ids=[
            "content_policy",
            "invalid_api_key",
            "model_not_found",
            "auth_failed",
            "permission_denied",
            "malformed_request",
        ],
    )
    def test_should_not_fallback_on_non_retriable_error(self, error_msg: str):
        exc = RuntimeError(error_msg)
        assert _should_fallback_to_direct(exc) is False

    def test_includes_exception_type_name_in_check(self):
        """The function checks f'{type(exc).__name__}: {exc}', so the type name
        itself can trigger a match (e.g. ConnectionError)."""
        exc = ConnectionError("something broke")
        assert _should_fallback_to_direct(exc) is True

    def test_timeout_error_type_matches(self):
        """TimeoutError type name contains 'timeout'."""
        exc = TimeoutError("deadline exceeded")
        assert _should_fallback_to_direct(exc) is True


# ===================================================================
# P2: Council synthesis A2A fallback to direct
# ===================================================================


class TestCouncilSynthesisFallback:
    """Test that synthesis phase falls back from A2A to direct on error."""

    @pytest.mark.asyncio
    async def test_synthesis_a2a_fails_falls_back_to_direct(self):
        """When synthesis A2A call fails with a retriable error, synthesis
        should fall back to direct LLM and billing_backend should be 'native'."""
        from ii_agent.integrations.a2a.as_client import A2AStreamEvent

        config_a = _make_model_config(model_id="model-a")
        config_b = _make_model_config(model_id="model-b")
        synth_config = _make_model_config(model_id="synth")
        usage = _make_token_usage()

        call_count = 0

        a2a_client = AsyncMock()

        async def mock_astream(*, messages, context_id, metadata):
            nonlocal call_count
            call_count += 1
            if "synthesis" in context_id:
                # Synthesis call fails
                yield A2AStreamEvent(
                    event_type="session.error",
                    data={"message": "Execution failed: Error: Failed to list models: 400"},
                )
            else:
                # Member calls succeed
                yield A2AStreamEvent(
                    event_type="assistant.message",
                    data={"content": f"A2A answer {call_count}"},
                )
                yield A2AStreamEvent(
                    event_type="assistant.usage",
                    data={"input_tokens": 10, "output_tokens": 5, "cost": 0.01},
                )

        a2a_client.astream = mock_astream

        def mock_get_client(config):
            client = MagicMock()

            async def send(messages):
                return SimpleNamespace(
                    content=[TextContent(text="Direct synthesis output")],
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

        # Members should succeed via A2A
        member_completes = [e for e in events if e["type"] == "council_member_complete"]
        assert len(member_completes) == 2
        assert all(e["billing_backend"] == "a2a:copilot" for e in member_completes)

        # Synthesis should fall back to native
        synth_completes = [e for e in events if e["type"] == "council_synthesis_complete"]
        assert len(synth_completes) == 1
        assert synth_completes[0]["billing_backend"] == "native"
        assert synth_completes[0]["content"] == "Direct synthesis output"

        # Council result should be present
        results = [e for e in events if e["type"] == "council_result"]
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_all_members_and_synthesis_fallback_to_direct(self):
        """Full cascade: all A2A calls fail, everything falls back to native."""
        from ii_agent.integrations.a2a.as_client import A2AStreamEvent

        config_a = _make_model_config(model_id="model-a")
        config_b = _make_model_config(model_id="model-b")
        synth_config = _make_model_config(model_id="synth")
        usage = _make_token_usage()

        a2a_client = AsyncMock()

        async def mock_astream(*, messages, context_id, metadata):
            # All A2A calls fail
            yield A2AStreamEvent(
                event_type="session.error",
                data={"message": "Execution failed: Error: Failed to list models: 400"},
            )

        a2a_client.astream = mock_astream

        def mock_get_client(config):
            client = MagicMock()

            async def send(messages):
                return SimpleNamespace(
                    content=[TextContent(text=f"Direct {config.model_id}")],
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

        # All members and synthesis should be native
        member_completes = [e for e in events if e["type"] == "council_member_complete"]
        assert len(member_completes) == 2
        assert all(e["billing_backend"] == "native" for e in member_completes)

        synth_completes = [e for e in events if e["type"] == "council_synthesis_complete"]
        assert len(synth_completes) == 1
        assert synth_completes[0]["billing_backend"] == "native"

    @pytest.mark.asyncio
    async def test_synthesis_non_retriable_error_raises(self):
        """A non-retriable synthesis A2A error should propagate, not fall back."""
        from ii_agent.integrations.a2a.as_client import A2AStreamEvent

        config_a = _make_model_config(model_id="model-a")
        config_b = _make_model_config(model_id="model-b")
        synth_config = _make_model_config(model_id="synth")

        a2a_client = AsyncMock()

        call_count = 0

        async def mock_astream(*, messages, context_id, metadata):
            nonlocal call_count
            call_count += 1
            if "synthesis" in context_id:
                # Non-retriable error (content policy) — should NOT fall back
                yield A2AStreamEvent(
                    event_type="session.error",
                    data={"message": "Content policy violation: request blocked"},
                )
            else:
                yield A2AStreamEvent(
                    event_type="assistant.message",
                    data={"content": f"A2A answer {call_count}"},
                )
                yield A2AStreamEvent(
                    event_type="assistant.usage",
                    data={"input_tokens": 10, "output_tokens": 5},
                )

        a2a_client.astream = mock_astream

        prefs = _make_council_preferences(
            model_ids=["model-a", "model-b"], synthesis_model_id="synth"
        )

        with (
            patch(
                "ii_agent.chat.application.council_service.cancel.raise_if_cancelled",
                new_callable=AsyncMock,
            ),
        ):
            with pytest.raises(RuntimeError, match="Content policy violation"):
                async for _ in CouncilService.stream_council_response(
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
                    pass
