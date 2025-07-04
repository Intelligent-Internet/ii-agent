#!/bin/bash

# Create workspace directory if it doesn't exist
mkdir -p /workspace

# Start the sandbox server in the background
echo "Starting sandbox server on port 17300..."
cd /app && python -m ii_client.sandbox_server --port 17300 --cwd /workspace &

# Start code-server in the background
echo "Starting code-server on port 9000..."
code-server \
  --port 9000 \
  --auth none \
  --bind-addr 0.0.0.0:9000 \
  --disable-telemetry \
  --disable-update-check \
  --trusted-origins * \
  --disable-workspace-trust \
  /workspace &

# Wait for both processes to start
sleep 3

# Check if processes are running
echo "Checking if services are running..."
if pgrep -f "sandbox_server" >/dev/null; then
  echo "✓ Sandbox server is running"
else
  echo "✗ Sandbox server failed to start"
fi

if pgrep -f "code-server" >/dev/null; then
  echo "✓ Code-server is running"
else
  echo "✗ Code-server failed to start"
fi

echo "Services started. Container ready."
echo "Sandbox server available on port 17300"
echo "Code-server available on port 9000"

# Keep the container running by waiting for all background processes
wait
