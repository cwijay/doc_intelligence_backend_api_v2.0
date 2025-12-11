import logging
import logging.config
import asyncio
import structlog

from app.core.config import settings


def configure_logging() -> None:
    """Configure application logging based on settings."""

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            (
                structlog.processors.JSONRenderer()
                if settings.LOG_FORMAT == "json"
                else structlog.dev.ConsoleRenderer()
            ),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    if settings.LOG_FORMAT == "json":
        formatter_class = "pythonjsonlogger.jsonlogger.JsonFormatter"
        format_string = "%(asctime)s %(name)s %(levelname)s %(message)s"
    else:
        formatter_class = "logging.Formatter"
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Base logging configuration
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "health_check_filter": {
                "()": "app.core.logging.HealthCheckFilter",
            },
        },
        "formatters": {
            "default": {
                "class": formatter_class,
                "format": format_string,
            },
            "access": {
                "class": formatter_class,
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "filters": ["health_check_filter"],
            },
        },
        "loggers": {
            "": {
                "level": settings.LOG_LEVEL,
                "handlers": ["default"],
                "propagate": False,
            },
            "uvicorn.error": {
                "level": "INFO",
                "handlers": ["default"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["access"],
                "propagate": False,
            },
            # Third-party loggers
            "httpx": {
                "level": "WARNING",
                "handlers": ["default"],
                "propagate": False,
            },
            "google": {
                "level": "WARNING",
                "handlers": ["default"],
                "propagate": False,
            },
            "urllib3": {
                "level": "WARNING",
                "handlers": ["default"],
                "propagate": False,
            },
            # Suppress nest_asyncio patch messages
            "nest_asyncio": {
                "level": "ERROR",
                "handlers": ["default"],
                "propagate": False,
            },
        },
    }

    # Note: File logging removed for simplified setup

    # Apply configuration
    logging.config.dictConfig(logging_config)

    # Set log levels for specific loggers based on environment
    if not settings.DEBUG:
        # Production: reduce verbosity
        logging.getLogger("asyncio").setLevel(logging.WARNING)
        logging.getLogger("concurrent.futures").setLevel(logging.WARNING)


class RequestLoggingMiddleware:
    """Middleware for logging HTTP requests and responses."""

    def __init__(self, app):
        self.app = app
        self.logger = structlog.get_logger("request")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Skip logging for health check requests to reduce log noise
        is_health_check = scope["path"] in ["/health", "/ready", "/live"]

        # Extract request info
        request_info = {
            "method": scope["method"],
            "path": scope["path"],
            "query_string": scope.get("query_string", b"").decode(),
            "headers": {
                key.decode(): value.decode()
                for key, value in scope.get("headers", [])
                if key.lower()
                in [b"user-agent", b"content-type", b"authorization", b"content-length"]
            },
        }

        # Add special handling for file uploads
        content_type = ""
        for key, value in scope.get("headers", []):
            if key.lower() == b"content-type":
                content_type = value.decode()
                break

        if "multipart/form-data" in content_type:
            request_info["is_file_upload"] = True

        # Remove sensitive data from headers
        if "authorization" in request_info["headers"]:
            request_info["headers"]["authorization"] = "***"

        # Log request - skip health checks to reduce noise
        if not is_health_check:
            if request_info["method"] == "POST":
                self.logger.info("POST request detected", **request_info)
            else:
                self.logger.info("Request started", **request_info)

        # Process request - record start time when request begins
        start_time = asyncio.get_event_loop().time()

        async def send_wrapper(message):
            nonlocal start_time

            if message["type"] == "http.response.start":
                status_code = message["status"]

                # Log response - skip health checks to reduce noise
                if not is_health_check:
                    response_info = {
                        **request_info,
                        "status_code": status_code,
                        "response_headers": {
                            key.decode(): value.decode()
                            for key, value in message.get("headers", [])
                            if key.lower() in [b"content-type", b"content-length"]
                        },
                    }

                    self.logger.info("Response started", **response_info)

            elif message["type"] == "http.response.body" and not message.get(
                "more_body", False
            ):
                # Request completed - calculate total duration from request start
                duration = asyncio.get_event_loop().time() - start_time

                # Skip completion logging for health checks to reduce noise
                if not is_health_check:
                    self.logger.info(
                        "Request completed",
                        method=request_info["method"],
                        path=request_info["path"],
                        duration=round(duration, 4),
                    )

            await send(message)

        await self.app(scope, receive, send_wrapper)


class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to log records."""

    def filter(self, record):
        # Get correlation ID from context (e.g., from FastAPI request state)
        correlation_id = getattr(record, "correlation_id", None)
        if not correlation_id:
            import uuid

            correlation_id = str(uuid.uuid4())[:8]

        record.correlation_id = correlation_id
        return True


class HealthCheckFilter(logging.Filter):
    """Filter out health check requests from uvicorn access logs."""

    def filter(self, record):
        # Check if the log record contains health check endpoints
        message = getattr(record, "getMessage", lambda: "")()
        if callable(message):
            message = message()

        # Filter out health check endpoints
        health_endpoints = ["/health", "/ready", "/live"]
        for endpoint in health_endpoints:
            if endpoint in message:
                return False

        return True


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def setup_request_logging(app):
    """Setup request logging middleware."""
    if settings.DEBUG:
        app.add_middleware(RequestLoggingMiddleware)


# Application-specific loggers
def get_api_logger() -> structlog.BoundLogger:
    """Get API logger."""
    return get_logger("api")


def get_db_logger() -> structlog.BoundLogger:
    """Get database logger."""
    return get_logger("database")


def get_auth_logger() -> structlog.BoundLogger:
    """Get authentication logger."""
    return get_logger("auth")


def get_service_logger(service_name: str) -> structlog.BoundLogger:
    """Get service-specific logger."""
    return get_logger(f"service.{service_name}")
