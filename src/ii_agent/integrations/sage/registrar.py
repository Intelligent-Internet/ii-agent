"""Agent-side registration helper for the SAGE integration.

The entrypoint is :func:`register_sage_hooks` which appends the pre- and
post-hooks onto a live :class:`IIAgent` instance. It honours existing
hooks on the agent (extending rather than replacing the lists) so host
applications can freely combine SAGE with their own observability hooks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ii_agent.core.config.sage_config import SageConfig
from ii_agent.core.logger import logger
from ii_agent.integrations.sage.client import SageClient
from ii_agent.integrations.sage.hooks import make_sage_hooks

if TYPE_CHECKING:  # pragma: no cover — type-checking only
    from ii_agent.agents.agent import IIAgent


def register_sage_hooks(
    agent: "IIAgent",
    *,
    config: SageConfig | None = None,
    client: SageClient | None = None,
) -> SageClient | None:
    """Wire the SAGE pre- and post-hooks onto ``agent``.

    The integration is strictly opt-in. When ``SAGE_ENABLED`` is unset or
    false, this is a no-op and returns ``None``.

    Args:
        agent: A constructed :class:`IIAgent` instance.
        config: Optional pre-built :class:`SageConfig`. Defaults to
            environment-driven configuration.
        client: Optional pre-built :class:`SageClient`. Useful for tests
            that inject a stub.

    Returns:
        The :class:`SageClient` bound to the hooks, or ``None`` when the
        integration is disabled.
    """
    cfg = config or SageConfig()
    if not cfg.enabled:
        logger.debug("SAGE integration disabled (SAGE_ENABLED is false or unset)")
        return None

    sage_client = client or SageClient(cfg)
    pre_hook, post_hook = make_sage_hooks(sage_client)

    # Extend existing hook lists rather than replacing them so callers can
    # freely combine SAGE with their own hooks.
    existing_pre = list(agent.pre_hooks or [])
    existing_post = list(agent.post_hooks or [])
    agent.pre_hooks = existing_pre + [pre_hook]
    agent.post_hooks = existing_post + [post_hook]

    logger.info(
        f"SAGE integration registered "
        f"(node={cfg.node_url}, domain={cfg.default_domain})"
    )
    return sage_client
