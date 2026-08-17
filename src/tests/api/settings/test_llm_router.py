import pytest

from ii_agent.settings.llm.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("POST", "/models"),
    ("GET", "/models"),
    ("GET", "/models/{setting_id}"),
    ("PUT", "/models/{model_id}"),
    ("DELETE", "/models/{model_id}"),
}


def test_llm_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_llm_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
