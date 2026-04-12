import pytest

from ii_agent.content.storybook.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/storybooks/session/{session_id}"),
    ("GET", "/storybooks/{storybook_id}"),
    ("POST", "/storybooks/{storybook_id}/voice"),
    ("GET", "/storybooks/{storybook_id}/progress"),
    ("POST", "/storybooks/{storybook_id}/cancel"),
    ("POST", "/storybooks/{storybook_id}/pages/{page_number}/text"),
    ("POST", "/storybooks/{storybook_id}/pages/{page_number}/regenerate"),
    ("GET", "/storybooks/{storybook_id}/edit/proxy"),
    ("POST", "/storybooks/{storybook_id}/edit/save"),
    ("POST", "/storybooks/{storybook_id}/edit/upload-background"),
    ("POST", "/storybooks/{storybook_id}/edit/ai-rewrite"),
    ("POST", "/storybooks/{storybook_id}/edit/ai-generate-background"),
    ("POST", "/storybooks/{storybook_id}/edit/ai-regenerate-image"),
    ("GET", "/storybooks/{storybook_id}/versions"),
    ("GET", "/storybooks/{storybook_id}/download"),
    ("GET", "/storybooks/{storybook_id}/download/stream"),
    ("GET", "/storybooks/{storybook_id}/download/page/{page_number}"),
    ("GET", "/storybooks/{storybook_id}/download/png/{page_number}"),
    ("GET", "/storybooks/{storybook_id}/download/png"),
    ("GET", "/storybooks/{storybook_id}/download/png/stream"),
}


def test_storybook_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_storybook_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
