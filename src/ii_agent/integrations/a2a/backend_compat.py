"""Model-to-backend compatibility validation for A2A inner-loop backends.

Each backend only supports a specific set of models:

* ``copilot``    — GitHub Copilot CLI.  No prefix restriction; Copilot handles
                   its own BYOK routing so any model ID can be forwarded.
* ``claude-code``— Anthropic Claude Code CLI.  Only ``claude-*`` model IDs.
* ``codex``      — OpenAI Codex CLI.  Only ``o4-``, ``o3-``, ``o1-``, and
                   ``gpt-`` model ID prefixes.

Usage::

    from ii_agent.integrations.a2a.backend_compat import check_model_backend_compat

    warning = check_model_backend_compat("claude-3-7-sonnet-20250219", "codex")
    if warning:
        logger.warning(warning)
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Model-prefix allow list per backend
# An empty tuple means *no restriction* (any model ID is accepted).
# ---------------------------------------------------------------------------

_BACKEND_MODEL_PREFIXES: dict[str, tuple[str, ...]] = {
    "copilot": (),  # No restriction — Copilot routes its own BYOK
    "claude-code": ("claude-",),
    "codex": ("o4-", "o3-", "o1-", "gpt-"),
}


def check_model_backend_compat(model_id: str, backend: str) -> Optional[str]:
    """Return a warning message if *model_id* is incompatible with *backend*.

    Parameters
    ----------
    model_id:
        The LLM model identifier configured for the agent (e.g.
        ``"claude-3-7-sonnet-20250219"`` or ``"o4-mini"``).
    backend:
        The A2A backend name: ``"copilot"``, ``"claude-code"``, or
        ``"codex"``.

    Returns
    -------
    str or None
        A human-readable warning string if the model is incompatible with
        the backend, or ``None`` if they are compatible.

    Examples
    --------
    >>> check_model_backend_compat("claude-3-7-sonnet-20250219", "codex")
    "Model 'claude-3-7-sonnet-20250219' may not be supported by the 'codex' backend ..."
    >>> check_model_backend_compat("o4-mini", "codex")
    None
    >>> check_model_backend_compat("anything", "copilot")
    None
    """
    allowed_prefixes = _BACKEND_MODEL_PREFIXES.get(backend)
    if allowed_prefixes is None:
        # Unknown backend — skip validation
        return None
    if not allowed_prefixes:
        # No restriction for this backend
        return None

    if any(model_id.startswith(prefix) for prefix in allowed_prefixes):
        return None

    return (
        f"Model '{model_id}' may not be supported by the '{backend}' backend "
        f"(expected one of: {', '.join(allowed_prefixes[:-1] + (allowed_prefixes[-1] + '...',))}). "
        f"The backend may reject requests or produce unexpected results."
    )
