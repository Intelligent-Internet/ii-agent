"""Tests for ii_agent.credits.models — CreditBalance.total property."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock


class TestCreditBalanceTotal:
    def test_total_sums_credits_and_bonus(self):
        """Call CreditBalance.total.fget via a mock to bypass ORM instrumentation."""
        from ii_agent.credits.models import CreditBalance

        cb = MagicMock()
        cb.credits = Decimal("100.5")
        cb.bonus_credits = Decimal("50.25")
        result = CreditBalance.total.fget(cb)
        assert result == Decimal("150.75")

    def test_total_with_zero_bonus(self):
        from ii_agent.credits.models import CreditBalance

        cb = MagicMock()
        cb.credits = Decimal("300")
        cb.bonus_credits = Decimal("0")
        result = CreditBalance.total.fget(cb)
        assert result == Decimal("300")
