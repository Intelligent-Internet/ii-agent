#!/bin/bash
set -euo pipefail

MODE="${1:-api}"
shift 2>/dev/null || true

# ---------------------------------------------------------------------------
# Configurable env vars (with sensible defaults)
# ---------------------------------------------------------------------------
GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-360}"
GUNICORN_BIND="${GUNICORN_BIND:-0.0.0.0:8000}"
# Graceful-timeout: how long gunicorn waits after SIGTERM for the worker's
# lifespan shutdown to complete before it sends SIGKILL. Must be < the
# compose-level stop_grace_period (30s) so the orchestrator never wins the
# race. 25s leaves 5s headroom. See
# docs/runtime-docs/postgres-recovery-mode-failures.md (Backend shutdown
# contract section).
GUNICORN_GRACEFUL_TIMEOUT="${GUNICORN_GRACEFUL_TIMEOUT:-25}"

CELERY_APP="${CELERY_APP:-ii_agent.workers.celery.app:celery_app}"
CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-4}"
CELERY_LOGLEVEL="${CELERY_LOGLEVEL:-info}"
CELERY_QUEUES="${CELERY_QUEUES:-default,high_priority,low_priority}"

FLOWER_PORT="${FLOWER_PORT:-5555}"

# ---------------------------------------------------------------------------
# Mode dispatch
# ---------------------------------------------------------------------------
case "$MODE" in
    api)
        echo "Starting API server (gunicorn + uvicorn workers)..."
        exec gunicorn ii_agent.ws_server:app \
            -k uvicorn.workers.UvicornWorker \
            --workers "$GUNICORN_WORKERS" \
            --timeout "$GUNICORN_TIMEOUT" \
            --graceful-timeout "$GUNICORN_GRACEFUL_TIMEOUT" \
            --bind "$GUNICORN_BIND" \
            "$@"
        ;;
    worker)
        echo "Starting Celery worker..."
        exec celery -A "$CELERY_APP" worker \
            --loglevel="$CELERY_LOGLEVEL" \
            --concurrency="$CELERY_CONCURRENCY" \
            --queues="$CELERY_QUEUES" \
            "$@"
        ;;
    beat)
        echo "Starting Celery beat..."
        exec celery -A "$CELERY_APP" beat \
            --loglevel="$CELERY_LOGLEVEL" \
            "$@"
        ;;
    flower)
        echo "Starting Celery Flower..."
        exec celery -A "$CELERY_APP" flower \
            --port="$FLOWER_PORT" \
            "$@"
        ;;
    *)
        echo "Unknown mode '$MODE' — executing as command..."
        exec "$MODE" "$@"
        ;;
esac
