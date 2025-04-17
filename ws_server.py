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
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tools.agent import Agent
from utils.workspace_manager import WorkspaceManager
from utils.llm_client import get_client
from prompts.instruction import INSTRUCTION_PROMPT
from dotenv import load_dotenv

load_dotenv()
MAX_OUTPUT_TOKENS_PER_TURN = 32768
MAX_TURNS = 200

# Initialize FastAPI app
app = FastAPI(title="Agent WebSocket API")

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Serve static files from frontend directory
from fastapi.staticfiles import StaticFiles
try:
    app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
except RuntimeError:
    # Directory might not exist yet
    os.makedirs("frontend", exist_ok=True)
    app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# Create a logger
logger = logging.getLogger("websocket_server")
logger.setLevel(logging.INFO)

# Active WebSocket connections
active_connections: Set[WebSocket] = set()

# Active agent tasks
active_tasks: Dict[WebSocket, asyncio.Task] = {}

# WebSocket message models
class ClientMessage(BaseModel):
    type: str
    content: Dict[str, Any]

class ServerMessage(BaseModel):
    type: str
    content: Dict[str, Any]

# Agent instance and workspace manager
agent = None
workspace_manager = None

async def run_agent_async(websocket: WebSocket, user_input: str, resume: bool = False):
    """Run the agent asynchronously and send results back to the websocket."""
    global agent
    
    try:
        # Run the agent with the query
        result = agent.run_agent(user_input, resume=resume)
        
        # Send result back to client
        await websocket.send_json({
            "type": "agent_response",
            "content": {"text": result}
        })
    except Exception as e:
        logger.error(f"Error running agent: {str(e)}")
        await websocket.send_json({
            "type": "error",
            "content": {"message": f"Error running agent: {str(e)}"}
        })
    finally:
        # Clean up the task reference
        if websocket in active_tasks:
            del active_tasks[websocket]

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global agent, workspace_manager
    
    # Accept the connection
    await websocket.accept()
    active_connections.add(websocket)
    
    try:
        # Initial connection message
        await websocket.send_json({
            "type": "connection_established",
            "content": {"message": "Connected to Agent WebSocket Server"}
        })
        
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
                        await websocket.send_json({
                            "type": "error",
                            "content": {"message": "A query is already being processed"}
                        })
                        continue
                        
                    # Process a query to the agent
                    user_input = content.get("text", "")
                    resume = content.get("resume", False)
                    
                    # Send acknowledgment
                    await websocket.send_json({
                        "type": "processing",
                        "content": {"message": "Processing your request..."}
                    })
                    
                    # Run the agent with the query in a separate task
                    task = asyncio.create_task(run_agent_async(websocket, user_input, resume))
                    active_tasks[websocket] = task
                
                elif msg_type == "workspace_info":
                    # Send information about the current workspace
                    if workspace_manager:
                        await websocket.send_json({
                            "type": "workspace_info",
                            "content": {"path": str(workspace_manager.root)}
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "content": {"message": "Workspace not initialized"}
                        })
                
                elif msg_type == "ping":
                    # Simple ping to keep connection alive
                    await websocket.send_json({
                        "type": "pong",
                        "content": {}
                    })
                
                elif msg_type == "cancel":
                    # Cancel the current agent task if one exists
                    if websocket in active_tasks and not active_tasks[websocket].done():
                        active_tasks[websocket].cancel()
                        await websocket.send_json({
                            "type": "system",
                            "content": {"message": "Query canceled"}
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "content": {"message": "No active query to cancel"}
                        })
                
                else:
                    # Unknown message type
                    await websocket.send_json({
                        "type": "error",
                        "content": {"message": f"Unknown message type: {msg_type}"}
                    })
            
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "content": {"message": "Invalid JSON format"}
                })
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                await websocket.send_json({
                    "type": "error",
                    "content": {"message": f"Error processing request: {str(e)}"}
                })
                
    except WebSocketDisconnect:
        # Handle disconnection
        active_connections.remove(websocket)
        # Cancel any running tasks
        if websocket in active_tasks and not active_tasks[websocket].done():
            active_tasks[websocket].cancel()
            del active_tasks[websocket]
        logger.info("Client disconnected")
    except Exception as e:
        # Handle other exceptions
        if websocket in active_connections:
            active_connections.remove(websocket)
        # Cancel any running tasks
        if websocket in active_tasks and not active_tasks[websocket].done():
            active_tasks[websocket].cancel()
            del active_tasks[websocket]
        logger.error(f"WebSocket error: {str(e)}")

@app.get("/")
async def redirect_to_frontend():
    """Redirect root to frontend index.html."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/frontend/index.html")

def initialize_agent(args):
    """Initialize the agent with command line arguments."""
    global agent, workspace_manager
    
    # Setup logging
    if os.path.exists(args.logs_path):
        os.remove(args.logs_path)
    logger_for_agent_logs = logging.getLogger("agent_logs")
    logger_for_agent_logs.setLevel(logging.DEBUG)
    logger_for_agent_logs.addHandler(logging.FileHandler(args.logs_path))
    if not args.minimize_stdout_logs:
        logger_for_agent_logs.addHandler(logging.StreamHandler())
    else:
        logger_for_agent_logs.propagate = False
    
    # Create console for agent
    from rich.console import Console
    console = Console()
    
    # Initialize LLM client
    client = get_client(
        "anthropic-direct",
        model_name="claude-3-7-sonnet@20250219",
        use_caching=False,
    )
    
    # Initialize workspace manager
    workspace_path = Path(args.workspace).resolve()
    workspace_manager = WorkspaceManager(
        root=workspace_path, container_workspace=args.use_container_workspace
    )
    
    # Initialize agent
    agent = Agent(
        client=client,
        workspace_manager=workspace_manager,
        console=console,
        logger_for_agent_logs=logger_for_agent_logs,
        max_output_tokens_per_turn=MAX_OUTPUT_TOKENS_PER_TURN,
        max_turns=MAX_TURNS,
        ask_user_permission=args.needs_permission,
        docker_container_id=args.docker_container_id,
    )
    
    return agent

def main():
    """Main entry point for the WebSocket server."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="WebSocket Server for interacting with the Agent")
    parser.add_argument(
        "--workspace",
        type=str,
        default="./workspace",
        help="Path to the workspace",
    )
    parser.add_argument(
        "--logs-path",
        type=str,
        default="agent_logs.txt",
        help="Path to save logs",
    )
    parser.add_argument(
        "--needs-permission",
        "-p",
        help="Ask for permission before executing commands",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--use-container-workspace",
        type=str,
        default=None,
        help="(Optional) Path to the container workspace to run commands in.",
    )
    parser.add_argument(
        "--docker-container-id",
        type=str,
        default=None,
        help="(Optional) Docker container ID to run commands in.",
    )
    parser.add_argument(
        "--minimize-stdout-logs",
        help="Minimize the amount of logs printed to stdout.",
        action="store_true",
        default=False,
    )
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
    
    # Initialize the agent
    initialize_agent(args)
    
    # Start the FastAPI server
    logger.info(f"Starting WebSocket server on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main() 