import pytest

from ii_agent.credits.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/credits/balance"),
    ("GET", "/credits/history"),
    ("GET", "/credits/usage"),
    ("GET", "/credits/usage/{session_id}"),
}


def test_credits_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_credits_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
