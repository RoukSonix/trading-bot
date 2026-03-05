"""Structured logging configuration for Trading Bot.

Provides JSON logging for production and human-readable logs for development.
Uses Loguru with automatic log rotation.

Usage:
    from shared.utils.logging_config import setup_logging, get_logger
    
    # Setup once at startup
    setup_logging()
    
    # Get logger for a module
    logger = get_logger(__name__)
    logger.info("Message", extra_field="value")
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


def json_formatter(record: dict) -> str:
    """Format log record as JSON for production.
    
    Args:
        record: Loguru log record
        
    Returns:
        JSON formatted log string
    """
    log_entry = {
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "level": record["level"].name,
        "message": record["message"],
        "logger": record["name"],
        "module": record["module"],
        "function": record["function"],
        "line": record["line"],
    }
    
    # Add exception info if present
    if record["exception"]:
        log_entry["exception"] = {
            "type": record["exception"].type.__name__ if record["exception"].type else None,
            "value": str(record["exception"].value) if record["exception"].value else None,
            "traceback": record["exception"].traceback if record["exception"].traceback else None,
        }
    
    # Add extra fields
    if record["extra"]:
        log_entry["extra"] = record["extra"]
    
    return json.dumps(log_entry, default=str)


def json_sink(message):
    """Sink that outputs JSON formatted logs."""
    record = message.record
    json_log = json_formatter(record)
    print(json_log, file=sys.stderr, flush=True)


def setup_logging(
    log_level: str = None,
    log_format: str = None,
    log_dir: str = "logs",
    rotation: str = "10 MB",
    retention: int = 5,
) -> None:
    """Configure logging for the application.
    
    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR). 
                   Defaults to LOG_LEVEL env var or INFO.
        log_format: Format type ('json' or 'text').
                    Defaults to LOG_FORMAT env var or 'text'.
        log_dir: Directory for log files. Defaults to 'logs'.
        rotation: When to rotate log files. Defaults to '10 MB'.
        retention: Number of rotated files to keep. Defaults to 5.
    """
    # Get configuration from environment if not provided
    log_level = log_level or os.environ.get("LOG_LEVEL", "INFO").upper()
    log_format = log_format or os.environ.get("LOG_FORMAT", "text").lower()
    environment = os.environ.get("ENVIRONMENT", "development").lower()
    
    # Force JSON in production
    if environment == "production" and log_format != "json":
        log_format = "json"
    
    # Remove default handler
    logger.remove()
    
    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Configure format
    if log_format == "json":
        # JSON format for production
        logger.add(
            json_sink,
            level=log_level,
            backtrace=True,
            diagnose=True,
        )
        
        # JSON file sink with rotation
        logger.add(
            str(log_path / "trading_bot_{time:YYYY-MM-DD}.json"),
            level=log_level,
            format=lambda r: json_formatter(r) + "\n",
            rotation=rotation,
            retention=retention,
            compression="gz",
        )
    else:
        # Human-readable format for development
        format_string = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
        
        # Console output
        logger.add(
            sys.stderr,
            format=format_string,
            level=log_level,
            colorize=True,
        )
        
        # File output with rotation
        logger.add(
            str(log_path / "trading_bot_{time:YYYY-MM-DD}.log"),
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            level=log_level,
            rotation=rotation,
            retention=retention,
            compression="gz",
        )
    
    # Log startup
    logger.info(
        "Logging configured",
        level=log_level,
        format=log_format,
        environment=environment,
        log_dir=str(log_path),
    )


def get_logger(name: str = None):
    """Get a logger instance.
    
    Args:
        name: Logger name (typically __name__). If None, returns the root logger.
        
    Returns:
        Loguru logger instance bound to the given name.
    """
    if name:
        return logger.bind(name=name)
    return logger


class LoggerAdapter:
    """Adapter to provide a standard logging interface with Loguru.
    
    Useful for integrating with libraries that expect standard logging.
    """
    
    def __init__(self, name: str = None):
        """Initialize the adapter.
        
        Args:
            name: Logger name
        """
        self._logger = get_logger(name)
    
    def debug(self, msg: str, *args, **kwargs) -> None:
        """Log debug message."""
        self._logger.debug(msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs) -> None:
        """Log info message."""
        self._logger.info(msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs) -> None:
        """Log warning message."""
        self._logger.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs) -> None:
        """Log error message."""
        self._logger.error(msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs) -> None:
        """Log critical message."""
        self._logger.critical(msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs) -> None:
        """Log exception with traceback."""
        self._logger.exception(msg, *args, **kwargs)


# Convenience exports
__all__ = [
    "setup_logging",
    "get_logger",
    "logger",
    "LoggerAdapter",
]
