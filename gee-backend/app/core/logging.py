"""
Structured logging module for Consorcio Canalero GEE Backend.
Uses structlog for JSON-formatted, structured logging.
"""

import logging
import sys
from typing import Any, Dict, List, Optional, Set
import structlog
from structlog.types import EventDict, Processor


# Sensitive fields that should be sanitized in logs
SENSITIVE_FIELDS: Set[str] = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "secret",
    "jwt",
    "authorization",
    "credentials",
    "supabase_key",
    "supabase_service_role_key",
    "supabase_jwt_secret",
    "gee_service_account_key",
    "email",
    "telefono",
    "contacto_telefono",
    "contacto_email",
}

# Placeholder for sanitized values
SANITIZED_VALUE = "[REDACTED]"


def sanitize_sensitive_data(
    data: Any,
    sensitive_fields: Optional[Set[str]] = None,
    max_depth: int = 10,
) -> Any:
    """
    Recursively sanitize sensitive data from dictionaries and lists.

    Args:
        data: The data structure to sanitize
        sensitive_fields: Set of field names to sanitize (defaults to SENSITIVE_FIELDS)
        max_depth: Maximum recursion depth to prevent stack overflow

    Returns:
        Sanitized copy of the data
    """
    if max_depth <= 0:
        return data

    fields = sensitive_fields or SENSITIVE_FIELDS

    if isinstance(data, dict):
        return {
            key: (
                SANITIZED_VALUE
                if key.lower() in fields
                else sanitize_sensitive_data(value, fields, max_depth - 1)
            )
            for key, value in data.items()
        }
    elif isinstance(data, list):
        return [sanitize_sensitive_data(item, fields, max_depth - 1) for item in data]
    elif isinstance(data, str):
        # Check if string looks like a JWT or API key
        if len(data) > 50 and ("." in data or data.startswith("ey")):
            return SANITIZED_VALUE
        return data
    else:
        return data


def add_app_context(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add application context to log events."""
    event_dict["app"] = "consorcio-canalero-gee"
    event_dict["service"] = "backend"
    return event_dict


def sanitize_event(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Sanitize sensitive data from log events."""
    return sanitize_sensitive_data(event_dict)


def configure_structlog(
    json_format: bool = True,
    log_level: str = "INFO",
) -> None:
    """
    Configure structlog with appropriate processors.

    Args:
        json_format: Whether to output JSON (True for production) or console format
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Shared processors for all configurations
    shared_processors: List[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        add_app_context,
        sanitize_event,
    ]

    if json_format:
        # Production: JSON output
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        # Development: Pretty console output
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Also configure uvicorn loggers
    for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.addHandler(handler)


def get_logger(name: str = "app") -> structlog.stdlib.BoundLogger:
    """
    Get a configured structlog logger.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


# Initialize logging on module import
# Will be reconfigured in main.py with proper settings
configure_structlog(json_format=False, log_level="INFO")


class RequestIdMiddleware:
    """
    Middleware to add request_id to all logs for request tracing.

    Usage:
        app.add_middleware(RequestIdMiddleware)
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        import uuid

        if scope["type"] == "http":
            request_id = str(uuid.uuid4())[:8]

            # Bind request_id to structlog context
            structlog.contextvars.clear_contextvars()
            structlog.contextvars.bind_contextvars(request_id=request_id)

            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"x-request-id", request_id.encode()))
                    message["headers"] = headers
                await send(message)

            await self.app(scope, receive, send_wrapper)
        else:
            await self.app(scope, receive, send)
