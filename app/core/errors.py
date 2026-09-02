from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[Any] = None
    request_id: Optional[str] = None


class AppException(HTTPException):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.error_code = error_code
        self.message = message
        self.details = details


def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.warning(
            "validation_error",
            path=request.url.path,
            errors=exc.errors(),
            request_id=request_id,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error="VALIDATION_ERROR",
                message="Invalid request parameters or payload.",
                details=exc.errors(),
                request_id=request_id,
            ).model_dump(),
        )

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.info(
            "app_exception",
            path=request.url.path,
            error_code=exc.error_code,
            message=exc.message,
            status_code=exc.status_code,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=exc.error_code,
                message=exc.message,
                details=exc.details,
                request_id=request_id,
            ).model_dump(),
            headers=exc.headers,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        error_code = "HTTP_ERROR"
        message = str(exc.detail)

        # If detail was structured as a dict
        if isinstance(exc.detail, dict):
            error_code = exc.detail.get("error", "HTTP_ERROR")
            message = exc.detail.get("message", "An HTTP error occurred")

        logger.info(
            "http_exception",
            path=request.url.path,
            status_code=exc.status_code,
            message=message,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=error_code,
                message=message,
                request_id=request_id,
            ).model_dump(),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            error=str(exc),
            exc_info=exc,
            request_id=request_id,
        )
        resp = JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="INTERNAL_SERVER_ERROR",
                message="An unexpected error occurred. Our team has been notified.",
                request_id=request_id,
            ).model_dump(),
        )
        origin = request.headers.get("origin")
        if origin:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
        return resp
