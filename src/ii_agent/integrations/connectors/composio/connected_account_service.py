"""Composio Connected Account Service - manages user connections."""

from typing import Optional, Dict, Any
from pydantic import BaseModel

from .client import ComposioClient

from ii_agent.core.logger import logger


def _to_dict(obj: Any) -> Dict[str, Any]:
    """Convert various object types to dictionary."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return {}


class ConnectionState(BaseModel):
    """Connection state model."""

    auth_scheme: str = "OAUTH2"
    val: Dict[str, Any] = {}


class ConnectedAccount(BaseModel):
    """Connected account model."""

    id: str
    status: str
    redirect_url: Optional[str] = None
    redirect_uri: Optional[str] = None
    connection_data: ConnectionState
    auth_config_id: str
    user_id: str


class ConnectedAccountService:
    """Service for managing Composio connected accounts."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the connected account service."""
        self._api_key = api_key
        self._client: "Composio | None" = None

    @property
    def client(self) -> "Composio":
        if self._client is None:
            self._client = ComposioClient.get_client(self._api_key)
        return self._client

    def _extract_connection_state(self, response: Any) -> ConnectionState:
        """Extract ConnectionState from Composio response."""
        # Try 'state' first (new API), then fall back to 'connection_data' or 'connectionData'
        state_obj = (
            getattr(response, "state", None)
            or getattr(response, "connection_data", None)
            or getattr(response, "connectionData", None)
        )

        if not state_obj:
            return ConnectionState()

        data = _to_dict(state_obj)
        val = _to_dict(data.get("val", {}))

        return ConnectionState(auth_scheme=data.get("auth_scheme", "OAUTH2"), val=val)

    def _build_state_val(
        self, initiation_fields: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Build state value dict from initiation fields."""
        state_val = {"status": "INITIALIZING"}

        if initiation_fields:
            for field_name, field_value in initiation_fields.items():
                if field_value:
                    # Handle special field name mapping
                    key = "extension" if field_name == "suffix.one" else field_name
                    state_val[key] = str(field_value)

        return state_val

    async def create_connected_account(
        self,
        auth_config_id: str,
        user_id: str,
        initiation_fields: Optional[Dict[str, str]] = None,
        callback_url: Optional[str] = None,
    ) -> ConnectedAccount:
        """Create a connected account for a user.

        Args:
            auth_config_id: Auth configuration ID
            user_id: Composio user ID
            initiation_fields: Optional initiation fields
            callback_url: OAuth callback URL

        Returns:
            ConnectedAccount with redirect URL for OAuth
        """
        logger.debug(f"Creating connected account for user: {user_id}")

        # Build config based on initiation fields
        config = {"auth_scheme": "OAUTH2"}
        if initiation_fields:
            config["val"] = self._build_state_val(initiation_fields)

        connection_request = self.client.connected_accounts.initiate(
            user_id=user_id,
            auth_config_id=auth_config_id,
            callback_url=callback_url,
            config=config,
            allow_multiple=True,
        )

        account = ConnectedAccount(
            id=connection_request.id,
            status=connection_request.status,
            redirect_url=getattr(connection_request, "redirect_url", None),
            redirect_uri=getattr(connection_request, "redirect_url", None),
            connection_data=ConnectionState(
                auth_scheme="OAUTH2",
                val=self._build_state_val(initiation_fields),
            ),
            auth_config_id=auth_config_id,
            user_id=user_id,
        )

        logger.debug(f"Successfully created connected account: {account.id}")
        return account

    async def get_connected_account(self, connected_account_id: str) -> Optional[ConnectedAccount]:
        """Get a connected account by ID.

        Args:
            connected_account_id: Connected account identifier

        Returns:
            ConnectedAccount or None if not found
        """
        logger.debug(f"Fetching connected account: {connected_account_id}")

        response = self.client.connected_accounts.get(connected_account_id)
        if not response:
            return None

        return ConnectedAccount(
            id=response.id,
            status=response.status,
            redirect_url=getattr(response, "redirect_url", None),
            redirect_uri=getattr(response, "redirect_uri", None),
            connection_data=self._extract_connection_state(response),
            auth_config_id=getattr(response, "auth_config_id", ""),
            user_id=getattr(response, "user_id", ""),
        )

    async def get_auth_status(self, connected_account_id: str) -> Dict[str, Any]:
        """Get authentication status for a connected account.

        Args:
            connected_account_id: Connected account identifier

        Returns:
            Dict with status and connection data
        """
        logger.debug(f"Getting auth status for connected account: {connected_account_id}")

        account = await self.get_connected_account(connected_account_id)
        if not account:
            return {"status": "not_found", "message": "Connected account not found"}

        return {
            "status": account.status,
            "redirect_url": account.redirect_url,
            "connection_data": account.connection_data.model_dump(),
        }

    async def delete_connected_account(self, connected_account_id: str) -> bool:
        """Delete a connected account from Composio.

        Args:
            connected_account_id: Connected account identifier

        Returns:
            True if deleted successfully
        """
        logger.debug(f"Deleting connected account: {connected_account_id}")

        try:
            self.client.connected_accounts.delete(connected_account_id)
            logger.info(f"Successfully deleted connected account: {connected_account_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete connected account {connected_account_id}: {e}")
            raise

    async def enable_connected_account(self, connected_account_id: str) -> Dict[str, Any]:
        """Enable a connected account (set status to ACTIVE).

        Args:
            connected_account_id: Connected account identifier

        Returns:
            Dict with success status and message
        """
        logger.debug(f"Enabling connected account: {connected_account_id}")

        try:
            result = self.client.connected_accounts.enable(connected_account_id)
            logger.info(f"Successfully enabled connected account: {connected_account_id}")
            return {"success": True, "message": "Account enabled successfully"}
        except Exception as e:
            logger.error(f"Failed to enable connected account {connected_account_id}: {e}")
            raise

    async def disable_connected_account(self, connected_account_id: str) -> Dict[str, Any]:
        """Disable a connected account (set status to INACTIVE).

        Args:
            connected_account_id: Connected account identifier

        Returns:
            Dict with success status and message
        """
        logger.debug(f"Disabling connected account: {connected_account_id}")

        try:
            result = self.client.connected_accounts.disable(connected_account_id)
            logger.info(f"Successfully disabled connected account: {connected_account_id}")
            return {"success": True, "message": "Account disabled successfully"}
        except Exception as e:
            logger.error(f"Failed to disable connected account {connected_account_id}: {e}")
            raise
