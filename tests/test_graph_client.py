"""Tests for Graph API client and retry logic.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from work_context_sync.graph_client import GraphClient, GraphAPIError


class TestGraphClient:
    """Test suite for GraphClient."""

    def test_successful_request(self, mock_config, mock_auth_session) -> None:
        """Test successful API request."""
        client = GraphClient(mock_config, mock_auth_session)
        
        # Mock the httpx.Client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": [{"id": "test"}]}
        
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.request.return_value = mock_response
            
            result = client.get("/me/calendarView", params={"$top": 10})
            
            assert result == {"value": [{"id": "test"}]}
            mock_client.request.assert_called_once()

    def test_retry_on_throttling(self, mock_config, mock_auth_session) -> None:
        """Test retry logic on 429 throttling."""
        client = GraphClient(mock_config, mock_auth_session)
        
        # First call returns 429, second succeeds
        throttle_response = MagicMock()
        throttle_response.status_code = 429
        throttle_response.headers = {"Retry-After": "1"}
        
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"value": []}
        
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return throttle_response
            return success_response
        
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.request.side_effect = side_effect
            
            with patch("time.sleep") as mock_sleep:
                result = client.get("/me/calendarView")
                
                # Should sleep for 1 second (Retry-After header)
                mock_sleep.assert_called_once_with(1)
                assert result == {"value": []}
                assert mock_client.request.call_count == 2

    def test_exponential_backoff(self, mock_config, mock_auth_session) -> None:
        """Test exponential backoff without Retry-After header."""
        client = GraphClient(mock_config, mock_auth_session)
        
        # Configure for 2 retries
        mock_config.graph.request_retry_count = 2
        mock_config.graph.request_retry_base_seconds = 2
        
        throttle_response = MagicMock()
        throttle_response.status_code = 429
        throttle_response.headers = {}  # No Retry-After
        
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"value": []}
        
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                return throttle_response
            return success_response
        
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.request.side_effect = side_effect
            
            with patch("time.sleep") as mock_sleep:
                result = client.get("/me/calendarView")
                
                # Should sleep with exponential backoff: 2s, 4s
                assert mock_sleep.call_count == 2
                mock_sleep.assert_any_call(2)
                mock_sleep.assert_any_call(4)

    def test_pagination(self, mock_config, mock_auth_session) -> None:
        """Test automatic pagination handling."""
        client = GraphClient(mock_config, mock_auth_session)
        
        # First page has next link, second page doesn't
        page1_response = MagicMock()
        page1_response.status_code = 200
        page1_response.json.return_value = {
            "value": [{"id": "item-1"}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next-page",
        }
        
        page2_response = MagicMock()
        page2_response.status_code = 200
        page2_response.json.return_value = {
            "value": [{"id": "item-2"}],
        }
        
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return page1_response
            return page2_response
        
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.request.side_effect = side_effect
            
            result = client.get_all("/me/calendarView", params={"$top": 1})
            
            assert result == {"value": [{"id": "item-1"}, {"id": "item-2"}]}
            assert mock_client.request.call_count == 2

    def test_max_retries_exceeded(self, mock_config, mock_auth_session) -> None:
        """Test that max retries exceeded raises error."""
        mock_config.graph.request_retry_count = 1
        
        client = GraphClient(mock_config, mock_auth_session)
        
        call_count = [0]
        def always_throttle(*args, **kwargs):
            call_count[0] += 1
            throttle_response = MagicMock()
            throttle_response.status_code = 429
            throttle_response.headers = {"Retry-After": "1"}
            throttle_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Too Many Requests",
                request=MagicMock(),
                response=throttle_response,
            )
            return throttle_response
        
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.request.side_effect = always_throttle
            
            with patch("time.sleep"):
                with pytest.raises(httpx.HTTPStatusError):
                    client.get("/me/calendarView")

    def test_error_response_not_retryable(self, mock_config, mock_auth_session) -> None:
        """Test that non-429 errors are not retried."""
        client = GraphClient(mock_config, mock_auth_session)
        
        def make_error_response(*args, **kwargs):
            error_response = MagicMock()
            error_response.status_code = 500
            error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Server Error",
                request=MagicMock(),
                response=error_response,
            )
            return error_response
        
        with patch("httpx.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.request.side_effect = make_error_response
            
            with pytest.raises(httpx.HTTPStatusError):
                client.get("/me/calendarView")
            
            # Should only make one request, no retries
            assert mock_client.request.call_count == 1
