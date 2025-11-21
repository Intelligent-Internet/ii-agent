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

# Determine the default II_AGENT_DIR
# Priority: $II_AGENT_DIR env var > script-provided path > ~/work/ii-agent
if [ -n "$II_AGENT_DIR" ]; then
    # Use user-provided env var
    :
else
    # Try to autodetect via git: look for a parent dir named ii-agent by walking up
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    # If install script was run near the repo, try to use ~/work/ii-agent or parent directories
    POSSIBLE="$SCRIPT_DIR/../../.. $PWD $HOME/work/ii-agent"
    for p in $POSSIBLE; do
        if [ -d "$p" ] && [ -f "$p/pyproject.toml" ]; then
            II_AGENT_DIR="$p"
            break
        fi
    done
fi

# If still not found, set a default but warn
if [ -z "$II_AGENT_DIR" ]; then
    II_AGENT_DIR="$HOME/work/ii-agent"
    if [ ! -d "$II_AGENT_DIR" ]; then
        echo "Warning: ii-agent directory not found at $II_AGENT_DIR. To set the correct path, set II_AGENT_DIR=/path/to/ii-agent and re-run install-repl.sh"
    fi
fi

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
exec python -m ii_agent.cli.main --repl "$@"
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

echo "If ii-agent repo is not in ~/work/ii-agent, run the installer as follows (example):"
echo "  II_AGENT_DIR=\"/Users/jim/work/ii-agent\" bash install-repl.sh"
echo ""
echo "REPL commands:"
echo "  /help     - Show available commands"
echo "  /context  - Show context window status (coming soon)"
echo "  /models   - List available models"
echo "  /exit     - Exit REPL"