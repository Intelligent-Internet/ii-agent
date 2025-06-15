from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
import aiohttp
import datetime
from typing import Dict, Any
from logging import getLogger
import os
from collections import defaultdict
from fastapi.middleware.cors import CORSMiddleware

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


@app.api_route("/api/proxy/static/{static_path:path}", methods=["GET"])
async def proxy_static(static_path: str, request: Request):
    """Proxy requests for static files to the appropriate container.

    Args:
        static_path: The path to the static file
        request: The incoming request

    Returns:
        The proxied response from the static file server
    """
    container_port = request.headers.get("x-subdomain", "unknown_unknown")
    port = container_port.split("-")[-1]
    container_name = "-".join(container_port.split("-")[:-1])

    # Construct target URL for static file
    target_url = f"http://{container_name}:{port}/static/{static_path}"
    print(f"Proxying static file request to {target_url}")

    try:
        # Convert headers from starlette to dict for aiohttp
        headers = dict(request.headers)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url=target_url,
                headers=headers,
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

                print(f"Received response with status {status}")

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
        print(f"Error proxying static file request to {target_url}: {error_message}")

        return JSONResponse(
            status_code=502,
            content={"error": f"Failed to fetch static file: {error_message}"},
        )


@app.api_route(
    "/api/proxy/{service_path:path}", methods=["GET", "POST", "PUT", "DELETE"]
)
async def proxy(service_path: str, request: Request):
    """Proxy requests to agent containers within the Docker network.

    Args:
        request: The incoming request to proxy
        service_path: The path to the service within the container

    Returns:
        The response from the target service
    """
    container_port = request.headers.get("x-subdomain", "unknown_unknown")
    port = container_port.split("-")[-1]
    container_name = "-".join(container_port.split("-")[:-1])

    # Construct target URL within Docker network
    target_url = f"http://{container_name}:{port}/{service_path}"
    print(f"Proxying request to {target_url}")

    try:
        # Convert headers from starlette to dict for aiohttp
        headers = dict(request.headers)
        body = await request.body()

        print(f"Headers being forwarded: {headers}")

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

                print(f"Received response with status {status}")
                print(content)
                print(response.headers)

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
        print(f"Error proxying request to {target_url}: {error_message}")

        # More specific error handling
        if (
            "not found" in error_message.lower()
            or "name resolution" in error_message.lower()
        ):
            print("DNS resolution failed - container name may not be resolvable")
        elif "refused" in error_message.lower():
            print("Connection refused - service may not be running on expected port")

        return JSONResponse(
            status_code=502,
            content={"error": f"Failed to connect to agent service: {error_message}"},
        )


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


@app.get("/api/debug-headers")
async def debug_headers(request: Request):
    """Debug endpoint to view incoming headers for troubleshooting"""
    headers = dict(request.headers)
    return {"headers": headers}
