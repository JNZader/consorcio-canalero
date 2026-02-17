"""
Custom exceptions for the Consorcio Canalero GEE Backend.
Provides structured error handling with proper status codes and messages.

NOTE: Only exceptions that are actually used are defined here.
Add new exceptions as needed when implementing new features.
"""

from typing import Any, Dict, Optional


class AppException(Exception):
    """
    Base exception for application-level errors.

    All custom exceptions should inherit from this class.
    Provides consistent error response format.
    """

    def __init__(
        self,
        message: str,
        code: str = "APP_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize application exception.

        Args:
            message: Human-readable error message
            code: Machine-readable error code
            status_code: HTTP status code
            details: Additional error details
        """
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON response."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


# ===========================================
# NOT FOUND ERRORS (404)
# ===========================================


class NotFoundError(AppException):
    """Base class for resource not found errors."""

    def __init__(
        self,
        message: str = "Recurso no encontrado",
        code: str = "NOT_FOUND",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ):
        details: Dict[str, Any] = {}
        if resource_type:
            details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id

        super().__init__(
            message=message,
            code=code,
            status_code=404,
            details=details,
        )


class ReportNotFoundError(NotFoundError):
    """Raised when a report (denuncia) is not found."""

    def __init__(self, report_id: str):
        super().__init__(
            message=f"Denuncia no encontrada: {report_id}",
            code="REPORT_NOT_FOUND",
            resource_type="report",
            resource_id=report_id,
        )


class SuggestionNotFoundError(NotFoundError):
    """Raised when a suggestion (sugerencia) is not found."""

    def __init__(self, suggestion_id: str):
        super().__init__(
            message=f"Sugerencia no encontrada: {suggestion_id}",
            code="SUGGESTION_NOT_FOUND",
            resource_type="suggestion",
            resource_id=suggestion_id,
        )


# ===========================================
# VALIDATION ERRORS (400)
# ===========================================


class ValidationError(AppException):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str = "Error de validacion",
        code: str = "VALIDATION_ERROR",
        field: Optional[str] = None,
        errors: Optional[list] = None,
    ):
        details: Dict[str, Any] = {}
        if field:
            details["field"] = field
        if errors:
            details["errors"] = errors

        super().__init__(
            message=message,
            code=code,
            status_code=400,
            details=details,
        )


# ===========================================
# RATE LIMITING ERRORS (429)
# ===========================================


class RateLimitExceededError(AppException):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Demasiadas solicitudes",
        retry_after: int = 60,
        limit: Optional[int] = None,
    ):
        details: Dict[str, Any] = {"retry_after": retry_after}
        if limit:
            details["limit"] = limit

        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details=details,
        )
        self.retry_after = retry_after


# ===========================================
# ERROR SANITIZATION HELPERS
# ===========================================


def sanitize_error_message(
    error: Exception, default_message: str = "Error interno del servidor"
) -> str:
    """
    Sanitize an error message for client exposure.

    Prevents leaking sensitive information like file paths, stack traces,
    or internal implementation details.

    Args:
        error: The exception to sanitize
        default_message: Default message if sanitization required

    Returns:
        A safe error message for client response
    """
    error_str = str(error)

    # Patterns that indicate sensitive information
    sensitive_patterns = [
        "/home/",
        "/var/",
        "/app/",
        "\\Users\\",
        "C:\\",
        "Traceback",
        'File "',
        "line ",
        "raise ",
        "password",
        "secret",
        "token",
        "credential",
        "api_key",
        "apikey",
    ]

    # Check if error contains sensitive info
    error_lower = error_str.lower()
    for pattern in sensitive_patterns:
        if pattern.lower() in error_lower:
            return default_message

    # If error is too long, it might contain stack trace
    if len(error_str) > 200:
        return default_message

    return error_str


def get_safe_error_detail(error: Exception, operation: str) -> str:
    """
    Get a safe error detail string for HTTP exceptions.

    Args:
        error: The exception
        operation: Description of the operation that failed

    Returns:
        Safe error message for HTTPException detail
    """
    safe_msg = sanitize_error_message(error, f"Error en {operation}")
    return (
        f"Error en {operation}: {safe_msg}"
        if safe_msg != f"Error en {operation}"
        else safe_msg
    )
