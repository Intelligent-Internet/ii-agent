"""Adapter utilities for extracting structured request payloads from A2A call contexts.

The A2A spec lets callers embed arbitrary metadata in the ``Task.metadata`` and
``Message.metadata`` fields.  II-Agent uses a namespaced ``"ii-agent"`` key at
both levels.  This module provides:

* Small type-coercion helpers (``_as_bool``, ``_as_int``, ``_as_str``).
* A dict-merge helper (``_deep_merge``).
* Key-alias lookup helpers (``_pick_first_key``, ``_extract_mapping``).
* The public ``extract_request_payload(context)`` function that produces a
  typed ``RequestPayload`` dataclass consumed by the adapter handler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence


# ---------------------------------------------------------------------------
# Type-coercion helpers
# ---------------------------------------------------------------------------

_TRUTHY_STRINGS = {"true", "1", "yes"}
_FALSY_STRINGS = {"false", "0", "no"}


def _as_bool(value: Any) -> bool:
    """Coerce *value* to ``bool``.

    String variants (case-insensitive, stripped) take precedence::

        "true" / "1" / "yes"   → True
        "false" / "0" / "no"   → False
        any other str           → bool(value)

    All other types fall back to ``bool(value)``.
    """
    if isinstance(value, str):
        normalised = value.strip().lower()
        if normalised in _TRUTHY_STRINGS:
            return True
        if normalised in _FALSY_STRINGS:
            return False
    return bool(value)


def _as_int(value: Any) -> Optional[int]:
    """Coerce *value* to ``int``, returning ``None`` on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _as_str(value: Any) -> Optional[str]:
    """Coerce *value* to ``str``, returning ``None`` for ``None`` input."""
    if value is None:
        return None
    return str(value)


# ---------------------------------------------------------------------------
# Dict utility helpers
# ---------------------------------------------------------------------------


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Recursively merge *source* into *target* in-place.

    * Scalar values in *source* overwrite those in *target*.
    * When both *target* and *source* have a ``dict`` under the same key the
      dicts are merged recursively.
    * All other type combinations result in *source* overwriting *target*.
    """
    for key, src_val in source.items():
        tgt_val = target.get(key)
        if isinstance(src_val, dict) and isinstance(tgt_val, dict):
            _deep_merge(tgt_val, src_val)
        else:
            target[key] = src_val


def _pick_first_key(
    source: dict[str, Any],
    keys: Sequence[str],
) -> Optional[Any]:
    """Return the first non-``None`` value found under any of *keys* in *source*.

    Returns ``None`` when no key matches or all matching values are ``None``.
    """
    for key in keys:
        value = source.get(key)
        if value is not None:
            return value
    return None


_II_AGENT_KEYS = ("ii-agent", "ii_agent", "iiAgent")


def _extract_mapping(
    source: dict[str, Any],
    keys: Sequence[str],
) -> dict[str, Any]:
    """Return a shallow copy of the first ``Mapping`` value found under any *keys*.

    Returns an empty dict when no matching non-``Mapping`` value is found or
    when *keys* is empty.
    """
    for key in keys:
        value = source.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


# ---------------------------------------------------------------------------
# Structured payload dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SandboxOptions:
    """Extracted sandbox configuration from request metadata."""

    reuse: bool = False
    timeout_seconds: Optional[int] = None


@dataclass
class UserContext:
    """Extracted user identity from request metadata."""

    user_id: Optional[str] = None
    api_key: Optional[str] = None


@dataclass
class RequestPayload:
    """Fully extracted and typed request payload from an A2A call context."""

    tool_args: dict[str, Any] = field(default_factory=dict)
    sandbox: SandboxOptions = field(default_factory=SandboxOptions)
    user: UserContext = field(default_factory=UserContext)


# ---------------------------------------------------------------------------
# Public extraction function
# ---------------------------------------------------------------------------


def extract_request_payload(context: Any) -> RequestPayload:
    """Extract a typed ``RequestPayload`` from an A2A call context.

    The function reads the ``"ii-agent"`` namespace from two metadata sources:

    1. ``context.metadata`` (task-level / connection-level)
    2. ``context.message.metadata`` (per-message)

    Per-message values are layered on top of task-level values via
    ``_deep_merge``.

    Parameters
    ----------
    context:
        Any A2A call context object (or duck-typed test stub) with optional
        ``metadata: dict`` and ``message.metadata: dict`` attributes.

    Returns
    -------
    RequestPayload
        Always returns a valid payload; missing/invalid values are replaced
        with safe defaults.
    """
    merged: dict[str, Any] = {}

    # ── Task-level metadata ──────────────────────────────────────────────────
    task_meta = getattr(context, "metadata", None) or {}
    if isinstance(task_meta, dict):
        ii_agent_task = _pick_first_key(task_meta, _II_AGENT_KEYS)
        if isinstance(ii_agent_task, dict):
            _deep_merge(merged, ii_agent_task)

    # ── Message-level metadata (layered on top) ───────────────────────────────
    message = getattr(context, "message", None)
    if message is not None:
        msg_meta = getattr(message, "metadata", None) or {}
        if isinstance(msg_meta, dict):
            ii_agent_msg = _pick_first_key(msg_meta, _II_AGENT_KEYS)
            if isinstance(ii_agent_msg, dict):
                _deep_merge(merged, ii_agent_msg)

    # ── Extract sections ─────────────────────────────────────────────────────
    _TOOL_ARGS_KEYS = ("tool_args", "toolArgs")
    _SANDBOX_KEYS = ("sandbox", "sandbox_options", "sandboxOptions")
    _USER_KEYS = ("user", "user_context", "userContext")

    tool_args = _extract_mapping(merged, _TOOL_ARGS_KEYS)

    sandbox_raw = _extract_mapping(merged, _SANDBOX_KEYS)
    sandbox = SandboxOptions(
        reuse=_as_bool(sandbox_raw.get("reuse", False)),
        timeout_seconds=_as_int(sandbox_raw.get("timeout") or sandbox_raw.get("timeout_seconds")),
    )

    user_raw = _extract_mapping(merged, _USER_KEYS)
    user = UserContext(
        user_id=_as_str(user_raw.get("user_id") or user_raw.get("userId")),
        api_key=_as_str(user_raw.get("api_key") or user_raw.get("apiKey")),
    )

    return RequestPayload(tool_args=tool_args, sandbox=sandbox, user=user)
