"""Sandbox domain enums."""

from enum import StrEnum


class SandboxStatus(StrEnum):
    """Sandbox lifecycle status values."""

    NOT_INITIALIZED = "not_initialized"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    DELETED = "deleted"
    ERROR = "error"


class SandboxProviderType(StrEnum):
    """Supported sandbox provider backends."""

    E2B = "e2b"
    DOCKER = "docker"


class PoolState(StrEnum):
    """Pool-managed sandbox lifecycle state.

    Only set on rows that belong to the pre-warmed sandbox pool. Plain
    session-bound sandboxes leave ``pool_state`` NULL.
    """

    AVAILABLE = "available"  # Pre-warmed, ready to be claimed
    CLAIMED = "claimed"  # Handed off to a session (no longer in pool)
    RETIRING = "retiring"  # Marked for shutdown by the cleanup loop
