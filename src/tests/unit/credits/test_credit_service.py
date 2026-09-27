"""Unit tests for CreditService — static helpers and mocked async methods."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.credits.models import CreditBalance, CreditTransaction
from ii_agent.credits.schemas import CreditBalanceResponse
from ii_agent.credits.service import CreditService
from ii_agent.credits.types import CreditType, TransactionType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_ID = uuid.uuid4()


def _make_service(balance_repo=None, tx_repo=None, config=None):
    balance_repo = balance_repo or MagicMock()
    tx_repo = tx_repo or MagicMock()
    config = config or MagicMock()
    return CreditService(
        balance_repo=balance_repo,
        transaction_repo=tx_repo,
        config=config,
    )


def _make_tx(**kwargs) -> CreditTransaction:
    defaults = dict(
        user_id=USER_ID,
        transaction_type=TransactionType.LLM_USAGE,
        credit_type=CreditType.REGULAR,
        amount=Decimal("-1.5"),
        balance_after=Decimal("8.5"),
        model_id="claude-3",
        run_id=None,
        description="test",
        data={"k": "v"},
    )
    defaults.update(kwargs)
    tx = CreditTransaction(**defaults)
    tx.id = uuid.uuid4()
    tx.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return tx


# ---------------------------------------------------------------------------
# _build_transaction (static)
# ---------------------------------------------------------------------------


class TestBuildTransaction:
    def test_returns_credit_transaction_instance(self):
        tx = CreditService._build_transaction(
            user_id=USER_ID,
            transaction_type=TransactionType.LLM_USAGE,
            credit_type=CreditType.REGULAR,
            amount=Decimal("-2"),
            balance_after=Decimal("8"),
        )
        assert isinstance(tx, CreditTransaction)

    def test_fields_set_correctly(self):
        sid = uuid.uuid4()
        rid = uuid.uuid4()
        tx = CreditService._build_transaction(
            user_id=USER_ID,
            transaction_type=TransactionType.SIGNUP_GRANT,
            credit_type=CreditType.BONUS,
            amount=Decimal("100"),
            balance_after=Decimal("100"),
            session_id=sid,
            run_id=rid,
            model_id="gpt-4",
            description="welcome bonus",
            metadata={"promo": "new_user"},
        )
        assert tx.user_id == USER_ID
        assert tx.transaction_type == TransactionType.SIGNUP_GRANT
        assert tx.credit_type == CreditType.BONUS
        assert tx.amount == Decimal("100")
        assert tx.balance_after == Decimal("100")
        assert tx.session_id == sid
        assert tx.run_id == rid
        assert tx.model_id == "gpt-4"
        assert tx.description == "welcome bonus"
        assert tx.data == {"promo": "new_user"}

    def test_none_metadata_stored_as_empty_dict(self):
        tx = CreditService._build_transaction(
            user_id=USER_ID,
            transaction_type=TransactionType.LLM_USAGE,
            credit_type=CreditType.REGULAR,
            amount=Decimal("-1"),
            balance_after=Decimal("9"),
            metadata=None,
        )
        assert tx.data == {}


# ---------------------------------------------------------------------------
# _tx_to_item (static)
# ---------------------------------------------------------------------------


class TestTxToItem:
    def test_converts_to_item(self):
        tx = _make_tx()
        item = CreditService._tx_to_item(tx)
        assert item.transaction_type == TransactionType.LLM_USAGE
        assert item.credit_type == CreditType.REGULAR
        assert item.amount == -1.5
        assert item.balance_after == 8.5
        assert item.model_id == "claude-3"
        assert item.description == "test"
        assert item.metadata == {"k": "v"}

    def test_id_and_created_at_propagated(self):
        tx = _make_tx()
        item = CreditService._tx_to_item(tx)
        assert item.id == tx.id
        assert item.created_at == tx.created_at

    def test_optional_fields_none(self):
        tx = _make_tx(run_id=None, model_id=None, description=None, data=None)
        item = CreditService._tx_to_item(tx)
        assert item.run_id is None
        assert item.model_id is None
        assert item.description is None
        assert item.metadata is None


# ---------------------------------------------------------------------------
# get_balance (async, mocked repo)
# ---------------------------------------------------------------------------


class TestGetBalance:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_balance(self):
        balance_repo = MagicMock()
        balance_repo.get_by_user_id = AsyncMock(return_value=None)
        svc = _make_service(balance_repo=balance_repo)
        db = MagicMock()
        result = await svc.get_balance(db, USER_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_balance_response(self):
        bal = MagicMock()
        bal.user_id = USER_ID
        bal.credits = Decimal("50")
        bal.bonus_credits = Decimal("10")
        bal.updated_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        balance_repo = MagicMock()
        balance_repo.get_by_user_id = AsyncMock(return_value=bal)
        svc = _make_service(balance_repo=balance_repo)
        db = MagicMock()
        result = await svc.get_balance(db, USER_ID)
        assert isinstance(result, CreditBalanceResponse)
        assert result.credits == 50.0
        assert result.bonus_credits == 10.0


# ---------------------------------------------------------------------------
# has_sufficient_credits (async, mocked repo)
# ---------------------------------------------------------------------------


class TestHasSufficientCredits:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_balance(self):
        balance_repo = MagicMock()
        balance_repo.get_by_user_id = AsyncMock(return_value=None)
        svc = _make_service(balance_repo=balance_repo)
        result = await svc.has_sufficient_credits(MagicMock(), USER_ID)
        assert result is False

    @pytest.mark.asyncio
    async def test_true_when_total_sufficient(self):
        bal = MagicMock()
        bal.total = Decimal("100")
        balance_repo = MagicMock()
        balance_repo.get_by_user_id = AsyncMock(return_value=bal)
        svc = _make_service(balance_repo=balance_repo)
        result = await svc.has_sufficient_credits(MagicMock(), USER_ID, Decimal("50"))
        assert result is True

    @pytest.mark.asyncio
    async def test_false_when_total_insufficient(self):
        bal = MagicMock()
        bal.total = Decimal("0.5")
        balance_repo = MagicMock()
        balance_repo.get_by_user_id = AsyncMock(return_value=bal)
        svc = _make_service(balance_repo=balance_repo)
        result = await svc.has_sufficient_credits(MagicMock(), USER_ID, Decimal("1"))
        assert result is False


# ---------------------------------------------------------------------------
# ensure_balance_exists (async, mocked repo)
# ---------------------------------------------------------------------------


class TestEnsureBalanceExists:
    @pytest.mark.asyncio
    async def test_returns_existing_balance(self):
        existing = MagicMock(spec=CreditBalance)
        balance_repo = MagicMock()
        balance_repo.get_by_user_id = AsyncMock(return_value=existing)
        svc = _make_service(balance_repo=balance_repo)
        result = await svc.ensure_balance_exists(MagicMock(), USER_ID)
        assert result is existing
        balance_repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_balance_when_none(self):
        new_bal = MagicMock(spec=CreditBalance)
        balance_repo = MagicMock()
        balance_repo.get_by_user_id = AsyncMock(return_value=None)
        balance_repo.save = AsyncMock(return_value=new_bal)
        svc = _make_service(balance_repo=balance_repo)
        result = await svc.ensure_balance_exists(MagicMock(), USER_ID)
        assert result is new_bal
        balance_repo.save.assert_called_once()
