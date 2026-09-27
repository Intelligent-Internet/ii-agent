import pytest

from ii_agent.chat.api.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/chat/conversations/{session_id}/advanced-mode"),
    ("POST", "/chat/conversations/{session_id}/advanced-mode"),
    ("POST", "/chat/conversations"),
    ("POST", "/chat/conversations/{session_id}/stop"),
    ("GET", "/chat/conversations/{session_id}"),
    ("DELETE", "/chat/conversations/{session_id}/messages/{message_id}"),
    ("DELETE", "/chat/conversations/{session_id}"),
}


def test_chat_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_chat_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
