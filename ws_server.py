#!/usr/bin/env python3
"""
FastAPI WebSocket Server for the Agent.

This script provides a WebSocket interface for interacting with the Agent,
allowing real-time communication with a frontend application.
"""

import os
import argparse
import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Dict, Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import anyio

from ii_agent.core.event import RealtimeEvent, EventType
from utils import parse_common_args
from ii_agent.agents.anthropic_fc import AnthropicFC
from ii_agent.agents.base import BaseAgent
from ii_agent.utils import WorkspaceManager
from ii_agent.llm import get_client
from dotenv import load_dotenv

from fastapi.staticfiles import StaticFiles

from ii_agent.llm.context_manager.file_based import FileBasedContextManager
from ii_agent.llm.context_manager.standard import StandardContextManager
from ii_agent.llm.token_counter import TokenCounter

load_dotenv()
MAX_OUTPUT_TOKENS_PER_TURN = 32768
MAX_TURNS = 200


app = FastAPI(title="Agent WebSocket API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


try:
    app.mount(
        "/workspace", StaticFiles(directory="workspace", html=True), name="workspace"
    )
except RuntimeError:
    # Directory might not exist yet
    os.makedirs("workspace", exist_ok=True)
    app.mount(
        "/workspace", StaticFiles(directory="workspace", html=True), name="workspace"
    )

# Create a logger
logger = logging.getLogger("websocket_server")
logger.setLevel(logging.INFO)

# Active WebSocket connections
active_connections: Set[WebSocket] = set()

# Active agents for each connection
active_agents: Dict[WebSocket, BaseAgent] = {}

# Active agent tasks
active_tasks: Dict[WebSocket, asyncio.Task] = {}

# Store message processors for each connection
message_processors: Dict[WebSocket, asyncio.Task] = {}

# Store global args for use in endpoint
global_args = None


async def save_uploaded_file(
    websocket: WebSocket, file_path: str, file_content: str
) -> str:
    """Save an uploaded file to the workspace.

    Args:
        websocket: The WebSocket connection
        file_path: The path where the file should be saved (relative to workspace)
        file_content: The content of the file (base64 encoded if binary)

    Returns:
        The absolute path where the file was saved
    """
    agent = active_agents.get(websocket)

    if not agent:
        raise ValueError("Agent not initialized for this connection")

    # Get the workspace path for this connection
    workspace_root = agent.workspace_manager.root

    # Ensure the file path is relative to the workspace
    if Path(file_path).is_absolute():
        file_path = Path(
            file_path
        ).name  # Just use the filename if absolute path provided

    # Create the full path
    full_path = workspace_root / file_path

    # Ensure the directory exists
    full_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if content is base64 encoded (for binary files)
    if file_content.startswith("data:"):
        # Handle data URLs (e.g., "data:application/pdf;base64,...")
        import base64

        # Split the header from the base64 content
        header, encoded = file_content.split(",", 1)

        # Decode the content
        decoded = base64.b64decode(encoded)

        # Write binary content
        with open(full_path, "wb") as f:
            f.write(decoded)
    else:
        # Write text content
        with open(full_path, "w") as f:
            f.write(file_content)

    # Log the upload
    logger.info(f"File uploaded to {full_path}")

    # Return the path where the file was saved
    return str(full_path)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)

    # Create a new agent for this connection
    agent = create_agent_for_connection(websocket)
    active_agents[websocket] = agent

    # Start message processor for this connection
    message_processor = agent.start_message_processing()
    message_processors[websocket] = message_processor

    try:
        # Initial connection message
        await websocket.send_json(
            RealtimeEvent(
                type=EventType.CONNECTION_ESTABLISHED,
                content={"message": "Connected to Agent WebSocket Server"},
            ).model_dump()
        )

        # Process messages from the client
        while True:
            # Receive and parse message
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type")
                content = message.get("content", {})

                if msg_type == "query":
                    # Check if there's an active task for this connection
                    if websocket in active_tasks and not active_tasks[websocket].done():
                        await websocket.send_json(
                            RealtimeEvent(
                                type=EventType.ERROR,
                                content={
                                    "message": "A query is already being processed"
                                },
                            ).model_dump()
                        )
                        continue

                    # Process a query to the agent
                    user_input = content.get("text", "")
                    resume = content.get("resume", False)

                    # Send acknowledgment
                    await websocket.send_json(
                        RealtimeEvent(
                            type=EventType.PROCESSING,
                            content={"message": "Processing your request..."},
                        ).model_dump()
                    )

                    # Run the agent with the query in a separate task
                    task = asyncio.create_task(
                        run_agent_async(websocket, user_input, resume)
                    )
                    active_tasks[websocket] = task

                elif msg_type == "workspace_info":
                    # Send information about the current workspace
                    if agent and agent.workspace_manager:
                        await websocket.send_json(
                            RealtimeEvent(
                                type=EventType.WORKSPACE_INFO,
                                content={"path": str(agent.workspace_manager.root)},
                            ).model_dump()
                        )
                    else:
                        await websocket.send_json(
                            RealtimeEvent(
                                type=EventType.ERROR,
                                content={"message": "Workspace not initialized"},
                            ).model_dump()
                        )

                elif msg_type == "upload_file":
                    # Handle file upload (single or multiple)
                    files = content.get("files", [])

                    # For backward compatibility, also support single file upload
                    if not files and content.get("path") and "content" in content:
                        files = [
                            {
                                "path": content.get("path", ""),
                                "content": content.get("content", ""),
                            }
                        ]

                    if not files:
                        await websocket.send_json(
                            RealtimeEvent(
                                type=EventType.ERROR,
                                content={"message": "No files provided for upload"},
                            ).model_dump()
                        )
                        continue

                    try:
                        results = []
                        for file_info in files:
                            file_path = file_info.get("path", "")
                            file_content = file_info.get("content", "")

                            if not file_path:
                                continue

                            result = await save_uploaded_file(
                                websocket, file_path, file_content
                            )
                            results.append({"path": file_path, "saved_path": result})

                        await websocket.send_json(
                            RealtimeEvent(
                                type=EventType.UPLOAD_SUCCESS,
                                content={
                                    "message": f"Successfully uploaded {len(results)} file(s)",
                                    "files": results,
                                },
                            ).model_dump()
                        )
                    except Exception as e:
                        logger.error(f"Error uploading files: {str(e)}")
                        await websocket.send_json(
                            RealtimeEvent(
                                type=EventType.ERROR,
                                content={"message": f"Error uploading files: {str(e)}"},
                            ).model_dump()
                        )

                elif msg_type == "ping":
                    # Simple ping to keep connection alive
                    await websocket.send_json(
                        RealtimeEvent(type=EventType.PONG, content={}).model_dump()
                    )

                elif msg_type == "cancel":
                    # Cancel the current agent task if one exists
                    if websocket in active_tasks and not active_tasks[websocket].done():
                        active_tasks[websocket].cancel()
                        await websocket.send_json(
                            RealtimeEvent(
                                type=EventType.SYSTEM,
                                content={"message": "Query canceled"},
                            ).model_dump()
                        )
                    else:
                        await websocket.send_json(
                            RealtimeEvent(
                                type=EventType.ERROR,
                                content={"message": "No active query to cancel"},
                            ).model_dump()
                        )

                else:
                    # Unknown message type
                    await websocket.send_json(
                        RealtimeEvent(
                            type=EventType.ERROR,
                            content={"message": f"Unknown message type: {msg_type}"},
                        ).model_dump()
                    )

            except json.JSONDecodeError:
                await websocket.send_json(
                    RealtimeEvent(
                        type=EventType.ERROR, content={"message": "Invalid JSON format"}
                    ).model_dump()
                )
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                await websocket.send_json(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": f"Error processing request: {str(e)}"},
                    ).model_dump()
                )

    except WebSocketDisconnect:
        # Handle disconnection
        logger.info("Client disconnected")
        cleanup_connection(websocket)
    except Exception as e:
        # Handle other exceptions
        logger.error(f"WebSocket error: {str(e)}")
        cleanup_connection(websocket)


async def run_agent_async(websocket: WebSocket, user_input: str, resume: bool = False):
    """Run the agent asynchronously and send results back to the websocket."""
    agent = active_agents.get(websocket)

    if not agent:
        await websocket.send_json(
            RealtimeEvent(
                type=EventType.ERROR,
                content={"message": "Agent not initialized for this connection"},
            ).model_dump()
        )
        return

    try:
        # Run the agent with the query
        result = await anyio.to_thread.run_sync(agent.run_agent, user_input, resume)

        # Send result back to client
        await websocket.send_json(
            RealtimeEvent(
                type=EventType.AGENT_RESPONSE, content={"text": result}
            ).model_dump()
        )
    except Exception as e:
        logger.error(f"Error running agent: {str(e)}")
        import traceback

        traceback.print_exc()
        await websocket.send_json(
            RealtimeEvent(
                type=EventType.ERROR,
                content={"message": f"Error running agent: {str(e)}"},
            ).model_dump()
        )
    finally:
        # Clean up the task reference
        if websocket in active_tasks:
            del active_tasks[websocket]


def cleanup_connection(websocket: WebSocket):
    """Clean up resources associated with a websocket connection."""
    # Remove from active connections
    if websocket in active_connections:
        active_connections.remove(websocket)

    # Cancel message processor
    if websocket in message_processors:
        message_processors[websocket].cancel()
        del message_processors[websocket]

    # Cancel any running tasks
    if websocket in active_tasks and not active_tasks[websocket].done():
        active_tasks[websocket].cancel()
        del active_tasks[websocket]

    # Remove agent for this connection
    if websocket in active_agents:
        del active_agents[websocket]


def create_agent_for_connection(websocket: WebSocket):
    """Create a new agent instance for a websocket connection."""
    global global_args

    # Setup logging
    logger_for_agent_logs = logging.getLogger(f"agent_logs_{id(websocket)}")
    logger_for_agent_logs.setLevel(logging.DEBUG)

    # Ensure we don't duplicate handlers
    if not logger_for_agent_logs.handlers:
        logger_for_agent_logs.addHandler(logging.FileHandler(global_args.logs_path))
        if not global_args.minimize_stdout_logs:
            logger_for_agent_logs.addHandler(logging.StreamHandler())
        else:
            logger_for_agent_logs.propagate = False

    # Initialize LLM client
    client = get_client(
        "anthropic-direct",
        model_name="claude-3-7-sonnet@20250219",
        use_caching=False,
        project_id=global_args.project_id,
        region=global_args.region,
    )

    # Create unique subdirectory for this connection
    connection_id = str(uuid.uuid4())
    workspace_path = Path(global_args.workspace).resolve()
    connection_workspace = workspace_path / connection_id
    connection_workspace.mkdir(parents=True, exist_ok=True)

    # Initialize workspace manager with connection-specific subdirectory
    workspace_manager = WorkspaceManager(
        root=connection_workspace,
        container_workspace=global_args.use_container_workspace,
    )

    # Initialize token counter
    token_counter = TokenCounter()

    # Create context manager based on argument
    if global_args.context_manager == "file-based":
        context_manager = FileBasedContextManager(
            workspace_dir=connection_workspace,
            token_counter=token_counter,
            logger=logger_for_agent_logs,
            token_budget=120_000,
        )
    else:  # standard
        context_manager = StandardContextManager(
            token_counter=token_counter,
            logger=logger_for_agent_logs,
            token_budget=120_000,
        )

    # Initialize agent with websocket
    agent = AnthropicFC(
        client=client,
        workspace_manager=workspace_manager,
        logger_for_agent_logs=logger_for_agent_logs,
        context_manager=context_manager,
        max_output_tokens_per_turn=MAX_OUTPUT_TOKENS_PER_TURN,
        max_turns=MAX_TURNS,
        ask_user_permission=global_args.needs_permission,
        docker_container_id=global_args.docker_container_id,
        websocket=websocket,
    )

    return agent


def main():
    """Main entry point for the WebSocket server."""
    global global_args

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="WebSocket Server for interacting with the Agent"
    )
    parser = parse_common_args(parser)
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to run the server on",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the server on",
    )
    args = parser.parse_args()
    global_args = args

    # Start the FastAPI server
    logger.info(f"Starting WebSocket server on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
