"""Retry decorator with exponential backoff for recoverable errors.

This module provides a retry mechanism for handling transient failures in
external API calls, particularly for InfoCert API integration.

Recoverable errors (will retry):
- Network timeouts (requests.Timeout)
- Connection errors (requests.ConnectionError)
- HTTP 429 (Too Many Requests / Rate Limiting)
- HTTP 502 (Bad Gateway)
- HTTP 503 (Service Unavailable)
- HTTP 504 (Gateway Timeout)

Non-recoverable errors (will NOT retry):
- HTTP 401, 403 (Authentication/Authorization errors)
- HTTP 400, 404, 405 (Client errors)
- HTTP 500, 501 (Internal server errors - not transient)
- All other exceptions

The decorator uses exponential backoff with jitter to prevent thundering herd.
"""

import time
import random
import functools
from typing import Callable, Any
from requests.exceptions import Timeout, ConnectionError, RequestException
from requests import Response

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def is_recoverable_error(exception: Exception) -> bool:
    """
    Determine if an error is recoverable and should be retried.

    Args:
        exception: The exception to check

    Returns:
        True if the error is recoverable, False otherwise
    """
    # Network-level errors are recoverable
    if isinstance(exception, (Timeout, ConnectionError)):
        return True

    # Check HTTP status codes for RequestException
    if isinstance(exception, RequestException):
        response: Response = getattr(exception, 'response', None)
        if response is not None:
            status_code = response.status_code

            # Rate limiting - recoverable
            if status_code == 429:
                return True

            # Server overload / temporary unavailability - recoverable
            if status_code in (502, 503, 504):
                return True

            # Auth errors - NOT recoverable
            if status_code in (401, 403):
                return False

            # Client errors - NOT recoverable
            if status_code in (400, 404, 405):
                return False

            # Internal server errors (except transient ones) - NOT recoverable
            if status_code == 500:
                return False

    # All other errors - NOT recoverable
    return False


def retry_on_recoverable_errors(func: Callable) -> Callable:
    """
    Decorator that retries a function on recoverable errors with exponential backoff.

    Uses configuration from settings:
    - retry_max_attempts: Maximum number of retry attempts
    - retry_backoff_base: Base backoff time in seconds
    - retry_backoff_max: Maximum backoff time in seconds

    Exponential backoff formula:
        wait_time = min(retry_backoff_base * (2 ** attempt) + jitter, retry_backoff_max)

    Example progression (base=1.0, max=32.0):
        Attempt 1: 1s + jitter
        Attempt 2: 2s + jitter
        Attempt 3: 4s + jitter
        Attempt 4: 8s + jitter
        Attempt 5: 16s + jitter
        Attempt 6: 32s (capped)

    Args:
        func: The function to decorate

    Returns:
        Wrapped function with retry logic
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        max_attempts = settings.retry_max_attempts
        backoff_base = settings.retry_backoff_base
        backoff_max = settings.retry_backoff_max

        last_exception = None

        for attempt in range(max_attempts):
            try:
                # Try to execute the function
                result = func(*args, **kwargs)

                # If we retried at least once, log success
                if attempt > 0:
                    logger.info(
                        f"[RETRY SUCCESS] {func.__name__} succeeded on attempt {attempt + 1}/{max_attempts}"
                    )

                return result

            except Exception as e:
                last_exception = e

                # Check if this error is recoverable
                if not is_recoverable_error(e):
                    logger.warning(
                        f"[RETRY SKIP] {func.__name__} failed with non-recoverable error: {type(e).__name__}: {str(e)}"
                    )
                    raise

                # If this was the last attempt, don't retry
                if attempt == max_attempts - 1:
                    logger.error(
                        f"[RETRY EXHAUSTED] {func.__name__} failed after {max_attempts} attempts. "
                        f"Last error: {type(e).__name__}: {str(e)}"
                    )
                    raise

                # Calculate backoff time with exponential growth and jitter
                backoff_time = min(
                    backoff_base * (2 ** attempt) + random.uniform(0, 1),
                    backoff_max
                )

                # Log retry attempt
                logger.warning(
                    f"[RETRY] {func.__name__} attempt {attempt + 1}/{max_attempts} failed: "
                    f"{type(e).__name__}: {str(e)}. "
                    f"Retrying in {backoff_time:.2f}s..."
                )

                # Wait before retrying
                time.sleep(backoff_time)

        # This should never be reached due to the raise in the loop
        # But included for safety
        if last_exception:
            raise last_exception

    return wrapper
