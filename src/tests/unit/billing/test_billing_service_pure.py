"""Unit tests for BillingService pure/static helper methods.

These tests cover the synchronous, non-DB portions of billing/service.py:
  - _get_price_id
  - _plan_cycle_from_price
  - _resolve_return_urls
  - _plan_credits
  - _normalize_billing_cycle (static)
  - _to_datetime (static)
  - _as_dict (static)
  - _resolve_plan_from_subscription
  - _ensure_api_key
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import stripe

from ii_agent.billing.exceptions import (
    BillingConfigurationError,
    BillingUnsupportedPlanError,
    StripeConfigError,
)
from ii_agent.billing.schemas import BillingCycle, PlanId
from ii_agent.billing.service import BillingService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(settings_factory, **stripe_overrides):
    """Build a BillingService from settings_factory with optional stripe overrides."""
    settings = settings_factory(stripe=stripe_overrides)
    return BillingService(settings=settings)


# ---------------------------------------------------------------------------
# _ensure_api_key
# ---------------------------------------------------------------------------


class TestEnsureApiKey:
    def test_raises_when_secret_key_is_none(self, settings_factory):
        svc = _make_service(settings_factory, secret_key=None)
        with pytest.raises(StripeConfigError, match="secret key"):
            svc._ensure_api_key()

    def test_sets_stripe_api_key(self, settings_factory):
        svc = _make_service(settings_factory, secret_key="sk_live_abc")
        svc._ensure_api_key()
        assert stripe.api_key == "sk_live_abc"

    def test_idempotent_when_key_already_set(self, settings_factory):
        svc = _make_service(settings_factory, secret_key="sk_test_xyz")
        svc._ensure_api_key()
        svc._ensure_api_key()  # should not raise
        assert stripe.api_key == "sk_test_xyz"


# ---------------------------------------------------------------------------
# _get_price_id
# ---------------------------------------------------------------------------


class TestGetPriceId:
    def test_returns_correct_price_for_plus_monthly(self, settings_factory):
        svc = _make_service(settings_factory)
        assert svc._get_price_id(PlanId.PLUS, BillingCycle.MONTHLY) == "price_plus_m"

    def test_returns_correct_price_for_plus_annually(self, settings_factory):
        svc = _make_service(settings_factory)
        assert svc._get_price_id(PlanId.PLUS, BillingCycle.ANNUALLY) == "price_plus_a"

    def test_returns_correct_price_for_pro_monthly(self, settings_factory):
        svc = _make_service(settings_factory)
        assert svc._get_price_id(PlanId.PRO, BillingCycle.MONTHLY) == "price_pro_m"

    def test_returns_correct_price_for_pro_annually(self, settings_factory):
        svc = _make_service(settings_factory)
        assert svc._get_price_id(PlanId.PRO, BillingCycle.ANNUALLY) == "price_pro_a"

    def test_raises_for_unknown_plan(self, settings_factory):
        svc = _make_service(settings_factory)
        with pytest.raises(BillingUnsupportedPlanError, match="enterprise"):
            svc._get_price_id("enterprise", BillingCycle.MONTHLY)

    def test_raises_for_free_plan(self, settings_factory):
        svc = _make_service(settings_factory)
        with pytest.raises(BillingUnsupportedPlanError):
            svc._get_price_id(PlanId.FREE, BillingCycle.MONTHLY)

    def test_raises_when_price_not_configured(self, settings_factory):
        svc = _make_service(settings_factory, price_plus_monthly=None)
        with pytest.raises(BillingConfigurationError, match="not configured"):
            svc._get_price_id(PlanId.PLUS, BillingCycle.MONTHLY)


# ---------------------------------------------------------------------------
# _plan_cycle_from_price
# ---------------------------------------------------------------------------


class TestPlanCycleFromPrice:
    def test_returns_none_when_price_is_none(self, settings_factory):
        svc = _make_service(settings_factory)
        assert svc._plan_cycle_from_price(None) is None

    def test_returns_none_when_price_not_in_map(self, settings_factory):
        svc = _make_service(settings_factory)
        assert svc._plan_cycle_from_price("price_unknown_xyz") is None

    def test_returns_plus_monthly(self, settings_factory):
        svc = _make_service(settings_factory)
        result = svc._plan_cycle_from_price("price_plus_m")
        assert result == (PlanId.PLUS, BillingCycle.MONTHLY)

    def test_returns_plus_annually(self, settings_factory):
        svc = _make_service(settings_factory)
        result = svc._plan_cycle_from_price("price_plus_a")
        assert result == (PlanId.PLUS, BillingCycle.ANNUALLY)

    def test_returns_pro_monthly(self, settings_factory):
        svc = _make_service(settings_factory)
        result = svc._plan_cycle_from_price("price_pro_m")
        assert result == (PlanId.PRO, BillingCycle.MONTHLY)

    def test_returns_pro_annually(self, settings_factory):
        svc = _make_service(settings_factory)
        result = svc._plan_cycle_from_price("price_pro_a")
        assert result == (PlanId.PRO, BillingCycle.ANNUALLY)

    def test_returns_none_when_configured_price_is_none(self, settings_factory):
        svc = _make_service(settings_factory, price_plus_monthly=None)
        # None price_ids should not match
        result = svc._plan_cycle_from_price("price_plus_m")
        # plan_cycle_from_price skips entries where configured_price is falsy
        # The originally-configured "price_plus_m" is gone so returns None
        assert result is None


# ---------------------------------------------------------------------------
# _resolve_return_urls
# ---------------------------------------------------------------------------


class TestResolveReturnUrls:
    def test_uses_explicit_success_and_cancel_urls_from_config(self, settings_factory):
        svc = _make_service(
            settings_factory,
            success_url="https://app.local/success",
            cancel_url="https://app.local/cancel",
            return_url=None,
        )
        success, cancel = svc._resolve_return_urls(None)
        assert success == "https://app.local/success"
        assert cancel == "https://app.local/cancel"

    def test_builds_default_success_url_from_base_url(self, settings_factory):
        svc = _make_service(
            settings_factory,
            success_url=None,
            cancel_url=None,
            return_url=None,
        )
        success, cancel = svc._resolve_return_urls("https://myapp.com")
        assert "billing/success" in success
        assert "{CHECKOUT_SESSION_ID}" in success
        assert cancel == "https://myapp.com"

    def test_strips_trailing_slash_from_base_url(self, settings_factory):
        svc = _make_service(
            settings_factory,
            success_url=None,
            cancel_url=None,
            return_url=None,
        )
        success, cancel = svc._resolve_return_urls("https://myapp.com/")
        assert not cancel.endswith("/")

    def test_uses_config_return_url_when_no_request_url(self, settings_factory):
        svc = _make_service(
            settings_factory,
            success_url=None,
            cancel_url=None,
            return_url="https://configured.io",
        )
        success, cancel = svc._resolve_return_urls(None)
        assert cancel == "https://configured.io"

    def test_raises_when_no_urls_configured(self, settings_factory):
        svc = _make_service(
            settings_factory,
            success_url=None,
            cancel_url=None,
            return_url=None,
        )
        with pytest.raises(BillingConfigurationError, match="not configured"):
            svc._resolve_return_urls(None)

    def test_request_url_overrides_config_return_url(self, settings_factory):
        svc = _make_service(
            settings_factory,
            success_url=None,
            cancel_url=None,
            return_url="https://old.io",
        )
        # Explicit return_url in request takes precedence
        _, cancel = svc._resolve_return_urls("https://new.io")
        assert cancel == "https://new.io"


# ---------------------------------------------------------------------------
# _plan_credits
# ---------------------------------------------------------------------------


class TestPlanCredits:
    def test_returns_none_for_none_plan(self, settings_factory):
        svc = _make_service(settings_factory)
        assert svc._plan_credits(None) is None

    def test_returns_credits_for_plus_plan(self, settings_factory):
        svc = _make_service(settings_factory)
        # settings_factory default: "plus" → 100.0
        assert svc._plan_credits("plus") == 100.0

    def test_returns_credits_for_pro_plan(self, settings_factory):
        svc = _make_service(settings_factory)
        assert svc._plan_credits("pro") == 250.0

    def test_returns_none_for_unknown_plan(self, settings_factory):
        svc = _make_service(settings_factory)
        assert svc._plan_credits("enterprise") is None


# ---------------------------------------------------------------------------
# _normalize_billing_cycle (static)
# ---------------------------------------------------------------------------


class TestNormalizeBillingCycle:
    def test_returns_none_for_none(self):
        assert BillingService._normalize_billing_cycle(None) is None

    def test_maps_month_to_monthly(self):
        assert BillingService._normalize_billing_cycle("month") == BillingCycle.MONTHLY

    def test_maps_monthly_to_monthly(self):
        assert BillingService._normalize_billing_cycle("monthly") == BillingCycle.MONTHLY

    def test_maps_year_to_annually(self):
        assert BillingService._normalize_billing_cycle("year") == BillingCycle.ANNUALLY

    def test_maps_annually_to_annually(self):
        assert BillingService._normalize_billing_cycle("annually") == BillingCycle.ANNUALLY

    def test_returns_none_for_unknown_interval(self):
        assert BillingService._normalize_billing_cycle("weekly") is None


# ---------------------------------------------------------------------------
# _to_datetime (static)
# ---------------------------------------------------------------------------


class TestToDatetime:
    def test_returns_none_for_none(self):
        assert BillingService._to_datetime(None) is None

    def test_returns_none_for_zero(self):
        assert BillingService._to_datetime(0) is None

    def test_converts_epoch_to_utc_datetime(self):
        result = BillingService._to_datetime(1_700_000_000)
        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc

    def test_correct_epoch_value(self):
        # 2024-01-01 00:00:00 UTC = 1735689600
        ts = 1_735_689_600
        result = BillingService._to_datetime(ts)
        assert result.year == 2025
        assert result.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# _as_dict (static)
# ---------------------------------------------------------------------------


class TestAsDict:
    def test_returns_empty_dict_for_none(self):
        assert BillingService._as_dict(None) == {}

    def test_returns_dict_unchanged(self):
        d = {"key": "value", "num": 42}
        assert BillingService._as_dict(d) is d

    def test_converts_object_with_to_dict_recursive(self):
        obj = MagicMock()
        obj.to_dict_recursive.return_value = {"a": 1}
        result = BillingService._as_dict(obj)
        assert result == {"a": 1}

    def test_converts_object_without_to_dict_recursive(self):
        """Falls back to dict() for plain objects."""

        class FakeStripeObj:
            def keys(self):
                return ["x"]

            def __getitem__(self, key):
                return 99

        obj = FakeStripeObj()
        result = BillingService._as_dict(obj)
        assert result == {"x": 99}


# ---------------------------------------------------------------------------
# _resolve_plan_from_subscription
# ---------------------------------------------------------------------------


class TestResolvePlanFromSubscription:
    def _make_svc(self, settings_factory):
        return _make_service(settings_factory)

    def test_uses_provided_plan_and_cycle(self, settings_factory):
        svc = self._make_svc(settings_factory)
        sub = {}
        plan, cycle = svc._resolve_plan_from_subscription(sub, "plus", "monthly")
        assert plan == "plus"
        assert cycle == "monthly"

    def test_falls_back_to_subscription_metadata(self, settings_factory):
        svc = self._make_svc(settings_factory)
        sub = {"metadata": {"plan_id": "pro", "billing_cycle": "annually"}, "items": {"data": []}}
        plan, cycle = svc._resolve_plan_from_subscription(sub, None, None)
        assert plan == "pro"
        assert cycle == "annually"

    def test_falls_back_to_price_reverse_lookup(self, settings_factory):
        svc = self._make_svc(settings_factory)
        sub = {
            "metadata": {},
            "items": {"data": [{"price": {"id": "price_pro_a"}}]},
        }
        plan, cycle = svc._resolve_plan_from_subscription(sub, None, None)
        assert plan == PlanId.PRO
        assert cycle == BillingCycle.ANNUALLY

    def test_price_lookup_does_not_override_explicit_values(self, settings_factory):
        svc = self._make_svc(settings_factory)
        sub = {
            "metadata": {},
            "items": {"data": [{"price": {"id": "price_pro_a"}}]},
        }
        # Explicit plan_id/billing_cycle should not be overwritten
        plan, cycle = svc._resolve_plan_from_subscription(sub, "plus", "monthly")
        assert plan == "plus"
        assert cycle == "monthly"

    def test_handles_empty_items(self, settings_factory):
        svc = self._make_svc(settings_factory)
        sub = {"metadata": {}, "items": {"data": []}}
        plan, cycle = svc._resolve_plan_from_subscription(sub, None, None)
        assert plan is None
        assert cycle is None

    def test_handles_missing_items_key(self, settings_factory):
        svc = self._make_svc(settings_factory)
        sub = {"metadata": {}}
        plan, cycle = svc._resolve_plan_from_subscription(sub, None, None)
        assert plan is None
        assert cycle is None

    def test_partial_override_preserves_existing_plan(self, settings_factory):
        svc = self._make_svc(settings_factory)
        sub = {
            "metadata": {"plan_id": "plus"},
            "items": {"data": [{"price": {"id": "price_pro_a"}}]},
        }
        # plan_id from metadata, cycle from reverse lookup
        plan, cycle = svc._resolve_plan_from_subscription(sub, None, None)
        assert plan == "plus"
        assert cycle == BillingCycle.ANNUALLY
