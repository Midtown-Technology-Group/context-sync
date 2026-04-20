"""Tests for configuration models and validation.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from work_context_sync.models import AppConfig, AuthMode, MailConfig


class TestAppConfig:
    """Test suite for AppConfig validation."""

    def test_valid_config(self, mock_config: AppConfig) -> None:
        """Test that valid configuration passes validation."""
        assert mock_config.vault_path.exists()
        assert mock_config.timezone == "America/New_York"
        assert mock_config.auth.mode == AuthMode.DEVICE_CODE

    def test_vault_path_expansion(self, temp_dir: Path) -> None:
        """Test that ~ is expanded to home directory."""
        config = AppConfig(
            tenant_id="a3599b15-c39c-4b41-a219-7e24dd5b5190",
            client_id="e02be6f7-063a-46a6-b2cc-109d5f51055c",
            vault_path=temp_dir,
            timezone="UTC",
            token_cache_path="~/.config/token.bin",
        )
        assert config.vault_path == temp_dir.resolve()

    def test_vault_path_must_exist(self) -> None:
        """Test that non-existent vault_path raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AppConfig(
                tenant_id="a3599b15-c39c-4b41-a219-7e24dd5b5190",
                client_id="e02be6f7-063a-46a6-b2cc-109d5f51055c",
                vault_path="/nonexistent/path/that/does/not/exist",
                timezone="UTC",
                token_cache_path="~/.config/token.bin",
            )
        assert "does not exist" in str(exc_info.value)

    def test_vault_path_must_be_directory(self, temp_dir: Path) -> None:
        """Test that vault_path must be a directory, not a file."""
        file_path = temp_dir / "not_a_directory.txt"
        file_path.write_text("test")
        
        with pytest.raises(ValidationError) as exc_info:
            AppConfig(
                tenant_id="a3599b15-c39c-4b41-a219-7e24dd5b5190",
                client_id="e02be6f7-063a-46a6-b2cc-109d5f51055c",
                vault_path=str(file_path),
                timezone="UTC",
                token_cache_path="~/.config/token.bin",
            )
        assert "not a directory" in str(exc_info.value)

    def test_invalid_timezone(self, temp_dir: Path) -> None:
        """Test that invalid timezone raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AppConfig(
                tenant_id="a3599b15-c39c-4b41-a219-7e24dd5b5190",
                client_id="e02be6f7-063a-46a6-b2cc-109d5f51055c",
                vault_path=temp_dir,
                timezone="Invalid/Timezone",
                token_cache_path="~/.config/token.bin",
            )
        assert "Invalid timezone" in str(exc_info.value)

    def test_invalid_uuid_format_tenant(self, temp_dir: Path) -> None:
        """Test that invalid tenant_id UUID raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AppConfig(
                tenant_id="not-a-valid-uuid",
                client_id="e02be6f7-063a-46a6-b2cc-109d5f51055c",
                vault_path=temp_dir,
                timezone="UTC",
                token_cache_path="~/.config/token.bin",
            )
        assert "Invalid UUID format" in str(exc_info.value)

    def test_invalid_uuid_format_client(self, temp_dir: Path) -> None:
        """Test that invalid client_id UUID raises error."""
        with pytest.raises(ValidationError) as exc_info:
            AppConfig(
                tenant_id="a3599b15-c39c-4b41-a219-7e24dd5b5190",
                client_id="also-not-valid",
                vault_path=temp_dir,
                timezone="UTC",
                token_cache_path="~/.config/token.bin",
            )
        assert "Invalid UUID format" in str(exc_info.value)

    def test_token_cache_path_expansion(self, temp_dir: Path) -> None:
        """Test that ~ is expanded in token_cache_path."""
        config = AppConfig(
            tenant_id="a3599b15-c39c-4b41-a219-7e24dd5b5190",
            client_id="e02be6f7-063a-46a6-b2cc-109d5f51055c",
            vault_path=temp_dir,
            timezone="UTC",
            token_cache_path="~/.config/work-context-sync/token.bin",
        )
        assert not config.token_cache_path.startswith("~")
        # Check home path is present (handle Windows/Unix path differences)
        assert str(Path.home()) in config.token_cache_path

    def test_mail_max_items_constraints(self, mock_config: AppConfig) -> None:
        """Test mail.max_items field constraints."""
        # Valid value
        mock_config.mail.max_items = 500
        assert mock_config.mail.max_items == 500

    def test_mail_max_items_too_high(self, temp_dir: Path) -> None:
        """Test that mail.max_items > 1000 raises error on creation."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            AppConfig(
                tenant_id="a3599b15-c39c-4b41-a219-7e24dd5b5190",
                client_id="e02be6f7-063a-46a6-b2cc-109d5f51055c",
                vault_path=temp_dir,
                timezone="UTC",
                token_cache_path="~/.config/token.bin",
                mail=MailConfig(max_items=2000),  # Too high
            )
        assert "max_items" in str(exc_info.value) or "Input should be less than or equal to 1000" in str(exc_info.value)

    def test_auth_mode_enum(self, mock_config: AppConfig) -> None:
        """Test that auth mode uses enum values."""
        assert mock_config.auth.mode == AuthMode.DEVICE_CODE
        
        # Test setting by string
        mock_config.auth.mode = "wam"  # type: ignore
        assert mock_config.auth.mode == AuthMode.WAM


class TestSecretMasking:
    """Test that secrets are properly masked."""

    def test_tenant_id_masked_in_repr(self, mock_config: AppConfig) -> None:
        """Test that tenant_id is masked in repr()."""
        repr_str = repr(mock_config)
        assert "a3599b15" not in repr_str  # Original value should not appear
        assert "**********" in repr_str or "SecretStr" in repr_str

    def test_client_id_masked_in_repr(self, mock_config: AppConfig) -> None:
        """Test that client_id is masked in repr()."""
        repr_str = repr(mock_config)
        assert "e02be6f7" not in repr_str  # Original value should not appear
        assert "**********" in repr_str or "SecretStr" in repr_str

    def test_secret_value_accessible(self, mock_config: AppConfig) -> None:
        """Test that secret value can be retrieved when needed."""
        tenant = mock_config.tenant_id.get_secret_value()
        assert tenant == "a3599b15-c39c-4b41-a219-7e24dd5b5190"
        
        client = mock_config.client_id.get_secret_value()
        assert client == "e02be6f7-063a-46a6-b2cc-109d5f51055c"
