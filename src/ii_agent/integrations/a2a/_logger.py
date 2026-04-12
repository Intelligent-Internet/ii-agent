"""Portable logger for A2A modules.

Uses loguru (via ``ii_agent.core.logger``) when available in the main backend,
and falls back to stdlib :mod:`logging` inside the lightweight sandbox
environment where loguru is not installed.

The shim provides a loguru-compatible ``.opt(exception=True)`` method so
call-sites can use the same API in both environments.
"""

from __future__ import annotations

import sys as _sys

try:
    from ii_agent.core.logger import logger  # noqa: F401 — re-export
except ImportError:
    import logging as _logging

    _stdlib = _logging.getLogger("ii_agent.integrations.a2a")

    class _Opt:
        """Proxy that attaches *exc_info* to every log call."""

        def __init__(self, base: _logging.Logger, exc_info: bool) -> None:
            self._base = base
            self._exc_info = exc_info

        def __getattr__(self, name: str):  # type: ignore[override]
            fn = getattr(self._base, name)
            if not self._exc_info:
                return fn

            def _with_exc(msg: str, *a, **kw):  # type: ignore[no-untyped-def]
                kw.setdefault("exc_info", _sys.exc_info())
                return fn(msg, *a, **kw)

            return _with_exc

    class _LoggerShim:
        """Stdlib logger wrapped with a loguru-compatible ``.opt()`` method."""

        def __init__(self, base: _logging.Logger) -> None:
            self._base = base

        def __getattr__(self, name: str):  # type: ignore[override]
            return getattr(self._base, name)

        def opt(self, *, exception: bool = False, **_kw) -> _Opt:  # type: ignore[no-untyped-def]
            return _Opt(self._base, exc_info=exception)

    logger = _LoggerShim(_stdlib)  # type: ignore[assignment]
