"""Tests for CreditUsageHandler billing_enabled toggle and backend-aware billing."""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.core.config.agent import AgentSettings
from ii_agent.credits.usage.handler import CreditUsageHandler, _USD_TO_CREDITS
from ii_agent.realtime.events.app_events import ModelUsageEvent, ToolUsageEvent
from ii_agent.settings.llm.schemas import PricingInfo

_USER = uuid.uuid4()
_SESSION = uuid.uuid4()
_RUN = uuid.uuid4()
_SETTING = uuid.uuid4()


def _make_handler(
    *, billing_enabled: bool = True, agent_settings: AgentSettings | None = None
) -> CreditUsageHandler:
    return CreditUsageHandler(
        credit_service=MagicMock(),
        pubsub=MagicMock(),
        billing_enabled=billing_enabled,
        agent_settings=agent_settings,
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


# ---------------------------------------------------------------------------
# Backend-aware billing strategy tests
# ---------------------------------------------------------------------------

_SONNET_PRICING = PricingInfo(
    input_price_per_million=3.0,
    output_price_per_million=15.0,
    cache_write_price_per_million=3.75,
    cache_read_price_per_million=0.3,
)


def _a2a_model_event(**overrides) -> ModelUsageEvent:
    defaults = dict(
        user_id=_USER,
        session_id=_SESSION,
        run_id=_RUN,
        setting_id=_SETTING,
        model_id="claude-sonnet-4-20250514",
        input_tokens=1_000_000,
        output_tokens=100_000,
        cache_read_tokens=0,
        cache_write_tokens=0,
        reasoning_tokens=0,
        is_user_key=False,
        pricing=_SONNET_PRICING,
        billing_backend="a2a:copilot",
        provider_reported_cost=0.0,
        premium_requests=1,
    )
    defaults.update(overrides)
    return ModelUsageEvent(**defaults)


class TestBackendAwareBilling:
    """CreditUsageHandler applies the correct billing strategy per backend."""

    def test_native_backend_uses_token_based(self) -> None:
        """Native events always use token-based pricing, ignoring agent_settings."""
        settings = AgentSettings(a2a_billing_strategy="none")
        handler = _make_handler(agent_settings=settings)
        event = _model_event(pricing=_SONNET_PRICING, billing_backend="native")

        credits = handler._calculate_credits_for_event(event)

        # 100 input tokens at $3/MTok + 50 output at $15/MTok
        expected_usd = Decimal("100") * Decimal("3.0") / Decimal("1_000_000") + Decimal(
            "50"
        ) * Decimal("15.0") / Decimal("1_000_000")
        expected = expected_usd * _USD_TO_CREDITS
        assert credits == expected

    def test_a2a_strategy_none_returns_zero(self) -> None:
        """When a2a_billing_strategy='none', A2A turns are free."""
        settings = AgentSettings(a2a_billing_strategy="none")
        handler = _make_handler(agent_settings=settings)
        event = _a2a_model_event()

        credits = handler._calculate_credits_for_event(event)

        assert credits == Decimal("0")

    def test_a2a_strategy_token_based_with_multiplier(self) -> None:
        """token_based strategy applies the multiplier to normal token cost."""
        settings = AgentSettings(
            a2a_billing_strategy="token_based",
            a2a_billing_multiplier=0.5,
        )
        handler = _make_handler(agent_settings=settings)
        event = _a2a_model_event()

        credits = handler._calculate_credits_for_event(event)

        # Full token cost
        full = handler._calculate_llm_credits(event)
        assert credits == full * Decimal("0.5")

    def test_a2a_strategy_token_based_default_multiplier(self) -> None:
        """With default multiplier (1.0), A2A token_based == native pricing."""
        settings = AgentSettings(a2a_billing_strategy="token_based")
        handler = _make_handler(agent_settings=settings)
        event = _a2a_model_event()

        credits = handler._calculate_credits_for_event(event)

        full = handler._calculate_llm_credits(event)
        assert credits == full

    def test_a2a_strategy_provider_reported_copilot(self) -> None:
        """Provider-reported Copilot billing: premium_requests × multiplier × overage_price."""
        settings = AgentSettings(
            a2a_billing_strategy="provider_reported",
            a2a_copilot_premium_request_cost=0.04,
            a2a_copilot_multipliers={"claude-sonnet": 1.0, "claude-opus": 3.0},
        )
        handler = _make_handler(agent_settings=settings)
        event = _a2a_model_event(premium_requests=1)

        credits = handler._calculate_credits_for_event(event)

        # 1 premium request × 1.0 multiplier × $0.04 = $0.04
        expected = Decimal("0.04") * _USD_TO_CREDITS
        assert credits == expected

    def test_a2a_strategy_provider_reported_copilot_zero_premium_requests(self) -> None:
        """Copilot provider_reported: 0 premium requests (cached/small) = no charge."""
        settings = AgentSettings(
            a2a_billing_strategy="provider_reported",
            a2a_copilot_premium_request_cost=0.04,
            a2a_copilot_multipliers={"claude-sonnet": 1.0},
        )
        handler = _make_handler(agent_settings=settings)
        event = _a2a_model_event(premium_requests=0)

        credits = handler._calculate_credits_for_event(event)

        assert credits == Decimal("0")

    def test_a2a_strategy_provider_reported_copilot_opus_multiplier(self) -> None:
        """Copilot provider_reported: Opus 3× multiplier applied correctly."""
        settings = AgentSettings(
            a2a_billing_strategy="provider_reported",
            a2a_copilot_premium_request_cost=0.04,
            a2a_copilot_multipliers={"claude-sonnet": 1.0, "claude-opus": 3.0},
        )
        handler = _make_handler(agent_settings=settings)
        event = _a2a_model_event(model_id="claude-opus-4-6", premium_requests=1)

        credits = handler._calculate_credits_for_event(event)

        # 1 premium request × 3.0 multiplier × $0.04 = $0.12
        expected = Decimal("1") * Decimal("3.0") * Decimal("0.04") * _USD_TO_CREDITS
        assert credits == expected

    def test_a2a_strategy_provider_reported_generic_backend(self) -> None:
        """Non-Copilot A2A backend uses provider_reported_cost directly."""
        settings = AgentSettings(a2a_billing_strategy="provider_reported")
        handler = _make_handler(agent_settings=settings)
        event = _a2a_model_event(
            billing_backend="a2a:claude-code",
            provider_reported_cost=0.70,
        )

        credits = handler._calculate_credits_for_event(event)

        expected = Decimal("0.70") * _USD_TO_CREDITS
        assert credits == expected

    def test_a2a_no_agent_settings_falls_through_to_token_based(self) -> None:
        """When agent_settings is None (chat path), A2A events use token-based."""
        handler = _make_handler(agent_settings=None)
        event = _a2a_model_event()

        credits = handler._calculate_credits_for_event(event)

        full = handler._calculate_llm_credits(event)
        assert credits == full

    def test_copilot_multiplier_longest_prefix_match(self) -> None:
        """Copilot multiplier resolution picks longest matching prefix."""
        settings = AgentSettings(
            a2a_billing_strategy="provider_reported",
            a2a_copilot_multipliers={
                "claude-sonnet": 1.0,
                "claude-sonnet-4-6": 1.5,
            },
            a2a_copilot_premium_request_cost=0.04,
        )
        handler = _make_handler(agent_settings=settings)

        # Should match "claude-sonnet-4-6" (longer), not "claude-sonnet"
        mult = handler._resolve_copilot_multiplier("claude-sonnet-4-6-20250514")
        assert mult == 1.5

    def test_copilot_multiplier_defaults_to_1(self) -> None:
        """Unknown model defaults to multiplier 1.0."""
        settings = AgentSettings(
            a2a_billing_strategy="provider_reported",
            a2a_copilot_multipliers={"claude-sonnet": 1.0},
        )
        handler = _make_handler(agent_settings=settings)

        mult = handler._resolve_copilot_multiplier("unknown-model-xyz")
        assert mult == 1.0


# ---------------------------------------------------------------------------
# Non-zero premium-request and multiplier matrix
# ---------------------------------------------------------------------------


class TestCopilotPremiumRequestMultiplierMatrix:
    """Parametrised tests for Copilot premium-request billing with multipliers."""

    @pytest.mark.parametrize(
        "model_id, premium_requests, multipliers, expected_usd",
        [
            # 2 premium reqs × sonnet 1.0 × $0.04 = $0.08
            (
                "claude-sonnet-4-20250514",
                2,
                {"claude-sonnet": 1.0},
                Decimal("0.08"),
            ),
            # 5 premium reqs × opus 3.0 × $0.04 = $0.60
            (
                "claude-opus-4-6",
                5,
                {"claude-opus": 3.0},
                Decimal("0.60"),
            ),
            # 1 premium req × custom 2.5 × $0.04 = $0.10
            (
                "claude-sonnet-4-6-20260101",
                1,
                {"claude-sonnet-4-6": 2.5},
                Decimal("0.10"),
            ),
            # Model not in map → default 1.0: 3 reqs × 1.0 × $0.04 = $0.12
            (
                "llama-unknown-70b",
                3,
                {"claude-sonnet": 1.0},
                Decimal("0.12"),
            ),
        ],
        ids=["sonnet-2reqs", "opus-5reqs", "custom-multiplier", "unknown-model-fallback"],
    )
    def test_premium_request_multiplier_combinations(
        self,
        model_id: str,
        premium_requests: int,
        multipliers: dict,
        expected_usd: Decimal,
    ) -> None:
        settings = AgentSettings(
            a2a_billing_strategy="provider_reported",
            a2a_copilot_premium_request_cost=0.04,
            a2a_copilot_multipliers=multipliers,
        )
        handler = _make_handler(agent_settings=settings)
        event = _a2a_model_event(
            model_id=model_id,
            premium_requests=premium_requests,
        )

        credits = handler._calculate_credits_for_event(event)

        expected = expected_usd * _USD_TO_CREDITS
        assert credits == expected

    def test_custom_overage_price(self) -> None:
        """Non-default overage price ($0.10) applied correctly."""
        settings = AgentSettings(
            a2a_billing_strategy="provider_reported",
            a2a_copilot_premium_request_cost=0.10,
            a2a_copilot_multipliers={"claude-sonnet": 1.0},
        )
        handler = _make_handler(agent_settings=settings)
        event = _a2a_model_event(premium_requests=2)

        credits = handler._calculate_credits_for_event(event)

        # 2 × 1.0 × $0.10 = $0.20
        expected = Decimal("0.20") * _USD_TO_CREDITS
        assert credits == expected
