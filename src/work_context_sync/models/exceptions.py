"""Custom exceptions for work-context-sync.

Provides structured error handling with context preservation.
"""
from __future__ import annotations


class WorkContextSyncError(Exception):
    """Base exception for all work-context-sync errors."""
    
    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class GraphAPIError(WorkContextSyncError):
    """Microsoft Graph API request failed."""
    
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        endpoint: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, cause=cause)
        self.status_code = status_code
        self.endpoint = endpoint


class SyncSourceError(WorkContextSyncError):
    """Individual data source sync failed.
    
    Preserves context about which source failed and why.
    """
    
    def __init__(
        self,
        source: str,
        cause: Exception,
        *,
        target_date: str | None = None,
    ) -> None:
        self.source = source
        self.target_date = target_date
        msg = f"Source '{source}' sync failed"
        if target_date:
            msg += f" for {target_date}"
        msg += f": {cause}"
        super().__init__(msg, cause=cause)


class AuthError(WorkContextSyncError):
    """Authentication or authorization failure."""
    
    def __init__(
        self,
        message: str,
        *,
        auth_method: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, cause=cause)
        self.auth_method = auth_method


class ConfigurationError(WorkContextSyncError):
    """Invalid configuration provided."""
    pass


class ValidationError(WorkContextSyncError):
    """Data validation failed."""
    pass
