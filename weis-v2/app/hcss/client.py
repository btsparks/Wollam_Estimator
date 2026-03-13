"""
HCSS Base API Client

Provides authenticated HTTP requests to HCSS APIs with:
    - Bearer token authentication (from HCSSAuth)
    - Automatic pagination (HCSS uses skip/take pattern, 100 records/page)
    - Retry with exponential backoff (3 retries: 1s, 2s, 4s)
    - Rate limiting awareness (respects 429 responses)
    - Timeout handling (30s default)
    - Detailed error logging

All HCSS API requests go through this client.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.hcss.auth import HCSSAuth

logger = logging.getLogger(__name__)

# Default pagination settings — HCSS APIs use skip/take pattern
DEFAULT_PAGE_SIZE = 100

# Retry settings — exponential backoff on transient failures
MAX_RETRIES = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]  # seconds between retries

# Default request timeout
DEFAULT_TIMEOUT = 30.0


class HCSSClient:
    """
    Base HTTP client for HCSS API requests.

    Handles authentication, pagination, retries, and error reporting.
    HeavyJob and HeavyBid wrappers use this client for all HTTP calls.

    Usage:
        auth = HCSSAuth()
        client = HCSSClient(auth, base_url="https://api.hcss.com/heavyjob")
        jobs = await client.get_paginated("/api/v1/jobs", params={"status": "Closed"})
    """

    def __init__(self, auth: HCSSAuth, base_url: str):
        """
        Args:
            auth: HCSSAuth instance for token management.
            base_url: Base URL for the API (e.g., https://api.hcss.com/heavyjob).
        """
        self._auth = auth
        self._base_url = base_url.rstrip("/")

    async def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        _http: httpx.AsyncClient | None = None,
    ) -> dict:
        """
        Authenticated GET request with retry logic.

        Args:
            endpoint: API path (e.g., '/api/v1/jobs').
            params: Query parameters.
            _http: Optional pre-existing httpx client (used by get_paginated
                   to reuse connections across pages).

        Returns:
            Parsed JSON response as dict.

        Raises:
            httpx.HTTPStatusError: After all retries exhausted.
            RuntimeError: If auth is not configured.
        """
        url = f"{self._base_url}{endpoint}"
        token = await self._auth.get_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                if _http:
                    response = await _http.get(
                        url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT,
                    )
                else:
                    async with httpx.AsyncClient() as http:
                        response = await http.get(
                            url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT,
                        )

                # Handle rate limiting — wait and retry
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "5"))
                    logger.warning(
                        "Rate limited on %s, waiting %d seconds",
                        endpoint, retry_after,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.error(
                    "HTTP %d on %s %s: %s",
                    e.response.status_code, "GET", url,
                    e.response.text[:500],
                )
                # Don't retry client errors (4xx) except 429
                if 400 <= e.response.status_code < 500:
                    raise

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                logger.warning(
                    "Request failed (attempt %d/%d) on %s: %s",
                    attempt + 1, MAX_RETRIES + 1, endpoint, str(e),
                )

            # Exponential backoff before retry
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt]
                logger.info("Retrying in %.1f seconds...", delay)
                await asyncio.sleep(delay)

        # All retries exhausted
        raise last_error or RuntimeError(f"Request failed after {MAX_RETRIES + 1} attempts: {endpoint}")

    async def get_paginated(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[dict]:
        """
        Paginated GET request — fetches all pages automatically.

        HCSS APIs use skip/take pagination:
            ?skip=0&take=100   → first 100 records
            ?skip=100&take=100 → next 100 records
            (stop when returned count < take)

        Args:
            endpoint: API path.
            params: Additional query parameters (skip/take are added automatically).
            page_size: Records per page (default 100).

        Returns:
            Combined list of all records across all pages.
        """
        all_records: list[dict] = []
        skip = 0
        params = dict(params or {})

        # Reuse one HTTP client for the entire pagination loop
        async with httpx.AsyncClient() as http:
            while True:
                params["skip"] = skip
                params["take"] = page_size

                response = await self.get(endpoint, params=params, _http=http)

                # HCSS returns records in various wrappers
                if isinstance(response, list):
                    records = response
                elif isinstance(response, dict) and "results" in response:
                    records = response["results"]
                elif isinstance(response, dict) and "data" in response:
                    records = response["data"]
                elif isinstance(response, dict) and "items" in response:
                    records = response["items"]
                else:
                    # Single-page response or unknown format — return as-is
                    records = [response] if response else []
                    all_records.extend(records)
                    break

                all_records.extend(records)

                # If API returned more than we asked for, it ignores
                # pagination — return everything from this single response
                if len(records) > page_size:
                    logger.info(
                        "API returned %d records (> page_size %d) — not paginating, using full result",
                        len(records), page_size,
                    )
                    break

                # If we got fewer records than the page size, we've reached the end
                if len(records) < page_size:
                    break

                skip += page_size
                logger.debug("Fetched %d records from %s, getting next page...", len(all_records), endpoint)

        logger.info("Fetched %d total records from %s", len(all_records), endpoint)
        return all_records

    async def get_cursor_paginated(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[dict]:
        """
        Cursor-based paginated GET — for endpoints using nextCursor pagination.

        HCSS timeCardInfo and similar endpoints use:
            {results: [...], metadata: {nextCursor: "xxx"}}
        Pass nextCursor as ?cursor= to get next page.
        """
        all_records: list[dict] = []
        params = dict(params or {})
        params["take"] = page_size

        async with httpx.AsyncClient() as http:
            while True:
                response = await self.get(endpoint, params=params, _http=http)

                if isinstance(response, dict) and "results" in response:
                    records = response["results"]
                elif isinstance(response, list):
                    records = response
                else:
                    records = [response] if response else []
                    all_records.extend(records)
                    break

                all_records.extend(records)

                # Check for next cursor in metadata
                metadata = response.get("metadata", {}) if isinstance(response, dict) else {}
                next_cursor = metadata.get("nextCursor")

                if not next_cursor or len(records) < page_size:
                    break

                params["cursor"] = next_cursor
                logger.debug(
                    "Fetched %d records from %s, getting next page (cursor=%s)...",
                    len(all_records), endpoint, next_cursor[:20],
                )

        logger.info("Fetched %d total records from %s (cursor pagination)", len(all_records), endpoint)
        return all_records

    async def post(self, endpoint: str, data: dict[str, Any] | None = None) -> dict:
        """
        Authenticated POST request with retry logic.

        Args:
            endpoint: API path.
            data: JSON body.

        Returns:
            Parsed JSON response as dict.
        """
        url = f"{self._base_url}{endpoint}"
        token = await self._auth.get_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient() as http:
                    response = await http.post(
                        url,
                        json=data,
                        headers=headers,
                        timeout=DEFAULT_TIMEOUT,
                    )

                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", "5"))
                        logger.warning("Rate limited on POST %s, waiting %d seconds", endpoint, retry_after)
                        await asyncio.sleep(retry_after)
                        continue

                    response.raise_for_status()
                    return response.json()

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.error(
                    "HTTP %d on POST %s: %s",
                    e.response.status_code, url,
                    e.response.text[:500],
                )
                if 400 <= e.response.status_code < 500:
                    raise

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                logger.warning(
                    "POST failed (attempt %d/%d) on %s: %s",
                    attempt + 1, MAX_RETRIES + 1, endpoint, str(e),
                )

            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt]
                await asyncio.sleep(delay)

        raise last_error or RuntimeError(f"POST failed after {MAX_RETRIES + 1} attempts: {endpoint}")
