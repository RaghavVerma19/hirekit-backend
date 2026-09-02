from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects incoming HTTP requests with bodies exceeding 10MB."""

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_CONTENT_LENGTH:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "PAYLOAD_TOO_LARGE",
                            "message": "Request payload exceeds maximum allowed size of 10MB.",
                        },
                    )
            except ValueError:
                pass

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces OWASP recommended security headers on all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        return response
