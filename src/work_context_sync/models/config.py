"""Configuration models for work-context-sync.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, DirectoryPath, Field, SecretStr, field_validator

from .enums import AuthMode


class MailConfig(BaseModel):
    include_sent: bool = True
    include_flagged: bool = True
    selected_folders: list[str] = Field(default_factory=lambda: ["sentitems"])
    max_items: int = Field(default=100, ge=1, le=1000)


class OutputConfig(BaseModel):
    write_raw_json: bool = True
    write_markdown: bool = True


class GraphConfig(BaseModel):
    max_page_size: int = Field(default=100, ge=1, le=999)
    chat_message_limit_per_chat: int = Field(default=25, ge=1, le=100)
    request_retry_count: int = Field(default=4, ge=0, le=10)
    request_retry_base_seconds: int = Field(default=2, ge=1, le=60)


class AuthConfig(BaseModel):
    mode: AuthMode = AuthMode.WAM
    prefer_azure_cli: bool = False
    allow_broker: bool = True


class AppConfig(BaseModel):
    tenant_id: SecretStr
    client_id: SecretStr
    vault_path: DirectoryPath
    timezone: str
    mail: MailConfig = Field(default_factory=MailConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    token_cache_path: str
    
    @field_validator("vault_path", mode="before")
    @classmethod
    def expand_and_validate_vault_path(cls, v: str | Path) -> Path:
        """Expand user home and resolve to absolute path."""
        if isinstance(v, str):
            v = Path(v)
        path = v.expanduser().resolve()
        if not path.exists():
            raise ValueError(f"vault_path does not exist: {path}")
        if not path.is_dir():
            raise ValueError(f"vault_path is not a directory: {path}")
        return path
    
    @field_validator("token_cache_path", mode="before")
    @classmethod
    def expand_token_cache_path(cls, v: str) -> str:
        """Expand user home in token cache path."""
        if v.startswith("~/"):
            return str(Path.home() / v[2:])
        return v
    
    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate timezone against zoneinfo database.
        
        Raises ValueError if timezone is invalid.
        """
        from zoneinfo import available_timezones, ZoneInfo
        
        # Check if it's a valid IANA timezone
        if v not in available_timezones():
            raise ValueError(
                f"Invalid timezone: {v}. "
                f"Use IANA timezone names like 'America/New_York' or 'UTC'."
            )
        
        # Try to instantiate to double-check
        try:
            ZoneInfo(v)
        except Exception as e:
            raise ValueError(f"Invalid timezone: {v} - {e}")
        
        return v
    
    @field_validator("tenant_id", "client_id", mode="before")
    @classmethod
    def validate_uuid_format(cls, v: str) -> str:
        """Validate UUID format for tenant and client IDs."""
        import re
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        if not re.match(uuid_pattern, v, re.IGNORECASE):
            raise ValueError(f"Invalid UUID format: {v}")
        return v
