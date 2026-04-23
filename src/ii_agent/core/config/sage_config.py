"""Configuration for the SAGE persistent memory integration.

All settings are driven by environment variables so no secrets live in the
source tree. The integration is strictly opt-in via ``SAGE_ENABLED``.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings


class SageConfig(BaseSettings):
    """Settings for the SAGE memory integration.

    Attributes:
        enabled: Master switch. When false (default) the integration is a
            no-op and never contacts a SAGE node.
        node_url: Base URL of the SAGE REST API (e.g. ``http://localhost:8090``).
        agent_id: Optional agent identifier (display name) used on
            ``register_agent``. If unset, registration is skipped.
        agent_key: Optional filesystem path to a 32-byte Ed25519 seed.
            Falls back to :meth:`AgentIdentity.default()` which respects
            ``SAGE_IDENTITY_PATH``.
        default_domain: Domain tag used for recall and propose when no
            per-call override is supplied.
        recall_top_k: Number of memories to fetch per pre-hook recall.
        pre_hook_timeout_s: Strict timeout for the pre-hook recall. On
            timeout the hook yields control immediately with no injected
            context — the agent turn is never blocked.
    """

    enabled: bool = False
    node_url: str = "http://localhost:8090"
    agent_id: str | None = None
    agent_key: str | None = None
    default_domain: str = "ii-agent"
    recall_top_k: int = 5
    pre_hook_timeout_s: float = 2.0

    class Config:
        env_prefix = "SAGE_"
        env_file = ".env"
        extra = "ignore"
