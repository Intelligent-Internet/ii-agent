#!/usr/bin/env bash
#
# stack_control.sh - Unified control script for ii-agent Docker stack
#
# ============================================================================
# OVERVIEW
# ============================================================================
# This script provides a single interface to manage all ii-agent services.
# It supports two modes:
#   - Cloud mode (default): Uses E2B sandboxes + ngrok for public access
#   - Local mode (--local): Uses Docker sandboxes, no external dependencies
#
# ============================================================================
# COMMAND REFERENCE (for AI agents and humans)
# ============================================================================
#
# LIFECYCLE COMMANDS:
#   start [service]     Start services. No service = start all.
#   stop [service]      Stop services. No service = stop all.
#   restart [service]   Restart without rebuilding. No service = restart all.
#   rebuild [service]   Stop, rebuild image, restart. No service = rebuild all buildable.
#   wake [id]           Wake stopped sandbox containers. id = session or sandbox UUID.
#
# BUILD COMMANDS:
#   build               Build the sandbox image (ii-agent-sandbox:latest)
#   build --local       Synonym for 'build' (sandbox image used in local mode)
#
# INFORMATION COMMANDS:
#   status              Show running containers and service URLs
#   logs [service]      View logs. Add -f to follow. No service = all logs.
#
# SETUP COMMANDS:
#   setup               Create .stack.env from template (cloud mode)
#   setup --local       Create .stack.env.local from template (local mode)
#
# ============================================================================
# SERVICES
# ============================================================================
# Buildable (have Dockerfiles, can be rebuilt):
#   frontend, backend, sandbox-server, tool-server
#
# Infrastructure (use pre-built images, cannot be rebuilt):
#   postgres, redis
#
# ============================================================================
# OPTIONS
# ============================================================================
#   --local      Use local mode (Docker sandboxes, no E2B/ngrok)
#   --build      Force rebuild images when starting (use with 'start')
#   --no-cache   Skip Docker cache (use with 'rebuild')
#   -f, --follow Follow logs continuously (use with 'logs')
#   -h, --help   Show help
#
# ============================================================================
# EXAMPLES
# ============================================================================
#   ./scripts/stack_control.sh start --local           # Start all local services
#   ./scripts/stack_control.sh stop --local            # Stop all local services
#   ./scripts/stack_control.sh rebuild --local         # Rebuild ALL services
#   ./scripts/stack_control.sh rebuild backend --local # Rebuild only backend
#   ./scripts/stack_control.sh restart backend --local # Restart backend (no rebuild)
#   ./scripts/stack_control.sh logs backend -f --local # Follow backend logs
#   ./scripts/stack_control.sh status --local          # Show service status
#   ./scripts/stack_control.sh build                   # Build sandbox image
#

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

# Colors for output (using $'...' syntax for portability)
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
NC=$'\033[0m' # No Color

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)

# Cloud stack mode configuration (default)
STACK_COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.stack.yaml"
STACK_ENV_FILE="$ROOT_DIR/docker/.stack.env"
STACK_ENV_EXAMPLE="$ROOT_DIR/docker/.stack.env.example"
STACK_PROJECT_NAME="ii-agent-stack"

# Local mode configuration
LOCAL_COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.local-only.yaml"
LOCAL_ENV_FILE="$ROOT_DIR/docker/.stack.env.local"
LOCAL_ENV_EXAMPLE="$ROOT_DIR/docker/.stack.env.local.example"
LOCAL_PROJECT_NAME="ii-agent-local"

# Services that have Dockerfiles and can be rebuilt
BUILDABLE_SERVICES="frontend backend sandbox-server tool-server"

# All valid services (buildable + infrastructure)
ALL_SERVICES="postgres redis sandbox-server tool-server backend frontend"

# Default values
USE_LOCAL_MODE=false
LOCAL_MODE_EXPLICIT=false  # Track if --local was explicitly passed
BUILD_FLAG=""
NO_CACHE_FLAG=""
FOLLOW_LOGS=false
COMMAND=""
TARGET_SERVICE=""  # Service to operate on (empty = all services)
WAKE_TARGET=""     # Session or sandbox ID for wake command

# Active configuration (set by get_compose_vars)
COMPOSE_FILE=""
ENV_FILE=""
ENV_EXAMPLE=""
PROJECT_NAME=""

# ============================================================================
# Logging functions
# ============================================================================

log_info() {
    printf '%s[INFO]%s %s\n' "$BLUE" "$NC" "$1"
}

log_success() {
    printf '%s[OK]%s %s\n' "$GREEN" "$NC" "$1"
}

log_warn() {
    printf '%s[WARN]%s %s\n' "$YELLOW" "$NC" "$1"
}

log_error() {
    printf '%s[ERROR]%s %s\n' "$RED" "$NC" "$1" >&2
}

# ============================================================================
# Help / Usage
# ============================================================================

usage() {
    cat <<'USAGE'
ii-agent Stack Control
======================

USAGE:
  ./scripts/stack_control.sh <command> [service] [options]

COMMANDS:
  start [service]     Start services (all if no service specified)
  stop [service]      Stop services (all if no service specified)
  restart [service]   Restart without rebuilding
  rebuild [service]   Rebuild from source and restart
  wake [id]           Wake stopped sandbox (session ID, sandbox ID, or 'all')
  status              Show running services and URLs
  logs [service]      View logs (-f to follow)
  build               Build the sandbox Docker image
  setup               Create environment file from template
  recover             Fix stuck sessions and restart backend

SERVICES:
  Buildable:       frontend, backend, sandbox-server, tool-server
  Infrastructure:  postgres, redis (pre-built images, cannot rebuild)

OPTIONS:
  --local        Force local mode (usually auto-detected)
  --build        Rebuild images when starting
  --no-cache     Skip Docker cache when rebuilding
  -f, --follow   Follow logs continuously
  -h, --help     Show this help

EXAMPLES:
  # First time setup:
  ./scripts/stack_control.sh setup       # Create env file from template
  ./scripts/stack_control.sh build       # Build sandbox image
  ./scripts/stack_control.sh start       # Start all services

  # Daily operations (mode auto-detected from running containers):
  ./scripts/stack_control.sh status              # Check what's running
  ./scripts/stack_control.sh logs backend -f     # Follow backend logs
  ./scripts/stack_control.sh restart backend     # Quick restart
  ./scripts/stack_control.sh rebuild backend     # Rebuild from source
  ./scripts/stack_control.sh stop                # Stop everything

  # Recovery (when frontend/backend is stuck):
  ./scripts/stack_control.sh recover             # Fix stuck sessions, restart backend

  # Wake stopped sandboxes (after reboot):
  ./scripts/stack_control.sh wake                # List stopped sandboxes
  ./scripts/stack_control.sh wake all            # Wake all stopped sandboxes
  ./scripts/stack_control.sh wake <session-id>   # Wake sandbox for specific session

  # For fine-grained stuck task control:
  ./scripts/local/stuck_task_control.sh          # List stuck tasks
  ./scripts/local/stuck_task_control.sh --help   # More options
USAGE
}

# ============================================================================
# Helper functions
# ============================================================================

# Auto-detect which mode to use based on running containers or available env files
auto_detect_mode() {
    # If --local was explicitly set, respect that
    if [[ "$LOCAL_MODE_EXPLICIT" == true ]]; then
        return
    fi

    # First check: Are there running containers that indicate the mode?
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^ii-agent-local-"; then
        USE_LOCAL_MODE=true
        log_info "Auto-detected local mode (found running ii-agent-local-* containers)"
        return
    fi

    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^ii-agent-stack-"; then
        USE_LOCAL_MODE=false
        log_info "Auto-detected cloud mode (found running ii-agent-stack-* containers)"
        return
    fi

    # Second check: if only local env exists, use local mode
    if [[ ! -f "$STACK_ENV_FILE" && -f "$LOCAL_ENV_FILE" ]]; then
        USE_LOCAL_MODE=true
        log_info "Auto-detected local mode (found .stack.env.local, no .stack.env)"
    fi
}

get_compose_vars() {
    if [[ "$USE_LOCAL_MODE" == true ]]; then
        COMPOSE_FILE="$LOCAL_COMPOSE_FILE"
        ENV_FILE="$LOCAL_ENV_FILE"
        ENV_EXAMPLE="$LOCAL_ENV_EXAMPLE"
        PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$LOCAL_PROJECT_NAME}"
    else
        COMPOSE_FILE="$STACK_COMPOSE_FILE"
        ENV_FILE="$STACK_ENV_FILE"
        ENV_EXAMPLE="$STACK_ENV_EXAMPLE"
        PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$STACK_PROJECT_NAME}"
    fi
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi

    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi
}

check_env_file() {
    if [[ ! -f "$ENV_FILE" ]]; then
        log_error "Environment file not found: $ENV_FILE"
        local mode_flag=""
        if [[ "$USE_LOCAL_MODE" == true ]]; then
            mode_flag=" --local"
        fi
        log_info "Run '$0 setup${mode_flag}' to create it from the template."
        exit 1
    fi
}

# Auto-create env file from template if missing (for start command)
ensure_env_file() {
    if [[ ! -f "$ENV_FILE" ]]; then
        if [[ -f "$ENV_EXAMPLE" ]]; then
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            echo "Created $ENV_FILE from template."
            echo ""
            if [[ "$USE_LOCAL_MODE" == true ]]; then
                echo "For local mode, you need to configure at minimum:"
                echo "  - LLM API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)"
                echo ""
                echo "Edit $ENV_FILE and rerun: $0 start --local"
            else
                echo "For cloud mode, you need to configure:"
                echo "  - LLM API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)"
                echo "  - E2B_API_KEY for cloud sandboxes"
                echo "  - NGROK_AUTHTOKEN for public tunnel"
                echo "  - Google Cloud credentials (if using GCS)"
                echo ""
                echo "Edit $ENV_FILE and rerun: $0 start"
            fi
            exit 1
        else
            log_error "Neither $ENV_FILE nor $ENV_EXAMPLE found"
            exit 1
        fi
    fi
}

compose() {
    docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

compose_up() {
    compose up -d ${BUILD_FLAG:+$BUILD_FLAG} "$@"
}

get_env_value() {
    local key=$1
    local default=${2:-}
    local value
    value=$(grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d '=' -f 2- || true)
    if [[ -z "$value" ]]; then
        printf '%s' "$default"
    else
        printf '%s' "$value"
    fi
}

update_env_value() {
    local key=$1
    local value=$2
    python3 - "$ENV_FILE" "$key" "$value" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]

lines = []
found = False
for raw_line in path.read_text().splitlines():
    if not raw_line.strip() or raw_line.strip().startswith('#'):
        lines.append(raw_line)
        continue
    name, sep, current = raw_line.partition('=')
    if name == key:
        lines.append(f"{key}={value}")
        found = True
    else:
        lines.append(raw_line)

if not found:
    lines.append(f"{key}={value}")

path.write_text("\n".join(lines).rstrip() + "\n")
PY
}

ensure_frontend_build_env() {
    local backend_port
    backend_port=$(get_env_value BACKEND_PORT 8000)
    local default_api_url="http://localhost:${backend_port}"
    local current_api_url
    current_api_url=$(get_env_value VITE_API_URL)
    if [[ -z "$current_api_url" ]]; then
        update_env_value VITE_API_URL "$default_api_url"
        echo "Defaulted VITE_API_URL to $default_api_url in $ENV_FILE"
    fi

    local current_build_mode
    current_build_mode=$(get_env_value FRONTEND_BUILD_MODE)
    if [[ -z "$current_build_mode" ]]; then
        update_env_value FRONTEND_BUILD_MODE production
        echo "Defaulted FRONTEND_BUILD_MODE to production in $ENV_FILE"
    fi

    local disable_chat_mode
    disable_chat_mode=$(get_env_value VITE_DISABLE_CHAT_MODE)
    if [[ -z "$disable_chat_mode" ]]; then
        update_env_value VITE_DISABLE_CHAT_MODE false
        echo "Defaulted VITE_DISABLE_CHAT_MODE to false in $ENV_FILE"
    fi
}

wait_for_ngrok_url() {
    local port
    port=$(get_env_value NGROK_METRICS_PORT 4040)
    sleep 5

    if resp=$(curl -fsS "http://localhost:${port}/api/tunnels" 2>/dev/null); then
        url=$(
            printf '%s' "$resp" | python3 - <<'PY'
import json, sys
try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)
for tunnel in data.get('tunnels', []):
    url = tunnel.get('public_url')
    if url and url.startswith('https://'):
        print(url)
        sys.exit(0)
sys.exit(1)
PY
        )
        if [[ -n "${url:-}" ]]; then
            printf '%s' "$url"
            return 0
        fi
    fi

    if log_line=$(compose logs ngrok --no-color 2>/dev/null | grep -E "url=https://" | tail -n1); then
        url=${log_line##*url=}
        url=${url%% *}
        if [[ -n "$url" ]]; then
            printf '%s' "$url"
            return 0
        fi
    fi

    return 1
}

# Show service URL after start/restart
show_service_url() {
    local service=$1
    local port
    case "$service" in
        frontend)
            port=$(get_env_value FRONTEND_PORT 1420)
            log_info "Frontend: http://localhost:$port"
            ;;
        backend)
            port=$(get_env_value BACKEND_PORT 8000)
            log_info "Backend: http://localhost:$port"
            ;;
        sandbox-server)
            port=$(get_env_value SANDBOX_SERVER_PORT 8100)
            log_info "Sandbox server: http://localhost:$port"
            ;;
        tool-server)
            port=$(get_env_value TOOL_SERVER_PORT 1236)
            log_info "Tool server: http://localhost:$port"
            ;;
        postgres)
            port=$(get_env_value POSTGRES_PORT 5432)
            log_info "PostgreSQL: localhost:$port"
            ;;
        redis)
            port=$(get_env_value REDIS_PORT 6379)
            log_info "Redis: localhost:$port"
            ;;
    esac
}

# Check if a service is valid
is_valid_service() {
    local service=$1
    for s in $ALL_SERVICES; do
        if [[ "$s" == "$service" ]]; then
            return 0
        fi
    done
    return 1
}

# Check if a service is buildable (has a Dockerfile)
is_buildable_service() {
    local service=$1
    for s in $BUILDABLE_SERVICES; do
        if [[ "$s" == "$service" ]]; then
            return 0
        fi
    done
    return 1
}

# ============================================================================
# Command implementations
# ============================================================================

cmd_setup() {
    get_compose_vars

    if [[ -f "$ENV_FILE" ]]; then
        log_warn "Environment file already exists: $ENV_FILE"
        read -p "Overwrite? (y/N): " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            log_info "Setup cancelled."
            return 0
        fi
    fi

    if [[ ! -f "$ENV_EXAMPLE" ]]; then
        log_error "Template file not found: $ENV_EXAMPLE"
        exit 1
    fi

    cp "$ENV_EXAMPLE" "$ENV_FILE"
    log_success "Created environment file: $ENV_FILE"

    if [[ "$USE_LOCAL_MODE" == true ]]; then
        log_info ""
        log_info "Local mode setup instructions:"
        log_info "  1. Edit $ENV_FILE with your LLM API keys"
        log_info "  2. Build the sandbox image: $0 build"
        log_info "  3. Start services: $0 start --local"
    else
        log_info ""
        log_info "Cloud stack setup instructions:"
        log_info "  1. Edit $ENV_FILE with your credentials:"
        log_info "     - LLM API keys (OpenAI, Anthropic, etc.)"
        log_info "     - E2B_API_KEY for cloud sandboxes"
        log_info "     - NGROK_AUTHTOKEN for public tunnel"
        log_info "     - Google Cloud credentials (if using GCS)"
        log_info "  2. Start services: $0 start"
    fi
}

# Build the sandbox image (ii-agent-sandbox:latest)
# This is the image used by sandbox-server to spawn ephemeral containers
cmd_build() {
    log_info "Building sandbox Docker image (ii-agent-sandbox:latest)..."

    if [[ ! -f "$ROOT_DIR/e2b.Dockerfile" ]]; then
        log_error "Sandbox Dockerfile not found: $ROOT_DIR/e2b.Dockerfile"
        exit 1
    fi

    docker build -t ii-agent-sandbox:latest -f "$ROOT_DIR/e2b.Dockerfile" "$ROOT_DIR"
    log_success "Sandbox image built: ii-agent-sandbox:latest"
    log_info "New sessions will use this image. Existing sandboxes are unaffected."
}

cmd_start() {
    auto_detect_mode
    get_compose_vars
    check_docker

    echo "Using $ROOT_DIR"
    ensure_env_file
    ensure_frontend_build_env

    # If a specific service was requested, just start that one
    if [[ -n "$TARGET_SERVICE" ]]; then
        log_info "Starting $TARGET_SERVICE..."
        compose_up "$TARGET_SERVICE"
        log_success "$TARGET_SERVICE started"
        show_service_url "$TARGET_SERVICE"
        return
    fi

    # Start all services
    if [[ "$USE_LOCAL_MODE" == true ]]; then
        # Check if sandbox image exists for local mode
        if ! docker image inspect ii-agent-sandbox:latest &> /dev/null; then
            log_warn "Sandbox image not found. Building it now..."
            cmd_build
        fi

        # Start all services at once
        compose_up

        # Print summary
        local frontend_port backend_port sandbox_port tool_port
        frontend_port=$(get_env_value FRONTEND_PORT 1420)
        backend_port=$(get_env_value BACKEND_PORT 8000)
        sandbox_port=$(get_env_value SANDBOX_SERVER_PORT 8100)
        tool_port=$(get_env_value TOOL_SERVER_PORT 1236)

        cat <<SUMMARY

Stack running in local mode (project: $PROJECT_NAME)
====================================================
  Frontend:        http://localhost:${frontend_port}
  Backend:         http://localhost:${backend_port}
  Sandbox server:  http://localhost:${sandbox_port}
  Tool server:     http://localhost:${tool_port}

Commands:
  Status:  $0 status --local
  Logs:    $0 logs [service] -f --local
  Stop:    $0 stop --local
SUMMARY
    else
        # Cloud stack mode - staged startup with ngrok URL discovery
        local previous_public_url
        previous_public_url=$(get_env_value PUBLIC_TOOL_SERVER_URL)

        compose_up postgres redis
        compose_up tool-server sandbox-server ngrok

        echo "Waiting for ngrok to publish a public HTTPS URL..."
        local current_public_url
        if new_url=$(wait_for_ngrok_url); then
            current_public_url="$new_url"
            update_env_value PUBLIC_TOOL_SERVER_URL "$current_public_url"
            echo "Public tool server URL detected: $current_public_url"
        else
            if [[ -n "$previous_public_url" && "$previous_public_url" != "auto" ]]; then
                echo "Unable to discover a new ngrok URL, falling back to previously configured PUBLIC_TOOL_SERVER_URL=$previous_public_url" >&2
                current_public_url="$previous_public_url"
            else
                echo "Failed to discover ngrok public URL. Check ngrok logs with 'docker compose logs ngrok'." >&2
                exit 1
            fi
        fi

        compose_up backend
        compose_up frontend

        local frontend_port backend_port sandbox_port tool_port ngrok_metrics_port
        frontend_port=$(get_env_value FRONTEND_PORT 1420)
        backend_port=$(get_env_value BACKEND_PORT 8000)
        sandbox_port=$(get_env_value SANDBOX_SERVER_PORT 8100)
        tool_port=$(get_env_value TOOL_SERVER_PORT 1236)
        ngrok_metrics_port=$(get_env_value NGROK_METRICS_PORT 4040)

        cat <<SUMMARY

Stack running in cloud mode (project: $PROJECT_NAME)
====================================================
  Frontend:             http://localhost:${frontend_port}
  Backend:              http://localhost:${backend_port}
  Sandbox server:       http://localhost:${sandbox_port}
  Tool server (local):  http://localhost:${tool_port}
  Tool server (public): ${current_public_url}
  ngrok dashboard:      http://localhost:${ngrok_metrics_port}

Commands:
  Status:  $0 status
  Logs:    $0 logs [service] -f
  Stop:    $0 stop
SUMMARY
    fi
}

cmd_stop() {
    auto_detect_mode
    get_compose_vars
    check_docker

    local mode_name
    if [[ "$USE_LOCAL_MODE" == true ]]; then
        mode_name="local"
    else
        mode_name="cloud"
    fi

    # If a specific service was requested, just stop that one
    if [[ -n "$TARGET_SERVICE" ]]; then
        log_info "Stopping $TARGET_SERVICE..."
        compose stop "$TARGET_SERVICE"
        log_success "$TARGET_SERVICE stopped"
        return
    fi

    # Stop all services
    log_info "Stopping ii-agent ($mode_name mode)..."

    if [[ -f "$ENV_FILE" ]]; then
        compose down
        log_success "All services stopped"
    else
        # Try to stop even without env file
        docker compose --project-name "$PROJECT_NAME" -f "$COMPOSE_FILE" down 2>/dev/null || true
        log_success "Services stopped"
    fi
}

cmd_restart() {
    auto_detect_mode
    get_compose_vars
    check_docker
    check_env_file

    # If a specific service was requested, just restart that one
    if [[ -n "$TARGET_SERVICE" ]]; then
        log_info "Restarting $TARGET_SERVICE (keeping existing image)..."
        compose restart "$TARGET_SERVICE"
        log_success "$TARGET_SERVICE restarted"
        show_service_url "$TARGET_SERVICE"
        return
    fi

    # Restart all services
    log_info "Restarting all services (keeping existing images)..."
    cmd_stop
    echo ""
    cmd_start
}

# Rebuild one or more services from source
# - If no service specified: rebuild ALL buildable services
# - If service specified: rebuild just that service
cmd_rebuild() {
    auto_detect_mode
    get_compose_vars
    check_docker
    check_env_file

    local cache_arg=""
    if [[ -n "$NO_CACHE_FLAG" ]]; then
        cache_arg="--no-cache"
    fi

    # If a specific service was requested, rebuild just that one
    if [[ -n "$TARGET_SERVICE" ]]; then
        local service=$TARGET_SERVICE

        # Check if service is buildable
        if ! is_buildable_service "$service"; then
            log_error "'$service' cannot be rebuilt (uses pre-built image)"
            log_info "Buildable services: $BUILDABLE_SERVICES"
            exit 1
        fi

        if [[ -n "$cache_arg" ]]; then
            log_info "Rebuilding $service (no cache)..."
        else
            log_info "Rebuilding $service..."
        fi

        compose stop "$service" || true
        compose build $cache_arg "$service"
        compose up -d "$service"

        log_success "$service rebuilt and restarted"
        show_service_url "$service"
        return
    fi

    # No service specified - rebuild ALL buildable services
    if [[ -n "$cache_arg" ]]; then
        log_info "Rebuilding ALL services (no cache)..."
    else
        log_info "Rebuilding ALL services..."
    fi

    log_info "Buildable services: $BUILDABLE_SERVICES"
    log_info "(postgres and redis use pre-built images, skipping)"
    echo ""

    # Stop all buildable services first
    log_info "Stopping buildable services..."
    for service in $BUILDABLE_SERVICES; do
        compose stop "$service" 2>/dev/null || true
    done

    # Rebuild all buildable services
    log_info "Building images..."
    for service in $BUILDABLE_SERVICES; do
        log_info "  Building $service..."
        compose build $cache_arg "$service"
    done

    # Start all buildable services
    log_info "Starting services..."
    for service in $BUILDABLE_SERVICES; do
        compose up -d "$service"
    done

    log_success "All services rebuilt and restarted"

    echo ""
    log_info "Service URLs:"
    for service in $BUILDABLE_SERVICES; do
        show_service_url "$service"
    done
}

cmd_status() {
    auto_detect_mode
    get_compose_vars
    check_docker

    local mode_name
    if [[ "$USE_LOCAL_MODE" == true ]]; then
        mode_name="local"
    else
        mode_name="cloud"
    fi

    printf '%sii-agent Status (%s mode)%s\n' "$BLUE" "$mode_name" "$NC"
    echo "============================================"
    echo "Project: $PROJECT_NAME"

    if [[ ! -f "$ENV_FILE" ]]; then
        log_warn "Environment file not configured: $ENV_FILE"
        echo ""
    fi

    # Check if any containers are running for this project
    local running_containers
    running_containers=$(docker ps --filter "label=com.docker.compose.project=$PROJECT_NAME" --format "{{.Names}}" 2>/dev/null | wc -l || echo "0")

    if [[ "$running_containers" -eq 0 ]]; then
        printf '%sNo services running.%s\n' "$YELLOW" "$NC"
        echo ""
        local mode_flag=""
        if [[ "$USE_LOCAL_MODE" == true ]]; then
            mode_flag=" --local"
        fi
        echo "Use '$0 start${mode_flag}' to start services."
        return 0
    fi

    compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

    echo ""
    printf '%sService URLs:%s\n' "$BLUE" "$NC"

    if [[ -f "$ENV_FILE" ]]; then
        local frontend_port backend_port sandbox_port tool_port
        frontend_port=$(get_env_value FRONTEND_PORT 1420)
        backend_port=$(get_env_value BACKEND_PORT 8000)
        sandbox_port=$(get_env_value SANDBOX_SERVER_PORT 8100)
        tool_port=$(get_env_value TOOL_SERVER_PORT 1236)

        echo "  Frontend:        http://localhost:$frontend_port"
        echo "  Backend API:     http://localhost:$backend_port"
        echo "  Sandbox Server:  http://localhost:$sandbox_port"
        echo "  Tool Server:     http://localhost:$tool_port"

        if [[ "$USE_LOCAL_MODE" == false ]]; then
            local ngrok_port public_url
            ngrok_port=$(get_env_value NGROK_METRICS_PORT 4040)
            public_url=$(get_env_value PUBLIC_TOOL_SERVER_URL "")
            echo "  ngrok Dashboard: http://localhost:$ngrok_port"
            if [[ -n "$public_url" ]]; then
                echo "  Tool Server (public): $public_url"
            fi
        fi
    fi

    # Also show sandbox containers if any are running
    echo ""
    local sandbox_containers
    sandbox_containers=$(docker ps --filter "name=ii-sandbox-" --format "{{.Names}}" 2>/dev/null | wc -l || echo "0")
    if [[ "$sandbox_containers" -gt 0 ]]; then
        printf '%sActive Sandboxes:%s\n' "$BLUE" "$NC"
        docker ps --filter "name=ii-sandbox-" --format "table {{.Names}}\t{{.Status}}\t{{.CreatedAt}}"
    fi
}

cmd_logs() {
    auto_detect_mode
    get_compose_vars
    check_docker
    check_env_file

    local follow_flag=""
    if [[ "$FOLLOW_LOGS" == true ]]; then
        follow_flag="-f"
    fi

    if [[ -n "$TARGET_SERVICE" ]]; then
        compose logs $follow_flag "$TARGET_SERVICE"
    else
        compose logs $follow_flag
    fi
}

# ============================================================================
# Wake Command - Restart stopped sandbox containers
# ============================================================================

cmd_wake() {
    auto_detect_mode
    get_compose_vars
    check_docker

    local target_id="${WAKE_TARGET:-}"

    echo ""
    printf '%s=== Sandbox Wake ===%s\n' "$BLUE" "$NC"
    echo ""

    # Get list of stopped sandbox containers
    local stopped_sandboxes
    stopped_sandboxes=$(docker ps -a --filter "name=ii-sandbox-" --filter "status=exited" --format "{{.Names}}" 2>/dev/null || true)

    if [[ -z "$stopped_sandboxes" ]]; then
        log_success "No stopped sandbox containers found"
        echo ""
        echo "All sandboxes are either running or have been removed."
        return 0
    fi

    # If no target specified, just list stopped sandboxes
    if [[ -z "$target_id" ]]; then
        log_info "Stopped sandbox containers:"
        echo ""
        docker ps -a --filter "name=ii-sandbox-" --filter "status=exited" --format "table {{.Names}}\t{{.Status}}\t{{.CreatedAt}}"
        echo ""
        echo "To wake a specific sandbox:"
        echo "  $0 wake <session-id>    # Wake by session UUID"
        echo "  $0 wake <sandbox-id>    # Wake by sandbox UUID (first 8 chars ok)"
        echo "  $0 wake all             # Wake all stopped sandboxes"
        return 0
    fi

    # Handle 'all' - wake all stopped sandboxes
    if [[ "$target_id" == "all" ]]; then
        log_info "Waking all stopped sandboxes..."
        local count=0
        for container in $stopped_sandboxes; do
            log_info "Starting $container..."
            if docker start "$container" &>/dev/null; then
                ((count++)) || true
                log_success "  Started $container"
            else
                log_error "  Failed to start $container"
            fi
        done
        echo ""
        log_success "Woke $count sandbox(es)"
        return 0
    fi

    # Try to find sandbox by session ID first (query database)
    local sandbox_id=""
    local postgres_container="${PROJECT_NAME}-postgres-1"
    local db_name db_user

    if [[ "$USE_LOCAL_MODE" == true ]]; then
        db_name="iiagentdev"
        db_user="iiagent"
    else
        db_name=$(get_env_value POSTGRES_DB "iiagent")
        db_user=$(get_env_value POSTGRES_USER "iiagent")
    fi

    # Check if target looks like a full UUID (session ID)
    if [[ "$target_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
        # Try to look up sandbox_id from session
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${postgres_container}$"; then
            sandbox_id=$(docker exec -i "$postgres_container" psql -U "$db_user" -d "$db_name" -t -A -c \
                "SELECT sandbox_id FROM sessions WHERE id = '$target_id';" 2>/dev/null || true)
            sandbox_id=$(echo "$sandbox_id" | tr -d '[:space:]')

            if [[ -n "$sandbox_id" ]]; then
                log_info "Session $target_id uses sandbox $sandbox_id"
            else
                # Maybe it's a sandbox ID, not session ID
                sandbox_id="$target_id"
            fi
        else
            log_warn "PostgreSQL not running, treating ID as sandbox ID"
            sandbox_id="$target_id"
        fi
    else
        # Partial ID - treat as sandbox ID prefix
        sandbox_id="$target_id"
    fi

    # Find container matching sandbox ID
    local container_name=""
    local short_id="${sandbox_id:0:11}"  # Container names use first 11 chars of UUID

    for container in $stopped_sandboxes; do
        if [[ "$container" == *"$short_id"* ]] || [[ "$container" == *"${sandbox_id:0:8}"* ]]; then
            container_name="$container"
            break
        fi
    done

    if [[ -z "$container_name" ]]; then
        log_error "No stopped sandbox found matching: $target_id"
        echo ""
        echo "Stopped sandboxes:"
        docker ps -a --filter "name=ii-sandbox-" --filter "status=exited" --format "  {{.Names}}"
        return 1
    fi

    # Wake the sandbox
    log_info "Waking sandbox: $container_name"
    if docker start "$container_name"; then
        sleep 2
        if docker ps --filter "name=$container_name" --format "{{.Status}}" | grep -q "Up"; then
            log_success "Sandbox is now running"
            docker ps --filter "name=$container_name" --format "table {{.Names}}\t{{.Status}}"
        else
            log_warn "Container started but may not be healthy yet"
        fi
    else
        log_error "Failed to start sandbox container"
        return 1
    fi
}

# ============================================================================
# Recover Command - Fix stuck sessions and restart backend
# ============================================================================

cmd_recover() {
    auto_detect_mode
    get_compose_vars
    check_docker

    local mode_name
    if [[ "$USE_LOCAL_MODE" == true ]]; then
        mode_name="local"
    else
        mode_name="cloud"
    fi

    echo ""
    printf '%s=== ii-agent Recovery (%s mode) ===%s\n' "$BLUE" "$mode_name" "$NC"
    echo ""

    # Step 1: Check backend health
    log_info "Step 1: Checking backend health..."
    local backend_container="${PROJECT_NAME}-backend-1"
    local backend_healthy=false

    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${backend_container}$"; then
        # Check if backend is responding
        if timeout 3 docker exec "$backend_container" curl -fsS http://localhost:8000/health &>/dev/null; then
            log_success "Backend is healthy"
            backend_healthy=true
        else
            log_warn "Backend is running but NOT responding (frozen)"
        fi
    else
        log_warn "Backend container is not running"
    fi

    # Step 2: Fix stuck tasks in database
    log_info "Step 2: Checking for stuck tasks..."
    local postgres_container="${PROJECT_NAME}-postgres-1"
    local db_name
    local db_user

    if [[ "$USE_LOCAL_MODE" == true ]]; then
        db_name="iiagentdev"
        db_user="iiagent"
    else
        db_name=$(get_env_value POSTGRES_DB "iiagent")
        db_user=$(get_env_value POSTGRES_USER "iiagent")
    fi

    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${postgres_container}$"; then
        # Get backend start time for comparison
        local backend_start=""
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${backend_container}$"; then
            backend_start=$(docker inspect "$backend_container" --format '{{.State.StartedAt}}' 2>/dev/null | cut -d'.' -f1 | tr 'T' ' ')
        fi

        # Count stuck tasks
        local stuck_count
        if [[ -n "$backend_start" ]]; then
            stuck_count=$(docker exec -i "$postgres_container" psql -U "$db_user" -d "$db_name" -t -A -c \
                "SELECT COUNT(*) FROM agent_run_tasks WHERE status = 'running' AND created_at < '${backend_start}';" 2>/dev/null || echo "0")
        else
            stuck_count=$(docker exec -i "$postgres_container" psql -U "$db_user" -d "$db_name" -t -A -c \
                "SELECT COUNT(*) FROM agent_run_tasks WHERE status = 'running';" 2>/dev/null || echo "0")
        fi

        stuck_count=$(echo "$stuck_count" | tr -d '[:space:]')

        if [[ "$stuck_count" -gt 0 ]]; then
            log_warn "Found $stuck_count stuck task(s)"
            echo ""
            echo "Stuck tasks:"
            docker exec -i "$postgres_container" psql -U "$db_user" -d "$db_name" -t -c \
                "SELECT id, session_id, status, created_at FROM agent_run_tasks WHERE status = 'running' ORDER BY created_at DESC LIMIT 10;" 2>/dev/null || true
            echo ""

            # Fix stuck tasks
            log_info "Marking stuck tasks as 'system_interrupted'..."
            local fixed_ids
            if [[ -n "$backend_start" ]]; then
                fixed_ids=$(docker exec -i "$postgres_container" psql -U "$db_user" -d "$db_name" -t -A -c \
                    "UPDATE agent_run_tasks SET status = 'system_interrupted', updated_at = NOW() WHERE status = 'running' AND created_at < '${backend_start}' RETURNING id;" 2>/dev/null || echo "")
            else
                fixed_ids=$(docker exec -i "$postgres_container" psql -U "$db_user" -d "$db_name" -t -A -c \
                    "UPDATE agent_run_tasks SET status = 'system_interrupted', updated_at = NOW() WHERE status = 'running' RETURNING id;" 2>/dev/null || echo "")
            fi

            if [[ -n "$fixed_ids" ]]; then
                log_success "Fixed $(echo "$fixed_ids" | wc -l) stuck task(s)"
            fi
        else
            log_success "No stuck tasks found"
        fi
    else
        log_warn "PostgreSQL container not running, cannot check for stuck tasks"
    fi

    # Step 3: Restart backend if unhealthy
    if [[ "$backend_healthy" == false ]]; then
        log_info "Step 3: Restarting backend..."
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${backend_container}$"; then
            docker restart "$backend_container"
            sleep 5
            if timeout 5 docker exec "$backend_container" curl -fsS http://localhost:8000/health &>/dev/null; then
                log_success "Backend restarted and healthy"
            else
                log_warn "Backend restarted but not yet healthy (may need more time)"
            fi
        else
            log_info "Starting backend service..."
            compose up -d backend
        fi
    else
        log_info "Step 3: Backend already healthy, skipping restart"
    fi

    echo ""
    printf '%s=== Recovery Complete ===%s\n' "$GREEN" "$NC"
    echo ""
    echo "Your sessions should now be accessible. Any interrupted tasks will"
    echo "need to be re-submitted as new queries."
    echo ""
    echo "For fine-grained control (filter by session/task):"
    echo "  ./scripts/local/stuck_task_control.sh --help"
    echo ""
}

# ============================================================================
# Argument parsing
# ============================================================================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            start|stop|restart|rebuild|status|logs|build|setup|recover|wake)
                COMMAND=$1
                shift
                ;;
            postgres|redis|sandbox-server|tool-server|backend|frontend)
                # Service name - validate it can be used with the command
                if [[ -z "$COMMAND" ]]; then
                    log_error "Please specify a command before the service name"
                    log_info "Example: $0 restart $1 --local"
                    exit 1
                fi
                case "$COMMAND" in
                    start|stop|restart|rebuild|logs)
                        TARGET_SERVICE=$1
                        ;;
                    *)
                        log_error "Service '$1' cannot be used with '$COMMAND' command"
                        exit 1
                        ;;
                esac
                shift
                ;;
            all|[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]*)
                # UUID or 'all' - for wake command
                if [[ "$COMMAND" == "wake" ]]; then
                    WAKE_TARGET=$1
                else
                    log_error "Argument '$1' can only be used with 'wake' command"
                    exit 1
                fi
                shift
                ;;
            --local)
                USE_LOCAL_MODE=true
                LOCAL_MODE_EXPLICIT=true
                shift
                ;;
            --build)
                BUILD_FLAG="--build"
                shift
                ;;
            --no-cache)
                NO_CACHE_FLAG="--no-cache"
                shift
                ;;
            -f|--follow)
                FOLLOW_LOGS=true
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_error "Unknown argument: $1"
                echo ""
                usage
                exit 1
                ;;
        esac
    done

    # Default to 'start' command for backward compatibility
    if [[ -z "$COMMAND" ]]; then
        COMMAND="start"
    fi
}

# ============================================================================
# Main
# ============================================================================

main() {
    parse_args "$@"

    case $COMMAND in
        start)
            cmd_start
            ;;
        stop)
            cmd_stop
            ;;
        restart)
            cmd_restart
            ;;
        rebuild)
            cmd_rebuild
            ;;
        status)
            cmd_status
            ;;
        logs)
            cmd_logs
            ;;
        build)
            cmd_build
            ;;
        setup)
            cmd_setup
            ;;
        recover)
            cmd_recover
            ;;
        wake)
            cmd_wake
            ;;
        *)
            log_error "Unknown command: $COMMAND"
            usage
            exit 1
            ;;
    esac
}

main "$@"
