"""Logging configuration for the application."""

import logging
import sys
from typing import Optional
from app.config import settings


class CorrelationIdFormatter(logging.Formatter):
    """
    Custom formatter that includes correlation ID in log messages.

    The correlation ID is retrieved from the context variable set by
    the CorrelationIdMiddleware. If no correlation ID is set, it's
    omitted from the log message.

    Format: timestamp - correlation_id - name - level - message
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with correlation ID if available.

        Args:
            record: Log record to format

        Returns:
            Formatted log message string
        """
        # Import here to avoid circular dependency
        from app.middleware.correlation_id import get_correlation_id

        # Get correlation ID from context
        correlation_id = get_correlation_id()

        # Add correlation_id as extra field (will be None if not set)
        record.correlation_id = correlation_id or "N/A"

        return super().format(record)


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

        # Custom formatter with correlation ID, timestamp, level, logger name, and message
        formatter = CorrelationIdFormatter(
            fmt="%(asctime)s - [%(correlation_id)s] - %(name)s - %(levelname)s - %(message)s",
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
