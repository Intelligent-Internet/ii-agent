"""Event-driven credit usage handler.

Subscribes to ``ModelUsageEvent`` and ``ToolUsageEvent`` on the pub/sub bus.
For each event it:
1. Calculates the credit cost (via ``PricingInfo`` / USD conversion).
2. Atomically deducts credits via ``CreditService``.
3. Publishes ``CreditsDeductedEvent`` for frontend balance updates + audit.
4. Cancels the agent run if the user's balance is exhausted.

Backend-aware billing
---------------------
When ``billing_backend`` on a ``ModelUsageEvent`` starts with ``"a2a:"``,
the handler consults ``AgentSettings`` for the configured billing strategy
(``a2a_billing_strategy``).  Three modes are supported:

* **token_based** (default): same PricingInfo × token-count calculation as
  native, optionally scaled by ``a2a_billing_multiplier``.
* **provider_reported**: uses the cost / premium-request data reported by the
  backend, converted to credits.  For Copilot this means
  ``premium_requests × multiplier × overage_price``.
* **none**: no LLM billing for A2A-served turns (subscription covers it).
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from ii_agent.core.config.agent import AgentSettings
from ii_agent.core.db import get_db_session_local
from ii_agent.core.redis.cancel import cancel_run
from ii_agent.credits.constants import MINIMUM_REQUIRED_CREDITS
from ii_agent.credits.service import CreditService
from ii_agent.settings.llm import PricingInfo
from ii_agent.credits.types import TransactionType
from ii_agent.realtime.events.app_events import (
    BaseEvent,
    CreditsDeductedEvent,
    ErrorCode,
    ModelUsageEvent,
    SystemErrorEvent,
    ToolUsageEvent,
)
from ii_agent.realtime.pubsub.callbacks import EventCallbackHandler

if TYPE_CHECKING:
    from ii_agent.realtime.pubsub.asyncio_pubsub import AsyncIOPubSub

logger = logging.getLogger(__name__)

# Conversion: 1 USD = 100 / 1.5 credits  (matches v1/utils/credit.py)
_USD_TO_CREDITS = Decimal("100") / Decimal("1.5")


class CreditUsageHandler(EventCallbackHandler):
    """Pub/sub subscriber that deducts credits for LLM and tool usage."""

    def __init__(
        self,
        *,
        credit_service: CreditService,
        pubsub: AsyncIOPubSub,
        billing_enabled: bool = True,
        agent_settings: AgentSettings | None = None,
    ) -> None:
        self._credit_service = credit_service
        self._pubsub = pubsub
        self._billing_enabled = billing_enabled
        self._agent_settings = agent_settings

    async def on_event(self, event: BaseEvent) -> None:
        if not self._billing_enabled:
            return
        if isinstance(event, ModelUsageEvent):
            await self._handle_llm_usage(event)
        elif isinstance(event, ToolUsageEvent):
            await self._handle_tool_usage(event)

    # ------------------------------------------------------------------
    # LLM token usage
    # ------------------------------------------------------------------

    async def _handle_llm_usage(self, event: ModelUsageEvent) -> None:
        try:
            # Skip LLM charge for user-provided API keys
            if event.is_user_key:
                logger.debug(
                    "Skipping LLM charge for user-provided key (session=%s, model=%s)",
                    event.session_id,
                    event.model_id,
                )
                return

            credits = self._calculate_credits_for_event(event)
            if credits <= Decimal("0"):
                return

            metadata = {
                "source": TransactionType.LLM_USAGE,
                "model_id": event.model_id,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "cache_read_tokens": event.cache_read_tokens,
                "cache_write_tokens": event.cache_write_tokens,
                "reasoning_tokens": event.reasoning_tokens,
            }

            remaining = await self._deduct_and_notify(
                user_id=event.user_id,
                session_id=event.session_id,
                run_id=event.run_id,
                amount=credits,
                transaction_type=TransactionType.LLM_USAGE,
                model_id=event.model_id,
                description=f"LLM usage: {event.model_id}",
                metadata=metadata,
                source=TransactionType.LLM_USAGE,
                audit_fields={
                    "model_id": event.model_id,
                    "input_tokens": event.input_tokens,
                    "output_tokens": event.output_tokens,
                    "cache_read_tokens": event.cache_read_tokens,
                    "cache_write_tokens": event.cache_write_tokens,
                },
            )

            if remaining is not None and remaining < MINIMUM_REQUIRED_CREDITS:
                await self._cancel_for_exhaustion(event.run_id, event.session_id)

        except Exception:
            logger.exception(
                "Failed to process LLM usage event (session=%s, run=%s)",
                event.session_id,
                event.run_id,
            )

    # ------------------------------------------------------------------
    # Tool usage
    # ------------------------------------------------------------------

    async def _handle_tool_usage(self, event: ToolUsageEvent) -> None:
        try:
            if event.cost_usd <= 0:
                return

            credits = Decimal(str(event.cost_usd)) * _USD_TO_CREDITS
            if credits <= Decimal("0"):
                return

            metadata = {
                "source": TransactionType.TOOL_USAGE,
                "tool_name": event.tool_name,
                "cost_usd": event.cost_usd,
            }

            remaining = await self._deduct_and_notify(
                user_id=event.user_id,
                session_id=event.session_id,
                run_id=event.run_id,
                amount=credits,
                transaction_type=TransactionType.TOOL_USAGE,
                description=f"Tool usage: {event.tool_name}",
                metadata=metadata,
                source=TransactionType.TOOL_USAGE,
                audit_fields={
                    "tool_name": event.tool_name,
                },
            )

            if remaining is not None and remaining < MINIMUM_REQUIRED_CREDITS:
                await self._cancel_for_exhaustion(event.run_id, event.session_id)

        except Exception:
            logger.exception(
                "Failed to process tool usage event (session=%s, tool=%s)",
                event.session_id,
                event.tool_name,
            )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _calculate_credits_for_event(self, event: ModelUsageEvent) -> Decimal:
        """Route to the appropriate billing strategy based on backend.

        For ``"native"`` and any unrecognised backend, falls through to the
        standard token-based calculation.  For A2A backends, the configured
        ``a2a_billing_strategy`` in :class:`AgentSettings` determines whether
        billing uses tokens, the provider-reported cost, or is skipped.
        """
        if not event.billing_backend.startswith("a2a:") or self._agent_settings is None:
            return self._calculate_llm_credits(event)

        strategy = self._agent_settings.a2a_billing_strategy

        if strategy == "none":
            logger.debug(
                "A2A billing strategy 'none': skipping charge for %s (session=%s)",
                event.billing_backend,
                event.session_id,
            )
            return Decimal("0")

        if strategy == "provider_reported":
            return self._calculate_provider_reported_credits(event)

        # Default: token_based with optional multiplier
        credits = self._calculate_llm_credits(event)
        multiplier = Decimal(str(self._agent_settings.a2a_billing_multiplier))
        if multiplier != Decimal("1"):
            logger.debug(
                "A2A token_based billing: applying multiplier %.3f (session=%s)",
                multiplier,
                event.session_id,
            )
        return credits * multiplier

    def _calculate_provider_reported_credits(self, event: ModelUsageEvent) -> Decimal:
        """Calculate credits from the backend's own cost/premium-request data.

        For Copilot: ``premium_requests × model_multiplier × overage_price``.
        For other A2A backends: uses ``provider_reported_cost`` directly.
        """
        assert self._agent_settings is not None  # noqa: S101

        if event.billing_backend == "a2a:copilot":
            # Resolve Copilot premium request multiplier for this model
            multiplier = self._resolve_copilot_multiplier(event.model_id)
            premium_cost = Decimal(str(self._agent_settings.a2a_copilot_premium_request_cost))
            # Use 0 as floor — Copilot may report 0 premium requests for cached/small responses
            effective_requests = Decimal(str(max(event.premium_requests, 0))) * Decimal(
                str(multiplier)
            )
            # If no premium requests were used, no charge
            if effective_requests == 0:
                logger.debug(
                    "Copilot provider_reported billing: model=%s premium_requests=0, no charge",
                    event.model_id,
                )
                return Decimal("0")
            total_usd = effective_requests * premium_cost
            logger.debug(
                "Copilot provider_reported billing: model=%s multiplier=%.2f "
                "premium_requests=%d effective=%.2f cost_usd=%.4f",
                event.model_id,
                multiplier,
                event.premium_requests,
                float(effective_requests),
                float(total_usd),
            )
            return total_usd * _USD_TO_CREDITS

        # Generic A2A backend: use the cost field the adapter reported
        if event.provider_reported_cost > 0:
            return Decimal(str(event.provider_reported_cost)) * _USD_TO_CREDITS

        # Fallback to token-based if backend didn't report cost
        logger.warning(
            "A2A backend '%s' reported no cost; falling back to token-based billing",
            event.billing_backend,
        )
        return self._calculate_llm_credits(event)

    def _resolve_copilot_multiplier(self, model_id: str) -> float:
        """Look up the Copilot premium-request multiplier for a model.

        Matches by longest prefix from the configurable multiplier table.
        """
        assert self._agent_settings is not None  # noqa: S101
        multipliers = self._agent_settings.a2a_copilot_multipliers
        normalized = model_id.lower()
        best_match = ""
        best_value = 1.0
        for prefix, value in multipliers.items():
            if normalized.startswith(prefix) and len(prefix) > len(best_match):
                best_match = prefix
                best_value = value
        if not best_match:
            logger.warning(
                "No Copilot multiplier for model '%s'; defaulting to 1.0",
                model_id,
            )
        return best_value

    def _calculate_llm_credits(self, event: ModelUsageEvent) -> Decimal:
        """Calculate credit cost from token counts using PricingInfo.

        Prefers DB-configured pricing from the event (set by the LLM turn loop
        from model_config.pricing). Falls back to hardcoded defaults only when
        the event carries no pricing.
        """
        pricing = event.pricing or PricingInfo.get_default_pricing(event.model_id, event.provider)

        input_cost = (
            Decimal(event.input_tokens)
            * Decimal(str(pricing.input_price_per_million))
            / Decimal("1_000_000")
        )
        output_cost = (
            Decimal(event.output_tokens)
            * Decimal(str(pricing.output_price_per_million))
            / Decimal("1_000_000")
        )
        cache_read_cost = (
            Decimal(event.cache_read_tokens)
            * Decimal(str(pricing.cache_read_price_per_million))
            / Decimal("1_000_000")
        )
        cache_write_cost = (
            Decimal(event.cache_write_tokens)
            * Decimal(str(pricing.cache_write_price_per_million))
            / Decimal("1_000_000")
        )
        # Reasoning tokens are billed at the output token rate
        reasoning_cost = (
            Decimal(event.reasoning_tokens)
            * Decimal(str(pricing.output_price_per_million))
            / Decimal("1_000_000")
        )

        total_usd = input_cost + output_cost + cache_read_cost + cache_write_cost + reasoning_cost
        return total_usd * _USD_TO_CREDITS

    async def _deduct_and_notify(
        self,
        *,
        user_id: uuid.UUID | None,
        session_id: uuid.UUID | None,
        run_id: uuid.UUID | None,
        amount: Decimal,
        transaction_type: TransactionType,
        model_id: str | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        source: TransactionType,
        audit_fields: dict[str, Any] | None = None,
    ) -> Decimal | None:
        """Deduct credits and publish ``CreditsDeductedEvent``.

        Returns the remaining balance (``Decimal``) on success,
        or ``None`` if the deduction failed.
        """
        if user_id is None:
            return None

        async with get_db_session_local() as db:
            try:
                await self._credit_service.deduct(
                    db,
                    user_id=user_id,
                    amount=amount,
                    transaction_type=transaction_type,
                    session_id=session_id,
                    run_id=run_id,
                    model_id=model_id,
                    description=description,
                    metadata=metadata,
                )
                await db.commit()
                balance = await self._credit_service.get_balance(db, user_id)
            except Exception:
                logger.warning(
                    "Credit deduction failed for user %s",
                    user_id,
                    exc_info=True,
                )
                return None

        if balance is None:
            logger.error(
                "get_balance returned None after successful deduct for user %s",
                user_id,
            )
            return None

        remaining = Decimal(str(balance.credits + balance.bonus_credits))

        await self._pubsub.publish(
            CreditsDeductedEvent(
                session_id=session_id,
                user_id=user_id,
                run_id=run_id,
                credits_used=float(amount),
                credits_remaining=float(remaining),
                source=source,
                content={
                    "credits_used": float(amount),
                    "credits_remaining": float(remaining),
                    "source": source,
                    **(audit_fields or {}),
                },
                **(audit_fields or {}),
            )
        )

        return remaining

    async def _cancel_for_exhaustion(
        self,
        run_id: uuid.UUID | None,
        session_id: uuid.UUID | None,
    ) -> None:
        """Cancel the active run and notify the frontend."""
        if run_id is not None:
            await cancel_run(str(run_id))
            logger.info("Cancelled run %s due to credit exhaustion", run_id)

        if session_id is not None:
            await self._pubsub.publish(
                SystemErrorEvent(
                    session_id=session_id,
                    error_code=ErrorCode.INSUFFICIENT_CREDITS,
                    detail="Insufficient credits. Please add more credits to continue.",
                    recoverable=False,
                )
            )
