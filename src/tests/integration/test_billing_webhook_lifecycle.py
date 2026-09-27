import pytest
from uuid import uuid4

from ii_agent.billing.exceptions import BillingUnsupportedPlanError
from ii_agent.billing.schemas import CreateCheckoutParams
from ii_agent.billing.service import BillingService

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_billing_checkout_rejects_free_plan(settings_factory):
    settings = settings_factory()
    billing_service = BillingService(settings=settings)

    with pytest.raises(BillingUnsupportedPlanError):
        # free plan must not proceed to checkout
        await billing_service.create_checkout_session(
            CreateCheckoutParams(
                plan_id="free", billing_cycle="monthly", user_id=uuid4(), return_url=None
            ),
        )
