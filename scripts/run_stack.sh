#!/usr/bin/env bash
#
# run_stack.sh - Control script for ii-agent
#
# Usage:
#   ./scripts/run_stack.sh [command] [options]
#
# Commands:
#   start       Start ii-agent services (default if no command given)
#   stop        Stop ii-agent services
#   restart     Restart ii-agent services
#   status      Show status of ii-agent services
#   logs        View logs (optionally for a specific service)
#   build       Build sandbox image (required for local mode)
#   setup       Initial setup - create env files from templates
#
# Options:
#   --local     Use local-only mode (Docker sandboxes, no E2B/ngrok)
#   --build     Force rebuild of Docker images
#   -f, --follow   Follow logs (for logs command)
#   -h, --help     Show this help message
#

set -euo pipefail

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

# Default values
USE_LOCAL_MODE=false
LOCAL_MODE_EXPLICIT=false  # Track if --local was explicitly passed
BUILD_FLAG=""
FOLLOW_LOGS=false
COMMAND=""
SERVICE=""

# Active configuration (set by get_compose_vars)
COMPOSE_FILE=""
ENV_FILE=""
ENV_EXAMPLE=""
PROJECT_NAME=""

# Logging functions
log_info() {
    printf '%s[INFO]%s %s\n' "$BLUE" "$NC" "$1"
}

log_success() {
    printf '%s[SUCCESS]%s %s\n' "$GREEN" "$NC" "$1"
}

log_warn() {
    printf '%s[WARN]%s %s\n' "$YELLOW" "$NC" "$1"
}

log_error() {
    printf '%s[ERROR]%s %s\n' "$RED" "$NC" "$1" >&2
}

usage() {
  cat <<USAGE
${BLUE}ii-agent Control Script${NC}

${YELLOW}Usage:${NC}
  $0 [command] [options]

${YELLOW}Commands:${NC}
  ${GREEN}start${NC}       Start ii-agent services (default if no command given)
  ${GREEN}stop${NC}        Stop ii-agent services
  ${GREEN}restart${NC}     Restart ii-agent services
  ${GREEN}status${NC}      Show status of ii-agent services
  ${GREEN}logs${NC}        View logs (optionally specify service name)
  ${GREEN}build${NC}       Build the sandbox Docker image (required for local mode)
  ${GREEN}setup${NC}       Initial setup - create env files from templates

${YELLOW}Options:${NC}
  ${GREEN}--local${NC}     Use local-only mode (Docker sandboxes, no E2B/ngrok)
  ${GREEN}--build${NC}     Force rebuild of Docker images when starting
  ${GREEN}-f, --follow${NC}   Follow logs continuously (for logs command)
  ${GREEN}-h, --help${NC}     Show this help message

${YELLOW}Examples:${NC}
  $0 start                    # Start with cloud stack (E2B + ngrok)
  $0 start --local            # Start with local-only mode
  $0 start --local --build    # Start local mode and rebuild images
  $0 stop                     # Stop cloud stack
  $0 stop --local             # Stop local-only stack
  $0 logs backend -f          # Follow backend logs
  $0 status                   # Show service status

${YELLOW}First Time Setup:${NC}
  Cloud mode:
    1. Run: $0 setup
    2. Edit docker/.stack.env with your API keys (E2B, ngrok, LLM providers)
    3. Run: $0 start

  Local mode:
    1. Run: $0 setup --local
    2. Edit docker/.stack.env.local with your LLM API keys
    3. Run: $0 build
    4. Run: $0 start --local
USAGE
}

# Auto-detect which mode to use based on available env files
auto_detect_mode() {
    # If --local was explicitly set, respect that
    if [[ "$LOCAL_MODE_EXPLICIT" == true ]]; then
        return
    fi

    # Auto-detect: if only local env exists, use local mode
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

# Auto-create env file from template if missing (backward compatible behavior for start command)
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

cmd_build() {
    log_info "Building sandbox Docker image..."

    if [[ ! -f "$ROOT_DIR/e2b.Dockerfile" ]]; then
        log_error "Sandbox Dockerfile not found: $ROOT_DIR/e2b.Dockerfile"
        exit 1
    fi

    docker build -t ii-agent-sandbox:latest -f "$ROOT_DIR/e2b.Dockerfile" "$ROOT_DIR"
    log_success "Sandbox image built successfully: ii-agent-sandbox:latest"
}

cmd_start() {
    auto_detect_mode
    get_compose_vars
    check_docker

    # Print the root directory (backward compatible with original)
    echo "Using $ROOT_DIR"

    # Ensure env file exists (auto-create from template like original)
    ensure_env_file

    ensure_frontend_build_env

    if [[ "$USE_LOCAL_MODE" == true ]]; then
        # Check if sandbox image exists for local mode
        if ! docker image inspect ii-agent-sandbox:latest &> /dev/null; then
            log_warn "Sandbox image not found. Building it now..."
            cmd_build
        fi

        # For local mode, start all services at once (no ngrok)
        compose_up

        # Print local mode summary
        local frontend_port backend_port sandbox_port tool_port
        frontend_port=$(get_env_value FRONTEND_PORT 1420)
        backend_port=$(get_env_value BACKEND_PORT 8000)
        sandbox_port=$(get_env_value SANDBOX_SERVER_PORT 8100)
        tool_port=$(get_env_value TOOL_SERVER_PORT 1236)

        cat <<SUMMARY
Stack is running in local mode (project name: $PROJECT_NAME)
  Frontend:        http://localhost:${frontend_port}
  Backend:         http://localhost:${backend_port}
  Sandbox server:  http://localhost:${sandbox_port}
  Tool server:     http://localhost:${tool_port}

Use 'docker compose --project-name $PROJECT_NAME -f docker/docker-compose.local-only.yaml ps' to inspect containers.
SUMMARY
    else
        # For cloud stack, use staged startup with ngrok URL discovery
        # This matches the original behavior exactly
        local previous_public_url
        previous_public_url=$(get_env_value PUBLIC_TOOL_SERVER_URL)

        # Start shared infrastructure first so ngrok can bind once the tunnel is live.
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

        # Start the backend after the PUBLIC_TOOL_SERVER_URL is finalized.
        compose_up backend
        compose_up frontend

        # Print original format summary
        local frontend_port backend_port sandbox_port tool_port ngrok_metrics_port
        frontend_port=$(get_env_value FRONTEND_PORT 1420)
        backend_port=$(get_env_value BACKEND_PORT 8000)
        sandbox_port=$(get_env_value SANDBOX_SERVER_PORT 8100)
        tool_port=$(get_env_value TOOL_SERVER_PORT 1236)
        ngrok_metrics_port=$(get_env_value NGROK_METRICS_PORT 4040)

        cat <<SUMMARY
Stack is running (project name: $PROJECT_NAME)
  Frontend:             http://localhost:${frontend_port}
  Backend:              http://localhost:${backend_port}
  Sandbox server:       http://localhost:${sandbox_port}
  Tool server (local):  http://localhost:${tool_port}
  Tool server (public): ${current_public_url}
  ngrok dashboard:      http://localhost:${ngrok_metrics_port}

Use 'docker compose --project-name $PROJECT_NAME -f docker/docker-compose.stack.yaml ps' to inspect containers.
SUMMARY
    fi
}

cmd_stop() {
    auto_detect_mode
    get_compose_vars
    check_docker

    local mode_name
    if [[ "$USE_LOCAL_MODE" == true ]]; then
        mode_name="local-only"
    else
        mode_name="cloud stack"
    fi

    log_info "Stopping ii-agent ($mode_name mode)..."

    if [[ -f "$ENV_FILE" ]]; then
        compose down
        log_success "ii-agent stopped successfully!"
    else
        # Try to stop even without env file
        docker compose --project-name "$PROJECT_NAME" -f "$COMPOSE_FILE" down 2>/dev/null || true
        log_success "ii-agent stopped."
    fi
}

cmd_restart() {
    cmd_stop
    echo ""
    cmd_start
}

cmd_status() {
    auto_detect_mode
    get_compose_vars
    check_docker

    local mode_name
    if [[ "$USE_LOCAL_MODE" == true ]]; then
        mode_name="local-only"
    else
        mode_name="cloud stack"
    fi

    printf '%sii-agent Status (%s mode)%s\n' "$BLUE" "$mode_name" "$NC"
    echo "============================================"
    echo "Project name: $PROJECT_NAME"

    if [[ ! -f "$ENV_FILE" ]]; then
        log_warn "Environment file not configured: $ENV_FILE"
        echo ""
    fi

    # Check if any containers are running for this project
    local running_containers
    running_containers=$(docker ps --filter "label=com.docker.compose.project=$PROJECT_NAME" --format "{{.Names}}" 2>/dev/null | wc -l || echo "0")

    if [[ "$running_containers" -eq 0 ]]; then
        printf '%sNo services running for project %s.%s\n' "$YELLOW" "$PROJECT_NAME" "$NC"
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
}

cmd_logs() {
    auto_detect_mode
    get_compose_vars
    check_docker
    check_env_file

    local service="${1:-}"
    local follow_flag=""

    if [[ "$FOLLOW_LOGS" == true ]]; then
        follow_flag="-f"
    fi

    if [[ -n "$service" && "$service" != "-f" && "$service" != "--follow" ]]; then
        compose logs $follow_flag "$service"
    else
        compose logs $follow_flag
    fi
}

# ============================================================================
# Argument parsing
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        start|stop|restart|status|logs|build|setup)
            COMMAND=$1
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
        -f|--follow)
            FOLLOW_LOGS=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            if [[ -z "$SERVICE" && "$COMMAND" == "logs" ]]; then
                SERVICE=$1
            else
                log_error "Unknown argument: $1"
                usage
                exit 1
            fi
            shift
            ;;
    esac
done

# Default to 'start' command for backward compatibility
if [[ -z "$COMMAND" ]]; then
    COMMAND="start"
fi

# Execute command
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
    status)
        cmd_status
        ;;
    logs)
        cmd_logs "$SERVICE"
        ;;
    build)
        cmd_build
        ;;
    setup)
        cmd_setup
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
