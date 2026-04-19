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

# Path where build manifest is stored inside every container image.
BUILD_MANIFEST_PATH="/app/build-manifest.json"

# ── Helpers ────────────────────────────────────────────────────────────────

compose() {
  docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

# Generate a JSON build manifest for baking into container images.
# Usage: _generate_build_manifest <target> [build_type]
#   target     - backend | frontend | sandbox
#   build_type - image (default) | patch
_generate_build_manifest() {
  local target="${1:-unknown}"
  local build_type="${2:-image}"
  local ts commit full_commit branch dirty dirty_files_json

  ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  commit=$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
  full_commit=$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || echo "unknown")
  branch=$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

  dirty="false"
  dirty_files_json="[]"
  if ! git -C "$ROOT_DIR" diff --quiet HEAD 2>/dev/null; then
    dirty="true"
    local files
    files=$(git -C "$ROOT_DIR" diff --name-only HEAD 2>/dev/null | head -30)
    if [[ -n "$files" ]]; then
      dirty_files_json="["
      local first=true
      while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        [[ "$first" == true ]] && first=false || dirty_files_json+=","
        dirty_files_json+="\"$f\""
      done <<< "$files"
      dirty_files_json+="]"
    fi
  fi

  printf '{"build_type":"%s","target":"%s","timestamp":"%s","git_commit":"%s","git_commit_full":"%s","git_branch":"%s","dirty":%s,"dirty_files":%s}' \
    "$build_type" "$target" "$ts" "$commit" "$full_commit" "$branch" "$dirty" "$dirty_files_json"
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
  rebuild [service ...]        Rebuild compose services (no cache) and restart
  build [targets ...] [flags]  Build backend/frontend/sandbox targets in parallel
  build-sandbox [--quick]      Build the sandbox image only (alias for build sandbox)
  patch-sandbox [--no-restart] Hot-patch source into running sandbox containers
  status                       Show running containers and URLs
  logs [service] [-f]          View logs for the full stack or a single service
  cleanup                      Remove stale sandbox containers
  setup                        Create docker/.stack.env.local from template

--- TWO BUILD COMMANDS — IMPORTANT DISTINCTION ---

  rebuild [service ...]   Wraps docker compose build + compose up. Only accepts
                          COMPOSE service names: backend, frontend, a2a-adapter,
                          postgres, redis, minio. Does NOT accept 'sandbox' —
                          the sandbox is a standalone Docker image (e2b.Dockerfile),
                          not a compose service.

  build [targets ...]     Builds any combination of backend, frontend, and sandbox
                          in parallel, but does NOT restart running containers.
                          After a 'build', run 'restart' to pick up the new images.
                          Sandbox is ONLY buildable via this command (or build-sandbox).

  Quick rule:
    Changed src/ code?      → build backend  (then restart)
    Changed frontend/?      → build frontend  (then restart)
    Changed e2b.Dockerfile  → build sandbox  (then restart)
    Changed both backend +  → build backend sandbox  (then restart)
      sandbox?
    Need immediate restart? → rebuild backend  (build + restart in one step,
                               compose services only, sandbox NOT supported)

Build targets (for 'build' command only):
  backend    FastAPI app, agent runtime, billing, APIs  [compose service]
  frontend   Chat UI and web client                     [compose service]
  sandbox    Tool execution / A2A adapter image         [standalone Docker image]
  all        Alias for backend frontend sandbox

Build flags:
  --no-cache   Full rebuild without layer cache
  --quick      Prefer cache (useful for rapid sandbox iteration)
  -h, --help   Show command help

Service start-up dependency order (enforced by Docker Compose healthchecks):
  postgres, redis, minio  →  a2a-adapter  →  backend  →  frontend
  The backend will stay in 'Created' state if a2a-adapter is unhealthy.

Agent-focused use cases:
  scripts/stack_control.sh build backend
      Rebuild the backend image after changing agent logic, routing, or APIs.
      Run 'restart' afterwards, or use 'rebuild backend' to do both in one step.

  scripts/stack_control.sh rebuild backend
      Build and immediately restart the backend (compose down + build + up).
      Use this for a clean in-place restart with the new image.

  scripts/stack_control.sh build sandbox --quick
      Fast sandbox iteration (uses layer cache). Then run 'restart' to apply.

  scripts/stack_control.sh build backend sandbox --no-cache
      Rebuild both backend and sandbox images from scratch in parallel.
      Run 'restart' afterwards to apply both.

  scripts/stack_control.sh build all --no-cache
      Clean rebuild of the full local agent stack.
EOF
}

print_build_help() {
  cat <<EOF
Usage:
  scripts/stack_control.sh build [targets ...] [--no-cache] [--quick]

Targets:
  backend    Compose service — FastAPI app, agent runtime, billing, APIs
  frontend   Compose service — Chat UI and web client
  sandbox    Standalone Docker image (e2b.Dockerfile) — NOT a compose service
  all        Alias for backend frontend sandbox

NOTE: 'build' only builds images. Running containers are NOT restarted.
  Run 'scripts/stack_control.sh restart' after building to apply changes.
  Or use 'rebuild' (backend/frontend only) to build + restart in one step.

NOTE: 'sandbox' is NOT accepted by 'rebuild'. It must be built via 'build sandbox'
  or 'build-sandbox', then restarted with 'restart' or 'restart a2a-adapter'.

Examples:
  scripts/stack_control.sh build backend              # build, then restart manually
  scripts/stack_control.sh rebuild backend            # build + restart in one step
  scripts/stack_control.sh build sandbox              # build sandbox image
  scripts/stack_control.sh build backend sandbox      # build both in parallel
  scripts/stack_control.sh build backend sandbox --quick   # with layer cache
  scripts/stack_control.sh build all --no-cache       # full clean rebuild

Agent-focused guidance:
  - Pick backend for agent runtime, billing, API, or orchestration changes.
  - Pick frontend for chat UX or client integration changes.
  - Pick sandbox for e2b.Dockerfile, start-services.sh, or adapter env changes.
  - Combine targets to rebuild exactly the surfaces touched by your change.
EOF
}

build_compose_target() {
  local target="$1"
  local use_cache="$2"
  local manifest
  manifest=$(_generate_build_manifest "$target")

  set -o pipefail
  echo "[$target] Starting compose build"
  if [[ "$use_cache" == true ]]; then
    compose build --build-arg "BUILD_MANIFEST=$manifest" "$target" 2>&1 | sed -u "s/^/[$target] /"
  else
    compose build --no-cache --build-arg "BUILD_MANIFEST=$manifest" "$target" 2>&1 | sed -u "s/^/[$target] /"
  fi
  echo "[$target] Build complete"
}

build_sandbox_target() {
  local use_cache="$1"
  local manifest
  manifest=$(_generate_build_manifest "sandbox")

  set -o pipefail
  echo "[sandbox] Starting Docker build for $SANDBOX_IMAGE"
  if [[ "$use_cache" == true ]]; then
    docker build --build-arg "BUILD_MANIFEST=$manifest" -t "$SANDBOX_IMAGE" -f "$ROOT_DIR/e2b.Dockerfile" "$ROOT_DIR" 2>&1 | sed -u 's/^/[sandbox] /'
  else
    docker build --no-cache --build-arg "BUILD_MANIFEST=$manifest" -t "$SANDBOX_IMAGE" -f "$ROOT_DIR/e2b.Dockerfile" "$ROOT_DIR" 2>&1 | sed -u 's/^/[sandbox] /'
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

      # Overwrite the build manifest so `cat /app/build-manifest.json` always
      # reflects the current state of the code inside this container.
      local build_manifest
      build_manifest=$(_generate_build_manifest "sandbox" "patch")
      echo "$build_manifest" | docker exec -i "$name" bash -c 'cat > /app/build-manifest.json'
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
  echo "Build manifest: /app/build-manifest.json  (overwritten by patch — reflects current state)"
  echo "  View with: docker exec <container> cat /app/build-manifest.json"
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
  # Generate a manifest for whichever services are being rebuilt.
  # If specific services are listed, tag the first; otherwise tag "all".
  local rebuild_target="${1:-all}"
  local manifest
  manifest=$(_generate_build_manifest "$rebuild_target")

  compose down
  compose build --no-cache --build-arg "BUILD_MANIFEST=$manifest" "$@"
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

print_cleanup_help() {
  cat <<EOF
Usage:
  scripts/stack_control.sh cleanup [--force] [--dry-run]

Options:
  --force   Remove all sandbox containers, including those with session metadata
  --dry-run Show which containers would be removed without deleting anything
  -h, --help Show this help message
EOF
}

cmd_cleanup() {
  local force=false
  local dry_run=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --force)
        force=true
        ;;
      --dry-run)
        dry_run=true
        ;;
      -h|--help)
        print_cleanup_help
        return 0
        ;;
      *)
        echo "Unknown cleanup option: $1"
        print_cleanup_help
        return 1
        ;;
    esac
    shift
  done

  echo "Removing stale sandbox containers..."
  local containers
  containers=$(docker ps -a --filter "label=ii-agent.sandbox=true" --format '{{.ID}}')
  if [[ -z "$containers" ]]; then
    echo "No sandbox containers found."
    return
  fi

  local orphaned=()
  local preserved=()
  local container_id

  while IFS= read -r container_id; do
    if [[ -z "$container_id" ]]; then
      continue
    fi
    local session_id
    session_id=$(docker inspect --format '{{ index .Config.Labels "ii-agent.session-id" }}' "$container_id" 2>/dev/null || true)
    if [[ -z "$session_id" || "$session_id" == "<no value>" ]]; then
      orphaned+=("$container_id")
    else
      preserved+=("$container_id")
    fi
  done <<< "$containers"

  local to_remove=()
  if [[ "$force" == true ]]; then
    echo "Force deletion enabled; removing all sandbox containers regardless of session metadata."
    while IFS= read -r container_id; do
      if [[ -n "$container_id" ]]; then
        to_remove+=("$container_id")
      fi
    done <<< "$containers"
  else
    to_remove=("${orphaned[@]}")
  fi

  if [[ ${#to_remove[@]} -eq 0 ]]; then
    echo "No orphaned sandbox containers found."
    echo "Preserving ${#preserved[@]} sandbox container(s) tied to sessions."
    return
  fi

  echo "Found ${#to_remove[@]} sandbox container(s) to remove."
  if [[ "$dry_run" == true ]]; then
    printf '%s\n' "${to_remove[@]}"
    return
  fi

  printf '%s\n' "${to_remove[@]}" | xargs docker rm -f
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
