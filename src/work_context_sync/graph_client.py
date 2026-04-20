"""Microsoft Graph API client with retry logic and logging.
"""
from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("work_context_sync.graph_client")


class GraphAPIError(Exception):
    """Graph API request failed."""
    pass


class GraphClient:
    """Microsoft Graph API client with automatic retry and pagination.
    
    Features:
    - Automatic token acquisition via auth_session
    - Exponential backoff for 429 (throttling) responses
    - Automatic pagination for paged responses
    - Request/response logging at DEBUG level
    """
    
    BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, config, auth_session):
        self.config = config
        self.auth_session = auth_session

    def _headers(self) -> dict:
        token = self.auth_session.acquire_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    def _request_with_retry(
        self, 
        client: httpx.Client, 
        url: str, 
        params: dict | None = None,
        method: str = "GET"
    ) -> httpx.Response:
        """Execute request with automatic retry on throttling.
        
        Args:
            client: HTTPX client instance
            url: Full URL to request
            params: Query parameters
            method: HTTP method (default GET)
            
        Returns:
            HTTPX response object
            
        Raises:
            GraphAPIError: If request fails after all retries
            httpx.HTTPStatusError: For non-retryable HTTP errors
        """
        retries = self.config.graph.request_retry_count
        base_wait = self.config.graph.request_retry_base_seconds
        
        # Log request at DEBUG level (URL only, no params with potential secrets)
        path = urlparse(url).path
        logger.debug("%s %s", method, path)

        for attempt in range(retries + 1):
            response = client.request(method, url, headers=self._headers(), params=params)
            
            # Success
            if response.status_code < 400:
                logger.debug("%s %s -> %d", method, path, response.status_code)
                return response
            
            # Throttling (429) - retry with backoff
            if response.status_code == 429:
                if attempt >= retries:
                    logger.error("Graph throttled on %s; max retries exceeded", path)
                    response.raise_for_status()
                
                retry_after = response.headers.get("Retry-After")
                wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else base_wait * (attempt + 1)
                logger.warning(
                    "Graph throttled on %s (attempt %d/%d); retrying in %ss",
                    path, attempt + 1, retries, wait_seconds
                )
                time.sleep(wait_seconds)
                continue
            
            # Other errors - raise immediately
            logger.error("Graph request failed: %s %s -> %d", method, path, response.status_code)
            response.raise_for_status()

        raise RuntimeError("Unreachable retry loop in GraphClient")

    def get(self, path: str, params: dict | None = None) -> dict:
        """Execute GET request to Graph API.
        
        Args:
            path: API path (e.g., "/me/calendarView")
            params: Query parameters
            
        Returns:
            JSON response as dict
        """
        with httpx.Client(timeout=30.0) as client:
            response = self._request_with_retry(client, f"{self.BASE_URL}{path}", params=params)
            return response.json()

    def get_all(self, path: str, params: dict | None = None) -> dict:
        """Execute GET with automatic pagination.
        
        Follows @odata.nextLink to retrieve all pages.
        
        Args:
            path: API path
            params: Initial query parameters
            
        Returns:
            Dict with "value" key containing all items
        """
        items = []
        next_url = f"{self.BASE_URL}{path}"
        request_params = params or {}
        page_count = 0

        with httpx.Client(timeout=30.0) as client:
            while next_url:
                response = self._request_with_retry(client, next_url, params=request_params)
                payload = response.json()
                page_items = payload.get("value", [])
                items.extend(page_items)
                page_count += 1
                
                next_url = payload.get("@odata.nextLink")
                request_params = None  # Only use params on first request
                
                if next_url:
                    logger.debug("Following pagination link (page %d, %d items so far)", page_count, len(items))

        logger.debug("Pagination complete: %d pages, %d total items", page_count, len(items))
        return {"value": items}
