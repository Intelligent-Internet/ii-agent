import pytest

from ii_agent.sessions.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("POST", "/sessions/bulk-delete"),
    ("GET", "/sessions/{session_id}"),
    ("GET", "/sessions"),
    ("GET", "/sessions/{session_id}/events"),
    ("GET", "/sessions/{session_id}/files"),
    ("POST", "/sessions/{session_id}/publish"),
    ("POST", "/sessions/{session_id}/unpublish"),
    ("DELETE", "/sessions/{session_id}"),
    ("POST", "/sessions/{session_id}/fork"),
    ("PATCH", "/sessions/{session_id}"),
    ("PATCH", "/sessions/{session_id}/plan"),
}


def test_sessions_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_sessions_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
