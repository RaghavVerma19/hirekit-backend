from contextlib import asynccontextmanager
import time
import uuid
from typing import AsyncGenerator
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import structlog

from app import __version__
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.errors import setup_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestSizeLimitMiddleware, SecurityHeadersMiddleware
from app.db.redis import close_redis, get_redis_client

# Initialize Logging
setup_logging()
logger = structlog.get_logger()

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    logger.info("application_startup", environment=settings.ENVIRONMENT, version=__version__)
    
    # Pre-warm Redis connection
    try:
        redis = await get_redis_client()
        await redis.ping()
        logger.info("redis_connected")
    except Exception as e:
        logger.warning("redis_connection_failed", error=str(e))

    yield

    # Shutdown: Close Redis pool
    logger.info("application_shutdown")
    await close_redis()


def create_application() -> FastAPI:
    """FastAPI Application Factory."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Attach Rate Limiter to app state
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 1. Security Headers Middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # 2. Request Size Limit Middleware (max 10MB)
    app.add_middleware(RequestSizeLimitMiddleware)

    # Request ID and Timing Middleware
    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.perf_counter()
        response = await call_next(request)
        process_time = time.perf_counter() - start_time

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.4f}s"
        return response

    # 3. CORS Middleware (Outermost to wrap all responses including error handlers)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Setup Exception Handlers
    setup_exception_handlers(app)

    # Mount API Routers
    app.include_router(api_v1_router, prefix=settings.API_V1_STR)

    return app


app = create_application()
