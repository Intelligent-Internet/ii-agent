"""Tests for ii_agent.auth.exceptions — AuthException and subclasses."""

from __future__ import annotations


class TestAuthExceptions:
    def test_auth_exception_sets_www_authenticate_header(self):
        from ii_agent.auth.exceptions import AuthException

        exc = AuthException("bad token")
        assert exc.status_code == 401
        assert "WWW-Authenticate" in exc.headers

    def test_auth_exception_without_message(self):
        from ii_agent.auth.exceptions import AuthException

        exc = AuthException()
        assert exc.status_code == 401

    def test_invalid_credentials_exception(self):
        from ii_agent.auth.exceptions import InvalidCredentialsException

        exc = InvalidCredentialsException("wrong password")
        assert exc.status_code == 401
