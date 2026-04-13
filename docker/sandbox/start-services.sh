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

# Start x11vnc server
echo "Starting x11vnc..."
x11vnc -display :99 -forever -nopw -shared -rfbport 5900 -bg -o /tmp/x11vnc.log
sleep 1

# Start window manager (needed for Chrome to render properly in VNC)
echo "Starting fluxbox window manager..."
fluxbox &
sleep 1

# Start noVNC websockify proxy (serves VNC over WebSocket on port 6080)
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
