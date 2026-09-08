"""Compatibility re-export. Prefer app.core.exceptions."""

from app.core.exceptions import (
    AccessDeniedError,
    AppError,
    AuthRequiredError,
    ConflictError,
    NotFoundError,
    RateLimitedError,
    ValidationError,
)

__all__ = [
    "AccessDeniedError",
    "AppError",
    "AuthRequiredError",
    "ConflictError",
    "NotFoundError",
    "RateLimitedError",
    "ValidationError",
]
