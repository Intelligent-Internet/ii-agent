"""
Centralized logging configuration using loguru.

Simple setup following best practices:
- JSON format for production (GCP Cloud Logging compatible)
- Human-readable format for local development
- Intercepts standard library logging via dictConfig + InterceptHandler
- Use logger.contextualize() for request context
"""

import json
import logging
import logging.config
import os
import sys
import traceback
import warnings
from typing import Any

from loguru import logger

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ENVIRONMENT = os.getenv("ENVIRONMENT", "local").lower()
IS_CELERY_WORKER = os.getenv("II_AGENT_CELERY_WORKER") == "1"

# JSON format for non-local environments or Celery workers
USE_JSON_LOGS = ENVIRONMENT != "local" or IS_CELERY_WORKER


def _serialize(record: dict[str, Any]) -> str:
    """Serialize log record to GCP-compatible JSON."""
    log_entry = {
        "severity": record["level"].name,
        "message": record["message"],
        "time": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "logger": record["name"] or "root",
        "location": {
            "file": record["file"].path if record["file"] else None,
            "line": record["line"],
            "function": record["function"],
        },
    }

    # Add all extra fields (context from logger.bind() or contextualize())
    if record["extra"]:
        log_entry.update(record["extra"])
        log_entry["labels"] = record["extra"]

    # Add exception info
    if record["exception"]:
        exc = record["exception"]
        if exc.type and exc.value:
            tb = traceback.format_exception(exc.type, exc.value, exc.traceback)
            log_entry["exception"] = {
                "type": exc.type.__name__,
                "message": str(exc.value),
                "stackTrace": "".join(tb),
            }
            log_entry["stack_trace"] = "".join(tb)

    return json.dumps(log_entry, default=str, ensure_ascii=False)


def _json_sink(message: Any) -> None:
    """Output JSON formatted logs to stdout."""
    sys.stdout.write(_serialize(message.record) + "\n")
    sys.stdout.flush()


class InterceptHandler(logging.Handler):
    """Redirect standard library logging to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {
        "loguru": {
            "()": InterceptHandler,
        },
    },
    "root": {
        "handlers": ["loguru"],
        "level": 0,
    },
    "loggers": {
        # Application
        "ii_agent": {"level": LOG_LEVEL},
        # HTTP clients
        # httpx at INFO so outgoing HTTP requests (e.g. POST api.anthropic.com)
        # appear in the log. Without this, a hung native LLM streaming call is
        # invisible until it eventually times out.
        "httpx": {"level": logging.INFO},
        "httpcore": {"level": logging.WARNING},
        # Async
        "asyncio": {"level": logging.WARNING},
        # Web server
        "uvicorn": {"level": logging.WARNING},
        "uvicorn.access": {"level": logging.WARNING},
        "websockets": {"level": logging.WARNING},
        # E2B sandbox
        "e2b": {"level": logging.WARNING},
        # Google GenAI
        "google_genai": {"level": logging.WARNING},
        "google_genai.models": {"level": logging.WARNING},
        # MCP (Model Context Protocol)
        "mcp": {"level": logging.WARNING},
        "mcp.server": {"level": logging.WARNING},
        # Scheduler
        "apscheduler": {"level": logging.WARNING},
        # Celery internal
        "celery": {"level": logging.INFO},
        "celery.app.trace": {"level": logging.INFO},
        "celery.redirected": {"level": logging.WARNING},
        # Third-party tools
        "ii_agent_tools": {"level": logging.INFO},
    },
}


def setup_logging() -> None:
    """Configure loguru sinks and apply stdlib dictConfig."""
    # Remove default loguru handler
    logger.remove()

    # Add loguru sink (JSON for production/celery, human-readable for local)
    common = {
        "level": LOG_LEVEL,
        "enqueue": not IS_CELERY_WORKER,  # Sync for Celery (fork-safe)
    }

    if USE_JSON_LOGS:
        logger.add(
            _json_sink,
            format="{message}",
            backtrace=False,
            diagnose=False,
            **common,
        )
    else:
        logger.add(
            sys.stdout,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            colorize=True,
            backtrace=True,
            diagnose=True,
            **common,
        )

    # Apply stdlib config: route all stdlib logging through InterceptHandler
    logging.config.dictConfig(LOGGING_CONFIG)


def reconfigure_logging() -> None:
    """Re-apply stdlib dictConfig after third-party imports.

    Call this from Celery signals (setup_logging, worker_process_init) to
    clean up handlers that libraries add after initial setup_logging().
    """
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", message=".*aiohttp.*")
    logging.config.dictConfig(LOGGING_CONFIG)


async def shutdown_logger() -> None:
    """Flush all pending log messages."""
    await logger.complete()


# Initialize on import
setup_logging()

# Export
__all__ = ["logger", "setup_logging", "reconfigure_logging", "shutdown_logger"]
