# II Sandbox Server

A standalone FastAPI server that manages sandbox lifecycle operations for the II Agent system.

## Architecture

The sandbox server handles all sandbox-related operations including:

- Creating and managing sandboxes
- Scheduling timeouts and lifecycle management
- File operations (upload, download, read, write)
- MCP (Model Context Protocol) setup
- Redis-based message queuing for delayed operations

## Components

- **Main Server** (`main.py`) - FastAPI application with REST API endpoints
- **Sandbox Manager** (`sandbox_manager.py`) - Core business logic for sandbox operations
- **Database Layer** (`database.py`) - SQLAlchemy models and operations
- **Providers** (`providers/`) - Sandbox provider implementations (E2B, etc.)
- **Queue System** (`queue.py`) - Redis-based message scheduling
- **Client** (`client.py`) - HTTP client for communicating with the server

## Configuration

Environment variables:

- `SANDBOX_SERVER_HOST` - Server host (default: 0.0.0.0)
- `SANDBOX_SERVER_PORT` - Server port (default: 8100)
- `SANDBOX_PROVIDER` - Provider type (default: e2b)
- `E2B_API_KEY` - E2B API key (required for E2B provider)
- `E2B_TEMPLATE` - E2B template (default: base)
- `REDIS_URL` - Redis URL (default: redis://localhost:6379)
- `MCP_PORT` - MCP port in sandboxes (default: 5173)

### Sandbox Container Services

Each Docker sandbox container runs the following services:

| Service | Port | Description |
|---------|------|-------------|
| MCP Server | 6060 | Model Context Protocol server for agent tool calls |
| code-server | 9000 | VS Code in the browser |
| noVNC | 6080 | Browser-based VNC viewer for user interaction handoff |
| x11vnc | 5900 | VNC server connected to the Xvfb virtual display (internal) |
| Xvfb | :99 | Virtual framebuffer for headed Chromium |

#### noVNC Browser Handoff

When the agent encounters situations requiring human interaction (CAPTCHAs, login pages,
authentication prompts), it can expose the noVNC port and share a URL with the user.
The user opens the URL in their browser to see and interact with the sandbox's virtual
display, then tells the agent to resume automation. This allows secure credential entry
without sharing passwords with the agent.

## Running the Server

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set environment variables:
   ```bash
   export E2B_API_KEY=your_e2b_api_key
   export REDIS_URL=redis://localhost:6379
   ```

3. Start the server:
   ```bash
   ./start_sandbox_server.sh
   ```

   Or run directly:
   ```bash
   uvicorn ii_sandbox_server.main:app --host 0.0.0.0 --port 8100
   ```

## API Endpoints

- `POST /sandboxes/create` - Create a new sandbox
- `POST /sandboxes/connect` - Connect to or resume a sandbox
- `POST /sandboxes/schedule-timeout` - Schedule a timeout for a sandbox
- `GET /sandboxes/{id}/status` - Get sandbox status
- `GET /sandboxes/{id}/info` - Get sandbox information
- `POST /sandboxes/{id}/pause` - Pause a sandbox
- `DELETE /sandboxes/{id}` - Delete a sandbox
- `POST /sandboxes/expose-port` - Expose a port from a sandbox
- `POST /sandboxes/write-file` - Write a file to a sandbox
- `POST /sandboxes/read-file` - Read a file from a sandbox
- `POST /sandboxes/download-file` - Download a file from a sandbox
- `POST /sandboxes/setup-mcp` - Setup MCP for a sandbox

## Integration

The II Agent application uses the `SandboxServerClient` to communicate with this server via HTTP. The original `sandbox_service.py` has been replaced with a simplified version that delegates all operations to this standalone server.

## Database

The server uses SQLite by default for storing sandbox metadata. The database is automatically initialized on startup.