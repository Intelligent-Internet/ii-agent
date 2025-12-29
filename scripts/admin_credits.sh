#!/bin/bash
# Admin Credit Management Tool
# Usage: ./scripts/admin_credits.sh [command] [args]

set -e

# Database connection details
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-docker-postgres-1}"
POSTGRES_USER="${POSTGRES_USER:-iiagent}"
POSTGRES_DB="${POSTGRES_DB:-iiagentdev}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

run_sql() {
    docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"
}

show_help() {
    echo "Admin Credit Management Tool"
    echo ""
    echo "Usage: $0 <command> [args]"
    echo ""
    echo "Commands:"
    echo "  list                    List all users and their credit balances"
    echo "  show <email>            Show credits for a specific user"
    echo "  topup <email> <amount>  Add credits to a user's balance"
    echo "  set <email> <amount>    Set a user's credit balance to exact amount"
    echo "  bonus <email> <amount>  Add bonus credits (used before regular credits)"
    echo ""
    echo "Examples:"
    echo "  $0 list"
    echo "  $0 show admin@ii.inc"
    echo "  $0 topup admin@ii.inc 5000"
    echo "  $0 set admin@ii.inc 10000"
    echo "  $0 bonus admin@ii.inc 2000"
    echo ""
    echo "Environment Variables:"
    echo "  POSTGRES_CONTAINER  Docker container name (default: docker-postgres-1)"
    echo "  POSTGRES_USER       Database user (default: iiagent)"
    echo "  POSTGRES_DB         Database name (default: iiagentdev)"
}

list_users() {
    echo -e "${GREEN}User Credit Balances:${NC}"
    run_sql "SELECT email, role, ROUND(credits::numeric, 2) as credits, ROUND(bonus_credits::numeric, 2) as bonus, ROUND((credits + bonus_credits)::numeric, 2) as total FROM users ORDER BY role DESC, email;"
}

show_user() {
    local email="$1"
    if [ -z "$email" ]; then
        echo -e "${RED}Error: Email required${NC}"
        echo "Usage: $0 show <email>"
        exit 1
    fi
    echo -e "${GREEN}Credits for $email:${NC}"
    run_sql "SELECT email, role, ROUND(credits::numeric, 2) as credits, ROUND(bonus_credits::numeric, 2) as bonus_credits, ROUND((credits + bonus_credits)::numeric, 2) as total_credits FROM users WHERE email = '$email';"
}

topup_credits() {
    local email="$1"
    local amount="$2"
    if [ -z "$email" ] || [ -z "$amount" ]; then
        echo -e "${RED}Error: Email and amount required${NC}"
        echo "Usage: $0 topup <email> <amount>"
        exit 1
    fi
    echo -e "${YELLOW}Adding $amount credits to $email...${NC}"
    run_sql "UPDATE users SET credits = credits + $amount, updated_at = NOW() WHERE email = '$email' RETURNING email, ROUND(credits::numeric, 2) as new_credits, ROUND(bonus_credits::numeric, 2) as bonus_credits;"
    echo -e "${GREEN}Done!${NC}"
}

set_credits() {
    local email="$1"
    local amount="$2"
    if [ -z "$email" ] || [ -z "$amount" ]; then
        echo -e "${RED}Error: Email and amount required${NC}"
        echo "Usage: $0 set <email> <amount>"
        exit 1
    fi
    echo -e "${YELLOW}Setting $email credits to $amount...${NC}"
    run_sql "UPDATE users SET credits = $amount, updated_at = NOW() WHERE email = '$email' RETURNING email, ROUND(credits::numeric, 2) as credits, ROUND(bonus_credits::numeric, 2) as bonus_credits;"
    echo -e "${GREEN}Done!${NC}"
}

add_bonus() {
    local email="$1"
    local amount="$2"
    if [ -z "$email" ] || [ -z "$amount" ]; then
        echo -e "${RED}Error: Email and amount required${NC}"
        echo "Usage: $0 bonus <email> <amount>"
        exit 1
    fi
    echo -e "${YELLOW}Adding $amount bonus credits to $email...${NC}"
    run_sql "UPDATE users SET bonus_credits = bonus_credits + $amount, updated_at = NOW() WHERE email = '$email' RETURNING email, ROUND(credits::numeric, 2) as credits, ROUND(bonus_credits::numeric, 2) as new_bonus_credits;"
    echo -e "${GREEN}Done!${NC}"
}

# Main command dispatch
case "${1:-}" in
    list)
        list_users
        ;;
    show)
        show_user "$2"
        ;;
    topup)
        topup_credits "$2" "$3"
        ;;
    set)
        set_credits "$2" "$3"
        ;;
    bonus)
        add_bonus "$2" "$3"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        if [ -n "$1" ]; then
            echo -e "${RED}Unknown command: $1${NC}"
            echo ""
        fi
        show_help
        exit 1
        ;;
esac
