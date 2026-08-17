#!/bin/bash
# ==============================================================================
# Stuck Task Control Script
# ==============================================================================
# This script manages tasks that are stuck in "running" status after a backend
# restart. This can happen when the backend process is terminated while 
# processing a task.
#
# Usage:
#   ./scripts/local/stuck_task_control.sh                              # List all stuck tasks
#   ./scripts/local/stuck_task_control.sh --session <id>               # List stuck tasks for session
#   ./scripts/local/stuck_task_control.sh --session <id> --fix         # Fix stuck tasks for session
#   ./scripts/local/stuck_task_control.sh --task <id> --fix            # Fix specific task
#   ./scripts/local/stuck_task_control.sh --fix-all                    # Fix ALL stuck tasks (use with caution)
#
# Examples:
#   ./scripts/local/stuck_task_control.sh --session 37cff1ba           # List tasks for session starting with 37cff1ba
#   ./scripts/local/stuck_task_control.sh --session 37cff1ba --fix     # Fix those tasks
#   ./scripts/local/stuck_task_control.sh --task a63c2a80 --fix        # Fix specific task
# ==============================================================================

set -euo pipefail

# Configuration
POSTGRES_CONTAINER="ii-agent-local-postgres-1"
POSTGRES_USER="iiagent"
POSTGRES_DB="iiagentdev"

# Colors (use $'...' to interpret escape sequences)
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m'
NC=$'\033[0m' # No Color

# Arguments
ACTION="list"
FIX_MODE=false
FIX_ALL=false
SESSION_ID=""
TASK_ID=""
ID_PREFIX_PATTERN='^[0-9a-fA-F-]+$'

validate_id_prefix() {
    local value="$1"
    local flag_name="$2"

    if [[ -z "$value" ]]; then
        echo -e "${RED}Error: ${flag_name} value cannot be empty${NC}"
        exit 1
    fi

    if [[ ! "$value" =~ $ID_PREFIX_PATTERN ]]; then
        echo -e "${RED}Error: ${flag_name} contains invalid characters${NC}"
        echo "Only hexadecimal characters and hyphens are allowed for ID prefixes."
        exit 1
    fi
}

show_help() {
    cat << EOF
${CYAN}Stuck Task Control${NC}

Manage agent tasks stuck in "running" status (typically after a backend restart).
Lists stuck tasks by default; use --fix to mark them as 'system_interrupted'.

${YELLOW}USAGE:${NC}
    $0 [OPTIONS]

${YELLOW}OPTIONS:${NC}
    -h, --help              Show this help message
    --session <id>          Filter by session ID (prefix match supported)
    --task <id>             Filter by task ID (prefix match supported)
    --fix                   Mark filtered tasks as 'system_interrupted'
                            ${RED}Requires --session or --task for safety${NC}
    --fix-all               Mark ALL stuck tasks (use with caution)

${YELLOW}EXAMPLES:${NC}
    ${GREEN}# List all stuck tasks across all sessions${NC}
    $0

    ${GREEN}# List stuck tasks for a specific session${NC}
    $0 --session 37cff1ba

    ${GREEN}# Fix stuck tasks for a specific session${NC}
    $0 --session 37cff1ba --fix

    ${GREEN}# Fix a specific task by ID${NC}
    $0 --task a63c2a80 --fix

    ${GREEN}# Fix ALL stuck tasks (dangerous!)${NC}
    $0 --fix-all

${YELLOW}NOTES:${NC}
    - IDs support prefix matching (first 8 chars usually sufficient)
    - --fix requires --session or --task to prevent accidental mass updates
    - Fixed tasks are marked 'system_interrupted' with updated_at = NOW()
    - After fixing, the session can accept new queries

EOF
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --fix)
            FIX_MODE=true
            shift
            ;;
        --fix-all)
            FIX_ALL=true
            FIX_MODE=true
            shift
            ;;
        --session)
            SESSION_ID="$2"
            shift 2
            ;;
        --task)
            TASK_ID="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            ;;
        *)
            echo -e "${RED}Unknown argument: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

if [[ -n "$SESSION_ID" ]]; then
    validate_id_prefix "$SESSION_ID" "--session"
fi

if [[ -n "$TASK_ID" ]]; then
    validate_id_prefix "$TASK_ID" "--task"
fi

# Safety check: --fix requires a filter unless --fix-all is used
if [[ "$FIX_MODE" == true && "$FIX_ALL" != true && -z "$SESSION_ID" && -z "$TASK_ID" ]]; then
    echo -e "${RED}Error: --fix requires --session or --task for safety${NC}"
    echo -e "Use ${YELLOW}--fix-all${NC} if you really want to fix ALL stuck tasks"
    exit 1
fi

# Helper function to run psql
run_psql() {
    docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A -c "$1"
}

# Check if postgres container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER}$"; then
    echo -e "${RED}Error: PostgreSQL container '$POSTGRES_CONTAINER' is not running${NC}"
    echo "Start the stack first: ./scripts/run_stack.sh start --local"
    exit 1
fi

# Get backend container start time (for detecting truly stuck tasks)
BACKEND_CONTAINER="ii-agent-local-backend-1"
get_backend_start_time() {
    docker inspect "$BACKEND_CONTAINER" --format '{{.State.StartedAt}}' 2>/dev/null | cut -d'.' -f1 | tr 'T' ' '
}

# Get stuck tasks (created BEFORE backend started - truly orphaned)
get_stuck_tasks() {
    local backend_start
    backend_start=$(get_backend_start_time)
    local where_clause="status = 'running'"
    if [[ -n "$backend_start" ]]; then
        # Only consider tasks created BEFORE the backend started as stuck
        where_clause="$where_clause AND created_at < '${backend_start}'"
    fi
    if [[ -n "$SESSION_ID" ]]; then
        where_clause="$where_clause AND session_id::text LIKE '${SESSION_ID}%'"
    fi
    if [[ -n "$TASK_ID" ]]; then
        where_clause="$where_clause AND id::text LIKE '${TASK_ID}%'"
    fi
    
    run_psql "SELECT id, session_id, status, created_at FROM agent_run_tasks WHERE $where_clause ORDER BY created_at DESC;"
}

# Count stuck tasks (created BEFORE backend started)
count_stuck_tasks() {
    local backend_start
    backend_start=$(get_backend_start_time)
    local where_clause="status = 'running'"
    if [[ -n "$backend_start" ]]; then
        where_clause="$where_clause AND created_at < '${backend_start}'"
    fi
    if [[ -n "$SESSION_ID" ]]; then
        where_clause="$where_clause AND session_id::text LIKE '${SESSION_ID}%'"
    fi
    if [[ -n "$TASK_ID" ]]; then
        where_clause="$where_clause AND id::text LIKE '${TASK_ID}%'"
    fi
    
    run_psql "SELECT COUNT(*) FROM agent_run_tasks WHERE $where_clause;"
}

# Fix stuck tasks (only those created BEFORE backend started)
fix_stuck_tasks() {
    local backend_start
    backend_start=$(get_backend_start_time)
    local where_clause="status = 'running'"
    if [[ -n "$backend_start" ]]; then
        where_clause="$where_clause AND created_at < '${backend_start}'"
    fi
    if [[ -n "$SESSION_ID" ]]; then
        where_clause="$where_clause AND session_id::text LIKE '${SESSION_ID}%'"
    fi
    if [[ -n "$TASK_ID" ]]; then
        where_clause="$where_clause AND id::text LIKE '${TASK_ID}%'"
    fi
    
    run_psql "UPDATE agent_run_tasks SET status = 'system_interrupted', updated_at = NOW() WHERE $where_clause RETURNING id;"
}

# Build filter description for display
get_filter_desc() {
    if [[ -n "$SESSION_ID" && -n "$TASK_ID" ]]; then
        echo "session='${SESSION_ID}*' AND task='${TASK_ID}*'"
    elif [[ -n "$SESSION_ID" ]]; then
        echo "session='${SESSION_ID}*'"
    elif [[ -n "$TASK_ID" ]]; then
        echo "task='${TASK_ID}*'"
    else
        echo "all"
    fi
}

# Main logic
if [[ "$FIX_MODE" == true ]]; then
    # Fix mode
    count=$(count_stuck_tasks)
    if [[ "$count" -eq 0 ]]; then
        echo -e "${GREEN}No stuck tasks found matching criteria ($(get_filter_desc)).${NC}"
        exit 0
    fi
    
    echo -e "${YELLOW}Fixing $count stuck task(s) matching: $(get_filter_desc)${NC}"
    
    # Capture session IDs before fixing (for post-fix guidance)
    affected_sessions=$(run_psql "SELECT DISTINCT session_id FROM agent_run_tasks WHERE status = 'running' $(
        [[ -n "$SESSION_ID" ]] && echo "AND session_id::text LIKE '${SESSION_ID}%'"
        [[ -n "$TASK_ID" ]] && echo "AND id::text LIKE '${TASK_ID}%'"
    );")
    
    fixed_ids=$(fix_stuck_tasks)
    
    if [[ -n "$fixed_ids" ]]; then
        echo -e "${GREEN}Successfully marked the following tasks as 'system_interrupted':${NC}"
        echo "$fixed_ids" | while read -r id; do
            [[ -n "$id" ]] && echo "  - $id"
        done
        
        # Provide guidance on resuming
        echo ""
        echo -e "${CYAN}=== Next Steps ===${NC}"
        echo -e "The affected session(s) can now accept new queries."
        echo -e "${YELLOW}Note:${NC} The interrupted task will NOT automatically resume."
        echo -e "You must submit a new query to continue working."
        echo ""
        if [[ -n "$affected_sessions" ]]; then
            echo -e "${GREEN}Session URL(s):${NC}"
            echo "$affected_sessions" | while read -r sess_id; do
                [[ -n "$sess_id" ]] && echo "  http://localhost:1420/${sess_id}"
            done
        fi
    else
        echo -e "${RED}No tasks were updated.${NC}"
    fi
else
    # List mode
    backend_start=$(get_backend_start_time)
    echo -e "${CYAN}=== Stuck Tasks ===${NC}"
    echo -e "${CYAN}(Tasks with status='running' created BEFORE backend started)${NC}"
    if [[ -n "$backend_start" ]]; then
        echo -e "Backend started: ${YELLOW}${backend_start}${NC}"
    else
        echo -e "${RED}Warning: Could not determine backend start time${NC}"
    fi
    if [[ -n "$SESSION_ID" || -n "$TASK_ID" ]]; then
        echo -e "Filter: $(get_filter_desc)"
    fi
    echo ""
    
    count=$(count_stuck_tasks)
    if [[ "$count" -eq 0 ]]; then
        echo -e "${GREEN}No stuck tasks found.${NC}"
        echo -e "(Tasks created after backend started are considered active, not stuck)"
        exit 0
    fi
    
    echo -e "${YELLOW}Found $count stuck task(s):${NC}"
    echo ""
    printf "%-38s | %-38s | %-8s | %s\n" "TASK_ID" "SESSION_ID" "STATUS" "CREATED_AT"
    printf "%-38s-+-%-38s-+-%-8s-+-%s\n" "--------------------------------------" "--------------------------------------" "--------" "-------------------"
    get_stuck_tasks | while IFS='|' read -r id session status created; do
        printf "%-38s | %-38s | %-8s | %s\n" "$id" "$session" "$status" "$created"
    done
    echo ""
    if [[ -n "$SESSION_ID" || -n "$TASK_ID" ]]; then
        echo -e "Run with ${GREEN}--fix${NC} to mark these as 'system_interrupted'"
    else
        echo -e "Use ${GREEN}--session <id>${NC} or ${GREEN}--task <id>${NC} to filter, then ${GREEN}--fix${NC}"
        echo -e "Or use ${YELLOW}--fix-all${NC} to fix all stuck tasks (use with caution)"
    fi
fi
