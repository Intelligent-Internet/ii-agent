import pytest

try:
    from ii_agent.app import health_router
except ImportError:
    pytest.skip("Transitive google-genai dependency not available", allow_module_level=True)
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/health"),
    ("GET", "/health/ready"),
    ("GET", "/health/host"),
    ("GET", "/health/sandbox-pool"),
}


def test_health_router_routes_registered():
    assert_routes_present(health_router, EXPECTED_ROUTES)


def test_health_router_auth_contract():
    assert_auth_contract(health_router, public=EXPECTED_ROUTES)
