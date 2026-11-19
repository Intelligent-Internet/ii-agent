"""GitHub connector implementation using GitHub App installation tokens."""

import logging
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import get_settings
from ii_agent.integrations.connectors.models import Connector, ConnectorType

from .base import BaseConnector, ConnectorData

logger = logging.getLogger(__name__)

GITHUB_SCOPES = ["read:user", "user:email", "repo"]

# Installation tokens expire after 1 hour
INSTALLATION_TOKEN_EXPIRY_MINUTES = 60


class GitHubConnector(BaseConnector):
    """GitHub connector implementation using GitHub App.

    Handles OAuth flow for user authorization, then uses GitHub App
    installation tokens for API access. Installation tokens expire
    after 1 hour and can be refreshed using the App's private key.
    """

    def __init__(self, db_session: AsyncSession):
        """Initialize GitHub connector.

        Args:
            db_session: SQLAlchemy async session for database operations
        """
        super().__init__(db_session)

    @property
    def connector_type(self) -> ConnectorType:
        """Return GitHub connector type.

        Returns:
            ConnectorType: GITHUB enum value
        """
        return ConnectorType.GITHUB

    @property
    def scopes(self) -> list[str]:
        """Return required OAuth scopes for GitHub.

        Returns:
            list[str]: List of GitHub OAuth scopes
        """
        return GITHUB_SCOPES

    def _get_private_key(self) -> Optional[str]:
        """Get the GitHub App private key, handling newline escaping.

        Returns:
            Optional[str]: The private key in PEM format, or None if not configured
        """
        private_key = get_settings().oauth.github_app_private_key
        if not private_key:
            return None
        # Handle escaped newlines from environment variables
        return private_key.replace("\\n", "\n")

    def _generate_jwt(self) -> str:
        """Generate a JWT for GitHub App authentication.

        The JWT is used to authenticate as the GitHub App itself,
        which is required to generate installation access tokens.

        Returns:
            str: Signed JWT token

        Raises:
            ValueError: If GitHub App is not configured
        """
        settings = get_settings()
        if not settings.oauth.github_app_id:
            raise ValueError("GitHub App ID is not configured")

        private_key = self._get_private_key()
        if not private_key:
            raise ValueError("GitHub App private key is not configured")

        now = int(time.time())
        payload = {
            "iat": now - 60,  # Issued 60 seconds ago to account for clock drift
            "exp": now + (10 * 60),  # Expires in 10 minutes
            "iss": settings.oauth.github_app_id,
        }

        return jwt.encode(payload, private_key, algorithm="RS256")

    async def _get_installation_id_for_user(self, user_login: str) -> Optional[int]:
        """Get the installation ID for a user.

        Args:
            user_login: GitHub username

        Returns:
            Optional[int]: Installation ID or None if not found
        """
        try:
            app_jwt = self._generate_jwt()
            async with httpx.AsyncClient() as client:
                # List all installations for the app
                response = await client.get(
                    "https://api.github.com/app/installations",
                    headers={
                        "Authorization": f"Bearer {app_jwt}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
                response.raise_for_status()
                installations = response.json()

                # Find installation for this user
                for installation in installations:
                    account = installation.get("account", {})
                    if account.get("login", "").lower() == user_login.lower():
                        return installation["id"]

                return None
        except Exception as e:
            logger.error(f"Failed to get installation ID for user {user_login}: {e}")
            return None

    async def _generate_installation_token(
        self, installation_id: int, repository: Optional[str] = None
    ) -> ConnectorData:
        """Generate an installation access token.

        Args:
            installation_id: GitHub App installation ID
            repository: Optional repository name (owner/repo) to scope the token to

        Returns:
            ConnectorData: New access token with expiry

        Raises:
            Exception: If token generation fails
        """
        app_jwt = self._generate_jwt()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            token_data = response.json()

            access_token = token_data["token"]
            # Parse expiry from response (ISO 8601 format)
            expires_at_str = token_data.get("expires_at")
            if expires_at_str:
                token_expiry = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            else:
                # Default to 1 hour from now
                token_expiry = datetime.now(timezone.utc) + timedelta(
                    minutes=INSTALLATION_TOKEN_EXPIRY_MINUTES
                )

            return ConnectorData(
                access_token=access_token,
                refresh_token=None,  # Installation tokens don't use refresh tokens
                token_expiry=token_expiry,
                metadata=None,  # Will be set by caller
            )

    def _is_github_app_configured(self) -> bool:
        """Check if GitHub App is properly configured.

        Returns:
            bool: True if App ID and private key are configured
        """
        return bool(get_settings().oauth.github_app_id and self._get_private_key())

    async def get_auth_url(self, state: str, redirect_uri: Optional[str] = None) -> str:
        """Generate GitHub OAuth authorization URL.

        Args:
            state: Encrypted state parameter for CSRF protection
            redirect_uri: Optional redirect URI from client (for multi-domain support)

        Returns:
            str: OAuth authorization URL to redirect user to

        Raises:
            ValueError: If GitHub is not configured
        """
        settings = get_settings()
        if not settings.oauth.github_client_id or not settings.oauth.github_client_secret:
            raise ValueError("GitHub integration is not configured")

        # Use client-provided redirect_uri or fall back to config
        effective_redirect_uri = redirect_uri or settings.oauth.github_redirect_uri

        params = {
            "client_id": settings.oauth.github_client_id,
            "redirect_uri": effective_redirect_uri,
            "state": state,
            "scope": " ".join(self.scopes),
        }

        authorization_url = (
            f"https://github.com/login/oauth/authorize?{urllib.parse.urlencode(params)}"
        )

        logger.info("GitHub OAuth URL generated")
        return authorization_url

    async def handle_callback(
        self, code: str, state: str, redirect_uri: Optional[str] = None
    ) -> ConnectorData:
        """Handle OAuth callback and exchange code for tokens.

        If GitHub App is configured, this will also obtain an installation
        token for API access. Otherwise, falls back to user access token.

        Args:
            code: Authorization code from GitHub OAuth
            state: State parameter for validation
            redirect_uri: Optional redirect URI from client (must match the one used in get_auth_url)

        Returns:
            ConnectorData: Access token and user metadata

        Raises:
            Exception: If OAuth exchange or user info retrieval fails
        """
        # Use client-provided redirect_uri or fall back to config
        settings = get_settings()
        effective_redirect_uri = redirect_uri or settings.oauth.github_redirect_uri

        async with httpx.AsyncClient() as client:
            # Exchange code for user access token
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.oauth.github_client_id,
                    "client_secret": settings.oauth.github_client_secret,
                    "code": code,
                    "redirect_uri": effective_redirect_uri,
                },
            )
            token_response.raise_for_status()
            token_data = token_response.json()

            if "error" in token_data:
                logger.error(f"GitHub OAuth error: {token_data}")
                raise RuntimeError(
                    f"GitHub OAuth error: {token_data.get('error_description', 'Unknown error')}"
                )

            user_access_token = token_data.get("access_token")
            granted_scope = token_data.get("scope", "")
            logger.info(f"GitHub access token obtained. Granted scopes: {granted_scope}")

            if not user_access_token:
                raise ConnectionError("Failed to obtain access token from GitHub")

            # Get user info
            user_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {user_access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            user_response.raise_for_status()
            user_data = user_response.json()

            user_login = user_data.get("login")
            metadata = {
                "login": user_login,
                "name": user_data.get("name"),
                "email": user_data.get("email"),
                "avatar_url": user_data.get("avatar_url"),
                "scopes_granted": granted_scope.split(",") if granted_scope else [],
            }

            # Try to get installation token if GitHub App is configured
            if self._is_github_app_configured():
                installation_id = await self._get_installation_id_for_user(user_login)

                if installation_id:
                    logger.info(
                        f"Found GitHub App installation {installation_id} for user {user_login}"
                    )
                    metadata["installation_id"] = installation_id
                    metadata["app_type"] = "github_app_installation"

                    # Generate installation access token
                    try:
                        installation_data = await self._generate_installation_token(installation_id)
                        return ConnectorData(
                            access_token=installation_data.access_token,
                            refresh_token=None,
                            token_expiry=installation_data.token_expiry,
                            metadata=metadata,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to generate installation token, falling back to user token: {e}"
                        )
                else:
                    logger.warning(
                        f"No GitHub App installation found for user {user_login}. "
                        f"User needs to install the app: https://github.com/apps/{settings.oauth.github_app_name}"
                    )
                    metadata["app_type"] = "github_app_not_installed"
            else:
                metadata["app_type"] = "oauth_app"

            # Fallback to user access token (doesn't expire)
            return ConnectorData(
                access_token=user_access_token,
                refresh_token=None,
                token_expiry=None,
                metadata=metadata,
            )

    async def refresh_access_token(self, connector: Connector) -> ConnectorData:
        """Refresh the installation access token.

        For GitHub App installations, generates a new installation token
        using the App's JWT. For OAuth apps, returns the existing token
        since user access tokens don't expire.

        Args:
            connector: Database connector model

        Returns:
            ConnectorData: New or existing access token

        Raises:
            Exception: If token refresh fails
        """
        metadata = connector.connector_metadata or {}
        installation_id = metadata.get("installation_id")

        if installation_id and self._is_github_app_configured():
            logger.info(f"Refreshing installation token for installation {installation_id}")
            try:
                new_token_data = await self._generate_installation_token(installation_id)
                return ConnectorData(
                    access_token=new_token_data.access_token,
                    refresh_token=None,
                    token_expiry=new_token_data.token_expiry,
                    metadata=metadata,
                )
            except Exception as e:
                logger.error(f"Failed to refresh installation token: {e}")
                raise RuntimeError(
                    "Failed to refresh GitHub token. Please reconnect your GitHub account."
                )

        # For OAuth app tokens (no expiry), return existing token
        logger.debug("Using existing user access token (no refresh needed)")
        return ConnectorData(
            access_token=connector.access_token,
            refresh_token=None,
            token_expiry=None,
            metadata=metadata,
        )

    async def validate_token(self, access_token: str) -> bool:
        """Validate if GitHub access token is still valid.

        Args:
            access_token: The access token to validate

        Returns:
            bool: True if token is valid, False otherwise
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.github.com/user",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to validate GitHub token: {e}")
            return False

    async def revoke_access(self, connector: Connector) -> bool:
        """Revoke GitHub access token.

        Note: GitHub doesn't support programmatic token revocation for OAuth Apps.
        Users must revoke access manually through GitHub settings.

        Args:
            connector: Database connector model with token to revoke

        Returns:
            bool: Always returns True
        """
        logger.info(
            f"GitHub token revocation requested for connector {connector.id}. "
            "Users must manually revoke access through GitHub settings."
        )
        return True

    async def get_valid_token(self, user_id: str) -> Optional[str]:
        """Get a valid access token, refreshing if necessary.

        Overrides base class to handle GitHub App installation token refresh.

        Args:
            user_id: User ID to get token for

        Returns:
            Optional[str]: Valid access token or None if not connected
        """
        connector = await self.get_connector(user_id)
        if not connector:
            return None

        metadata = connector.connector_metadata or {}
        installation_id = metadata.get("installation_id")

        # For installation tokens, check expiry and refresh if needed
        if installation_id and self._is_github_app_configured():
            should_refresh = False

            if connector.token_expiry:
                expiry = connector.token_expiry
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)

                # Refresh if token expires within 5 minutes
                now = datetime.now(timezone.utc)
                if expiry <= now + timedelta(minutes=5):
                    should_refresh = True
                    logger.info(
                        f"Installation token expiring soon (expires: {expiry}), refreshing..."
                    )
            else:
                # No expiry set, should refresh to get a proper token
                should_refresh = True

            if should_refresh:
                try:
                    connector_data = await self.refresh_access_token(connector)
                    connector.access_token = connector_data.access_token
                    connector.token_expiry = connector_data.token_expiry
                    connector.updated_at = datetime.now(timezone.utc)
                    await self.db_session.commit()
                    await self.db_session.refresh(connector)
                    logger.info("Successfully refreshed installation token")
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}")
                    # Return existing token and let the API call fail if invalid
                    pass

        return connector.access_token

    async def get_repositories(self, user_id: str, per_page: int = 100) -> list[dict]:
        """Get list of repositories accessible to the user.

        Args:
            user_id: User ID to get repositories for
            per_page: Number of repositories per page (max 100)

        Returns:
            list[dict]: List of repository information

        Raises:
            Exception: If API call fails or token is invalid
        """
        access_token = await self.get_valid_token(user_id)
        if not access_token:
            raise RuntimeError("GitHub is not connected")

        async with httpx.AsyncClient() as client:
            repos_response = await client.get(
                "https://api.github.com/user/repos",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                params={
                    "sort": "updated",
                    "per_page": per_page,
                    "affiliation": "owner,collaborator,organization_member",
                },
            )

            if repos_response.status_code == 401:
                logger.error("GitHub token is invalid (401 Unauthorized)")
                raise RuntimeError(
                    "GitHub token is invalid or expired. Please reconnect your GitHub account."
                )

            repos_response.raise_for_status()
            return repos_response.json()

    async def get_app_config(self) -> dict:
        """Get GitHub App configuration.

        Returns:
            dict: GitHub App configuration with name and installation URL
        """
        app_name = get_settings().oauth.github_app_name or None

        if app_name:
            installation_url = f"https://github.com/apps/{app_name}/installations/select_target"
        else:
            installation_url = None

        return {
            "app_name": app_name,
            "installation_url": installation_url,
        }
