from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        error_code: str = "application_error",
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.data = data or {}


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", *, data: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            status_code=404,
            error_code="not_found",
            data=data,
        )


class BadRequestError(AppError):
    def __init__(self, message: str = "Bad request", *, data: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            status_code=400,
            error_code="bad_request",
            data=data,
        )


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Unauthorized", *, data: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            status_code=401,
            error_code="unauthorized",
            data=data,
        )


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden", *, data: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            status_code=403,
            error_code="forbidden",
            data=data,
        )


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict", *, data: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            status_code=409,
            error_code="conflict",
            data=data,
        )
