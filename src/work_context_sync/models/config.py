from __future__ import annotations

from pydantic import BaseModel, Field


class MailConfig(BaseModel):
    include_sent: bool = True
    include_flagged: bool = True
    selected_folders: list[str] = Field(default_factory=lambda: ["sentitems"])
    max_items: int = 100


class OutputConfig(BaseModel):
    write_raw_json: bool = True
    write_markdown: bool = True


class GraphConfig(BaseModel):
    max_page_size: int = 100
    chat_message_limit_per_chat: int = 25
    request_retry_count: int = 4
    request_retry_base_seconds: int = 2


class AuthConfig(BaseModel):
    mode: str = "wam"  # Options: wam, interactive, device-code, azure-cli, auto
    prefer_azure_cli: bool = False
    allow_broker: bool = True  # Use Windows Web Account Manager (WAM) for SSO


class AppConfig(BaseModel):
    tenant_id: str
    client_id: str
    vault_path: str
    timezone: str
    mail: MailConfig = Field(default_factory=MailConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    token_cache_path: str
