"""Tests for async Graph client and pipeline.
"""
from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from work_context_sync.async_graph_client import AsyncGraphClient
from work_context_sync.async_pipeline import run_async_sync


class TestAsyncGraphClient:
    """Test suite for AsyncGraphClient."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self, mock_config, mock_auth_session) -> None:
        """Test async context manager properly opens/closes client."""
        async with AsyncGraphClient(mock_config, mock_auth_session) as client:
            assert client._client is not None
            assert isinstance(client._client, httpx.AsyncClient)
        # After exit, client should be closed
        assert client._client is None

    @pytest.mark.asyncio
    async def test_successful_async_request(self, mock_config, mock_auth_session) -> None:
        """Test successful async API request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": [{"id": "test"}]}
        
        async with AsyncGraphClient(mock_config, mock_auth_session) as client:
            with patch.object(client._client, 'request', new_callable=AsyncMock) as mock_request:
                mock_request.return_value = mock_response
                
                result = await client.get("/me/calendarView", params={"$top": 10})
                
                assert result == {"value": [{"id": "test"}]}
                mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_batch_requests(self, mock_config, mock_auth_session) -> None:
        """Test concurrent batch requests."""
        mock_response1 = MagicMock()
        mock_response1.status_code = 200
        mock_response1.json.return_value = {"value": ["result1"]}
        
        mock_response2 = MagicMock()
        mock_response2.status_code = 200
        mock_response2.json.return_value = {"value": ["result2"]}
        
        async with AsyncGraphClient(mock_config, mock_auth_session) as client:
            with patch.object(client._client, 'request', new_callable=AsyncMock) as mock_request:
                mock_request.side_effect = [mock_response1, mock_response2]
                
                results = await client.batch_get(
                    ["/path/1", "/path/2"],
                    [{"$top": 10}, {"$top": 20}]
                )
                
                assert len(results) == 2
                assert results[0] == {"value": ["result1"]}
                assert results[1] == {"value": ["result2"]}
                assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_async_pagination(self, mock_config, mock_auth_session) -> None:
        """Test async pagination handling."""
        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "value": [{"id": "item1"}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next-page",
        }
        
        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {
            "value": [{"id": "item2"}],
        }
        
        async with AsyncGraphClient(mock_config, mock_auth_session) as client:
            with patch.object(client._client, 'request', new_callable=AsyncMock) as mock_request:
                mock_request.side_effect = [page1, page2]
                
                result = await client.get_all("/me/calendarView", params={"$top": 1})
                
                assert result == {"value": [{"id": "item1"}, {"id": "item2"}]}
                assert mock_request.call_count == 2


class TestAsyncPipeline:
    """Test suite for async pipeline."""

    @pytest.mark.asyncio
    async def test_run_async_sync_basic(self, mock_config, temp_dir: Path) -> None:
        """Test basic async sync execution."""
        # Mock the graph client to avoid actual API calls
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": []}
        
        with patch('work_context_sync.async_graph_client.AsyncGraphClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get_all.return_value = {"value": []}
            
            with patch('work_context_sync.auth.GraphAuthSession'):
                await run_async_sync(
                    config=mock_config,
                    target_date=date(2026, 4, 20),
                    selected_sources=["calendar"]
                )

    @pytest.mark.asyncio
    async def test_concurrent_source_fetching(self) -> None:
        """Test that multiple sources are fetched concurrently."""
        # Track when each fetch starts
        fetch_times = {}
        
        async def mock_fetch_calendar(client, target_date):
            fetch_times['calendar'] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)  # Simulate work
            return {"value": []}
        
        async def mock_fetch_mail(client, target_date):
            fetch_times['mail'] = asyncio.get_event_loop().time()
            await asyncio.sleep(0.1)  # Simulate work
            return {"value": []}
        
        # Patch the fetchers
        from work_context_sync import async_pipeline
        original_fetchers = async_pipeline.ASYNC_SOURCE_FETCHERS.copy()
        
        try:
            async_pipeline.ASYNC_SOURCE_FETCHERS['calendar'] = mock_fetch_calendar
            async_pipeline.ASYNC_SOURCE_FETCHERS['mail'] = mock_fetch_mail
            
            # Both should execute with minimal time difference (concurrent)
            start = asyncio.get_event_loop().time()
            await asyncio.gather(
                mock_fetch_calendar(None, None),
                mock_fetch_mail(None, None)
            )
            elapsed = asyncio.get_event_loop().time() - start
            
            # Should take ~0.1s (concurrent), not ~0.2s (sequential)
            assert elapsed < 0.15, f"Fetchers ran sequentially (took {elapsed}s)"
            
        finally:
            async_pipeline.ASYNC_SOURCE_FETCHERS = original_fetchers
