import pytest

from ii_agent.content.slides.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("POST", "/slides"),
    ("GET", "/slides"),
    ("GET", "/slides/download"),
    ("GET", "/slides/download/stream"),
}


def test_slides_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_slides_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
