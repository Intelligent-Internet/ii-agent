from decimal import Decimal

from ii_agent.billing.utils import credits_to_usd, usd_to_credits


def test_usd_to_credits_contract():
    assert usd_to_credits(1.5) == Decimal("100")


def test_credits_to_usd_contract():
    assert credits_to_usd(100) == Decimal("1.5")


def test_credit_usd_roundtrip():
    credits = usd_to_credits(Decimal("0.33"))
    assert credits_to_usd(credits) == Decimal("0.33")


def test_usd_to_credits_accepts_float():
    """Float inputs are converted to Decimal internally."""
    result = usd_to_credits(1.5)
    assert isinstance(result, Decimal)
    assert result == Decimal("100")


def test_credits_to_usd_accepts_float():
    result = credits_to_usd(100.0)
    assert isinstance(result, Decimal)
    assert result == Decimal("1.5")


# ---------------------------------------------------------------------------
# billing/utils.py – finalize_storybook_async_operation
# ---------------------------------------------------------------------------

import asyncio
from unittest.mock import MagicMock


class TestBillingUtilsFinalize:
    def test_finalize_storybook_logs_warning(self):
        from ii_agent.billing.utils import finalize_storybook_async_operation

        mock_reservation = MagicMock()
        mock_scope = MagicMock()

        asyncio.run(
            finalize_storybook_async_operation(
                reservation_service=mock_reservation,
                scope=mock_scope,
                reservation_id="res-123",
                result=None,
                release_reason="unused",
            )
        )
        # Function completes without error (logs a warning internally)

    def test_finalize_storybook_with_result(self):
        from ii_agent.billing.utils import finalize_storybook_async_operation

        asyncio.run(
            finalize_storybook_async_operation(
                reservation_service=MagicMock(),
                scope=MagicMock(),
                reservation_id="res-456",
                result={"output": "done"},
                release_reason="completed",
                settlement_error=None,
            )
        )
