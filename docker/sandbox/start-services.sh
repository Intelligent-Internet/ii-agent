#!/bin/bash

# If running as root, fix workspace permissions and switch to pn user
if [ "$(id -u)" = "0" ]; then
    echo "Running as root, fixing workspace permissions and switching to pn user..."
    # Ensure /workspace is owned by pn user before switching
    chown -R pn:pn /workspace 2>/dev/null || true
    exec gosu pn bash "$0" "$@"
fi

# Set up environment
export HOME=/home/pn
export PATH="/home/pn/.bun/bin:/app/ii_agent/.venv/bin:$PATH"


# Create workspace directory if it doesn't exist
mkdir -p /workspace
cd /workspace

# Start Xvfb with a known display number so x11vnc can connect to it
echo "Starting Xvfb virtual display..."
Xvfb :99 -screen 0 1280x720x24 &
sleep 1
export DISPLAY=:99

# Start the sandbox server in the background
echo "Starting sandbox server..."
tmux new-session -d -s sandbox-server-system-never-kill -c /workspace "DISPLAY=:99 WORKSPACE_DIR=/workspace python -m ii_tool.mcp.server"

# Start x11vnc (VNC server connected to the virtual display)
echo "Starting x11vnc on port 5900..."
tmux new-session -d -s vnc-server-system-never-kill 'x11vnc -display :99 -forever -nopw -listen 0.0.0.0 -rfbport 5900 -shared'

# Start noVNC web proxy (allows browser-based VNC access)
echo "Starting noVNC on port 6080..."
tmux new-session -d -s novnc-server-system-never-kill 'websockify --web /usr/share/novnc 6080 localhost:5900'

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

# Wait for both processes to start
sleep 3

# Check if processes are running
echo "Checking if services are running..."
if pgrep -f "mcp.server" >/dev/null; then
  echo "✓ Sandbox server is running"
else
  echo "✗ Sandbox server failed to start"
fi

if pgrep -f "code-server" >/dev/null; then
  echo "✓ Code-server is running"
else
  echo "✗ Code-server failed to start"
fi

if pgrep -f "x11vnc" >/dev/null; then
  echo "✓ x11vnc is running on port 5900"
else
  echo "✗ x11vnc failed to start"
fi

if pgrep -f "websockify" >/dev/null; then
  echo "✓ noVNC is running on port 6080"
else
  echo "✗ noVNC failed to start"
fi

echo "Services started. Container ready."
echo "Sandbox server available"
echo "Code-server available on port 9000"
echo "noVNC viewer available on port 6080"

# Keep the container running by tailing the tmux sessions
# This prevents the container from exiting while services run in tmux
exec tail -f /dev/null
