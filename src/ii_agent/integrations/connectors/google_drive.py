"""Google Drive connector implementation."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests as http_requests
from google.auth import _helpers
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import get_settings
from ii_agent.integrations.connectors.models import Connector, ConnectorType

from .base import BaseConnector, ConnectorData

logger = logging.getLogger(__name__)

GOOGLE_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]


class GoogleDriveConnector(BaseConnector):
    """Google Drive connector implementation.

    Handles OAuth flow, token management, and Google Drive API operations
    for file access and synchronization.
    """

    def __init__(self, db_session: AsyncSession):
        """Initialize Google Drive connector.

        Args:
            db_session: SQLAlchemy async session for database operations
        """
        super().__init__(db_session)

    @property
    def connector_type(self) -> ConnectorType:
        """Return Google Drive connector type.

        Returns:
            ConnectorType: GOOGLE_DRIVE enum value
        """
        return ConnectorType.GOOGLE_DRIVE

    @property
    def scopes(self) -> list[str]:
        """Return required OAuth scopes for Google Drive.

        Returns:
            list[str]: List of Google OAuth scopes
        """
        return GOOGLE_DRIVE_SCOPES

    def _create_flow(self) -> Flow:
        """Create OAuth flow for Google Drive.

        Returns:
            Flow: Configured OAuth flow instance
        """
        settings = get_settings()
        return Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.oauth.google_client_id,
                    "client_secret": settings.oauth.google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.oauth.google_redirect_uri],
                }
            },
            scopes=self.scopes,
            redirect_uri=settings.oauth.google_redirect_uri,
        )

    async def get_auth_url(self, state: str) -> str:
        """Generate Google Drive OAuth authorization URL.

        Args:
            state: Encrypted state parameter for CSRF protection

        Returns:
            str: OAuth authorization URL to redirect user to

        Raises:
            ValueError: If Google Drive is not configured
        """
        settings = get_settings()
        if not settings.oauth.google_client_id or not settings.oauth.google_client_secret:
            raise ValueError("Google Drive integration is not configured")

        flow = self._create_flow()
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            state=state,
            prompt="consent",
        )

        return authorization_url

    async def handle_callback(self, code: str, state: str) -> ConnectorData:
        """Handle OAuth callback and exchange code for tokens.

        Args:
            code: Authorization code from Google OAuth
            state: State parameter for validation

        Returns:
            ConnectorData: Access token, refresh token, expiry, and user metadata

        Raises:
            Exception: If OAuth exchange or user info retrieval fails
        """
        flow = self._create_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials

        user_info_service = build("oauth2", "v2", credentials=credentials)
        user_info = user_info_service.userinfo().get().execute()

        token_expiry = self._normalize_expiry(credentials.expiry)

        metadata = {
            "email": user_info.get("email"),
            "name": user_info.get("name"),
            "scopes": self.scopes,
        }

        return ConnectorData(
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            token_expiry=token_expiry,
            metadata=metadata,
        )

    async def refresh_access_token(self, connector: Connector) -> ConnectorData:
        """Refresh Google Drive access token using refresh token.

        Args:
            connector: Database connector model with refresh token

        Returns:
            ConnectorData: New access token and expiry information

        Raises:
            Exception: If token refresh fails
        """
        if not connector.refresh_token:
            raise ValueError("No refresh token available")

        settings = get_settings()
        token_response = http_requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.oauth.google_client_id,
                "client_secret": settings.oauth.google_client_secret,
                "refresh_token": connector.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        token_data = token_response.json()

        if "access_token" not in token_data:
            raise ConnectionError("No access token in refresh response")

        new_expiry = _helpers.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600))

        return ConnectorData(
            access_token=token_data["access_token"],
            refresh_token=connector.refresh_token,
            token_expiry=new_expiry,
            metadata=connector.connector_metadata,
        )

    async def validate_token(self, access_token: str) -> bool:
        """Validate if Google Drive access token is still valid.

        Args:
            access_token: The access token to validate

        Returns:
            bool: True if token is valid, False otherwise
        """
        try:
            response = http_requests.get(
                f"https://www.googleapis.com/oauth2/v1/tokeninfo?access_token={access_token}"
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to validate Google Drive token: {e}")
            return False

    async def revoke_access(self, connector: Connector) -> bool:
        """Revoke Google Drive access token.

        Args:
            connector: Database connector model with token to revoke

        Returns:
            bool: True if revocation successful, False otherwise
        """
        if not connector.access_token:
            return True

        try:
            revoke_response = http_requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": connector.access_token},
                headers={"content-type": "application/x-www-form-urlencoded"},
            )

            if revoke_response.status_code == 200:
                logger.info(f"Successfully revoked Google Drive token for connector {connector.id}")
                return True
            else:
                logger.warning(
                    f"Failed to revoke Google Drive token: "
                    f"status={revoke_response.status_code}, response={revoke_response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Error revoking Google Drive token: {e}")
            return False

    def _normalize_expiry(self, expiry: Optional[datetime]) -> Optional[datetime]:
        """Ensure datetime values include timezone info for comparisons.

        Args:
            expiry: Datetime to normalize

        Returns:
            Optional[datetime]: Datetime with timezone info or None
        """
        if expiry is None:
            return None
        if expiry.tzinfo is None:
            return expiry.replace(tzinfo=timezone.utc)
        return expiry

    async def get_credentials(self, user_id: str) -> Optional[Credentials]:
        """Get Google OAuth credentials for user.

        This method automatically refreshes expired tokens.

        Args:
            user_id: User ID to get credentials for

        Returns:
            Optional[Credentials]: Google OAuth credentials or None
        """
        connector = await self.get_connector(user_id)
        if not connector:
            return None

        if await self._should_refresh_token(connector):
            connector_data = await self.refresh_access_token(connector)
            connector.access_token = connector_data.access_token
            connector.token_expiry = connector_data.token_expiry
            connector.updated_at = datetime.utcnow()
            await self.db_session.commit()
            await self.db_session.refresh(connector)

        normalized_expiry = self._normalize_expiry(connector.token_expiry)

        settings = get_settings()
        return Credentials(
            token=connector.access_token,
            refresh_token=connector.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.oauth.google_client_id,
            client_secret=settings.oauth.google_client_secret,
            scopes=self.scopes,
            expiry=normalized_expiry,
        )

    async def get_picker_config(self, user_id: str) -> dict:
        """Get configuration for Google Drive picker.

        Args:
            user_id: User ID to get picker config for

        Returns:
            dict: Picker configuration with access token and developer key
        """
        connector = await self.get_connector(user_id)

        settings = get_settings()
        developer_key = settings.oauth.google_picker_developer_key or None
        app_id = settings.oauth.google_client_id or None

        if not connector:
            return {
                "is_connected": False,
                "developer_key": developer_key,
                "app_id": app_id,
            }

        if connector.refresh_token:
            try:
                connector_data = await self.refresh_access_token(connector)
                connector.access_token = connector_data.access_token
                connector.token_expiry = connector_data.token_expiry
                await self.db_session.commit()

                return {
                    "is_connected": True,
                    "access_token": connector.access_token,
                    "developer_key": developer_key,
                    "app_id": app_id,
                }
            except Exception as e:
                logger.error(f"Failed to refresh token for picker: {e}")

        return {
            "is_connected": True,
            "access_token": connector.access_token,
            "developer_key": developer_key,
            "app_id": app_id,
        }
