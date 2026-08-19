"""Unit tests for pure helper functions in auth/router.py."""

from __future__ import annotations

import base64
import hashlib
import json
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _render_auth_callback_html
# ---------------------------------------------------------------------------


class TestRenderAuthCallbackHtml:
    def _render(self, token_payload, return_origin, return_url):
        from ii_agent.auth.router import _render_auth_callback_html

        return _render_auth_callback_html(token_payload, return_origin, return_url)

    def test_embeds_token_payload_as_json(self):
        payload = {"access_token": "tok123", "token_type": "bearer"}
        html = self._render(payload, None, None)
        assert json.dumps(payload) in html

    def test_embeds_return_origin(self):
        html = self._render({}, "https://example.com", None)
        assert '"https://example.com"' in html

    def test_embeds_return_url(self):
        html = self._render({}, None, "https://example.com/callback")
        assert '"https://example.com/callback"' in html

    def test_defaults_to_empty_strings_when_none(self):
        html = self._render({"a": 1}, None, None)
        # Should contain empty-string JSON for origin & url
        assert '""' in html

    def test_returns_valid_html(self):
        html = self._render({}, None, None)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html


# ---------------------------------------------------------------------------
# _make_pkce_pair
# ---------------------------------------------------------------------------


class TestMakePkcePair:
    def test_returns_verifier_and_challenge(self):
        from ii_agent.auth.router import _make_pkce_pair

        verifier, challenge = _make_pkce_pair()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)
        assert len(verifier) > 20
        assert len(challenge) > 20

    def test_challenge_is_sha256_of_verifier(self):
        from ii_agent.auth.router import _make_pkce_pair

        verifier, challenge = _make_pkce_pair()
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        assert challenge == expected

    def test_different_calls_produce_different_pairs(self):
        from ii_agent.auth.router import _make_pkce_pair

        v1, _ = _make_pkce_pair()
        v2, _ = _make_pkce_pair()
        assert v1 != v2


# ---------------------------------------------------------------------------
# _sanitize_return_to
# ---------------------------------------------------------------------------


class TestSanitizeReturnTo:
    def _sanitize(self, value):
        from ii_agent.auth.router import _sanitize_return_to

        return _sanitize_return_to(value)

    def test_none_returns_none_pair(self):
        assert self._sanitize(None) == (None, None)

    def test_empty_string_returns_none_pair(self):
        assert self._sanitize("") == (None, None)

    def test_valid_https_url(self):
        url = "https://app.example.com/dashboard?q=1"
        origin, full = self._sanitize(url)
        assert origin == "https://app.example.com"
        assert full == url

    def test_valid_http_url(self):
        origin, full = self._sanitize("http://localhost:3000/path")
        assert origin == "http://localhost:3000"
        assert full == "http://localhost:3000/path"

    def test_rejects_javascript_scheme(self):
        from ii_agent.core.exceptions import ValidationError

        with pytest.raises(ValidationError, match="Invalid return_to"):
            self._sanitize("javascript:alert(1)")

    def test_rejects_data_scheme(self):
        from ii_agent.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self._sanitize("data:text/html,<h1>hi</h1>")

    def test_rejects_missing_netloc(self):
        from ii_agent.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self._sanitize("https://")


# ---------------------------------------------------------------------------
# _make_state / _verify_state
# ---------------------------------------------------------------------------


class TestMakeAndVerifyState:
    @patch(
        "ii_agent.auth.router.get_settings",
        return_value=type(
            "S",
            (),
            {"oauth": type("O", (), {"session_secret_key": "test-secret-key-1234"})()},
        )(),
    )
    def test_roundtrip(self, _mock_settings):
        from ii_agent.auth.router import _make_state, _verify_state

        state = _make_state()
        assert _verify_state(state) is True

    @patch(
        "ii_agent.auth.router.get_settings",
        return_value=type(
            "S",
            (),
            {"oauth": type("O", (), {"session_secret_key": "test-secret-key-1234"})()},
        )(),
    )
    def test_rejects_tampered_state(self, _mock_settings):
        from ii_agent.auth.router import _verify_state

        assert _verify_state("bogus.tampered.value") is False

    @patch(
        "ii_agent.auth.router.get_settings",
        return_value=type(
            "S",
            (),
            {"oauth": type("O", (), {"session_secret_key": "test-secret-key-1234"})()},
        )(),
    )
    def test_each_state_is_unique(self, _mock_settings):
        from ii_agent.auth.router import _make_state

        s1 = _make_state()
        s2 = _make_state()
        assert s1 != s2
