"""Utilities for handling A2A Extensions in adapter request/response processing.

A2A Extensions (https://google.github.io/A2A/#extensions) let agents advertise
and negotiate optional capabilities beyond the core spec.  These helpers are
used by the adapter layer to collect requested extensions from an incoming A2A
call context and to annotate responses with extension issue records when a
requested extension cannot be satisfied.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# Canonical A2A Extension URIs for II-Agent
# ---------------------------------------------------------------------------

REASONING_EXTENSION_URI: str = "urn:ii-agent:extensions:reasoning/v1"
"""Extension URI for streaming reasoning deltas (chain-of-thought thinking)."""

TOOL_TELEMETRY_EXTENSION_URI: str = "urn:ii-agent:extensions:tool-telemetry/v1"
"""Extension URI for structured tool call and tool result telemetry."""


def append_extension_issue(
    info: Optional[dict[str, Any]],
    *,
    uri: str,
    code: str,
    detail: Optional[str] = None,
) -> None:
    """Append an extension-issue record to *info* in-place.

    An extension issue record has the shape::

        {"uri": "https://...", "code": "UNSUPPORTED", "detail": "..."}

    The ``detail`` key is omitted when no detail is supplied.

    Parameters
    ----------
    info:
        The mutable mapping to append to.  If ``None`` the call is a no-op.
    uri:
        The extension URI that caused the issue.
    code:
        A short machine-readable code such as ``"UNSUPPORTED"`` or ``"MISSING"``.
    detail:
        Optional human-readable explanation.
    """
    if info is None:
        return

    existing = info.get("issues")
    if not isinstance(existing, list):
        existing = []
        info["issues"] = existing

    record: dict[str, Any] = {"uri": uri, "code": code}
    if detail is not None:
        record["detail"] = detail

    existing.append(record)


def _accumulate_extensions(
    bucket: set[str],
    values: Any,
) -> None:
    """Add string-convertible items from *values* into *bucket*.

    - Iterables of strings/numbers are normalised to stripped strings.
    - ``None``, empty strings, whitespace-only strings, and non-string/numeric
      items are silently ignored.
    - Non-iterable scalars (e.g. a bare ``int``) are silently ignored.
    """
    if values is None:
        return

    try:
        items: Iterable[Any] = iter(values)
    except TypeError:
        return

    for item in items:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                bucket.add(stripped)
        elif isinstance(item, (int, float)):
            bucket.add(str(item))
        # Other types (dict, list, None, …) are silently skipped.


def collect_requested_extensions(ctx: Any) -> set[str]:
    """Return the union of all extension URIs requested in *ctx*.

    The function is tolerant of missing attributes — if the context object
    does not have ``call_context``, ``message``, or their sub-attributes, those
    sources are simply skipped.

    Parameters
    ----------
    ctx:
        An A2A call context object (or any duck-typed equivalent used in tests).
        Expected optional attributes::

            ctx.call_context.requested_extensions  # Iterable[str] | None
            ctx.message.extensions                 # Iterable[str] | None

    Returns
    -------
    set[str]
        De-duplicated set of extension URI strings.
    """
    bucket: set[str] = set()

    # Source 1: call_context.requested_extensions
    call_context = getattr(ctx, "call_context", None)
    if call_context is not None:
        _accumulate_extensions(bucket, getattr(call_context, "requested_extensions", None))

    # Source 2: message.extensions
    message = getattr(ctx, "message", None)
    if message is not None:
        _accumulate_extensions(bucket, getattr(message, "extensions", None))

    return bucket
