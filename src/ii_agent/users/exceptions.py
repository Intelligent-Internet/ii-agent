"""Custom exceptions for users domain."""

from ii_agent.core.exceptions import PermissionDeniedError


class UsersException(PermissionDeniedError):
    """Base exception for users domain."""

    pass


class WaitlistDeniedException(UsersException):
    """Raised when user is not on the waitlist during private beta."""

    pass


class UserDisabledException(PermissionDeniedError):
    """Raised when a disabled user attempts to authenticate."""

    status_code = 401
