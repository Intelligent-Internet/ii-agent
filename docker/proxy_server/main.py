from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, Response
import aiohttp
import datetime
from typing import Dict, Any
import websockets
from logging import getLogger
import os
from collections import defaultdict
from fastapi.middleware.cors import CORSMiddleware
import asyncio

logger = getLogger(__name__)

app = FastAPI(title="Agent Proxy API")
# Dictionary to store registered services: {container_name: {service_name: {"port": service_port, "registered_at": registered_at}}}
registered_services: Dict[str, Dict[str, Any]] = defaultdict(lambda: defaultdict(dict))

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or specify your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAIN_APP_HOST = os.environ.get("MAIN_APP_HOST", "localhost")
MAIN_APP_PORT = os.environ.get("MAIN_APP_PORT", "9000")


@app.get("/api/ping")
async def ping():
    """Simple health check endpoint to test API availability.

    Returns:
        A simple JSON response indicating the API is up
    """
    return {"status": "ok", "message": "pong"}


@app.post("/api/register")
async def register_service(request: Request):
    """Register an external service with the WebSocket server.

    External services can register their name, container name, and port for later discovery
    and communication.

    Args:
        request: The request containing the service details

    Returns:
        JSON response confirming registration
    """
    try:
        data = await request.json()
        port = data.get("port")
        container_name = data.get("container_name")

        # Validate required fields
        if not port:
            return JSONResponse(status_code=400, content={"error": "Port is required"})

        if not container_name:
            return JSONResponse(
                status_code=400, content={"error": "Container name is required"}
            )

        new_service = {
            "registered_at": datetime.datetime.now().isoformat(),
        }

        # Register a service within a container
        registered_services[container_name][port] = new_service

        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "message": f"Service of container '{container_name}' running on port '{port}'",
                "service": registered_services[container_name][port],
            },
        )

    except Exception as e:
        logger.error(f"Error registering service: {str(e)}")
        return JSONResponse(
            status_code=500, content={"error": f"Failed to register service: {str(e)}"}
        )


@app.websocket("/{service_path:path}")
async def websocket_proxy(websocket: WebSocket, service_path: str):
    """Proxy WebSocket connections to agent containers within the Docker network.

    Args:
        websocket: The incoming WebSocket connection to proxy
        service_path: The path to the WebSocket service within the container
    """
    print("HERE")
    logger.info("HERE")
    await websocket.accept()

    try:
        # Extract container name and port from host header (same logic as HTTP proxy)
        host = websocket.headers.get("host", "")
        if not host:
            await websocket.close(code=1002, reason="Missing host header")
            return

        # Extract subdomain part (everything before first dot)
        container_name_port = host.split(".")[0].split("-")
        container_name = "-".join(container_name_port[:-1])
        port = container_name_port[-1]

        # Construct target WebSocket URL within Docker network
        # The service_path already contains the correct path (e.g., "ws")
        target_ws_url = f"ws://{container_name}:{port}/{service_path}"
        print(f"target_ws_url: {target_ws_url}")

        # Add query parameters if they exist in the original request
        query_string = websocket.url.query
        if query_string:
            target_ws_url += f"?{query_string}"

        logger.info(f"Proxying WebSocket to {target_ws_url}")

        # Connect to the target WebSocket
        async with websockets.connect(target_ws_url) as target_ws:
            logger.info(f"Connected to target WebSocket: {target_ws_url}")

            # Create tasks for bidirectional message forwarding
            async def forward_to_target():
                try:
                    while True:
                        message = await websocket.receive_text()
                        await target_ws.send(message)
                        logger.info(f"Forwarded message to target: {message}")
                except Exception as e:
                    logger.error(f"Error forwarding to target: {e}")

            async def forward_to_client():
                try:
                    async for message in target_ws:
                        await websocket.send_text(message)
                        logger.info(f"Forwarded message to client: {message}")
                except Exception as e:
                    logger.error(f"Error forwarding to client: {e}")

            # Run both forwarding tasks concurrently
            await asyncio.gather(
                forward_to_target(), forward_to_client(), return_exceptions=True
            )

    except websockets.exceptions.ConnectionClosed:
        print("Target WebSocket connection closed")
    except Exception as e:
        error_message = str(e)
        print(f"Error in WebSocket proxy: {error_message}")

        # More specific error handling
        if (
            "not found" in error_message.lower()
            or "name resolution" in error_message.lower()
        ):
            print("DNS resolution failed - container name may not be resolvable")
        elif "refused" in error_message.lower():
            print(
                "Connection refused - WebSocket service may not be running on expected port"
            )

        try:
            await websocket.close(code=1011, reason=f"Proxy error: {error_message}")
        except:
            pass  # Connection might already be closed


@app.get("/api/debug-headers")
async def debug_headers(request: Request):
    """Debug endpoint to view incoming headers for troubleshooting"""
    headers = dict(request.headers)
    return {"headers": headers}


def is_websocket_upgrade_request(request: Request) -> bool:
    """Check if the request is a WebSocket upgrade request"""
    connection = request.headers.get("connection", "").lower()
    upgrade = request.headers.get("upgrade", "").lower()
    return "upgrade" in connection and upgrade == "websocket"


async def handle_websocket_upgrade(service_path: str, request: Request):
    """Handle WebSocket upgrade requests for Socket.IO compatibility"""
    try:
        # Extract container info from host header
        host = request.headers.get("host", "")
        if not host:
            return JSONResponse(status_code=400, content={"error": "Missing host header"})

        container_name_port = host.split(".")[0].split("-")
        container_name = "-".join(container_name_port[:-1])
        port = container_name_port[-1]

        # Construct target URL
        target_url = f"http://{container_name}:{port}/{service_path}"
        
        # Add query parameters if they exist
        if request.url.query:
            target_url += f"?{request.url.query}"

        logger.info(f"Handling WebSocket upgrade to {target_url}")

        # Forward the upgrade request with all headers
        headers = dict(request.headers)
        body = await request.body()

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=body,
                timeout=60.0,
            ) as response:
                # For upgrade requests, we need to return the response as-is
                content = await response.read()
                status = response.status

                # Preserve all headers for upgrade response
                response_headers = dict(response.headers)
                
                logger.info(f"WebSocket upgrade response status: {status}")
                logger.info(f"WebSocket upgrade response headers: {response_headers}")

                return Response(
                    content=content,
                    status_code=status,
                    headers=response_headers,
                )

    except Exception as e:
        logger.error(f"Error handling WebSocket upgrade: {str(e)}")
        return JSONResponse(
            status_code=502,
            content={"error": f"Failed to upgrade WebSocket connection: {str(e)}"}
        )


@app.api_route("/{service_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(service_path: str, request: Request):
    """Proxy requests to agent containers within the Docker network.
    
    Now handles both regular HTTP requests and WebSocket upgrade requests.

    Args:
        request: The incoming request to proxy
        service_path: The path to the service within the container

    Returns:
        The response from the target service
    """
    # Check if this is a WebSocket upgrade request (for Socket.IO)
    if is_websocket_upgrade_request(request):
        return await handle_websocket_upgrade(service_path, request)
    
    # Regular HTTP request handling
    container_port = request.headers.get("x-subdomain", "unknown_unknown")
    port = container_port.split("-")[-1]
    container_name = "-".join(container_port.split("-")[:-1])
    host = request.headers.get("host", "")
    if host:
        # Extract subdomain part (everything before first dot)
        container_name_port = host.split(".")[0].split("-")
        container_name = "-".join(container_name_port[:-1])
        port = container_name_port[-1]

    # Construct target URL within Docker network
    target_url = f"http://{container_name}:{port}/{service_path}"
    logger.info(f"Proxying request to {target_url}")

    try:
        # Convert headers from starlette to dict for aiohttp
        headers = dict(request.headers)
        body = await request.body()

        logger.info(f"Headers being forwarded: {headers}")

        async with aiohttp.ClientSession() as session:
            method = getattr(session, request.method.lower())

            async with method(
                url=target_url,
                headers=headers,
                data=body,
                timeout=60.0,
            ) as response:
                content = await response.read()
                status = response.status

                # Filter out problematic headers including content-encoding if there are issues
                response_headers = {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower()
                    not in ("transfer-encoding", "content-length", "content-encoding")
                }

                logger.info(f"Received response with status {status}")
                logger.info(content)
                logger.info(response.headers)

                return Response(
                    content=content,
                    status_code=status,
                    headers=response_headers,
                    media_type=response.headers.get(
                        "Content-Type", "application/octet-stream"
                    ),
                )
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error proxying request to {target_url}: {error_message}")

        # More specific error handling
        if (
            "not found" in error_message.lower()
            or "name resolution" in error_message.lower()
        ):
            logger.error("DNS resolution failed - container name may not be resolvable")
        elif "refused" in error_message.lower():
            logger.error(
                "Connection refused - service may not be running on expected port"
            )

        return JSONResponse(
            status_code=502,
            content={"error": f"Failed to connect to agent service: {error_message}"},
        )