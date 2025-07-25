"""Exception classes for the runtime system.

This module defines custom exceptions used throughout the runtime system to
handle various error conditions in a structured way.
"""


class RuntimeError(Exception):
    """Base exception for runtime-related errors."""


class RuntimeTimeoutError(RuntimeError):
    """Exception raised when a runtime operation times out."""


class RuntimeResourceError(RuntimeError):
    """Exception raised for resource-related errors."""


class RuntimeUninitializedError(RuntimeError):
    """Exception raised when a runtime is not initialized."""
