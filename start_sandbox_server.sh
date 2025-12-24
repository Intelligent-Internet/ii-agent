#!/bin/bash

# II Sandbox Server Startup Script
# This script starts the standalone sandbox server

set -e

# Default configuration
DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="8100"
DEFAULT_PROVIDER="e2b"

# Allow overriding via environment variables
export SERVER_HOST="${SERVER_HOST:-$DEFAULT_HOST}"
export SERVER_PORT="${SERVER_PORT:-$DEFAULT_PORT}"
# Support both SANDBOX_PROVIDER and PROVIDER env vars
export PROVIDER="${SANDBOX_PROVIDER:-${PROVIDER:-$DEFAULT_PROVIDER}}"
export REDIS_URL="${REDIS_URL:-$DEFAULT_REDIS_URL}"

export MCP_PORT="${MCP_PORT:-5173}"

# Timeout configuration
export TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-5400}"
export PAUSE_BEFORE_TIMEOUT_SECONDS="${PAUSE_BEFORE_TIMEOUT_SECONDS:-600}"
export TIMEOUT_BUFFER_SECONDS="${TIMEOUT_BUFFER_SECONDS:-300}"

echo "Starting II Sandbox Server..."
echo "Host: $SERVER_HOST"
echo "Port: $SERVER_PORT"
echo "Provider: $PROVIDER"
echo "Redis URL: $REDIS_URL"

# Check if E2B API key is set when using E2B provider
if [ "$PROVIDER" = "e2b" ] && [ -z "$E2B_API_KEY" ]; then
  echo "Error: E2B_API_KEY environment variable is required when using E2B provider"
  exit 1
fi

# Check if Redis is accessible
echo "Checking Redis connection..."
if command -v redis-cli >/dev/null 2>&1; then
  if ! redis-cli -u "$REDIS_URL" ping >/dev/null 2>&1; then
    echo "Warning: Cannot connect to Redis at $REDIS_URL"
    echo "Make sure Redis is running or update REDIS_URL environment variable"
  else
    echo "Redis connection OK"
  fi
else
  echo "Warning: redis-cli not found, skipping Redis connection check"
fi

# Start the server using uvicorn
echo "Starting server..."
exec uvicorn ii_sandbox_server.main:app \
  --host "$SERVER_HOST" \
  --port "$SERVER_PORT" \
  --reload \
  --log-level info
