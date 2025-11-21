#!/bin/bash
# Install ii-agent REPL to ~/.local/bin with memvid and duckdb support

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Installing ii-agent REPL to ~/.local${NC}"

# Create ~/.local/bin if it doesn't exist
mkdir -p ~/.local/bin

# Create wrapper script for REPL
cat > ~/.local/bin/ii-repl << 'EOF'
#!/bin/bash
# ii-agent REPL launcher with memvid and duckdb support

# Get the directory where ii-agent is installed
II_AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd ../.. && pwd)/work/ii-agent"

# Set PYTHONPATH to include ii-agent source
export PYTHONPATH="$II_AGENT_DIR/src:$PYTHONPATH"

# Skip PostgreSQL migrations in REPL mode (uses DuckDB instead)
export IIAGENT_SKIP_MIGRATIONS="1"
export IIAGENT_SKIP_SERVER_APP_IMPORT="1"

# Activate virtual environment if it exists
if [ -f "$II_AGENT_DIR/.venv/bin/activate" ]; then
    source "$II_AGENT_DIR/.venv/bin/activate"
fi

# Run the REPL with all arguments passed through
exec python -m ii_agent.cli.main repl "$@"
EOF

# Make it executable
chmod +x ~/.local/bin/ii-repl

echo -e "${GREEN}✓ REPL installed to ~/.local/bin/ii-repl${NC}"
echo ""
echo "Features enabled:"
echo "  • MemVid storage (QR-encoded MP4 checkpoints)"
echo "  • DuckDB analytics"
echo "  • Dictionary storage with LRU cache"
echo "  • Slab checkpointing system"
echo "  • Context window management"
echo ""
echo "To use the REPL, make sure ~/.local/bin is in your PATH:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
echo ""
echo "Then run:"
echo "  ii-repl"
echo ""
echo "REPL commands:"
echo "  /help     - Show available commands"
echo "  /context  - Show context window status (coming soon)"
echo "  /models   - List available models"
echo "  /exit     - Exit REPL"