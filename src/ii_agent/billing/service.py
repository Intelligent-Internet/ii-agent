"""Billing service – Stripe checkout sessions, portal, and webhook handling."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import stripe
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.exceptions import (
    BillingConfigurationError,
    BillingGatewayError,
    BillingServiceError,
    BillingUnsupportedPlanError,
    StripeConfigError,
)
from ii_agent.billing.models import BillingTransaction
from ii_agent.billing.schemas import (
    BillingCycle,
    CheckoutResult,
    CreateCheckoutParams,
    CreatePortalParams,
    PlanId,
    PortalResult,
)
from ii_agent.core.config.settings import Settings
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.users.models import User

# Stripe interval → canonical billing cycle mapping
_INTERVAL_TO_CYCLE: dict[str, str] = {
    "month": BillingCycle.MONTHLY,
    "monthly": BillingCycle.MONTHLY,
    "year": BillingCycle.ANNUALLY,
    "annually": BillingCycle.ANNUALLY,
}


class BillingService:
    """Stripe checkout / portal / webhook integration.

    All public methods accept Pydantic DTOs and return Pydantic DTOs.
    ORM models are only used internally within private helper methods.
    """

    def __init__(self, *, settings: Settings) -> None:
        self._stripe = settings.stripe
        self._credits = settings.credits
        self._price_map: dict[str, dict[str, str | None]] = {
            PlanId.PLUS: {
                BillingCycle.MONTHLY: self._stripe.price_plus_monthly,
                BillingCycle.ANNUALLY: self._stripe.price_plus_annually,
            },
            PlanId.PRO: {
                BillingCycle.MONTHLY: self._stripe.price_pro_monthly,
                BillingCycle.ANNUALLY: self._stripe.price_pro_annually,
            },
        }

    # ------------------------------------------------------------------
    # Stripe API helpers (private)
    # ------------------------------------------------------------------

    def _ensure_api_key(self) -> None:
        if not self._stripe.secret_key:
            raise StripeConfigError("Stripe secret key is not configured")
        if stripe.api_key != self._stripe.secret_key:
            stripe.api_key = self._stripe.secret_key

    def _get_price_id(self, plan_id: str, billing_cycle: str) -> str:
        plan_prices = self._price_map.get(plan_id)
        if not plan_prices:
            raise BillingUnsupportedPlanError(f"Plan '{plan_id}' is not available for upgrade")
        price_id = plan_prices.get(billing_cycle)
        if not price_id:
            raise BillingConfigurationError(
                f"Stripe price ID is not configured for plan '{plan_id}' "
                f"with billing cycle '{billing_cycle}'"
            )
        return price_id

    def _plan_cycle_from_price(self, price_id: str | None) -> tuple[str, str] | None:
        """Reverse-lookup: Stripe price ID → (plan_id, billing_cycle)."""
        if not price_id:
            return None
        for plan_id, cycles in self._price_map.items():
            for cycle, configured_price in cycles.items():
                if configured_price and configured_price == price_id:
                    return plan_id, cycle
        return None

    def _resolve_return_urls(self, return_url: str | None) -> tuple[str, str]:
        base_url = (return_url or self._stripe.return_url or "").rstrip("/")

        success_url = self._stripe.success_url
        cancel_url = self._stripe.cancel_url

        if base_url:
            success_url = (
                success_url or f"{base_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
            )
            cancel_url = cancel_url or base_url

        if not success_url or not cancel_url:
            raise BillingConfigurationError(
                "Stripe success and cancel URLs are not configured. "
                "Provide them via configuration or request."
            )
        return success_url, cancel_url

    def _plan_credits(self, plan_id: str | None) -> float | None:
        if not plan_id:
            return None
        return self._credits.default_plans_credits.get(plan_id)

    @staticmethod
    def _normalize_billing_cycle(raw: str | None) -> str | None:
        """Map Stripe interval values (``month``/``year``) to canonical names."""
        if not raw:
            return None
        return _INTERVAL_TO_CYCLE.get(raw)

    @staticmethod
    def _to_datetime(timestamp: int | None) -> datetime | None:
        if not timestamp:
            return None
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    @staticmethod
    def _as_dict(stripe_object: Any) -> dict[str, Any]:
        """Convert a Stripe API object to a plain dict."""
        if stripe_object is None:
            return {}
        if isinstance(stripe_object, dict):
            return stripe_object
        # Stripe API objects expose to_dict_recursive for deep conversion.
        if hasattr(stripe_object, "to_dict_recursive"):
            return stripe_object.to_dict_recursive()
        return dict(stripe_object)

    def _resolve_plan_from_subscription(
        self,
        subscription: dict[str, Any],
        plan_id: str | None,
        billing_cycle: str | None,
    ) -> tuple[str | None, str | None]:
        """Resolve plan_id and billing_cycle by falling through
        subscription metadata → price ID reverse lookup."""
        sub_metadata = subscription.get("metadata", {}) or {}
        plan_id = plan_id or sub_metadata.get("plan_id")
        billing_cycle = billing_cycle or sub_metadata.get("billing_cycle")

        items = subscription.get("items", {}).get("data", []) or []
        first_item = items[0] if items else {}
        price_id = (first_item.get("price") or {}).get("id")

        if price_id and (not plan_id or not billing_cycle):
            mapped = self._plan_cycle_from_price(price_id)
            if mapped:
                plan_id = plan_id or mapped[0]
                billing_cycle = billing_cycle or mapped[1]

        return plan_id, billing_cycle

    # ------------------------------------------------------------------
    # DB helpers (private – ORM stays internal)
    # ------------------------------------------------------------------

    async def _get_user(self, user_id: uuid.UUID) -> User | None:
        async with get_db_session_local() as db:
            return await db.get(User, user_id)

    async def _update_user_subscription(
        self, db: AsyncSession, user_id: uuid.UUID, updates: dict[str, Any]
    ) -> User | None:
        """Lock user row and apply subscription field updates atomically.

        Only keys present in *updates* are written. ``None`` values ARE written
        (e.g. to clear ``billing_cycle`` on cancellation).

        Returns ``None`` if the user does not exist.
        """
        result = await db.execute(select(User).where(User.id == user_id).with_for_update())
        user = result.scalar_one_or_none()
        if not user:
            return None

        if "plan_id" in updates:
            user.subscription_plan = updates["plan_id"]
        if "status" in updates:
            user.subscription_status = updates["status"]
        if "billing_cycle" in updates:
            user.subscription_billing_cycle = updates["billing_cycle"]
        if "customer_id" in updates:
            user.stripe_customer_id = updates["customer_id"]
        if "period_end" in updates:
            user.subscription_current_period_end = self._to_datetime(updates["period_end"])
        return user

    async def _record_transaction(
        self,
        db: AsyncSession,
        *,
        event_id: str | None,
        user_id: uuid.UUID,
        values: dict[str, Any],
    ) -> None:
        if not event_id:
            logger.warning(
                f"Skipping billing transaction for user {user_id} due to missing event id"
            )
            return

        existing = await db.execute(
            select(BillingTransaction)
            .where(BillingTransaction.stripe_event_id == event_id)
            .with_for_update()
        )
        if existing.scalar_one_or_none():
            logger.debug(f"Billing transaction already exists for event {event_id}")
            return

        db.add(BillingTransaction(user_id=user_id, stripe_event_id=event_id, **values))
        logger.info(f"Stored billing transaction for user {user_id} (event {event_id})")

    async def _resolve_user_id(
        self, metadata: dict[str, Any], customer_id: str | None
    ) -> uuid.UUID | None:
        """Resolve user_id from event metadata, falling back to customer lookup."""
        raw_user_id = metadata.get("user_id")
        if raw_user_id:
            return uuid.UUID(raw_user_id) if isinstance(raw_user_id, str) else raw_user_id
        return await self._lookup_user_by_customer_id(customer_id)

    async def _lookup_user_by_customer_id(self, customer_id: str | None) -> uuid.UUID | None:
        if not customer_id:
            return None
        async with get_db_session_local() as db:
            result = await db.execute(select(User.id).where(User.stripe_customer_id == customer_id))
            row = result.first()
            return row[0] if row else None

    async def _retrieve_subscription(self, subscription_id: str | None) -> dict[str, Any] | None:
        if not subscription_id:
            return None
        self._ensure_api_key()
        try:
            subscription = await run_in_threadpool(stripe.Subscription.retrieve, subscription_id)
            return self._as_dict(subscription)
        except stripe.error.StripeError as exc:
            logger.error(f"Failed to retrieve subscription {subscription_id}: {exc}")
            return None

    # ------------------------------------------------------------------
    # Checkout session creation
    # ------------------------------------------------------------------

    async def create_checkout_session(self, params: CreateCheckoutParams) -> CheckoutResult:
        """Create a Stripe checkout session for the selected plan."""
        if params.plan_id == PlanId.FREE:
            raise BillingUnsupportedPlanError("Free plan does not require checkout")

        self._ensure_api_key()

        price_id = self._get_price_id(params.plan_id, params.billing_cycle)
        success_url, cancel_url = self._resolve_return_urls(params.return_url)

        metadata = {
            "plan_id": params.plan_id,
            "billing_cycle": params.billing_cycle,
            "user_id": str(params.user_id),
        }

        customer_kwargs: dict[str, Any] = {}
        user = await self._get_user(params.user_id)
        if user and user.stripe_customer_id:
            customer_kwargs["customer"] = user.stripe_customer_id

        session = await run_in_threadpool(
            stripe.checkout.Session.create,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(params.user_id),
            metadata=metadata,
            subscription_data={"metadata": metadata},
            automatic_tax={"enabled": True},
            **customer_kwargs,
        )

        return CheckoutResult(
            session_id=session.id,
            url=getattr(session, "url", None),
        )

    # ------------------------------------------------------------------
    # Portal session
    # ------------------------------------------------------------------

    async def create_portal_session(self, params: CreatePortalParams) -> PortalResult:
        """Create a Stripe billing portal session."""
        user = await self._get_user(params.user_id)
        if not user:
            raise BillingServiceError("User not found")

        if not user.stripe_customer_id:
            raise BillingServiceError(
                "Stripe customer not found for this account. Complete a checkout first."
            )

        portal_return_url = params.return_url or self._stripe.portal_return_url
        if not portal_return_url:
            raise BillingConfigurationError(
                "A return URL must be provided for the billing portal session"
            )

        self._ensure_api_key()

        try:
            session = await run_in_threadpool(
                stripe.billing_portal.Session.create,
                customer=user.stripe_customer_id,
                return_url=portal_return_url,
            )
        except stripe.error.StripeError as exc:
            raise BillingGatewayError(
                f"Failed to create billing portal session: {exc.user_message or str(exc)}"
            ) from exc

        url = getattr(session, "url", None)
        if not url:
            raise BillingServiceError("Stripe did not return a portal URL")

        return PortalResult(url=url)

    # ------------------------------------------------------------------
    # Webhook handling
    # ------------------------------------------------------------------

    def construct_webhook_event(self, payload: bytes, signature: str | None) -> stripe.Event:
        if not self._stripe.webhook_secret:
            raise BillingConfigurationError("Stripe webhook secret is not configured")
        if not signature:
            raise BillingServiceError("Missing Stripe signature header")

        self._ensure_api_key()

        try:
            return stripe.Webhook.construct_event(payload, signature, self._stripe.webhook_secret)
        except ValueError as exc:
            raise BillingServiceError("Invalid Stripe webhook payload") from exc
        except stripe.error.SignatureVerificationError as exc:
            raise BillingServiceError("Invalid Stripe signature") from exc

    async def handle_webhook_event(self, event: stripe.Event) -> None:
        event_type = event.get("type")
        event_id = event.get("id")
        data_object = event.get("data", {}).get("object")

        logger.info(f"Processing Stripe event {event_id} ({event_type})")

        if event_type == "checkout.session.completed":
            await self._handle_checkout_completed(event_id, data_object)
        elif event_type == "invoice.payment_succeeded":
            await self._handle_invoice_paid(event_id, data_object)
        elif event_type == "customer.subscription.deleted":
            await self._handle_subscription_deleted(event_id, data_object)
        elif event_type == "customer.subscription.updated":
            await self._handle_subscription_updated(event_id, data_object)
        else:
            logger.debug(f"Unhandled Stripe event type: {event_type}")

    # ------------------------------------------------------------------
    # Webhook event handlers (private)
    # ------------------------------------------------------------------

    async def _handle_checkout_completed(self, event_id: str | None, session_object: Any) -> None:
        session_data = self._as_dict(session_object)
        metadata = session_data.get("metadata", {}) or {}

        raw_user_id = metadata.get("user_id")
        plan_id = metadata.get("plan_id")
        billing_cycle = metadata.get("billing_cycle")
        subscription_id = session_data.get("subscription")
        customer_id = session_data.get("customer")

        if not raw_user_id:
            logger.warning(f"Checkout session {event_id} missing user or plan metadata")
            return

        user_id = uuid.UUID(raw_user_id) if isinstance(raw_user_id, str) else raw_user_id

        subscription = await self._retrieve_subscription(subscription_id)
        status = subscription.get("status") if subscription else session_data.get("status")

        period_end: int | None = None

        if subscription:
            plan_id, billing_cycle = self._resolve_plan_from_subscription(
                subscription, plan_id, billing_cycle
            )
            if not customer_id:
                customer_id = subscription.get("customer")

            items = subscription.get("items", {}).get("data", []) or []
            period_end = items[0].get("current_period_end") if items else None

        credits = self._plan_credits(plan_id)

        updates: dict[str, Any] = {"plan_id": plan_id, "status": status}
        if billing_cycle:
            updates["billing_cycle"] = billing_cycle
        if customer_id:
            updates["customer_id"] = customer_id
        if period_end:
            updates["period_end"] = period_end
        if credits is not None:
            updates["credits"] = credits

        async with get_db_session_local() as db:
            user = await self._update_user_subscription(db, user_id, updates)
            if not user:
                raise BillingServiceError(
                    f"User {user_id} not found for checkout session completion"
                )

            logger.info(
                f"Updated subscription for user {user_id} via checkout completion: plan={plan_id}, status={status}"
            )

            await self._record_transaction(
                db,
                event_id=event_id or session_data.get("id"),
                user_id=user_id,
                values={
                    "stripe_object_id": session_data.get("id"),
                    "stripe_customer_id": customer_id,
                    "stripe_subscription_id": subscription_id,
                    "plan_id": plan_id,
                    "billing_cycle": billing_cycle,
                    "status": status,
                    "raw_payload": session_data,
                },
            )

    async def _handle_invoice_paid(self, event_id: str | None, invoice_object: Any) -> None:
        invoice_data = self._as_dict(invoice_object)
        invoice_id = invoice_data.get("id")
        subscription_id = invoice_data.get("subscription")
        customer_id = invoice_data.get("customer")
        metadata = invoice_data.get("metadata", {}) or {}

        plan_id = metadata.get("plan_id")
        billing_cycle = metadata.get("billing_cycle")

        subscription = await self._retrieve_subscription(subscription_id)
        if subscription:
            sub_metadata = subscription.get("metadata", {}) or {}
            plan_id = plan_id or sub_metadata.get("plan_id")
            billing_cycle = billing_cycle or sub_metadata.get("billing_cycle")
            customer_id = customer_id or subscription.get("customer")

        user_id = await self._resolve_user_id(metadata, customer_id)
        if not user_id:
            logger.warning(f"Invoice payment event {event_id} missing user identification")
            return

        if not plan_id:
            line_items = invoice_data.get("lines", {}).get("data", [])
            if line_items:
                price_id = ((line_items[0] or {}).get("price") or {}).get("id")
                mapped = self._plan_cycle_from_price(price_id)
                if mapped:
                    plan_id, inferred_cycle = mapped
                    billing_cycle = billing_cycle or inferred_cycle

        credits = self._plan_credits(plan_id)
        amount_paid = invoice_data.get("amount_paid")
        status = invoice_data.get("status")
        period_end = subscription.get("current_period_end") if subscription else None
        effective_status = subscription.get("status", status) if subscription else status

        updates: dict[str, Any] = {"status": effective_status}
        if plan_id:
            updates["plan_id"] = plan_id
        if customer_id:
            updates["customer_id"] = customer_id
        if period_end:
            updates["period_end"] = period_end
        if credits is not None:
            updates["credits"] = credits
        if billing_cycle:
            updates["billing_cycle"] = billing_cycle

        async with get_db_session_local() as db:
            user = await self._update_user_subscription(db, user_id, updates)
            if not user:
                raise BillingServiceError(f"User {user_id} not found for invoice event")

            await self._record_transaction(
                db,
                event_id=event_id or invoice_id,
                user_id=user_id,
                values={
                    "stripe_object_id": invoice_id,
                    "stripe_customer_id": customer_id,
                    "stripe_subscription_id": subscription_id,
                    "stripe_invoice_id": invoice_id,
                    "stripe_payment_intent_id": invoice_data.get("payment_intent"),
                    "amount": ((amount_paid or 0) / 100 if amount_paid is not None else None),
                    "currency": invoice_data.get("currency"),
                    "plan_id": plan_id,
                    "billing_cycle": billing_cycle,
                    "credits": credits,
                    "status": status,
                    "raw_payload": self._as_dict(invoice_data),
                },
            )

        logger.info(
            f"Recorded billing transaction for user {user_id}: invoice={invoice_id}, plan={plan_id}, amount={(amount_paid or 0) / 100 if amount_paid is not None else None}"
        )

    async def _handle_subscription_deleted(
        self, event_id: str | None, subscription_object: Any
    ) -> None:
        subscription_data = self._as_dict(subscription_object)
        metadata = subscription_data.get("metadata", {}) or {}
        customer_id = subscription_data.get("customer")

        user_id = await self._resolve_user_id(metadata, customer_id)
        if not user_id:
            logger.warning(f"Subscription cancel event {event_id} missing user identification")
            return

        status = subscription_data.get("status") or "canceled"
        period_end = subscription_data.get("current_period_end") or subscription_data.get(
            "canceled_at"
        )

        updates: dict[str, Any] = {
            "status": status,
            "plan_id": PlanId.FREE,
            "billing_cycle": None,
            "credits": self._credits.default_user_credits,
        }
        if period_end:
            updates["period_end"] = period_end

        items = subscription_data.get("items", {}).get("data", []) or []
        first_plan = items[0].get("plan", {}) if items else {}
        txn_billing_cycle = first_plan.get("interval")

        async with get_db_session_local() as db:
            user = await self._update_user_subscription(db, user_id, updates)
            if not user:
                logger.warning(f"Could not update canceled subscription for missing user {user_id}")
                return

            logger.info(f"Marked subscription canceled for user {user_id} via event {event_id}")

            await self._record_transaction(
                db,
                event_id=event_id or subscription_data.get("id"),
                user_id=user_id,
                values={
                    "stripe_object_id": subscription_data.get("id"),
                    "stripe_customer_id": customer_id,
                    "stripe_subscription_id": subscription_data.get("id"),
                    "status": status,
                    "plan_id": PlanId.FREE,
                    "billing_cycle": txn_billing_cycle,
                    "raw_payload": subscription_data,
                },
            )

    async def _handle_subscription_updated(
        self, event_id: str | None, subscription_object: Any
    ) -> None:
        subscription_data = self._as_dict(subscription_object)
        metadata = subscription_data.get("metadata", {}) or {}
        customer_id = subscription_data.get("customer")

        plan_id, billing_cycle = self._resolve_plan_from_subscription(
            subscription_data,
            metadata.get("plan_id"),
            metadata.get("billing_cycle"),
        )

        # Extra billing_cycle fallback: recurring.interval → plan.interval
        if not billing_cycle:
            items = subscription_data.get("items", {}).get("data", []) or []
            first_item = items[0] if items else {}
            recurring = (first_item.get("price") or {}).get("recurring") or {}
            interval = recurring.get("interval")
            if interval:
                billing_cycle = self._normalize_billing_cycle(interval) or interval
            elif first_item:
                plan_interval = (first_item.get("plan") or {}).get("interval")
                if plan_interval:
                    billing_cycle = plan_interval

        user_id = await self._resolve_user_id(metadata, customer_id)
        if not user_id:
            logger.warning(f"Subscription update event {event_id} missing user identification")
            return

        status = subscription_data.get("status")
        period_end = subscription_data.get("current_period_end")
        credits = self._plan_credits(plan_id)

        updates: dict[str, Any] = {}
        if plan_id:
            updates["plan_id"] = plan_id
        if status:
            updates["status"] = status
        if billing_cycle:
            updates["billing_cycle"] = billing_cycle
        if customer_id:
            updates["customer_id"] = customer_id
        if period_end:
            updates["period_end"] = period_end
        if credits is not None:
            updates["credits"] = credits

        async with get_db_session_local() as db:
            user = await self._update_user_subscription(db, user_id, updates)
            if not user:
                logger.warning(f"Could not update subscription for missing user {user_id}")
                return

            logger.info(
                f"Updated subscription for user {user_id} via subscription updated event: "
                f"plan={plan_id}, status={status}"
            )

            await self._record_transaction(
                db,
                event_id=event_id or subscription_data.get("id"),
                user_id=user_id,
                values={
                    "stripe_object_id": subscription_data.get("id"),
                    "stripe_customer_id": customer_id,
                    "stripe_subscription_id": subscription_data.get("id"),
                    "plan_id": plan_id,
                    "billing_cycle": billing_cycle,
                    "credits": credits,
                    "status": status,
                    "raw_payload": subscription_data,
                },
            )


__all__ = [
    "BillingService",
]
