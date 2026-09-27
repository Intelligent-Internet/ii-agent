"""Middleware and exception handlers for unhandled errors."""

from __future__ import annotations

from typing import Callable

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ii_agent.core.exceptions import IIAgentError, NotFoundException, PermissionException
from ii_agent.core.logger import logger


def _is_db_unavailable(exc: BaseException) -> bool:
    """Detect transient PostgreSQL unavailability.

    Returns True when ``exc`` (or any cause/context in its chain) is
    an asyncpg ``CannotConnectNowError`` (SQLSTATE 57P03 — emitted while
    the database is in startup, recovery, or shutdown).  SQLAlchemy
    typically wraps this in ``OperationalError`` / ``DBAPIError``; we
    walk the exception chain to find the original.

    Why a dedicated mapping: prior to 2026-04-25 these surfaced as
    opaque HTTP 500 ``Internal Server Error`` responses during a PG
    crash-recovery window (~7 min for a soft-killed container in WSL2).
    Clients had no way to distinguish "PG is recovering, retry shortly"
    from "the backend has a real bug".  See
    ``docs/runtime-docs/postgres-recovery-mode-failures.md``.
    """
    try:
        from asyncpg.exceptions import CannotConnectNowError  # type: ignore
    except ImportError:  # pragma: no cover — asyncpg always present in prod
        return False

    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, CannotConnectNowError):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


async def exception_logging_middleware(request: Request, call_next: Callable) -> Response:
    """Middleware to handle and log unhandled exceptions."""
    try:
        return await call_next(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    except Exception as exc:
        if _is_db_unavailable(exc):
            # Don't log full traceback — this is an expected transient
            # condition (PG crash-recovery, restart, failover).  A WARNING
            # with the cause is enough to track frequency without flooding
            # the log stream during a multi-minute recovery window.
            logger.warning(
                f"Database temporarily unavailable (PG in recovery): {type(exc).__name__}"
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Database temporarily unavailable",
                    "error_code": "db_unavailable",
                },
                headers={"Retry-After": "5"},
            )
        logger.exception("Unhandled exception")
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


async def permission_exception_handler(request: Request, exc: PermissionException) -> JSONResponse:
    """Exception handler for PermissionException."""
    logger.warning(f"Permission denied: {exc}")
    return JSONResponse(status_code=403, content={"detail": str(exc)})


async def not_found_exception_handler(request: Request, exc: NotFoundException) -> JSONResponse:
    """Exception handler for NotFoundException."""
    logger.warning(f"Not found: {exc}")
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def ii_agent_error_handler(request: Request, exc: IIAgentError) -> JSONResponse:
    """Exception handler for IIAgentError and subclasses."""
    logger.warning(f"IIAgentError: {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "error_code": exc.error_code},
        headers=exc.headers,
    )
