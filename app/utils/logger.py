"""Logging configuration for the application."""

import logging
import sys
from typing import Optional
from app.config import settings


def setup_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Set up and configure logger with consistent formatting.

    Args:
        name: Logger name (typically __name__ from calling module)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name or __name__)

    # Only configure if handlers haven't been set up yet
    if not logger.handlers:
        logger.setLevel(getattr(logging, settings.log_level.upper()))

        # Console handler with detailed formatting
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, settings.log_level.upper()))

        # Detailed formatter with timestamp, level, logger name, and message
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)

        logger.addHandler(console_handler)

    return logger


def log_exception(logger: logging.Logger, exception: Exception, context: str = ""):
    """
    Log exception with context information.

    Args:
        logger: Logger instance
        exception: Exception to log
        context: Additional context information
    """
    error_msg = f"{context}: {type(exception).__name__}: {str(exception)}" if context else f"{type(exception).__name__}: {str(exception)}"
    logger.error(error_msg, exc_info=True)
