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

# Escape a string for embedding inside a JSON string literal.
# Handles backslash, double-quote, and control chars commonly seen in paths.
_json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

# Generate a JSON build manifest for baking into container images.
# Usage: _generate_build_manifest <target> [build_type]
#   target     - backend | frontend | sandbox
#   build_type - image (default) | patch
#
# Manifest schema (manifest_version = 2):
#   {
#     "manifest_version": 2,                            # bumped when verdict logic changes
#     "build_type":       "image" | "patch",
#     "target":           "backend" | "frontend" | "sandbox",
#     "timestamp":        ISO-8601 UTC,
#     "git_commit":       short HEAD sha,
#     "git_commit_full":  full HEAD sha,
#     "git_branch":       current branch,
#     "dirty":            bool — any tracked file differs from HEAD,
#
#     # Authoritative whitelist hash set used by `verify` for the verdict.
#     # Lists every file that ships in this image (per _path_in_target_image).
#     "tracked_files": [
#       {"path": "<repo-relative>", "size": <bytes>, "sha256": "<hex>"},
#       ...
#     ],
#     "tracked_files_truncated": bool,                  # hit TRACKED_FILE_CAP (5000)
#
#     # Forensic detail only; NOT consulted by the v2 verdict (it is a strict
#     # subset of tracked_files). Retained so users can still see which files
#     # were uncommitted at build time.
#     "dirty_files":           [{...}, ...],
#     "dirty_files_deleted":   ["<path>", ...],
#     "dirty_files_truncated": bool
#   }
#
# Verify verdict (v2):
#   UP TO DATE  iff git_commit_full == HEAD AND every tracked_files entry
#               still matches the working-tree sha256.
#   STALE       on any drift; legacy (v1, no manifest_version) is forced
#               STALE so a one-time rebuild enables full verification.
# Returns 0 if the given path is COPY'd into the named target's image,
# 1 otherwise. The verdict from this function is the single source of truth
# for "what belongs in this image" and is consumed both by dirty-file
# tracking and by the v2 tracked_files whitelist used by `verify`.
#
# IMPORTANT: keep in lockstep with two things:
#   1. The Dockerfile COPY rules:
#        backend       docker/backend/Dockerfile
#        frontend      docker/frontend/Dockerfile
#        sandbox       e2b.Dockerfile
#        a2a-adapter   reuses sandbox image
#   2. The repo-root .dockerignore (mirrored in the global exclusion block
#      below). When .dockerignore patterns change, update them here too.
_path_in_target_image() {
  local target="$1" path="$2"
  # Global exclusions mirroring .dockerignore. Keep in sync.
  case "$path" in
    *.json|*.xml|*.db|.env|.venv*|workspace/*|frontend/node_modules/*) return 1 ;;
  esac
  case "$target" in
    backend)
      case "$path" in
        src/*) return 0 ;;
        migrations/*) return 0 ;;
        pyproject.toml|uv.lock|README.md|alembic.ini) return 0 ;;
        scripts/start.sh) return 0 ;;
        docker/backend/*) return 0 ;;
      esac
      ;;
    frontend)
      case "$path" in
        frontend/*) return 0 ;;
        docker/frontend/*) return 0 ;;
      esac
      ;;
    sandbox|a2a-adapter)
      case "$path" in
        e2b.Dockerfile) return 0 ;;
        docker/sandbox/*) return 0 ;;
        src/ii_server/*) return 0 ;;
        src/ii_agent_tools/*) return 0 ;;
        src/ii_agent/__init__.py) return 0 ;;
        src/ii_agent/integrations/__init__.py) return 0 ;;
        src/ii_agent/integrations/a2a/*) return 0 ;;
        src/ii_agent/settings/skills/builtin/ii-app/*) return 0 ;;
      esac
      ;;
  esac
  return 1
}

_generate_build_manifest() {
  local target="${1:-unknown}"
  local build_type="${2:-image}"
  local ts commit full_commit branch
  local -r DIRTY_FILE_CAP=100
  local -r TRACKED_FILE_CAP=5000
  local -r TRACKED_FILE_WARN=2000

  ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  commit=$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
  full_commit=$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || echo "unknown")
  branch=$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

  local dirty="false"
  local dirty_files_json="[]"
  local dirty_deleted_json="[]"
  local truncated="false"

  if ! git -C "$ROOT_DIR" diff --quiet HEAD 2>/dev/null; then
    dirty="true"
    local -a all_files=()
    local f
    while IFS= read -r f; do
      [[ -z "$f" ]] && continue
      # Only track files that actually ship in this target's image.
      _path_in_target_image "$target" "$f" || continue
      all_files+=("$f")
    done < <(git -C "$ROOT_DIR" diff --name-only HEAD 2>/dev/null)

    local total=${#all_files[@]}
    if (( total > DIRTY_FILE_CAP )); then
      truncated="true"
      all_files=("${all_files[@]:0:$DIRTY_FILE_CAP}")
    fi

    local -a present_entries=()
    local -a deleted_entries=()
    local path size sha escaped_path
    for f in "${all_files[@]}"; do
      escaped_path=$(_json_escape "$f")
      path="$ROOT_DIR/$f"
      if [[ -f "$path" ]]; then
        size=$(stat -c '%s' "$path" 2>/dev/null || echo "0")
        sha=$(sha256sum "$path" 2>/dev/null | awk '{print $1}')
        [[ -z "$sha" ]] && sha="unknown"
        present_entries+=("{\"path\":\"$escaped_path\",\"size\":$size,\"sha256\":\"$sha\"}")
      else
        deleted_entries+=("\"$escaped_path\"")
      fi
    done

    if (( ${#present_entries[@]} > 0 )); then
      dirty_files_json="[$(IFS=,; echo "${present_entries[*]}")]"
    fi
    if (( ${#deleted_entries[@]} > 0 )); then
      dirty_deleted_json="[$(IFS=,; echo "${deleted_entries[*]}")]"
    fi
  fi

  # ── tracked_files: full whitelist hash set (v2 manifest) ────────────────
  # Walks every file git knows about (cached + untracked-but-not-ignored)
  # and includes the ones _path_in_target_image() says belong to this image.
  # Hash mismatch on any of these flips `verify` to STALE.
  local tracked_files_json="[]"
  local tracked_truncated="false"
  local -a tracked_entries=()
  local f path size sha escaped_path tracked_count=0
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    _path_in_target_image "$target" "$f" || continue
    path="$ROOT_DIR/$f"
    [[ -f "$path" ]] || continue
    if (( tracked_count >= TRACKED_FILE_CAP )); then
      tracked_truncated="true"
      break
    fi
    size=$(stat -c '%s' "$path" 2>/dev/null || echo "0")
    sha=$(sha256sum "$path" 2>/dev/null | awk '{print $1}')
    [[ -z "$sha" ]] && sha="unknown"
    escaped_path=$(_json_escape "$f")
    tracked_entries+=("{\"path\":\"$escaped_path\",\"size\":$size,\"sha256\":\"$sha\"}")
    tracked_count=$((tracked_count + 1))
  done < <(git -C "$ROOT_DIR" ls-files --cached --others --exclude-standard 2>/dev/null)

  if (( ${#tracked_entries[@]} > 0 )); then
    tracked_files_json="[$(IFS=,; echo "${tracked_entries[*]}")]"
  fi
  if (( tracked_count >= TRACKED_FILE_WARN )) && [[ "$tracked_truncated" == "true" ]]; then
    echo "[$target] WARNING: tracked_files truncated at $TRACKED_FILE_CAP entries" >&2
  elif (( tracked_count >= TRACKED_FILE_WARN )); then
    echo "[$target] NOTE: tracked_files has $tracked_count entries (warn at $TRACKED_FILE_WARN)" >&2
  fi

  printf '{"manifest_version":2,"build_type":"%s","target":"%s","timestamp":"%s","git_commit":"%s","git_commit_full":"%s","git_branch":"%s","dirty":%s,"tracked_files":%s,"tracked_files_truncated":%s,"dirty_files":%s,"dirty_files_deleted":%s,"dirty_files_truncated":%s}' \
    "$build_type" "$target" "$ts" "$commit" "$full_commit" "$branch" "$dirty" "$tracked_files_json" "$tracked_truncated" "$dirty_files_json" "$dirty_deleted_json" "$truncated"
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
  restart [service ...]        Restart services. With no args (or 'all'),
                               does a full 'compose down' + 'compose up -d'.
                               With one or more service names, force-recreates
                               ONLY those services (other running containers
                               are left alone). 'sandbox' is a pseudo-target
                               that recreates a2a-adapter (the only compose
                               service consuming the sandbox image).
                               Examples:
                                 restart                       (full cycle)
                                 restart backend               (just backend)
                                 restart a2a-adapter           (just adapter)
                                 restart backend a2a-adapter   (both, others kept)
  rebuild [target ...]         Rebuild (no cache) and restart. Accepts compose
                               services (backend, frontend, a2a-adapter, postgres,
                               redis, minio), the standalone 'sandbox' image, or
                               'all'. With no args (or 'all'): rebuilds every
                               compose service AND the sandbox image AND cycles
                               the whole stack. With named targets, builds only
                               those targets and force-recreates ONLY the matching
                               services (other running services are untouched).
                               Sandbox is rebuilt when no args are given,
                               'all' is passed, or 'sandbox' is explicitly listed.
  build [targets ...] [flags]  Build backend/frontend/sandbox targets in parallel
  build-sandbox [--quick]      Build the sandbox image only (alias for build sandbox)
  patch-sandbox [--no-restart] Hot-patch source into running sandbox containers
  status [--show-deleted]      Show running containers, URLs, and live sandboxes
                               (--show-deleted also lists sandboxes attached to
                                soft-deleted sessions awaiting reap)
  logs [service] [-f]          View logs for the full stack or a single service
  cleanup                      Remove stale sandbox containers
  verify [targets ...] [--all] Verify every file shipped in the image still
                               matches its working-tree SHA. Reports STALE on
                               any drift (closes the post-build clean-file
                               edit blind spot from v1 manifests).
  refresh-manifest [targets ...]
                               Re-bake build-manifest.json metadata into an
                               existing container/image WITHOUT re-validating
                               file content (tracked_files is preserved
                               verbatim). Use only when you committed a
                               change and want commit/timestamp metadata
                               refreshed; use 'rebuild' to re-validate.
  setup                        Create docker/.stack.env.local from template

--- TWO BUILD COMMANDS — IMPORTANT DISTINCTION ---

  rebuild [target ...]    Wraps docker compose build + recreate of the targeted
                          services + (when sandbox is in scope) e2b.Dockerfile
                          build + a2a-adapter recreate.

                          Recreate scope mirrors the build scope:
                            - no args / 'all' → full 'compose down' + 'compose up -d'
                              (whole stack cycles).
                            - named targets   → only those services (and a2a-adapter
                              when sandbox is rebuilt) are force-recreated; other
                              running containers (postgres, redis, minio, etc.)
                              keep going.

                          Sandbox rebuild is triggered when:
                            - no args  → rebuild everything (compose + sandbox)
                            - 'all'    → rebuild everything (compose + sandbox)
                            - 'sandbox' is explicitly listed (alone or with others)
                          Otherwise the sandbox image is left untouched.

                          When the sandbox image is rebuilt, a2a-adapter is
                          force-recreated so it picks up the new image (it
                          references ii-agent-sandbox:latest by image ref, so
                          a plain compose up does not pull in the change).

  build [targets ...]     Builds any combination of backend, frontend, and sandbox
                          in parallel, but does NOT restart running containers.
                          After a 'build', run 'restart' to pick up the new images.

  Quick rule:
    Changed src/ code?              → rebuild backend
    Changed frontend/?              → rebuild frontend
    Changed e2b.Dockerfile          → rebuild sandbox
    Changed both backend + sandbox? → rebuild backend sandbox
    Want a full clean rebuild?      → rebuild  (no args = everything)

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
  scripts/stack_control.sh rebuild backend
      Build and restart ONLY the backend (force-recreate, --no-deps).
      Postgres / redis / minio / frontend / a2a-adapter keep running.
      Sandbox image is left untouched.

  scripts/stack_control.sh rebuild sandbox
      Rebuild the sandbox image (e2b.Dockerfile) and force-recreate
      ONLY a2a-adapter so chat sessions pick up the new image. No
      other compose services are touched.

  scripts/stack_control.sh rebuild backend sandbox
      Backend + sandbox in one step. Force-recreates backend AND
      a2a-adapter; everything else keeps running.

  scripts/stack_control.sh rebuild
      Full rebuild: every compose service AND the sandbox image.
      Does a sweeping 'compose down' + 'compose up -d'. Equivalent
      to 'rebuild all'.

  scripts/stack_control.sh restart a2a-adapter
      Force-recreate just the adapter (picks up env_file changes).
      Other services keep running. This was the historical footgun:
      the legacy 'restart' did 'compose down' first and knocked out
      the whole stack — fixed in this version.

  scripts/stack_control.sh build sandbox --quick
      Fast sandbox iteration (uses layer cache). Run 'restart a2a-adapter'
      afterwards to apply, or prefer 'rebuild sandbox' for the one-step path.

  scripts/stack_control.sh build all --no-cache
      Clean rebuild of every image WITHOUT restarting. Run 'restart'
      afterwards. Prefer 'rebuild' for the one-step path.
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
  Or use 'rebuild' to build + restart in one step. Unlike previous versions,
  'rebuild' now supports the 'sandbox' target as well as compose services.

Examples:
  scripts/stack_control.sh build backend              # build, then restart manually
  scripts/stack_control.sh rebuild backend            # build + restart backend only
  scripts/stack_control.sh rebuild sandbox            # build sandbox + recreate a2a-adapter
  scripts/stack_control.sh rebuild backend sandbox    # both, in one step
  scripts/stack_control.sh rebuild                    # full rebuild (compose + sandbox)
  scripts/stack_control.sh build sandbox              # build sandbox image (no restart)
  scripts/stack_control.sh build backend sandbox --quick   # with layer cache
  scripts/stack_control.sh build all --no-cache       # full clean rebuild (no restart)

Agent-focused guidance:
  - Pick backend for agent runtime, billing, API, or orchestration changes.
  - Pick frontend for chat UX or client integration changes.
  - Pick sandbox for e2b.Dockerfile, start-services.sh, or adapter env changes.
  - Combine targets to rebuild exactly the surfaces touched by your change.
EOF
}

# Write the build manifest for $target to $ROOT_DIR/build-manifest-$target.json
# (the path the Dockerfiles COPY from). Echoes the absolute path.
# File-based delivery is required because tracked_files lists can exceed the
# Linux execve ARG_MAX (~2 MB shared by argv+env) when passed via --build-arg.
# Per-target filenames keep parallel builds in cmd_build race-free.
_write_build_manifest_file() {
  local target="$1"
  local build_type="${2:-image}"
  local manifest_path="$ROOT_DIR/build-manifest-${target}.json"
  _generate_build_manifest "$target" "$build_type" > "$manifest_path"
  printf '%s' "$manifest_path"
}

build_compose_target() {
  local target="$1"
  local use_cache="$2"
  local manifest_path manifest_file
  manifest_path=$(_write_build_manifest_file "$target")
  manifest_file="build-manifest-${target}.json"

  set -o pipefail
  echo "[$target] Starting compose build"
  if [[ "$use_cache" == true ]]; then
    compose build --build-arg "MANIFEST_FILE=$manifest_file" "$target" 2>&1 | sed -u "s/^/[$target] /"
  else
    compose build --no-cache --build-arg "MANIFEST_FILE=$manifest_file" "$target" 2>&1 | sed -u "s/^/[$target] /"
  fi
  rm -f "$manifest_path"
  echo "[$target] Build complete"
}

build_sandbox_target() {
  local use_cache="$1"
  local manifest_path manifest_file
  manifest_path=$(_write_build_manifest_file "sandbox")
  manifest_file="build-manifest-sandbox.json"

  set -o pipefail
  echo "[sandbox] Starting Docker build for $SANDBOX_IMAGE"
  if [[ "$use_cache" == true ]]; then
    docker build --build-arg "MANIFEST_FILE=$manifest_file" -t "$SANDBOX_IMAGE" -f "$ROOT_DIR/e2b.Dockerfile" "$ROOT_DIR" 2>&1 | sed -u 's/^/[sandbox] /'
  else
    docker build --no-cache --build-arg "MANIFEST_FILE=$manifest_file" -t "$SANDBOX_IMAGE" -f "$ROOT_DIR/e2b.Dockerfile" "$ROOT_DIR" 2>&1 | sed -u 's/^/[sandbox] /'
  fi
  rm -f "$manifest_path"
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

  # Scoping rule (see also cmd_rebuild):
  #   - No args, or 'all' → sweeping restart (compose down + compose up -d).
  #     Picks up env_file changes for every service and re-runs healthcheck
  #     dependency chain.
  #   - One or more service names → targeted restart of ONLY those services
  #     (compose up -d --force-recreate --no-deps <services>). Other running
  #     containers are left alone. We use --force-recreate (not `docker
  #     restart`) so env_file / compose-config changes are picked up. We use
  #     --no-deps so healthy upstream services (postgres, redis, minio) keep
  #     running.
  #   - 'sandbox' is a pseudo-target (standalone Docker image, not a compose
  #     service). The only compose service that consumes the sandbox image
  #     is a2a-adapter, so 'restart sandbox' force-recreates a2a-adapter.
  local sweeping=true
  local recreate_sandbox=false
  local -a recreate_services=()

  if (( $# > 0 )); then
    local arg
    for arg in "$@"; do
      case "$arg" in
        all)     sweeping=true ;;                       # explicit full restart
        sandbox) recreate_sandbox=true; sweeping=false ;;
        *)       recreate_services+=("$arg"); sweeping=false ;;
      esac
    done
  fi

  if $sweeping; then
    echo "Restarting ii-agent local stack (full)..."
    compose down
    compose up -d
  else
    local sandbox_note=""
    $recreate_sandbox && sandbox_note=" (sandbox pseudo-target → a2a-adapter)"
    echo "Restarting selected services: ${recreate_services[*]:-<none>}${sandbox_note}"
    if $recreate_sandbox; then
      # Avoid duplicate a2a-adapter in the args.
      local already_listed=false
      local s
      for s in "${recreate_services[@]}"; do
        [[ "$s" == "a2a-adapter" ]] && already_listed=true
      done
      $already_listed || recreate_services+=(a2a-adapter)
    fi
    if (( ${#recreate_services[@]} > 0 )); then
      compose up -d --force-recreate --no-deps "${recreate_services[@]}"
    fi
  fi

  echo ""
  cmd_status
}

cmd_rebuild() {
  ensure_env
  echo "Rebuilding (no cache) and restarting ii-agent local stack..."

  # Partition args into:
  #   - compose_args: real compose service names to pass to `compose build`
  #   - include_sandbox: whether to also build the standalone sandbox image
  #     (e2b.Dockerfile) and force-recreate a2a-adapter (which reuses it)
  #   - compose_scope: "all" (build every compose service) | "specific"
  #     (only the listed ones) | "none" (sandbox only — skip compose build)
  #
  # Sandbox is a standalone Docker image, NOT a compose service. It is
  # rebuilt automatically when:
  #   - no targets are given (full rebuild),
  #   - `all` is passed,
  #   - `sandbox` is explicitly listed.
  #
  # Recreate scoping (see also cmd_restart):
  #   - compose_scope=all → sweeping `down` + `up -d` (whole stack cycles).
  #   - compose_scope=specific or none → targeted recreate of ONLY the
  #     services that were rebuilt (and a2a-adapter when sandbox is in
  #     scope), via `up -d --force-recreate --no-deps <services>`. Other
  #     running services keep going. This is the fix for the historical
  #     footgun where `rebuild backend` knocked out postgres/redis/etc.
  local include_sandbox=false
  local compose_scope=""        # "all" | "specific" | "none"
  local -a compose_args=()

  if (( $# == 0 )); then
    include_sandbox=true
    compose_scope="all"
  else
    local arg
    for arg in "$@"; do
      case "$arg" in
        all)      include_sandbox=true; compose_scope="all" ;;     # build everything
        sandbox)  include_sandbox=true ;;                          # not a compose service
        *)        compose_args+=("$arg")
                  [[ -z "$compose_scope" ]] && compose_scope="specific" ;;
      esac
    done
    # If only `sandbox` was specified, there are no compose targets.
    [[ -z "$compose_scope" ]] && compose_scope="none"
  fi

  # Compose build needs a SEPARATE manifest per target — _path_in_target_image()
  # is keyed by target ("backend"/"frontend"), so a single shared manifest
  # tagged "all" would emit tracked_files=[] and break verify.
  #
  # Only `backend` and `frontend` are buildable compose services; everything
  # else uses prebuilt images and needs no build step.
  local -a buildable_compose=()
  case "$compose_scope" in
    all)       buildable_compose=(backend frontend) ;;
    specific)
      local arg
      for arg in "${compose_args[@]}"; do
        case "$arg" in backend|frontend) buildable_compose+=("$arg") ;; esac
      done
      ;;
    none)      ;;  # sandbox-only: skip compose build entirely
  esac

  # Only do the sweeping `compose down` for full rebuilds. Targeted rebuilds
  # leave other services running and rely on `up -d --force-recreate`
  # below to swap in the new image without disturbing the rest of the stack.
  if [[ "$compose_scope" == "all" ]]; then
    compose down
  fi

  local target manifest_path manifest_file
  for target in "${buildable_compose[@]}"; do
    echo ""
    echo "Building compose target: $target"
    manifest_path=$(_write_build_manifest_file "$target")
    manifest_file="build-manifest-${target}.json"
    compose build --no-cache --build-arg "MANIFEST_FILE=$manifest_file" "$target"
    rm -f "$manifest_path"
  done

  if $include_sandbox; then
    echo ""
    echo "Rebuilding sandbox image (e2b.Dockerfile) — used by sandbox runtime + a2a-adapter..."
    build_sandbox_target false
  fi

  if [[ "$compose_scope" == "all" ]]; then
    # Full rebuild path: bring everything up (preserves depends_on + healthcheck
    # ordering). a2a-adapter is part of "everything", but its image ref didn't
    # change unless sandbox was also rebuilt, so force-recreate it explicitly
    # when needed.
    compose up -d
    if $include_sandbox; then
      # a2a-adapter references ii-agent-sandbox:latest by image ref, so
      # `compose up -d` alone reuses the existing container. Force-recreate
      # so it picks up the freshly-built image.
      echo ""
      echo "Recreating a2a-adapter to pick up rebuilt sandbox image..."
      compose up -d --no-deps --force-recreate a2a-adapter
    fi
  else
    # Targeted rebuild path: recreate ONLY the services we rebuilt, plus
    # a2a-adapter when the sandbox image changed. Other running services
    # are untouched (postgres, redis, minio, frontend, etc.).
    local -a recreate_targets=("${buildable_compose[@]}")
    if $include_sandbox; then
      local already_listed=false
      local s
      for s in "${recreate_targets[@]}"; do
        [[ "$s" == "a2a-adapter" ]] && already_listed=true
      done
      $already_listed || recreate_targets+=(a2a-adapter)
    fi
    if (( ${#recreate_targets[@]} > 0 )); then
      echo ""
      echo "Recreating: ${recreate_targets[*]}"
      compose up -d --force-recreate --no-deps "${recreate_targets[@]}"
    fi
  fi

  echo ""
  cmd_status
}

print_status_help() {
  cat <<EOF
Usage:
  scripts/stack_control.sh status [--show-deleted] [--all] [--no-platform]
                                  [--json] [--strict]

Options:
  --show-deleted   Include sandboxes attached to soft-deleted sessions
                   (those waiting to be reaped). Hidden by default.
  --all            Alias for --show-deleted.
  --no-platform    Skip the Platform Health section (faster; useful when
                   /proc is unreadable or output is being parsed).
  --json           Emit a single JSON document instead of human output.
                   Intended for the external heartbeat (Phase 5) and CI
                   smoke tests. Implies --no-* (compose ps + sandbox list
                   are omitted; only the platform-health payload).
  --strict         Set the process exit code from the platform-health
                   roll-up: 0=OK/WATCH, 2=WARN, 3=CRIT. Composable with
                   either text or --json output.
  -h, --help       Show this help message.

The sandbox section lists each live sandbox with one of:
  - URL              Active session: http://HOST:FRONTEND_PORT/<session-id>
  - [standby slot=N] Pre-warmed pool sandbox not yet claimed
  - [retiring slot=N]Pool sandbox marked for shutdown
If a session has a pending delete_after timestamp, the remaining time is
shown as "(deletes in <duration>)" next to its URL.

The Platform Health section runs entirely from /proc + coreutils and does
not require the backend to be reachable. Per-host targets and rationale
live in docs/runtime-docs/wsl2-host-configuration.md.
EOF
}

# Format a number of seconds as a compact duration (e.g. "2h13m", "47s").
_fmt_duration() {
  local secs="${1:-0}"
  if [[ -z "$secs" || "$secs" == "NULL" ]]; then
    printf 'n/a'
    return
  fi
  if (( secs < 0 )); then
    secs=0
  fi
  if (( secs < 60 )); then
    printf '%ds' "$secs"
  elif (( secs < 3600 )); then
    printf '%dm%02ds' $(( secs / 60 )) $(( secs % 60 ))
  elif (( secs < 86400 )); then
    printf '%dh%02dm' $(( secs / 3600 )) $(( (secs % 3600) / 60 ))
  else
    printf '%dd%02dh' $(( secs / 86400 )) $(( (secs % 86400) / 3600 ))
  fi
}

# List live sandboxes joined with their (optional) session, classifying each
# row as standby / retiring / active / pending-delete / deleted-session.
# Reads POSTGRES_* and FRONTEND_PORT/SANDBOX_DOCKER_HOST from $ENV_FILE.
_list_sandboxes() {
  local show_deleted="${1:-false}"

  # Source env safely so we can resolve POSTGRES creds + URL host/port.
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a

  local pg_user="${POSTGRES_USER:-iiagent}"
  local pg_db="${POSTGRES_DB:-iiagentdev}"
  local pg_container="${PROJECT_NAME}-postgres-1"
  local frontend_port="${FRONTEND_PORT:-1420}"
  local host="${SANDBOX_DOCKER_HOST:-localhost}"

  if ! docker ps --format '{{.Names}}' | grep -qx "$pg_container"; then
    echo "  (postgres container '$pg_container' not running — skipping sandbox list)"
    return 0
  fi

  local sql
  sql=$(cat <<'SQL'
SELECT
  s.id::text,
  COALESCE(s.status::text, ''),
  COALESCE(s.pool_state::text, ''),
  COALESCE(s.pool_slot::text, ''),
  COALESCE(s.session_id::text, ''),
  COALESCE(sess.is_deleted::text, ''),
  COALESCE(EXTRACT(EPOCH FROM (sess.delete_after - now()))::bigint::text, ''),
  COALESCE(EXTRACT(EPOCH FROM (s.retire_at  - now()))::bigint::text, ''),
  COALESCE(EXTRACT(EPOCH FROM (s.timeout_at - now()))::bigint::text, '')
FROM agent_sandboxes s
LEFT JOIN sessions sess ON sess.id = s.session_id
WHERE s.status NOT IN ('deleted', 'error')
ORDER BY
  (s.pool_slot IS NULL),
  s.pool_slot NULLS LAST,
  s.created_at DESC;
SQL
)

  local rows
  rows=$(docker exec -i "$pg_container" \
    psql -U "$pg_user" -d "$pg_db" -A -F '|' -t -v ON_ERROR_STOP=1 -c "$sql" 2>/dev/null) || {
    echo "  (failed to query agent_sandboxes table)"
    return 0
  }

  if [[ -z "$rows" ]]; then
    echo "  (no live sandboxes)"
    return 0
  fi

  printf '  %-38s  %-9s  %s\n' "SANDBOX ID" "STATUS" "URL / STATE"
  printf '  %-38s  %-9s  %s\n' "--------------------------------------" "---------" "-----------"

  local sandbox_id status pool_state pool_slot session_id sess_deleted secs_delete secs_retire secs_timeout
  local label note shown=0 hidden=0
  while IFS='|' read -r sandbox_id status pool_state pool_slot session_id sess_deleted secs_delete secs_retire secs_timeout; do
    [[ -z "$sandbox_id" ]] && continue

    label=""
    note=""

    if [[ -n "$pool_state" ]]; then
      # Pool-managed row.
      case "$pool_state" in
        available)
          label="[standby slot=${pool_slot:-?}]"
          ;;
        retiring)
          label="[retiring slot=${pool_slot:-?}]"
          if [[ -n "$secs_retire" ]]; then
            note=" (retires in $(_fmt_duration "$secs_retire"))"
          fi
          ;;
        claimed)
          if [[ -n "$session_id" ]]; then
            label="http://${host}:${frontend_port}/${session_id}"
          else
            label="[claimed slot=${pool_slot:-?} unattached]"
          fi
          ;;
        *)
          label="[pool=${pool_state} slot=${pool_slot:-?}]"
          ;;
      esac
    elif [[ -n "$session_id" ]]; then
      label="http://${host}:${frontend_port}/${session_id}"
    else
      label="[orphan — no session, no pool]"
    fi

    # Annotate session-level deletion state.
    if [[ "$sess_deleted" == "t" || "$sess_deleted" == "true" ]]; then
      if [[ "$show_deleted" != true ]]; then
        hidden=$((hidden + 1))
        continue
      fi
      note="${note} [session DELETED — awaiting reap]"
    elif [[ -n "$secs_delete" ]]; then
      note="${note} (deletes in $(_fmt_duration "$secs_delete"))"
    fi

    if [[ -n "$secs_timeout" && "$secs_timeout" -lt 0 ]] 2>/dev/null; then
      note="${note} [timed out]"
    fi

    printf '  %-38s  %-9s  %s%s\n' "$sandbox_id" "$status" "$label" "$note"
    shown=$((shown + 1))
  done <<< "$rows"

  if (( hidden > 0 )); then
    echo ""
    echo "  ($hidden sandbox(es) hidden — attached to deleted sessions; pass --show-deleted to view)"
  fi
}

cmd_status() {
  ensure_env

  local show_deleted=false
  local show_platform=true
  local emit_json=false
  local strict=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --show-deleted|--all)
        show_deleted=true
        ;;
      --no-platform)
        show_platform=false
        ;;
      --json)
        emit_json=true
        ;;
      --strict)
        strict=true
        ;;
      -h|--help)
        print_status_help
        return 0
        ;;
      *)
        echo "Unknown status option: $1"
        echo ""
        print_status_help
        return 1
        ;;
    esac
    shift
  done

  # JSON mode short-circuits the human-friendly output. Compose state and
  # sandbox inventory are deliberately omitted: they're trivially queryable
  # via `docker compose ps --format json`, while the platform-health payload
  # is the new value-add this flag exposes.
  if [[ "$emit_json" == "true" ]]; then
    local _ph_lib="${ROOT_DIR}/scripts/local/lib/platform_checks.sh"
    if [[ ! -r "$_ph_lib" ]]; then
      printf '{"verdict":"OK","error":"platform_checks library missing"}\n'
      return 0
    fi
    # shellcheck disable=SC1090
    source "$_ph_lib"
    platform_checks_json
    echo
    if [[ "$strict" == "true" ]]; then
      _status_strict_exit
    fi
    return 0
  fi

  echo "=== ii-agent local stack status ==="
  compose ps
  echo ""

  # Source env to resolve network-facing host (best-effort).
  local lan_host=""
  (
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
    # Prefer an explicit LAN address; fall back to host extracted from
    # VITE_API_URL or STORAGE_SERVE_BASE_URL if it isn't localhost.
    if [[ -n "${SANDBOX_DOCKER_HOST:-}" && "${SANDBOX_DOCKER_HOST}" != "localhost" && "${SANDBOX_DOCKER_HOST}" != "127.0.0.1" ]]; then
      echo "$SANDBOX_DOCKER_HOST"
      exit 0
    fi
    for url in "${VITE_API_URL:-}" "${STORAGE_SERVE_BASE_URL:-}"; do
      [[ -z "$url" ]] && continue
      h="${url#*://}"
      h="${h%%:*}"
      h="${h%%/*}"
      if [[ -n "$h" && "$h" != "localhost" && "$h" != "127.0.0.1" ]]; then
        echo "$h"
        exit 0
      fi
    done
  ) > /tmp/.stack_lan_host.$$
  lan_host=$(cat /tmp/.stack_lan_host.$$ 2>/dev/null || true)
  rm -f /tmp/.stack_lan_host.$$

  echo "Service URLs (local):"
  echo "  Frontend:  http://localhost:${FRONTEND_PORT:-1420}"
  echo "  Backend:   http://localhost:${BACKEND_PORT:-8000}"
  echo "  Minio UI:  http://localhost:${MINIO_CONSOLE_PORT:-9001}"
  if [[ -n "$lan_host" ]]; then
    echo ""
    echo "Service URLs (network — $lan_host):"
    echo "  Frontend:  http://${lan_host}:${FRONTEND_PORT:-1420}"
    echo "  Backend:   http://${lan_host}:${BACKEND_PORT:-8000}"
    echo "  Minio UI:  http://${lan_host}:${MINIO_CONSOLE_PORT:-9001}"
  fi
  echo ""
  echo "=== Sandboxes ==="
  _list_sandboxes "$show_deleted"

  if [[ "$show_platform" == "true" ]]; then
    echo ""
    # Source on demand so users without /proc (or with --no-platform) pay
    # nothing for it. Library is best-effort; absence is silently ignored.
    local _ph_lib="${ROOT_DIR}/scripts/local/lib/platform_checks.sh"
    if [[ -r "$_ph_lib" ]]; then
      # shellcheck disable=SC1090
      source "$_ph_lib"
      platform_checks_run
      if [[ "$strict" == "true" ]]; then
        _status_strict_exit
      fi
    fi
  fi
}

# --- helper ----------------------------------------------------------------
# Translate the platform-health roll-up verdict into a process exit code
# suitable for CI / heartbeat consumers:
#   OK / WATCH / BOOTSTRAP -> 0   (default — humans always see 0)
#   WARN                   -> 2
#   CRIT                   -> 3
# Caller must have already sourced platform_checks.sh and run either
# platform_checks_run or platform_checks_json.
_status_strict_exit() {
  if ! declare -F platform_checks_verdict >/dev/null; then
    return 0
  fi
  local v
  v=$(platform_checks_verdict)
  case "$v" in
    CRIT) exit 3 ;;
    WARN) exit 2 ;;
    *)    exit 0 ;;
  esac
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

# ── verify ────────────────────────────────────────────────────────────────
#
# Compare the build manifest embedded in a container / image against the
# current working tree.
#
# For each file the manifest recorded as "dirty at build time", we recompute
# sha256 of the on-disk file and report OK / CHANGED / MISSING. We also
# report whether the build commit matches the working-tree HEAD.
#
# This gives a precise "is this image stale?" signal — no guessing from
# names alone.

# Emit the raw manifest JSON for a given target to stdout.
# target: backend | frontend | sandbox | a2a-adapter
_read_manifest() {
  local target="$1"
  case "$target" in
    backend|frontend|a2a-adapter)
      local container="ii-agent-local-${target}-1"
      docker exec "$container" cat "$BUILD_MANIFEST_PATH" 2>/dev/null
      ;;
    sandbox)
      local image="${SANDBOX_DOCKER_IMAGE:-ii-agent-sandbox:latest}"
      docker run --rm --entrypoint cat "$image" "$BUILD_MANIFEST_PATH" 2>/dev/null
      ;;
    *)
      echo "ERROR: unknown verify target: $target" >&2
      echo "Valid targets: backend frontend sandbox a2a-adapter" >&2
      return 2
      ;;
  esac
}

cmd_verify() {
  local targets=()
  local show_all=false
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -a|--all)     show_all=true; shift ;;
      -h|--help)
        cat <<EOF
Usage: scripts/stack_control.sh verify [--all] [target ...]

Compare a container/image's baked build-manifest.json against the current
working tree. Reports per-file sha256 drift and whether the image's commit
matches HEAD.

Targets (default: all four below):
  backend       ii-agent-local-backend-1 container
  frontend      ii-agent-local-frontend-1 container
  sandbox       ii-agent-sandbox:latest image
  a2a-adapter   ii-agent-local-a2a-adapter-1 container
  all           all four of the above (explicit alias)

Options:
  --all, -a     List every file (default: only drifted/missing files)
  -h, --help    Show this help
EOF
        return 0
        ;;
      all)           targets=(backend frontend sandbox a2a-adapter); shift ;;
      backend|frontend|sandbox|a2a-adapter)
                     targets+=("$1"); shift ;;
      *)             echo "Unknown target: $1" >&2; return 2 ;;
    esac
  done

  if (( ${#targets[@]} == 0 )); then
    targets=(backend frontend sandbox a2a-adapter)
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 required for verify" >&2
    return 1
  fi

  local head_commit
  head_commit=$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || echo "unknown")

  local worktree_dirty="clean"
  if ! git -C "$ROOT_DIR" diff --quiet HEAD 2>/dev/null; then
    worktree_dirty="dirty"
  fi

  local overall_rc=0
  local first=true
  for target in "${targets[@]}"; do
    [[ "$first" == true ]] && first=false || echo ""
    echo "=== verify: $target ==="

    local manifest
    if ! manifest=$(_read_manifest "$target"); then
      echo "  FAIL: could not read manifest"
      overall_rc=1
      continue
    fi
    if [[ -z "$manifest" ]]; then
      echo "  FAIL: manifest empty or missing ($BUILD_MANIFEST_PATH)"
      overall_rc=1
      continue
    fi

    # Run the per-file comparison in python for clean JSON + sha handling.
    # `|| rc=$?` lets `set -e` coexist with non-zero exit (STALE) from python.
    # Manifest is staged in a temp file (not env) because tracked_files lists
    # can exceed Linux execve ARG_MAX (env+argv combined cap, ~2 MB).
    local rc=0 manifest_tmp
    manifest_tmp=$(mktemp -t verify-manifest.XXXXXX.json)
    printf '%s' "$manifest" > "$manifest_tmp"
    SM_MANIFEST_FILE="$manifest_tmp" \
    SM_ROOT="$ROOT_DIR" \
    SM_HEAD="$head_commit" \
    SM_WORKTREE="$worktree_dirty" \
    SM_SHOWALL="$show_all" \
    python3 - <<'PY' || rc=$?
import hashlib
import json
import os
import sys

with open(os.environ["SM_MANIFEST_FILE"], "r") as _mf:
    manifest_raw = _mf.read()
root = os.environ["SM_ROOT"]
head = os.environ["SM_HEAD"]
worktree = os.environ["SM_WORKTREE"]
show_all = os.environ["SM_SHOWALL"] == "true"

try:
    m = json.loads(manifest_raw)
except json.JSONDecodeError as e:
    print(f"  FAIL: manifest is not valid JSON ({e})")
    sys.exit(1)

manifest_version = m.get("manifest_version", 1)
built_commit = m.get("git_commit_full", "unknown")
built_branch = m.get("git_branch", "unknown")
built_ts = m.get("timestamp", "unknown")
built_type = m.get("build_type", "unknown")
built_dirty = m.get("dirty", False)
dirty_files = m.get("dirty_files", []) or []
deleted = m.get("dirty_files_deleted", []) or []
dirty_truncated = m.get("dirty_files_truncated", False)
tracked_files = m.get("tracked_files", []) or []
tracked_truncated = m.get("tracked_files_truncated", False)

print(f"  manifest:   v{manifest_version}")
print(f"  built_at:   {built_ts}  ({built_type})")
print(f"  built_cmt:  {built_commit[:12]}  branch={built_branch}  worktree_at_build={'dirty' if built_dirty else 'clean'}")
print(f"  head_cmt:   {head[:12]}  worktree_now={worktree}")

commit_match = (built_commit == head)
print(f"  commit:     {'MATCH' if commit_match else 'DIFFERS'}")


def _normalize(entry):
    # Legacy manifests stored dirty_files as ["path", ...] strings.
    if isinstance(entry, str):
        return {"path": entry, "size": None, "sha256": None}
    return entry


def _check(entries, label):
    """Hash each entry against the working tree. Returns (ok, changed, missing,
    no_hash, lines). Lines are appended only for non-OK entries unless
    --all is set.
    """
    ok = changed = missing = no_hash = 0
    lines = []
    for e in (_normalize(x) for x in entries):
        path = e.get("path", "")
        want_sha = e.get("sha256")
        want_size = e.get("size")
        abs_path = os.path.join(root, path)

        if not os.path.isfile(abs_path):
            missing += 1
            lines.append(f"    MISSING  [{label}] {path}")
            continue

        if not want_sha or want_sha == "unknown":
            no_hash += 1
            if show_all:
                lines.append(f"    NO-HASH  [{label}] {path}  (legacy entry — name only)")
            continue

        h = hashlib.sha256()
        try:
            with open(abs_path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        except OSError as exc:
            missing += 1
            lines.append(f"    MISSING  [{label}] {path}  ({exc})")
            continue

        got_sha = h.hexdigest()
        got_size = os.path.getsize(abs_path)
        if got_sha == want_sha:
            ok += 1
            if show_all:
                lines.append(f"    OK       [{label}] {path}  ({got_size}B)")
        else:
            changed += 1
            size_note = ""
            if want_size is not None and want_size != got_size:
                size_note = f"  size {want_size}→{got_size}"
            lines.append(f"    CHANGED  [{label}] {path}{size_note}")
    return ok, changed, missing, no_hash, lines


# Legacy manifest (no manifest_version) — force STALE so a one-time rebuild
# enables full verification under the v2 verdict.
if manifest_version < 2:
    print("  files:      legacy manifest (no tracked_files); cannot verify image content")
    print("  verdict:    STALE — legacy manifest, rebuild to enable full verification")
    sys.exit(1)

# v2 verdict: tracked_files is authoritative. dirty_files shown for context only.
t_ok, t_changed, t_missing, t_no_hash, t_lines = _check(tracked_files, "tracked")
d_ok, d_changed, d_missing, d_no_hash, d_lines = _check(dirty_files, "dirty@build")

print(
    f"  tracked:    {len(tracked_files)} file(s) in image  "
    f"(ok={t_ok} changed={t_changed} missing={t_missing})"
)
if dirty_files or deleted:
    print(
        f"  dirty@build:{len(dirty_files)} file(s) were uncommitted at build time  "
        f"(ok={d_ok} changed={d_changed} missing={d_missing})  -- informational only"
    )
if deleted:
    print(f"  deleted_in_diff: {len(deleted)} file(s) were in-diff but absent on disk at build time")
if tracked_truncated:
    print("  WARNING: tracked_files truncated (>5000 entries); verification is partial.")
if dirty_truncated:
    print("  NOTE: dirty_files truncated (>100 entries).")

# Show drift details (tracked first, then dirty for context).
detail_lines = t_lines + d_lines
if detail_lines:
    print("  details:")
    for line in detail_lines:
        print(line)

# Exit code semantics (v2):
#   0 = commit matches HEAD AND every tracked_files entry matches working tree
#   1 = any drift detected (rebuild recommended)
if commit_match and t_changed == 0 and t_missing == 0:
    print("  verdict:    UP TO DATE")
    sys.exit(0)

reasons = []
if not commit_match:
    reasons.append(f"commit drift ({built_commit[:7]} → {head[:7]})")
if t_changed:
    reasons.append(f"{t_changed} tracked file(s) changed")
if t_missing:
    reasons.append(f"{t_missing} tracked file(s) missing on disk")
print("  verdict:    STALE — " + "; ".join(reasons))
sys.exit(1)
PY
    rm -f "$manifest_tmp"
    if (( rc != 0 )); then
      overall_rc=1
    fi
  done

  return "$overall_rc"
}

# ── refresh-manifest ───────────────────────────────────────────────────────
#
# Re-bake build-manifest.json into existing images / containers without
# rebuilding any source layers. Use this when only the manifest metadata
# is stale (e.g. you committed your changes and just want `verify` to show
# the new commit sha) but the baked code itself is still current.
#
# IMPORTANT — does NOT re-validate file content:
#   The new manifest's `tracked_files` array is preserved verbatim from the
#   prior baked manifest. Only metadata (manifest_version, build_type,
#   target, timestamp, git_commit*, git_branch, dirty, dirty_files,
#   dirty_files_deleted, dirty_files_truncated) is refreshed. To re-validate
#   that the in-image bytes match the working tree, run `rebuild`.
#
# - For container targets (backend, frontend, a2a-adapter): writes the new
#   manifest with `docker cp` directly into the running container. No
#   restart required.
# - For image targets (sandbox): builds a tiny derivative image
#   (`FROM <existing> + COPY manifest`) and retags it back to the original
#   tag. Already-running containers using the old image keep running until
#   restarted; the new manifest takes effect for any container started from
#   the tag thereafter.
cmd_refresh_manifest() {
  local targets=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        cat <<EOF
Usage: scripts/stack_control.sh refresh-manifest [target ...]

Re-bake build-manifest.json metadata into existing containers/images.

WARNING: this does NOT re-validate file content. The 'tracked_files' array
is preserved verbatim from the prior manifest; only commit/timestamp/dirty
metadata is refreshed. To re-validate file content, run 'rebuild'.

Targets (default: sandbox a2a-adapter):
  backend       ii-agent-local-backend-1 (docker cp)
  frontend      ii-agent-local-frontend-1 (docker cp)
  a2a-adapter   ii-agent-local-a2a-adapter-1 (docker cp)
  sandbox       \${SANDBOX_DOCKER_IMAGE:-ii-agent-sandbox:latest}
                (rebuild a 1-line derivative image, retag)
  all           all four
EOF
        return 0
        ;;
      all)        targets=(backend frontend sandbox a2a-adapter); shift ;;
      backend|frontend|sandbox|a2a-adapter)
                  targets+=("$1"); shift ;;
      *)          echo "Unknown target: $1" >&2; return 2 ;;
    esac
  done

  if (( ${#targets[@]} == 0 )); then
    targets=(sandbox a2a-adapter)
  fi

  local overall_rc=0
  for target in "${targets[@]}"; do
    echo "=== refresh-manifest: $target ==="
    local manifest tmpfile prior_manifest
    manifest=$(_generate_build_manifest "$target")

    # Preserve `tracked_files` from the prior baked manifest so we don't
    # accidentally overwrite a known-good content snapshot with whatever
    # the host happens to contain right now (which may differ from the
    # bytes actually shipped in the image).
    prior_manifest=$(_read_manifest "$target" 2>/dev/null || echo '')
    if [[ -n "$prior_manifest" ]]; then
      manifest=$(MANIFEST="$manifest" PRIOR="$prior_manifest" python3 - <<'PY'
import json, os
new = json.loads(os.environ["MANIFEST"])
try:
    prior = json.loads(os.environ["PRIOR"])
except json.JSONDecodeError:
    prior = {}
prior_tracked = prior.get("tracked_files")
prior_truncated = prior.get("tracked_files_truncated")
if prior_tracked is not None:
    new["tracked_files"] = prior_tracked
if prior_truncated is not None:
    new["tracked_files_truncated"] = prior_truncated
print(json.dumps(new))
PY
)
      echo "  preserved tracked_files from prior manifest (no content re-validation)"
    else
      echo "  NOTE: no prior manifest readable — new tracked_files reflects host working tree"
    fi

    tmpfile=$(mktemp -t build-manifest.XXXXXX.json)
    printf '%s' "$manifest" > "$tmpfile"

    case "$target" in
      backend|frontend|a2a-adapter)
        local container="ii-agent-local-${target}-1"
        if ! docker ps --format '{{.Names}}' | grep -qx "$container"; then
          echo "  SKIP: container $container not running"
          rm -f "$tmpfile"
          overall_rc=1
          continue
        fi
        # Try docker cp first (works for writable-rootfs containers).
        # If the container has a read-only rootfs (e.g. a2a-adapter), fall
        # back to recreating it from its image — for a2a-adapter that's the
        # sandbox image, which the caller should have refreshed already in
        # this same invocation.
        local cp_err
        cp_err=$(docker cp "$tmpfile" "${container}:${BUILD_MANIFEST_PATH}" 2>&1) || true
        if [[ -z "$cp_err" ]]; then
          echo "  OK: wrote ${BUILD_MANIFEST_PATH} into $container (docker cp)"
        elif echo "$cp_err" | grep -q "read-only"; then
          echo "  NOTE: $container has read-only rootfs; recreating from image"
          if compose up -d --no-deps --force-recreate "$target" 2>&1 | sed -u "s/^/  /"; then
            echo "  OK: recreated $container from image (manifest taken from image)"
          else
            echo "  FAIL: compose force-recreate $target failed"
            overall_rc=1
          fi
        else
          echo "  FAIL: docker cp into $container failed: $cp_err"
          overall_rc=1
        fi
        ;;
      sandbox)
        local image="${SANDBOX_DOCKER_IMAGE:-ii-agent-sandbox:latest}"
        if ! docker image inspect "$image" >/dev/null 2>&1; then
          echo "  SKIP: image $image not found"
          rm -f "$tmpfile"
          overall_rc=1
          continue
        fi
        # Build a derivative image from a scratch context that contains
        # only the new manifest. `--build-context` is overkill — just feed
        # the Dockerfile via stdin and pipe the manifest in via stdin too.
        # Simpler: build from a temp dir.
        local builddir
        builddir=$(mktemp -d -t sandbox-manifest.XXXXXX)
        cp "$tmpfile" "${builddir}/build-manifest.json"
        cat > "${builddir}/Dockerfile" <<EOF
FROM ${image}
COPY build-manifest.json ${BUILD_MANIFEST_PATH}
EOF
        if docker build -q -t "$image" "$builddir" 2>&1 | sed -u "s/^/  /"; then
          echo "  OK: rebuilt $image with refreshed ${BUILD_MANIFEST_PATH}"
        else
          echo "  FAIL: docker build of derivative image failed"
          overall_rc=1
        fi
        rm -rf "$builddir"
        ;;
    esac

    rm -f "$tmpfile"
  done

  return "$overall_rc"
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
  status)         shift; cmd_status "$@" ;;
  logs)           shift; cmd_logs "$@" ;;
  cleanup)        cmd_cleanup ;;
  verify)         shift; cmd_verify "$@" ;;
  refresh-manifest) shift; cmd_refresh_manifest "$@" ;;
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
