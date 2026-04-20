"""Async Microsoft Graph API client with retry logic and connection pooling.

This is the async version of graph_client.py using httpx.AsyncClient.
"""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("work_context_sync.async_graph_client")


class AsyncGraphClient:
    """Async Microsoft Graph API client with automatic retry and pagination.
    
    Uses httpx.AsyncClient for efficient async HTTP requests with connection
    pooling. Supports automatic pagination and exponential backoff for throttling.
    
    Example:
        async with AsyncGraphClient(config, auth_session) as client:
            events = await client.get_all("/me/calendarView", params={...})
    """
    
    BASE_URL = "https://graph.microsoft.com/v1.0"
    
    def __init__(self, config, auth_session, timeout: float = 30.0):
        self.config = config
        self.auth_session = auth_session
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
    
    async def __aenter__(self) -> AsyncGraphClient:
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _headers(self) -> dict:
        """Generate authorization headers."""
        token = self.auth_session.acquire_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
    
    async def _request_with_retry(
        self, 
        url: str, 
        params: dict | None = None,
        method: str = "GET"
    ) -> httpx.Response:
        """Execute async request with automatic retry on throttling.
        
        Args:
            url: Full URL to request
            params: Query parameters
            method: HTTP method (default GET)
            
        Returns:
            HTTPX response object
        """
        if not self._client:
            raise RuntimeError("AsyncGraphClient not entered as context manager")
        
        retries = self.config.graph.request_retry_count
        base_wait = self.config.graph.request_retry_base_seconds
        
        # Log request at DEBUG level (URL only, no params with potential secrets)
        path = urlparse(url).path
        logger.debug("%s %s", method, path)

        for attempt in range(retries + 1):
            response = await self._client.request(
                method, url, headers=self._headers(), params=params
            )
            
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
                await asyncio.sleep(wait_seconds)
                continue
            
            # Other errors - raise immediately
            logger.error("Graph request failed: %s %s -> %d", method, path, response.status_code)
            response.raise_for_status()

        raise RuntimeError("Unreachable retry loop in AsyncGraphClient")
    
    async def get(self, path: str, params: dict | None = None) -> dict:
        """Execute async GET request to Graph API.
        
        Args:
            path: API path (e.g., "/me/calendarView")
            params: Query parameters
            
        Returns:
            JSON response as dict
        """
        response = await self._request_with_retry(f"{self.BASE_URL}{path}", params=params)
        return response.json()
    
    async def get_all(self, path: str, params: dict | None = None) -> dict:
        """Execute async GET with automatic pagination.
        
        Follows @odata.nextLink to retrieve all pages concurrently.
        
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

        while next_url:
            response = await self._request_with_retry(next_url, params=request_params)
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
    
    async def batch_get(self, paths: list[str], params_list: list[dict | None] | None = None) -> list[dict]:
        """Execute multiple GET requests concurrently.
        
        Args:
            paths: List of API paths
            params_list: Optional list of query parameters for each path
            
        Returns:
            List of JSON responses in same order as paths
        """
        if params_list is None:
            params_list = [None] * len(paths)
        
        tasks = [
            self.get(path, params) 
            for path, params in zip(paths, params_list)
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)
