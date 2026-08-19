import pytest

from ii_agent.integrations.connectors.composio.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/composio/toolkits"),
    ("GET", "/composio/profiles"),
    ("POST", "/composio/oauth-complete"),
    ("GET", "/composio/toolkits/{toolkit_slug}"),
    ("GET", "/composio/toolkits/{toolkit_slug}/actions"),
    ("POST", "/composio/{toolkit_slug}/connect"),
    ("GET", "/composio/{toolkit_slug}/status"),
    ("DELETE", "/composio/{toolkit_slug}"),
    ("GET", "/composio/profiles/{profile_id}/mcp-config"),
    ("POST", "/composio/profiles/{profile_id}/sync-to-agent"),
    ("DELETE", "/composio/profiles/{profile_id}"),
    ("POST", "/composio/profiles/{profile_id}/enable"),
    ("POST", "/composio/profiles/{profile_id}/disable"),
    ("PUT", "/composio/profiles/{profile_id}/tools"),
}


def test_composio_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_composio_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
