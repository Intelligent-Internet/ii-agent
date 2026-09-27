"""Composio MCP Server Service - manages MCP server creation and URL generation."""

import secrets
import string
from typing import Optional, List, Any
from pydantic import BaseModel

from composio_client.types.tool_router_create_session_params import ConfigToolkit

from .client import ComposioClient

from ii_agent.core.logger import logger

# Server name constraints
MAX_SERVER_NAME_LENGTH = 30
MIN_SERVER_NAME_LENGTH = 4
CUID_LENGTH = 8


class MCPCommands(BaseModel):
    """MCP server commands for different clients."""

    cursor: Optional[str] = None
    claude: Optional[str] = None
    windsurf: Optional[str] = None


class MCPServer(BaseModel):
    """MCP server model."""

    id: str
    name: str
    auth_config_ids: List[str] = []
    allowed_tools: List[str] = []
    mcp_url: Optional[str] = None
    toolkits: List[str] = []
    commands: MCPCommands
    updated_at: Optional[str] = None
    created_at: Optional[str] = None
    managed_auth_via_composio: bool = True


class MCPUrlResponse(BaseModel):
    """MCP URL generation response."""

    mcp_url: str
    connected_account_urls: List[str] = []
    user_ids_url: List[str] = []


def _extract_mcp_commands(commands_obj: Any) -> MCPCommands:
    """Extract MCPCommands from Composio response object."""
    if not commands_obj:
        return MCPCommands()
    return MCPCommands(
        cursor=getattr(commands_obj, "cursor", None),
        claude=getattr(commands_obj, "claude", None),
        windsurf=getattr(commands_obj, "windsurf", None),
    )


class MCPServerService:
    """Service for managing Composio MCP servers."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the MCP server service."""
        self._api_key = api_key
        self._client: "Composio | None" = None

    @property
    def client(self) -> "Composio":
        if self._client is None:
            self._client = ComposioClient.get_client(self._api_key)
        return self._client

    def _generate_cuid(self) -> str:
        """Generate a random CUID-like string."""
        chars = string.ascii_lowercase + string.digits
        return "".join(secrets.choice(chars) for _ in range(CUID_LENGTH))

    def _generate_server_name(self, toolkit_name: str) -> str:
        """Generate a valid MCP server name (max 30 chars, alphanumeric + hyphens)."""
        # Clean the toolkit name: lowercase alphanumeric with hyphens
        clean_name = "".join(c.lower() if c.isalnum() else "-" for c in toolkit_name)
        clean_name = clean_name.strip("-")

        cuid = self._generate_cuid()

        # Calculate max length for app name portion
        max_name_length = MAX_SERVER_NAME_LENGTH - CUID_LENGTH - 1
        if len(clean_name) > max_name_length:
            clean_name = clean_name[:max_name_length]

        server_name = f"{clean_name}-{cuid}" if clean_name else f"app-{cuid}"

        # Ensure minimum length
        if len(server_name) < MIN_SERVER_NAME_LENGTH:
            server_name = f"app-{cuid}"

        return server_name

    def _response_to_mcp_server(self, response: Any) -> MCPServer:
        """Convert Composio API response to MCPServer model."""
        return MCPServer(
            id=response.id,
            name=response.name,
            auth_config_ids=getattr(response, "auth_config_ids", []),
            allowed_tools=getattr(response, "allowed_tools", []),
            mcp_url=getattr(response, "mcp_url", None),
            toolkits=getattr(response, "toolkits", []),
            commands=_extract_mcp_commands(getattr(response, "commands", None)),
            updated_at=getattr(response, "updated_at", None),
            created_at=getattr(response, "created_at", None),
            managed_auth_via_composio=getattr(response, "managed_auth_via_composio", True),
        )

    def _call_mcp_create(
        self,
        toolkits: List[ConfigToolkit],
        name: str,
        allowed_tools: Optional[List[str]],
    ):
        """Call MCP create API using new SDK signature."""
        return self.client.mcp.create(
            name=name,
            toolkits=toolkits,
            allowed_tools=allowed_tools or None,
        )

    def _call_generate_mcp_url(self, mcp_server_id: str, user_id: str):
        """Generate a user-scoped MCP URL using new SDK signature."""
        return self.client.mcp.generate(user_id=user_id, mcp_config_id=mcp_server_id)

    def _call_mcp_get(self, mcp_server_id: str):
        """Retrieve MCP server details."""
        return self.client.mcp.get(mcp_server_id)

    def _call_mcp_update(
        self,
        mcp_server_id: str,
        toolkits: List[ConfigToolkit],
        allowed_tools: Optional[List[str]] = None,
    ):
        """Update MCP server with new toolkits."""
        return self.client.mcp.update(
            server_id=mcp_server_id,
            toolkits=toolkits,
            allowed_tools=allowed_tools or None,
        )

    async def create_mcp_server(
        self,
        auth_config_ids: List[str],
        name: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        toolkit_name: str = "composio",
        toolkit_slug: Optional[str] = None,
        composio_user_id: Optional[str] = None,
    ) -> MCPServer:
        """Create an MCP server for toolkit access.

        Args:
            auth_config_ids: List of auth configuration IDs
            name: Optional server name (auto-generated if not provided)
            allowed_tools: Optional list of allowed tools (empty = all tools)
            toolkit_name: Toolkit name for auto-generating server name
            toolkit_slug: Toolkit slug (if different from display name)

        Returns:
            MCPServer with server ID and configuration
        """
        server_name = name or self._generate_server_name(toolkit_name)
        logger.debug(f"Creating MCP server '{server_name}' with auth_configs: {auth_config_ids}")

        toolkit_id = toolkit_slug or toolkit_name
        toolkits = [ConfigToolkit(toolkit=toolkit_id)]
        if auth_config_ids:
            toolkits[0]["auth_config"] = auth_config_ids[0]

        response = self._call_mcp_create(toolkits, server_name, allowed_tools)
        # mcp_url_response = await self.generate_mcp_url(
        #         mcp_server_id=response.id,
        #         # connected_account_ids=[connected_account.id],
        #         composio_user_id=composio_user_id
        #     )

        instance_mcp_url = response.generate(composio_user_id)
        mcp_url_response = instance_mcp_url["url"]

        server = self._response_to_mcp_server(response)

        logger.debug(f"Successfully created MCP server: {server.id}")
        return server, mcp_url_response

    async def generate_mcp_url(
        self,
        mcp_server_id: str,
        connected_account_ids: Optional[List[str]] = None,
        composio_user_id: Optional[str] = None,
    ) -> MCPUrlResponse:
        """Generate MCP URL for accessing the server.

        Args:
            mcp_server_id: MCP server identifier
            connected_account_ids: Optional list of connected account IDs
            composio_user_id: Optional list of user IDs

        Returns:
            MCPUrlResponse with generated MCP URL
        """
        logger.debug(f"Generating MCP URL for server: {mcp_server_id}")

        if not composio_user_id:
            raise ValueError("user_id is required to generate MCP URL with the new SDK")

        response = self._call_generate_mcp_url(mcp_server_id, composio_user_id)

        logger.debug("Successfully generated MCP URL")
        return MCPUrlResponse(
            mcp_url=response["url"],
            connected_account_urls=[],
            user_ids_url=[response["url"]],
        )

    async def get_mcp_server(self, mcp_server_id: str) -> Optional[MCPServer]:
        """Get an MCP server by ID.

        Args:
            mcp_server_id: MCP server identifier

        Returns:
            MCPServer or None if not found
        """
        logger.debug(f"Fetching MCP server: {mcp_server_id}")

        response = self._call_mcp_get(mcp_server_id)
        if not response:
            return None

        return self._response_to_mcp_server(response)

    async def update_mcp_server(
        self,
        mcp_server_id: str,
        auth_config_ids: List[str],
        toolkit_slug: str,
        allowed_tools: Optional[List[str]] = None,
    ) -> MCPServer:
        """Update an existing MCP server by adding new toolkits.

        Args:
            mcp_server_id: MCP server identifier
            auth_config_ids: List of auth configuration IDs to add
            toolkit_slug: Toolkit slug to add
            allowed_tools: Optional list of allowed tools

        Returns:
            Updated MCPServer
        """
        logger.debug(f"Updating MCP server {mcp_server_id} with toolkit: {toolkit_slug}")

        # Get existing server to retrieve current toolkits
        existing_server = await self.get_mcp_server(mcp_server_id)
        if not existing_server:
            raise ValueError(f"MCP server {mcp_server_id} not found")

        # Build new toolkit config
        new_toolkit = ConfigToolkit(toolkit=toolkit_slug)
        if auth_config_ids:
            new_toolkit["auth_config"] = auth_config_ids[0]

        # Combine existing and new toolkits
        existing_toolkits = []
        for tk_slug in existing_server.toolkits:
            # Find corresponding auth_config from existing auth_config_ids
            existing_toolkit = ConfigToolkit(toolkit=tk_slug)
            existing_toolkits.append(existing_toolkit)

        # Add new toolkit if not already present
        if toolkit_slug not in existing_server.toolkits:
            existing_toolkits.append(new_toolkit)
            logger.debug(f"Adding new toolkit {toolkit_slug} to MCP server")
        else:
            # Update existing toolkit with new auth_config
            for tk in existing_toolkits:
                if tk.get("toolkit") == toolkit_slug and auth_config_ids:
                    tk["auth_config"] = auth_config_ids[0]
            logger.debug(f"Updating existing toolkit {toolkit_slug} in MCP server")

        response = self._call_mcp_update(mcp_server_id, existing_toolkits, allowed_tools)
        server = self._response_to_mcp_server(response)

        logger.debug(f"Successfully updated MCP server: {server.id}")
        return server
