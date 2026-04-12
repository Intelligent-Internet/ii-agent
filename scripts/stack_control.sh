#!/usr/bin/env bash
#
# stack_control.sh - Manage ii-agent local Docker stack
#
# Usage:
#   scripts/stack_control.sh <command> [options]
#
# Commands:
#   start           Start all services
#   stop            Stop all services
#   restart         Restart all services (picks up env changes)
#   rebuild         Rebuild images from scratch (no cache) and restart
#   build-sandbox   Build the sandbox Docker image (full --no-cache)
#   build-sandbox --quick  Rebuild sandbox image with layer cache (fast for src-only changes)
#   patch-sandbox   Hot-patch source files into running sandbox containers
#   status          Show running containers and URLs
#   logs [service]  View logs (add -f to follow)
#   cleanup         Remove orphaned sandbox containers
#   setup           Create .stack.env.local from template
#
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.local.yaml"
ENV_FILE="$ROOT_DIR/docker/.stack.env.local"
ENV_EXAMPLE="$ROOT_DIR/docker/.stack.env.local.example"
PROJECT_NAME=${COMPOSE_PROJECT_NAME:-ii-agent-local}
SANDBOX_IMAGE=${SANDBOX_DOCKER_IMAGE:-ii-agent-sandbox:latest}

# ── Helpers ────────────────────────────────────────────────────────────────

compose() {
  docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found."
    echo "Run: scripts/stack_control.sh setup"
    exit 1
  fi
}

# ── Commands ───────────────────────────────────────────────────────────────

cmd_setup() {
  if [[ -f "$ENV_FILE" ]]; then
    echo "$ENV_FILE already exists. Remove it first to re-create."
    exit 1
  fi
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "Created $ENV_FILE from template."
  echo "Edit it with your API keys, then run: scripts/stack_control.sh start"
}

cmd_build_sandbox() {
  local use_cache=false
  if [[ "${1:-}" == "--quick" ]]; then
    use_cache=true
    shift
  fi

  if [[ "$use_cache" == true ]]; then
    echo "Building sandbox image (with cache, fast): $SANDBOX_IMAGE"
    docker build -t "$SANDBOX_IMAGE" -f "$ROOT_DIR/e2b.Dockerfile" "$ROOT_DIR"
  else
    echo "Building sandbox image (no cache, full rebuild): $SANDBOX_IMAGE"
    docker build --no-cache -t "$SANDBOX_IMAGE" -f "$ROOT_DIR/e2b.Dockerfile" "$ROOT_DIR"
  fi
  echo "Done. Image: $SANDBOX_IMAGE"

  # Verify the image was actually updated
  local image_date
  image_date=$(docker images "$SANDBOX_IMAGE" --format '{{.CreatedAt}}' | head -1)
  echo "Image timestamp: $image_date"
}

cmd_patch_sandbox() {
  # Hot-patch source files into all running sandbox containers.
  # Copies the A2A adapter and related source into each sandbox without
  # requiring a full image rebuild. Useful for rapid iteration.
  local containers
  containers=$(docker ps --filter "name=ii-sandbox" --format '{{.Names}}')
  if [[ -z "$containers" ]]; then
    echo "No running sandbox containers found."
    return
  fi

  local count patched=0
  count=$(echo "$containers" | wc -l)
  echo "Found $count running sandbox container(s). Patching..."

  local src_a2a="$ROOT_DIR/src/ii_agent/integrations/a2a"
  local dst_a2a="/app/ii_sandbox/src/ii_agent/integrations/a2a"

  while IFS= read -r name; do
    if docker cp "$src_a2a/." "$name:$dst_a2a/" 2>/dev/null; then
      echo "  Patched: $name"
      patched=$((patched + 1))
    else
      echo "  FAILED:  $name"
    fi
  done <<< "$containers"

  echo "Done. Patched $patched/$count container(s)."
  echo ""
  echo "NOTE: Restart the adapter process inside each sandbox to pick up changes."
  echo "  docker exec <container> tmux send-keys -t adapter C-c && docker exec <container> tmux send-keys -t adapter 'python -m ii_agent.integrations.a2a.adapter_server' Enter"
}

cmd_start() {
  ensure_env
  echo "Starting ii-agent local stack..."
  compose up -d "$@"
  echo ""
  cmd_status
}

cmd_stop() {
  ensure_env
  echo "Stopping ii-agent local stack..."
  compose down "$@"
}

cmd_restart() {
  ensure_env
  echo "Restarting ii-agent local stack..."
  compose down
  compose up -d "$@"
  echo ""
  cmd_status
}

cmd_rebuild() {
  ensure_env
  echo "Rebuilding (no cache) and restarting ii-agent local stack..."
  compose down
  compose build --no-cache "$@"
  compose up -d
  echo ""
  cmd_status
}

cmd_status() {
  ensure_env
  echo "=== ii-agent local stack status ==="
  compose ps
  echo ""
  echo "Service URLs:"
  echo "  Frontend:  http://localhost:${FRONTEND_PORT:-1420}"
  echo "  Backend:   http://localhost:${BACKEND_PORT:-8000}"
  echo "  Minio UI:  http://localhost:${MINIO_CONSOLE_PORT:-9001}"
}

cmd_logs() {
  ensure_env
  compose logs "$@"
}

cmd_cleanup() {
  echo "Removing orphaned sandbox containers..."
  local containers
  containers=$(docker ps -a --filter "label=ii-agent.sandbox=true" --filter "status=exited" -q)
  if [[ -z "$containers" ]]; then
    echo "No orphaned sandbox containers found."
    return
  fi
  local count
  count=$(echo "$containers" | wc -l)
  echo "Found $count orphaned containers. Removing..."
  echo "$containers" | xargs docker rm -f
  echo "Done."
}

# ── Main ───────────────────────────────────────────────────────────────────

case "${1:-help}" in
  setup)          cmd_setup ;;
  build-sandbox)  shift; cmd_build_sandbox "$@" ;;
  patch-sandbox)  cmd_patch_sandbox ;;
  start)          shift; cmd_start "$@" ;;
  stop)           shift; cmd_stop "$@" ;;
  restart)        shift; cmd_restart "$@" ;;
  rebuild)        shift; cmd_rebuild "$@" ;;
  status)         cmd_status ;;
  logs)           shift; cmd_logs "$@" ;;
  cleanup)        cmd_cleanup ;;
  help|--help|-h)
    sed -n '2,/^set /p' "$0" | head -n -1
    ;;
  *)
    echo "Unknown command: $1"
    echo "Run: scripts/stack_control.sh --help"
    exit 1
    ;;
esac
