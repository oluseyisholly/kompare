from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError
from app.core.logger import logger


def _error_response(
    *,
    status_code: int,
    message: str,
    error_code: str,
    data: dict[str, Any] | None = None,
) -> JSONResponse:
    payload = {
        "responseCode": status_code,
        "message": message,
        "data": {
            "error": error_code,
            **(data or {}),
        },
    }
    return JSONResponse(status_code=status_code, content=payload)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error_response(
            status_code=exc.status_code,
            message=exc.message,
            error_code=exc.error_code,
            data=exc.data,
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        message = detail if isinstance(detail, str) else "Request failed"
        data = detail if isinstance(detail, dict) else {"detail": detail}
        return _error_response(
            status_code=exc.status_code,
            message=message,
            error_code="http_error",
            data=data,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            status_code=422,
            message="Validation failed",
            error_code="validation_error",
            data={"details": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return _error_response(
            status_code=500,
            message="Internal server error",
            error_code="internal_server_error",
        )
