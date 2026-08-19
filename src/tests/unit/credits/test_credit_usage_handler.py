"""Tests for CreditUsageHandler billing_enabled toggle and backend-aware billing."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.credits.usage.handler import CreditUsageHandler
from ii_agent.realtime.events.app_events import ModelUsageEvent, ToolUsageEvent

_USER = uuid.uuid4()
_SESSION = uuid.uuid4()
_RUN = uuid.uuid4()
_SETTING = uuid.uuid4()


def _make_handler(
    *, billing_enabled: bool = True,
) -> CreditUsageHandler:
    return CreditUsageHandler(
        credit_service=MagicMock(),
        pubsub=MagicMock(),
        billing_enabled=billing_enabled,
    )


def _model_event(**overrides) -> ModelUsageEvent:
    defaults = dict(
        user_id=_USER,
        session_id=_SESSION,
        run_id=_RUN,
        setting_id=_SETTING,
        model_id="claude-sonnet-4-20250514",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        is_user_key=False,
    )
    defaults.update(overrides)
    return ModelUsageEvent(**defaults)


def _tool_event(**overrides) -> ToolUsageEvent:
    defaults = dict(
        user_id=_USER,
        session_id=_SESSION,
        run_id=_RUN,
        tool_name="web_search",
        cost_usd=0.01,
    )
    defaults.update(overrides)
    return ToolUsageEvent(**defaults)


class TestBillingEnabledToggle:
    """CreditUsageHandler respects the billing_enabled flag."""

    @pytest.mark.asyncio
    async def test_billing_disabled_skips_model_event(self) -> None:
        handler = _make_handler(billing_enabled=False)
        handler._handle_llm_usage = AsyncMock()

        await handler.on_event(_model_event())

        handler._handle_llm_usage.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_billing_disabled_skips_tool_event(self) -> None:
        handler = _make_handler(billing_enabled=False)
        handler._handle_tool_usage = AsyncMock()

        await handler.on_event(_tool_event())

        handler._handle_tool_usage.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_billing_enabled_processes_model_event(self) -> None:
        handler = _make_handler(billing_enabled=True)
        handler._handle_llm_usage = AsyncMock()

        await handler.on_event(_model_event())

        handler._handle_llm_usage.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_billing_enabled_processes_tool_event(self) -> None:
        handler = _make_handler(billing_enabled=True)
        handler._handle_tool_usage = AsyncMock()

        await handler.on_event(_tool_event())

        handler._handle_tool_usage.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_billing_disabled_ignores_unrecognised_event(self) -> None:
        handler = _make_handler(billing_enabled=False)
        event = MagicMock()

        await handler.on_event(event)
        # No error, no processing

    @pytest.mark.asyncio
    async def test_default_billing_enabled_is_true(self) -> None:
        handler = CreditUsageHandler(
            credit_service=MagicMock(),
            pubsub=MagicMock(),
        )
        assert handler._billing_enabled is True
