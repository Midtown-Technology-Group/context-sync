"""Structured logging configuration for work-context-sync.

Provides INFO-level logging with plain text format and secret masking.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any


class SecretMaskingFilter(logging.Filter):
    """Masks sensitive values in log records.
    
    Masks:
    - UUIDs (tenant_id, client_id patterns)
    - JWT tokens (base64 patterns)
    - Access tokens
    """
    
    MASKED = "****"
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Mask secrets in log message."""
        if isinstance(record.msg, str):
            record.msg = self._mask_secrets(record.msg)
        
        # Also mask in args
        if record.args:
            record.args = tuple(
                self._mask_secrets(str(arg)) if isinstance(arg, str) else arg
                for arg in record.args
            )
        
        return True
    
    def _mask_secrets(self, text: str) -> str:
        """Apply masking rules to text."""
        import re
        
        # Mask UUIDs (but preserve first/last 4 chars for debugging)
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        text = re.sub(uuid_pattern, lambda m: f"{m.group()[:4]}****{m.group()[-4:]}", text, flags=re.IGNORECASE)
        
        # Mask JWT tokens (eyJ... base64 pattern)
        jwt_pattern = r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*'
        text = re.sub(jwt_pattern, "eyJ****...****", text)
        
        # Mask bearer tokens
        bearer_pattern = r'Bearer\s+[a-zA-Z0-9_-]+'
        text = re.sub(bearer_pattern, "Bearer ****", text)
        
        return text


def setup_logging(
    level: int = logging.INFO,
    log_file: Path | None = None,
    format_string: str | None = None,
) -> logging.Logger:
    """Configure logging for work-context-sync.
    
    Args:
        level: Logging level (default: INFO)
        log_file: Optional file path for log output
        format_string: Custom format string (default: plain text)
    
    Returns:
        Configured root logger for the package
    """
    if format_string is None:
        format_string = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    
    # Create formatter
    formatter = logging.Formatter(
        format_string,
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Get package logger
    logger = logging.getLogger("work_context_sync")
    logger.setLevel(level)
    logger.handlers = []  # Clear existing handlers
    logger.propagate = False  # Don't bubble to root
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(SecretMaskingFilter())
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(SecretMaskingFilter())
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger for a module.
    
    Args:
        name: Module name (e.g., 'pipeline', 'auth'). 
              If None, returns package root logger.
    
    Returns:
        Configured logger instance
    """
    if name:
        return logging.getLogger(f"work_context_sync.{name}")
    return logging.getLogger("work_context_sync")
