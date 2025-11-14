"""Correlation ID middleware for request tracing.

This middleware provides request correlation IDs for distributed tracing across:
- API requests
- Service calls
- DynamoDB operations
- InfoCert API calls
- Application logs

The correlation ID:
1. Is extracted from X-Correlation-ID header if provided by client
2. Otherwise, a new UUID is generated for each request
3. Is stored in context variable (available throughout request lifecycle)
4. Is added to response headers (X-Correlation-ID)
5. Is included in all log messages (via logger formatter)
6. Is stored in DynamoDB for audit trail
"""

import uuid
import contextvars
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Context variable to store correlation ID for current request
# This is thread-safe and works with async code
correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'correlation_id',
    default=None
)


def get_correlation_id() -> Optional[str]:
    """
    Get the correlation ID for the current request context.

    Returns:
        Correlation ID string or None if not set
    """
    return correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> None:
    """
    Set the correlation ID for the current request context.

    Args:
        correlation_id: UUID string to set as correlation ID
    """
    correlation_id_var.set(correlation_id)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle correlation IDs for request tracing.

    For each incoming request:
    1. Checks for X-Correlation-ID header
    2. If not present, generates new UUID
    3. Stores in context variable for use throughout request
    4. Adds X-Correlation-ID to response headers

    Example usage:
        app = FastAPI()
        app.add_middleware(CorrelationIdMiddleware)

    Client can provide correlation ID:
        curl -H "X-Correlation-ID: abc-123-def" http://api/process

    Or middleware will generate one:
        curl http://api/process
        # Response header: X-Correlation-ID: 550e8400-e29b-41d4-a716-446655440000
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process each request to extract/generate correlation ID.

        Args:
            request: FastAPI Request object
            call_next: Next middleware/route handler

        Returns:
            Response with X-Correlation-ID header
        """
        # Extract correlation ID from request header or generate new one
        correlation_id = request.headers.get('X-Correlation-ID')

        if not correlation_id:
            # Generate new UUID for this request
            correlation_id = str(uuid.uuid4())

        # Store in context variable (available throughout request lifecycle)
        set_correlation_id(correlation_id)

        # Process request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers['X-Correlation-ID'] = correlation_id

        return response
