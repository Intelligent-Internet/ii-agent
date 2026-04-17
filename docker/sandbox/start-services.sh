#!/bin/bash

# If running as root, use gosu to re-execute as user
if [ "$(id -u)" = "0" ]; then
    echo "Running as root, switching to user with gosu..."
    exec gosu user bash "$0" "$@"
fi

# Set up environment
export HOME=/home/user
export PATH="/home/user/.bun/bin:/app/ii_sandbox/.venv/bin:$PATH"


# Create workspace directory if it doesn't exist and ensure ownership
mkdir -p /workspace
chown -R "$(id -u):$(id -g)" /workspace
cd /workspace

# Ensure X11 socket directory exists (Xvfb cannot create it as non-root)
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix

# Start Xvfb virtual display
echo "Starting Xvfb..."
Xvfb :99 -screen 0 1920x1080x24 -ac &
export DISPLAY=:99
export AGENT_BROWSER_HEADED=1
sleep 1

# Start x11vnc server with generated password
echo "Starting x11vnc..."
VNC_PASSWORD=$(head -c 8 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 8)
echo "$VNC_PASSWORD" > /tmp/.vnc_password
x11vnc -display :99 -forever -passwdfile /tmp/.vnc_password -shared -rfbport 5900 -bg -o /tmp/x11vnc.log
echo "VNC password: $VNC_PASSWORD (also saved to /tmp/.vnc_password)"
sleep 1

# Start window manager (needed for Chrome to render properly in VNC)
echo "Starting fluxbox window manager..."
fluxbox &
sleep 1

# Start noVNC websockify proxy (serves VNC over WebSocket on port 6080)
# Note: VNC password is required when connecting via noVNC
echo "Starting noVNC on port 6080..."
websockify --web=/usr/share/novnc 6080 localhost:5900 &
sleep 1

# Start the sandbox server in the background
echo "Starting sandbox server..."
tmux new-session -d -s sandbox-server-system-never-kill -c /workspace 'WORKSPACE_DIR=/workspace DISPLAY=:99 python -m ii_server.mcp.server'

# Start code-server in the background
echo "Starting code-server on port 9000..."
tmux new-session -d -s code-server-system-never-kill -c /workspace 'code-server \
  --port 9000 \
  --auth none \
  --bind-addr 0.0.0.0:9000 \
  --disable-telemetry \
  --disable-update-check \
  --trusted-origins * \
  --disable-workspace-trust \
  /workspace'

# Start A2A adapter (with supervised auto-restart on exit)
# The adapter hosts the II-Agent A2A protocol endpoint used by A2AInnerLoop.
# SANDBOX_ADAPTER_PORT defaults to 18100 (control-plane reserved range 18000-18999).
# SANDBOX_ADAPTER_BACKEND selects the inner-loop backend:
#   simulate   - built-in mock stream (default, no external deps)
#   copilot    - GitHub Copilot CLI via github-copilot-sdk (uses gh auth or GITHUB_TOKEN)
#   claude-code - Claude Code CLI subprocess (requires ANTHROPIC_API_KEY)
#   codex       - OpenAI Codex CLI subprocess (requires OPENAI_API_KEY)
SANDBOX_ADAPTER_PORT="${SANDBOX_ADAPTER_PORT:-18100}"
SANDBOX_ADAPTER_BACKEND="${SANDBOX_ADAPTER_BACKEND:-simulate}"
echo "Starting A2A adapter on port ${SANDBOX_ADAPTER_PORT} (backend=${SANDBOX_ADAPTER_BACKEND})..."
tmux new-session -d -s copilot-adapter-system-never-kill -c /workspace \
  "while true; do \
     DISPLAY=:99 AGENT_BROWSER_HEADED=1 \
     python -m ii_agent.integrations.a2a.adapter_server \
       --host 0.0.0.0 --port ${SANDBOX_ADAPTER_PORT} \
       --backend ${SANDBOX_ADAPTER_BACKEND}; \
     echo 'A2A adapter exited, restarting in 2s...'; \
     sleep 2; \
   done"

# Wait for both processes to start
sleep 3

# Check if processes are running
echo "Checking if services are running..."
if pgrep -f "ii_server.mcp.server" >/dev/null; then
  echo "✓ Sandbox server is running"
else
  echo "✗ Sandbox server failed to start"
fi

if pgrep -f "code-server" >/dev/null; then
  echo "✓ Code-server is running"
else
  echo "✗ Code-server failed to start"
fi

if pgrep -f "websockify" >/dev/null; then
  echo "✓ noVNC is running on port 6080"
else
  echo "✗ noVNC failed to start"
fi

echo "Services started. Container ready."
echo "Sandbox server available"
echo "Code-server available on port 9000"
echo "noVNC available on port 6080"

# Keep the container running by waiting for all background processes
wait
