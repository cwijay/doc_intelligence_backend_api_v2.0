"""Health check and monitoring endpoints.

Provides endpoints for:
- Basic health checks
- Detailed service status
- Kubernetes readiness/liveness probes
- Basic metrics
"""

import time
from typing import Dict, Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import get_logger
from app.core.db_client import db
from app.core.cache import get_cache_status
from app.core.gcs_client import get_gcs_status

logger = get_logger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint with API information."""
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "running",
        "docs": "/docs" if settings.DEBUG else None,
        "redoc": "/redoc" if settings.DEBUG else None,
        "health": "/health",
        "status_endpoint": "/status",
    }


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint with database connectivity verification.

    Returns 200 if healthy, 503 if database is unavailable.
    Used by load balancers and orchestration tools.
    """
    try:
        # If database is disabled, report healthy without DB check
        if not settings.DATABASE_ENABLED:
            return {
                "status": "healthy",
                "timestamp": time.time(),
                "version": settings.VERSION,
                "environment": settings.ENVIRONMENT,
                "database": "disabled",
            }

        # Check database connection (critical for service health)
        db_available = await db.test_connection(timeout=5.0)

        if not db_available:
            logger.warning("Health check failed: database unavailable")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "unhealthy",
                    "timestamp": time.time(),
                    "version": settings.VERSION,
                    "database": "unavailable",
                },
            )

        return {
            "status": "healthy",
            "timestamp": time.time(),
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "database": "connected",
        }

    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "timestamp": time.time(),
                "version": settings.VERSION,
                "error": str(e),
            },
        )


@router.get("/status")
async def detailed_status() -> Dict[str, Any]:
    """Detailed status endpoint with service health checks."""
    try:
        # Get database health
        db_available = await db.test_connection(timeout=5.0)

        # Object storage health. "disabled" means storage was never configured
        # here, which is a valid deployment; only a configured-but-failed
        # client ("unavailable") is a fault, and it takes document upload and
        # download down with it.
        gcs = get_gcs_status()
        gcs_failed = gcs["status"] == "unavailable"

        # Overall status
        overall_status = "healthy" if db_available and not gcs_failed else "degraded"

        status_response = {
            "application": {
                "name": settings.PROJECT_NAME,
                "version": settings.VERSION,
                "environment": settings.ENVIRONMENT,
                "debug": settings.DEBUG,
                "status": overall_status,
            },
            "services": {
                "postgresql": {
                    "status": "connected" if db_available else "unavailable",
                    "enabled": settings.DATABASE_ENABLED,
                    "pool_size": settings.DB_POOL_SIZE,
                    "max_overflow": settings.DB_MAX_OVERFLOW,
                    "pool_stats": db.get_pool_stats(),
                },
                "cache": get_cache_status(),
                "gcs": gcs,
            },
            "configuration": {
                "cors_enabled": True,
                "cors_origins": settings.resolved_cors_origins,
                "api_prefix": settings.API_V1_STR,
                "log_level": settings.LOG_LEVEL,
                "log_format": settings.LOG_FORMAT,
            },
            "system": {
                "timestamp": time.time(),
                "uptime": time.time(),
            },
        }

        return status_response

    except Exception as e:
        logger.error("Status check failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "timestamp": time.time(), "error": str(e)},
        )


@router.get("/ready")
async def readiness_check() -> Dict[str, Any]:
    """Readiness probe endpoint for Kubernetes."""
    try:
        # Check if database is ready
        db_available = await db.test_connection(timeout=5.0)

        if not db_available:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "ready": False,
                    "reason": "Database not ready",
                    "timestamp": time.time(),
                },
            )

        return {"ready": True, "timestamp": time.time()}

    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"ready": False, "reason": str(e), "timestamp": time.time()},
        )


@router.get("/live")
async def liveness_check() -> Dict[str, Any]:
    """Liveness probe endpoint for Kubernetes."""
    return {"alive": True, "timestamp": time.time()}


@router.get("/metrics")
async def metrics() -> Dict[str, Any]:
    """Basic metrics endpoint."""
    try:
        return {
            "application": {
                "name": settings.PROJECT_NAME,
                "version": settings.VERSION,
                "uptime": time.time(),
            },
            "requests": {
                "total": "not_implemented",
                "errors": "not_implemented",
                "response_time": "not_implemented",
            },
            "postgresql": {
                "pool_size": settings.DB_POOL_SIZE,
                "max_overflow": settings.DB_MAX_OVERFLOW,
            },
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error("Metrics collection failed", error=str(e))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Metrics collection failed", "timestamp": time.time()},
        )
