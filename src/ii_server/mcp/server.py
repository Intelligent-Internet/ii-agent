from __future__ import annotations

import asyncio
import json
import os
import subprocess
from argparse import ArgumentParser
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.proxy import ProxyClient
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse

from ii_server.tools.manager import get_sandbox_tools

load_dotenv()

_codex_process: Optional[subprocess.Popen[str]] = None
_codex_url = os.getenv("CODEX_SSE_URL", "http://0.0.0.0:1324")


def get_codex_process() -> Optional[subprocess.Popen[str]]:
    return _codex_process


def set_codex_process(process: subprocess.Popen[str]) -> None:
    global _codex_process
    _codex_process = process


def get_codex_url() -> str:
    return _codex_url


async def create_mcp(
    workspace_dir: str,
    custom_mcp_config: Dict[str, Any] | None = None,
) -> FastMCP:
    main_server = FastMCP()
    tools_registered = False

    async def register_tools() -> bool:
        nonlocal tools_registered
        if tools_registered:
            return True

        tools = get_sandbox_tools(workspace_path=workspace_dir)
        for tool in tools:
            main_server.tool(
                tool.execute_mcp_wrapper,
                name=tool.name,
                description=tool.description,
                annotations=ToolAnnotations(
                    title=tool.display_name,
                    readOnlyHint=tool.read_only,
                ),
            )

            mcp_tool = await main_server._tool_manager.get_tool(tool.name)
            mcp_tool.parameters = tool.input_schema

        tools_registered = True
        return True

    @main_server.custom_route("/health", methods=["GET"])
    async def health(request):
        return JSONResponse({"status": "ok"}, status_code=200)

    @main_server.custom_route("/custom-mcp", methods=["POST"])
    async def add_mcp_config(request):
        config = await request.json()
        if not config:
            return JSONResponse({"error": "Invalid request"}, status_code=400)

        # Require API key authentication for MCP config registration
        api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        expected_key = os.getenv("MCP_API_KEY")
        if not expected_key or api_key != expected_key:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        mcp_servers = config.get("mcpServers", {})
        for server_name, server_conf in mcp_servers.items():
            single_config = {"mcpServers": {server_name: server_conf}}
            proxy = FastMCP.as_proxy(ProxyClient(single_config))
            main_server.mount(proxy, prefix=f"mcp_{server_name}")
        return JSONResponse({"status": "success"}, status_code=200)

    @main_server.custom_route("/register-codex", methods=["POST"])
    async def register_codex(request):
        if get_codex_process() is not None:
            process = get_codex_process()
            if process and process.poll() is None:
                return JSONResponse(
                    {"status": "already_running", "url": get_codex_url()},
                    status_code=200,
                )

        try:
            process = subprocess.Popen(
                ["sse-http-server", "--addr", get_codex_url().replace("http://", "")],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            set_codex_process(process)

            if process.poll() is not None:
                stdout, stderr = process.communicate()
                return JSONResponse(
                    {
                        "status": "error",
                        "message": f"Codex server failed to start: {stderr or stdout}",
                    },
                    status_code=500,
                )

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{get_codex_url()}/health",
                        timeout=5.0,
                    )
                    response.raise_for_status()
            except Exception:
                pass

            return JSONResponse(
                {"status": "success", "url": get_codex_url()},
                status_code=200,
            )
        except FileNotFoundError:
            return JSONResponse(
                {
                    "status": "error",
                    "message": (
                        "sse-http-server executable not found. "
                        "Make sure it's installed and in PATH."
                    ),
                },
                status_code=500,
            )
        except Exception as exc:
            return JSONResponse(
                {
                    "status": "error",
                    "message": f"Failed to start Codex server: {exc}",
                },
                status_code=500,
            )

    if custom_mcp_config:
        mcp_servers = custom_mcp_config.get("mcpServers", {})
        for server_name, server_conf in mcp_servers.items():
            single_config = {"mcpServers": {server_name: server_conf}}
            proxy = FastMCP.as_proxy(ProxyClient(single_config))
            main_server.mount(proxy, prefix=f"mcp_{server_name}")

    await register_tools()
    return main_server


async def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--workspace_dir", type=str, default=None)
    parser.add_argument("--custom_mcp_config", type=str, default=None)
    parser.add_argument("--port", type=int, default=6060)

    args = parser.parse_args()

    workspace_dir = os.getenv("WORKSPACE_DIR")
    if args.workspace_dir:
        workspace_dir = args.workspace_dir

    if not workspace_dir:
        raise ValueError(
            "workspace_dir is not set. Please set the WORKSPACE_DIR environment "
            "variable or pass it as an argument --workspace_dir"
        )

    os.makedirs(workspace_dir, exist_ok=True)

    custom_mcp_config = None
    if args.custom_mcp_config:
        with open(args.custom_mcp_config, "r", encoding="utf-8") as file_obj:
            custom_mcp_config = json.load(file_obj)

    mcp = await create_mcp(
        workspace_dir=workspace_dir,
        custom_mcp_config=custom_mcp_config,
    )
    await mcp.run_async(transport="http", host="0.0.0.0", port=args.port)


def cli() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    cli()
