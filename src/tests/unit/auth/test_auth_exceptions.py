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


class TestUserDisabledException:
    def test_status_code_is_401(self):
        """Disabled-user attempts must return 401 Unauthorized, not 403 Forbidden."""
        from ii_agent.users.exceptions import UserDisabledException

        exc = UserDisabledException("User account is disabled")
        assert exc.status_code == 401

    def test_is_permission_denied_error(self):
        """UserDisabledException must be a PermissionDeniedError (not AuthException)."""
        from ii_agent.core.exceptions import PermissionDeniedError
        from ii_agent.users.exceptions import UserDisabledException

        exc = UserDisabledException("User account is disabled")
        assert isinstance(exc, PermissionDeniedError)

    def test_no_circular_import(self):
        """Importing UserDisabledException must not trigger circular auth import."""
        # This test would fail with ImportError at collection time if circular
        from ii_agent.users.exceptions import UserDisabledException  # noqa: F401
