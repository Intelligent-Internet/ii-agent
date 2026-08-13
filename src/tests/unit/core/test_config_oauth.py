"""Tests for ii_agent.core.config.oauth — OAuth2Settings helpers."""

from __future__ import annotations


class TestOAuth2Settings:
    def _make_settings(self, **kwargs):
        from ii_agent.core.config.oauth import OAuth2Settings

        return OAuth2Settings(**kwargs)

    def test_has_google_oauth_true(self):
        """Line 139: both google credentials set."""
        s = self._make_settings(google_client_id="id", google_client_secret="secret")
        assert s.has_google_oauth() is True

    def test_has_google_oauth_false(self):
        """Line 139: missing google credentials."""
        s = self._make_settings()
        assert s.has_google_oauth() is False

    def test_has_github_oauth_true(self):
        """Line 143: both github credentials set."""
        s = self._make_settings(github_client_id="gid", github_client_secret="gsecret")
        assert s.has_github_oauth() is True

    def test_has_github_oauth_false(self):
        s = self._make_settings()
        assert s.has_github_oauth() is False

    def test_has_github_app_true(self):
        """Line 147: github app configured."""
        s = self._make_settings(github_app_id="app-id", github_app_private_key="priv-key")
        assert s.has_github_app() is True

    def test_has_github_app_false(self):
        s = self._make_settings()
        assert s.has_github_app() is False

    def test_has_revenuecat_oauth_true(self):
        """Line 156: revenuecat client id set."""
        s = self._make_settings(revenuecat_client_id="rc-id")
        assert s.has_revenuecat_oauth() is True

    def test_has_revenuecat_oauth_false(self):
        s = self._make_settings()
        assert s.has_revenuecat_oauth() is False

    def test_has_ii_oauth_true(self):
        """Line 160: ii_client_id set."""
        s = self._make_settings(ii_client_id="ii-id")
        assert s.has_ii_oauth() is True

    def test_has_ii_oauth_false(self):
        s = self._make_settings()
        assert s.has_ii_oauth() is False
