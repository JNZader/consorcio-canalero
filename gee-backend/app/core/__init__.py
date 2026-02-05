"""
Core module for the Consorcio Canalero GEE Backend.
Contains logging, exceptions, and rate limiting utilities.
"""

from app.core.logging import get_logger, sanitize_sensitive_data
from app.core.exceptions import (
    AppException,
    ReportNotFoundError,
    SuggestionNotFoundError,
    ValidationError,
    RateLimitExceededError,
)
from app.core.rate_limit import DistributedRateLimiter

__all__ = [
    "get_logger",
    "sanitize_sensitive_data",
    "AppException",
    "ReportNotFoundError",
    "SuggestionNotFoundError",
    "ValidationError",
    "RateLimitExceededError",
    "DistributedRateLimiter",
]
