from typing import Any

from fastapi import HTTPException, status


class AppError(HTTPException):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"

    def __init__(self, message: str, field_errors: dict[str, str] | None = None) -> None:
        detail: dict[str, Any] = {"code": self.code, "message": message}
        if field_errors:
            detail["field_errors"] = field_errors
        super().__init__(status_code=self.status_code, detail=detail)


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "VALIDATION_ERROR"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "REFERENCE_NOT_FOUND"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class AuthRequiredError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "AUTH_REQUIRED"

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message)


class AccessDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "ACCESS_DENIED"

    def __init__(self, message: str = "You do not have permission to perform this action") -> None:
        super().__init__(message)


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
