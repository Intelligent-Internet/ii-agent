"""Composio Auth Config Service - handles authentication configuration.

Refactored: DB access moved to repository; this service accepts an optional
existing_auth_config_id instead of querying the database directly.
"""

from typing import Optional, Dict
from pydantic import BaseModel

from .client import ComposioClient
from ii_agent.core.config.settings import get_settings
from ii_agent.core.logger import logger


class AuthConfig(BaseModel):
    """Authentication configuration model."""

    id: str
    auth_scheme: str
    is_composio_managed: bool = True
    toolkit_slug: str


class AuthConfigService:
    """Service for managing Composio authentication configurations."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key
        self._client: "Composio | None" = None

    @property
    def client(self) -> "Composio":
        if self._client is None:
            self._client = ComposioClient.get_client(self._api_key)
        return self._client

    def build_custom_auth_config(
        self, prefix_toolkit_slug_composio: str
    ) -> Optional[Dict[str, str]]:
        """Build custom auth config from environment variables."""
        client_id_key = f"{prefix_toolkit_slug_composio}_client_id"
        client_secret_key = f"{prefix_toolkit_slug_composio}_client_secret"

        settings = get_settings()
        client_id = settings.__dict__.get(client_id_key, None)
        client_secret = settings.__dict__.get(client_secret_key, None)

        if not client_id or not client_secret:
            logger.debug(
                f"Custom auth config not found for {prefix_toolkit_slug_composio} "
                f"(missing {client_id_key} or {client_secret_key})"
            )
            return None

        composio_callback_url = "https://backend.composio.dev/api/v3/toolkits/auth/callback"
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "oauth_redirect_uri": composio_callback_url,
        }

    async def create_auth_config(
        self,
        toolkit_slug: str,
        initiation_fields: Optional[Dict[str, str]] = None,
        custom_auth_config: Optional[Dict[str, str]] = None,
        use_custom_auth: bool = False,
        existing_auth_config_id: Optional[str] = None,
    ) -> AuthConfig:
        """Create authentication configuration for a toolkit.

        Args:
            toolkit_slug: Toolkit identifier (e.g., "gmail")
            initiation_fields: Optional initiation fields
            custom_auth_config: Optional custom authentication credentials
            use_custom_auth: Whether to use custom auth
            existing_auth_config_id: If provided, reuse this auth config instead of creating a new one
        """
        try:
            prefix_toolkit_slug_composio = f"{toolkit_slug}_composio"
            if toolkit_slug.startswith("google") or toolkit_slug == "gmail":
                prefix_toolkit_slug_composio = "google_composio"

            # Reuse existing auth config if provided
            if existing_auth_config_id:
                logger.info(
                    f"Returning existing auth config for {toolkit_slug}: {existing_auth_config_id}"
                )
                return AuthConfig(
                    id=existing_auth_config_id,
                    auth_scheme="OAUTH2",
                    is_composio_managed=not use_custom_auth,
                    toolkit_slug=toolkit_slug,
                )

            # Try to build custom auth config from environment if not provided
            if use_custom_auth and not custom_auth_config:
                custom_auth_config = self.build_custom_auth_config(prefix_toolkit_slug_composio)
                if custom_auth_config:
                    logger.debug(f"Using custom auth config from environment for {toolkit_slug}")

            logger.debug(f"Creating auth config for toolkit: {toolkit_slug}")

            if use_custom_auth and custom_auth_config:
                credentials = {
                    field_name: str(field_value)
                    for field_name, field_value in custom_auth_config.items()
                    if field_value
                }
                response = self.client.auth_configs.create(
                    toolkit_slug,
                    {
                        "type": "use_custom_auth",
                        "credentials": credentials,
                        "auth_scheme": "OAUTH2",
                    },
                )
            else:
                response = self.client.auth_configs.create(
                    toolkit_slug,
                    {
                        "type": "use_composio_managed_auth",
                        "tool_access_config": {"tools_for_connected_account_creation": []},
                    },
                )

            auth_config_obj = getattr(response, "auth_config", response)

            auth_config = AuthConfig(
                id=auth_config_obj.id,
                auth_scheme=auth_config_obj.auth_scheme,
                is_composio_managed=getattr(
                    auth_config_obj, "is_composio_managed", not use_custom_auth
                ),
                toolkit_slug=toolkit_slug,
            )

            logger.debug(f"Successfully created auth config: {auth_config.id}")
            return auth_config

        except Exception as e:
            logger.opt(exception=True).error(
                f"Failed to create auth config for {toolkit_slug}: {e}"
            )
            raise

    async def get_auth_config(self, auth_config_id: str) -> Optional[AuthConfig]:
        """Get authentication configuration by ID."""
        try:
            logger.debug(f"Fetching auth config: {auth_config_id}")
            response = self.client.auth_configs.get(auth_config_id)
            if not response:
                return None
            return AuthConfig(
                id=response.id,
                auth_scheme=response.auth_scheme,
                is_composio_managed=getattr(response, "is_composio_managed", True),
                toolkit_slug=getattr(response, "toolkit_slug", ""),
            )
        except Exception as e:
            logger.opt(exception=True).error(f"Failed to get auth config {auth_config_id}: {e}")
            raise

    async def delete_auth_config(self, auth_config_id: str) -> bool:
        """Delete authentication configuration by ID."""
        try:
            logger.debug(f"Deleting auth config: {auth_config_id}")
            self.client.auth_configs.delete(auth_config_id)
            logger.info(f"Successfully deleted auth config: {auth_config_id}")
            return True
        except Exception as e:
            logger.opt(exception=True).error(f"Failed to delete auth config {auth_config_id}: {e}")
            raise
