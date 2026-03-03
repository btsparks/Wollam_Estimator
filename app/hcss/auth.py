"""
HCSS OAuth 2.0 Authentication Manager

Handles the client_credentials OAuth flow for HCSS API access.
Token is cached and automatically refreshed 5 minutes before expiry.

Credentials are loaded from environment variables:
    HCSS_CLIENT_ID     — OAuth client ID from HCSS
    HCSS_CLIENT_SECRET — OAuth client secret from HCSS

If credentials are not set, is_configured returns False and all
API calls will fail with a clear error message. The rest of WEIS
(historical JCD queries, agents, etc.) continues to work.
"""

from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

# Default HCSS identity endpoint
DEFAULT_TOKEN_URL = "https://api.hcss.com/identity/connect/token"

# Refresh token 5 minutes (300 seconds) before it expires
TOKEN_REFRESH_BUFFER_SECONDS = 300


class HCSSAuth:
    """
    OAuth 2.0 client credentials manager for HCSS APIs.

    Usage:
        auth = HCSSAuth()
        if auth.is_configured:
            token = await auth.get_token()
            # Use token in API requests
        else:
            print("HCSS credentials not configured")
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        token_url: str = DEFAULT_TOKEN_URL,
    ):
        """
        Initialize auth manager.

        Args:
            client_id: HCSS OAuth client ID. Falls back to HCSS_CLIENT_ID env var.
            client_secret: HCSS OAuth client secret. Falls back to HCSS_CLIENT_SECRET env var.
            token_url: HCSS identity token endpoint.
        """
        self._client_id = client_id or os.environ.get("HCSS_CLIENT_ID", "")
        self._client_secret = client_secret or os.environ.get("HCSS_CLIENT_SECRET", "")
        self._token_url = token_url

        # Cached token state
        self._access_token: str | None = None
        self._token_expires_at: float = 0  # Unix timestamp

    @property
    def is_configured(self) -> bool:
        """Check if HCSS credentials are set."""
        return bool(self._client_id and self._client_secret)

    async def get_token(self) -> str:
        """
        Get a valid bearer token, refreshing if needed.

        Returns:
            Bearer token string.

        Raises:
            RuntimeError: If credentials are not configured.
            httpx.HTTPStatusError: If token request fails.
        """
        if not self.is_configured:
            raise RuntimeError(
                "HCSS API credentials not configured. "
                "Set HCSS_CLIENT_ID and HCSS_CLIENT_SECRET environment variables."
            )

        return await self.refresh_if_needed()

    async def refresh_if_needed(self) -> str:
        """
        Return cached token if still valid, otherwise request a new one.

        Refreshes if token is None or will expire within 5 minutes.

        Returns:
            Valid bearer token string.
        """
        now = time.time()

        if self._access_token and now < (self._token_expires_at - TOKEN_REFRESH_BUFFER_SECONDS):
            return self._access_token

        logger.info("Requesting new HCSS OAuth token...")
        return await self._request_token()

    async def _request_token(self) -> str:
        """
        Request a new OAuth token from HCSS identity server.

        Uses the client_credentials grant type. Token typically expires
        in ~1 hour (3600 seconds), but we respect whatever expires_in
        the server returns.

        Returns:
            New bearer token string.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30.0,
            )
            response.raise_for_status()

        token_data = response.json()
        self._access_token = token_data["access_token"]

        # Calculate expiry time — default to 3600s if not provided
        expires_in = token_data.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in

        logger.info("HCSS OAuth token obtained, expires in %d seconds", expires_in)
        return self._access_token
