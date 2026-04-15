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
#   build           Build any combination of backend/frontend/sandbox in parallel
#   build-sandbox   Build the sandbox Docker image (full --no-cache)
#   build-sandbox --quick  Rebuild sandbox image with layer cache (fast for src-only changes)
#   patch-sandbox   Hot-patch source files into running sandbox containers and restart services
#   patch-sandbox --no-restart  Hot-patch without restarting (processes keep old code)
#   status          Show running containers and URLs
#   logs [service]  View logs (add -f to follow)
#   cleanup         Remove stale sandbox containers
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

print_help() {
  cat <<EOF
stack_control.sh - Manage ii-agent local Docker stack

Usage:
  scripts/stack_control.sh <command> [options]

Commands:
  start                        Start all services
  stop                         Stop all services
  restart                      Restart all services (picks up env changes)
  rebuild [service ...]        Rebuild compose services with no cache and restart
  build [targets ...] [flags]  Build backend/frontend/sandbox in parallel
  build-sandbox [--quick]      Build the sandbox image only
  patch-sandbox [--no-restart] Hot-patch source into running sandbox containers
  status                       Show running containers and URLs
  logs [service] [-f]          View logs for the full stack or a single service
  cleanup                      Remove stale sandbox containers
  setup                        Create docker/.stack.env.local from template

Build targets:
  backend    FastAPI app, agent runtime, billing, APIs
  frontend   Chat UI and web client
  sandbox    Tool execution / code sandbox image
  all        Alias for backend frontend sandbox

Build flags:
  --no-cache   Full rebuild without cache for selected targets
  --quick      Prefer cache (useful for rapid sandbox iteration)
  -h, --help   Show command help

Agent-focused use cases:
  scripts/stack_control.sh build backend
      Rebuild the backend when changing agent logic, routing, billing, or APIs.

  scripts/stack_control.sh build frontend backend
      Rebuild both UI and API together when chat contracts or UX flows change.

  scripts/stack_control.sh build sandbox --quick
      Fast iteration when changing tool execution, A2A adapter, or sandbox code.

  scripts/stack_control.sh build all --no-cache
      Clean parallel rebuild of the full local agent stack.

Notes:
  - The build command runs selected targets in parallel and returns non-zero if any target fails.
  - Use rebuild when you want compose services rebuilt and then restarted.
EOF
}

print_build_help() {
  cat <<EOF
Usage:
  scripts/stack_control.sh build [targets ...] [--no-cache] [--quick]

Targets:
  backend | frontend | sandbox | all

Examples:
  scripts/stack_control.sh build backend
  scripts/stack_control.sh build frontend backend
  scripts/stack_control.sh build backend sandbox --quick
  scripts/stack_control.sh build all --no-cache

Agent-focused guidance:
  - Pick backend for agent runtime, billing, API, or orchestration changes.
  - Pick frontend for chat UX or client integration changes.
  - Pick sandbox for tool bridge, code execution, or adapter environment changes.
  - Combine targets in one command to rebuild the exact surfaces touched by your change.
EOF
}

build_compose_target() {
  local target="$1"
  local use_cache="$2"

  set -o pipefail
  echo "[$target] Starting compose build"
  if [[ "$use_cache" == true ]]; then
    compose build "$target" 2>&1 | sed -u "s/^/[$target] /"
  else
    compose build --no-cache "$target" 2>&1 | sed -u "s/^/[$target] /"
  fi
  echo "[$target] Build complete"
}

build_sandbox_target() {
  local use_cache="$1"

  set -o pipefail
  echo "[sandbox] Starting Docker build for $SANDBOX_IMAGE"
  if [[ "$use_cache" == true ]]; then
    docker build -t "$SANDBOX_IMAGE" -f "$ROOT_DIR/e2b.Dockerfile" "$ROOT_DIR" 2>&1 | sed -u 's/^/[sandbox] /'
  else
    docker build --no-cache -t "$SANDBOX_IMAGE" -f "$ROOT_DIR/e2b.Dockerfile" "$ROOT_DIR" 2>&1 | sed -u 's/^/[sandbox] /'
  fi
  local image_date
  image_date=$(docker images "$SANDBOX_IMAGE" --format '{{.CreatedAt}}' | head -1)
  echo "[sandbox] Image timestamp: $image_date"
  echo "[sandbox] Build complete"
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
  elif [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    print_build_help
    return 0
  fi

  build_sandbox_target "$use_cache"
}

cmd_build() {
  ensure_env

  local use_cache=true
  local targets=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      backend|frontend|sandbox)
        targets+=("$1")
        ;;
      all)
        targets+=(backend frontend sandbox)
        ;;
      --no-cache)
        use_cache=false
        ;;
      --quick)
        use_cache=true
        ;;
      -h|--help)
        print_build_help
        return 0
        ;;
      *)
        echo "Unknown build target or option: $1"
        echo ""
        print_build_help
        return 1
        ;;
    esac
    shift
  done

  if [[ ${#targets[@]} -eq 0 ]]; then
    targets=(backend frontend sandbox)
  fi

  local deduped=()
  local target
  for target in "${targets[@]}"; do
    local seen=false
    local existing
    for existing in "${deduped[@]}"; do
      if [[ "$existing" == "$target" ]]; then
        seen=true
        break
      fi
    done
    if [[ "$seen" == false ]]; then
      deduped+=("$target")
    fi
  done

  echo "Building targets in parallel: ${deduped[*]}"
  if [[ "$use_cache" == true ]]; then
    echo "Build mode: cache-enabled"
  else
    echo "Build mode: no-cache"
  fi
  echo ""

  local pids=()
  local labels=()

  for target in "${deduped[@]}"; do
    case "$target" in
      backend|frontend)
        build_compose_target "$target" "$use_cache" &
        pids+=("$!")
        labels+=("$target")
        ;;
      sandbox)
        build_sandbox_target "$use_cache" &
        pids+=("$!")
        labels+=("sandbox")
        ;;
    esac
  done

  local failures=0
  local idx
  for idx in "${!pids[@]}"; do
    if wait "${pids[$idx]}"; then
      echo "✓ ${labels[$idx]} build succeeded"
    else
      echo "✗ ${labels[$idx]} build failed"
      failures=$((failures + 1))
    fi
  done

  if [[ "$failures" -gt 0 ]]; then
    echo ""
    echo "Parallel build finished with $failures failure(s)."
    return 1
  fi

  echo ""
  echo "Parallel build finished successfully."
}

cmd_patch_sandbox() {
  # Hot-patch source files into all running sandbox containers and restart
  # affected Python services so the new code is loaded into memory.
  #
  # Patches three source trees:
  #   ii_agent/integrations/a2a → copilot-adapter-system-never-kill (has auto-restart loop)
  #   ii_server                 → sandbox-server-system-never-kill
  #   ii_agent_tools            → imported by ii_server at runtime
  #
  # Use --no-restart to copy files without restarting services.
  local restart=true
  if [[ "${1:-}" == "--no-restart" ]]; then
    restart=false
    shift
  fi

  # ----- Check for uncommitted changes in patched source trees -----
  local dirty_files
  dirty_files=$(git -C "$ROOT_DIR" status --porcelain \
    src/ii_agent/integrations/a2a \
    src/ii_server \
    src/ii_agent_tools 2>/dev/null | head -30)

  local is_dirty=false
  if [[ -n "$dirty_files" ]]; then
    is_dirty=true
    echo "WARNING: Uncommitted changes detected in source trees to be patched:"
    echo "$dirty_files" | sed 's/^/  /'
    echo ""
    echo "The manifest will record host_commit as DIRTY-<hash> since the patched"
    echo "code does not correspond to any git commit."
    echo ""
    read -rp "Proceed with patching uncommitted code? [y/N] " confirm
    if [[ "${confirm,,}" != "y" && "${confirm,,}" != "yes" ]]; then
      echo "Aborted."
      return 1
    fi
    echo ""
  fi

  local containers
  containers=$(docker ps --filter "name=ii-sandbox" --format '{{.Names}}')
  if [[ -z "$containers" ]]; then
    echo "No running sandbox containers found."
    return
  fi

  local count patched=0 restarted=0
  count=$(echo "$containers" | wc -l)
  echo "Found $count running sandbox container(s). Patching..."

  # Source → destination mappings
  local src_a2a="$ROOT_DIR/src/ii_agent/integrations/a2a"
  local dst_a2a="/app/ii_sandbox/src/ii_agent/integrations/a2a"
  local src_server="$ROOT_DIR/src/ii_server"
  local dst_server="/app/ii_sandbox/src/ii_server"
  local src_tools="$ROOT_DIR/src/ii_agent_tools"
  local dst_tools="/app/ii_sandbox/src/ii_agent_tools"

  while IFS= read -r name; do
    local ok=true

    # Patch A2A adapter
    if ! docker cp "$src_a2a/." "$name:$dst_a2a/" 2>/dev/null; then
      echo "  FAILED copying a2a to $name"
      ok=false
    fi

    # Patch sandbox server (ii_server)
    if ! docker cp "$src_server/." "$name:$dst_server/" 2>/dev/null; then
      echo "  FAILED copying ii_server to $name"
      ok=false
    fi

    # Patch agent tools (ii_agent_tools)
    if ! docker cp "$src_tools/." "$name:$dst_tools/" 2>/dev/null; then
      echo "  FAILED copying ii_agent_tools to $name"
      ok=false
    fi

    if [[ "$ok" == true ]]; then
      echo "  Patched: $name"
      patched=$((patched + 1))

      # Write patch manifest log inside the container for debugging.
      # This file is ephemeral — destroyed on full container rebuild.
      local patch_ts
      patch_ts=$(date -u '+%Y-%m-%dT%H:%M:%S.%3NZ')
      local host_commit
      host_commit=$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
      if [[ "$is_dirty" == true ]]; then
        host_commit="DIRTY-${host_commit}"
      fi
      local mtimes
      mtimes=$(cd "$ROOT_DIR" && find src/ii_agent/integrations/a2a src/ii_server src/ii_agent_tools \
        -name '*.py' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -10 | \
        while read -r ts f; do
          echo "  - $(date -u -d "@$ts" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo "$ts") $f"
        done)
      local manifest_entry
      local dirty_section=""
      if [[ "$is_dirty" == true ]]; then
        dirty_section="uncommitted_changes:
$(echo "$dirty_files" | sed 's/^/  /')
"
      fi
      manifest_entry="--- patch ${patch_ts} ---
host_commit: ${host_commit}
restart: ${restart}
${dirty_section}sources_patched:
  - ${src_a2a} -> ${dst_a2a}
  - ${src_server} -> ${dst_server}
  - ${src_tools} -> ${dst_tools}
host_mtimes:
${mtimes}
"
      docker exec -i "$name" bash -c 'cat >> /app/ii_sandbox/patch-manifest.log' <<< "$manifest_entry"
    fi

    # Restart Python services so they pick up the new code
    if [[ "$restart" == true && "$ok" == true ]]; then
      # Each tmux session runs a command directly (not a shell), so when the
      # process dies the session closes. Safest approach: kill + recreate.
      docker exec "$name" bash -c '
        # --- Restart sandbox server (no auto-restart loop) ---
        tmux kill-session -t sandbox-server-system-never-kill 2>/dev/null || true
        sleep 1
        tmux new-session -d -s sandbox-server-system-never-kill -c /workspace \
          "WORKSPACE_DIR=/workspace DISPLAY=:99 python -m ii_server.mcp.server"

        # --- Restart A2A adapter (with auto-restart loop) ---
        tmux kill-session -t copilot-adapter-system-never-kill 2>/dev/null || true
        sleep 1
        ADAPTER_PORT="${SANDBOX_ADAPTER_PORT:-18100}"
        ADAPTER_BACKEND="${SANDBOX_ADAPTER_BACKEND:-simulate}"
        tmux new-session -d -s copilot-adapter-system-never-kill -c /workspace \
          "while true; do \
             DISPLAY=:99 AGENT_BROWSER_HEADED=1 \
             python -m ii_agent.integrations.a2a.adapter_server \
               --host 0.0.0.0 --port ${ADAPTER_PORT} \
               --backend ${ADAPTER_BACKEND}; \
             echo A2A adapter exited, restarting in 2s...; \
             sleep 2; \
           done"

        # code-server is Node.js — does not load our Python code, no restart needed
      ' &

      restarted=$((restarted + 1))
    fi
  done <<< "$containers"

  # Wait for background restart commands to finish
  wait

  echo ""
  echo "Done. Patched $patched/$count container(s)."
  if [[ "$restart" == true ]]; then
    echo "Restarted services in $restarted container(s)."
    echo "  - A2A adapter: killed (auto-restarts via while-true loop)"
    echo "  - Sandbox server: re-launched in tmux session"
    echo "  - ii_agent_tools: reloaded by sandbox server restart"
  else
    echo "Services NOT restarted (--no-restart). Processes still run old code."
    echo "Restart manually or re-run without --no-restart."
  fi
  echo ""
  echo "Patch manifest: /app/ii_sandbox/patch-manifest.log  (inside each sandbox container)"
  echo "  View with: docker exec <container> cat /app/ii_sandbox/patch-manifest.log"
  echo "  This file does not survive a full container rebuild."
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
  echo "Removing stale sandbox containers..."
  local containers
  containers=$(docker ps -a --filter "label=ii-agent.sandbox=true" -q)
  if [[ -z "$containers" ]]; then
    echo "No sandbox containers found."
    return
  fi
  local count
  count=$(echo "$containers" | wc -l)
  echo "Found $count sandbox container(s). Removing..."
  echo "$containers" | xargs docker rm -f
  echo "Done."
}

# ── Main ───────────────────────────────────────────────────────────────────

case "${1:-help}" in
  setup)          cmd_setup ;;
  build)          shift; cmd_build "$@" ;;
  build-sandbox)  shift; cmd_build_sandbox "$@" ;;
  patch-sandbox)  shift; cmd_patch_sandbox "$@" ;;
  start)          shift; cmd_start "$@" ;;
  stop)           shift; cmd_stop "$@" ;;
  restart)        shift; cmd_restart "$@" ;;
  rebuild)        shift; cmd_rebuild "$@" ;;
  status)         cmd_status ;;
  logs)           shift; cmd_logs "$@" ;;
  cleanup)        cmd_cleanup ;;
  help|--help|-h)
    print_help
    ;;
  *)
    echo "Unknown command: $1"
    echo ""
    print_help
    exit 1
    ;;
esac
