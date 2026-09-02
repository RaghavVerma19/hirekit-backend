import logging
import sys
import structlog
from app.core.config import settings


def setup_logging() -> None:
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.ENVIRONMENT == "development":
        # Human-readable colored console logging in dev
        processors = shared_processors + [structlog.dev.ConsoleRenderer()]
    else:
        # Structured JSON logging in production
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.DEBUG else logging.INFO
        ),
        cache_logger_on_first_use=True,
    )

    # Bridge standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
    )


logger = structlog.get_logger()
