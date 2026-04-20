"""Tests for logging configuration and secret masking.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from work_context_sync.utils.logging_config import SecretMaskingFilter, get_logger, setup_logging


class TestSecretMaskingFilter:
    """Test suite for secret masking in logs."""

    @pytest.fixture
    def masking_filter(self) -> SecretMaskingFilter:
        """Provide a masking filter instance."""
        return SecretMaskingFilter()

    def test_mask_uuid(self, masking_filter: SecretMaskingFilter) -> None:
        """Test UUID masking in log records."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Tenant ID: a3599b15-c39c-4b41-a219-7e24dd5b5190",
            args=(),
            exc_info=None,
        )
        masking_filter.filter(record)
        # UUIDs are masked with first 4 chars + **** + last 4 chars
        assert "a359****5190" in record.msg or "****" in record.msg
        assert "a3599b15-c39c-4b41-a219-7e24dd5b5190" not in record.msg

    def test_mask_jwt_token(self, masking_filter: SecretMaskingFilter) -> None:
        """Test JWT token masking."""
        # JWT format: header.payload.signature
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
            args=(),
            exc_info=None,
        )
        masking_filter.filter(record)
        # Full JWT is masked
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi" not in record.msg
        assert "****" in record.msg

    def test_mask_bearer_token(self, masking_filter: SecretMaskingFilter) -> None:
        """Test Bearer token masking."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            args=(),
            exc_info=None,
        )
        masking_filter.filter(record)
        assert "Bearer ****" in record.msg
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in record.msg

    def test_no_masking_for_clean_text(self, masking_filter: SecretMaskingFilter) -> None:
        """Test that clean text is not affected."""
        original = "This is a normal log message with no secrets"
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=original,
            args=(),
            exc_info=None,
        )
        masking_filter.filter(record)
        assert record.msg == original

    def test_mask_in_args(self, masking_filter: SecretMaskingFilter) -> None:
        """Test masking in log arguments."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Processing tenant %s",
            args=("a3599b15-c39c-4b41-a219-7e24dd5b5190",),
            exc_info=None,
        )
        masking_filter.filter(record)
        assert record.args is not None
        assert "a359****" in record.args[0]


class TestSetupLogging:
    """Test suite for logging setup."""

    def test_setup_logging_returns_logger(self, temp_dir: Path) -> None:
        """Test that setup_logging returns configured logger."""
        logger = setup_logging(level=logging.INFO)
        assert logger.name == "work_context_sync"
        assert logger.level == logging.INFO

    def test_setup_logging_creates_file(self, temp_dir: Path) -> None:
        """Test that log file is created."""
        log_file = temp_dir / "test.log"
        logger = setup_logging(level=logging.DEBUG, log_file=log_file)
        
        # Close file handlers to release the file
        for handler in logger.handlers:
            handler.close()
        
        assert log_file.exists()

    def test_setup_logging_log_file_content(self, temp_dir: Path) -> None:
        """Test that log file contains expected content."""
        log_file = temp_dir / "test.log"
        logger = setup_logging(level=logging.DEBUG, log_file=log_file)
        logger.info("Test message")
        
        # Close file handlers to release the file
        for handler in logger.handlers:
            handler.close()
        
        content = log_file.read_text()
        assert "Test message" in content
        assert "INFO" in content

    def test_verbose_level(self, temp_dir: Path) -> None:
        """Test verbose (DEBUG) logging level."""
        logger = setup_logging(level=logging.DEBUG)
        assert logger.isEnabledFor(logging.DEBUG)

    def test_quiet_level(self, temp_dir: Path) -> None:
        """Test quiet (WARNING) logging level."""
        logger = setup_logging(level=logging.WARNING)
        assert not logger.isEnabledFor(logging.INFO)
        assert logger.isEnabledFor(logging.WARNING)


class TestGetLogger:
    """Test suite for get_logger helper."""

    def test_get_root_logger(self) -> None:
        """Test getting root package logger."""
        logger = get_logger()
        assert logger.name == "work_context_sync"

    def test_get_module_logger(self) -> None:
        """Test getting named module logger."""
        logger = get_logger("auth")
        assert logger.name == "work_context_sync.auth"

    def test_get_nested_logger(self) -> None:
        """Test getting nested module logger."""
        logger = get_logger("sources.calendar")
        assert logger.name == "work_context_sync.sources.calendar"
