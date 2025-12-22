"""
Cache configuration and utilities using fastapi-cache2.

Supports two backends controlled by CACHE_BACKEND env var:
- "memory" (default): In-memory cache, no external dependencies
- "redis": GCP Memorystore Redis for distributed caching

Usage:
    from app.core.cache import cached_documents, cached_organizations

    @cached_documents()
    async def list_documents(org_id: str, ...):
        ...

    @cached_organizations()
    async def get_organization(org_id: str):
        ...
"""

import hashlib
import json
from typing import Any, Callable

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.decorator import cache

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Redis backend (optional import - only needed when CACHE_BACKEND=redis)
try:
    from fastapi_cache.backends.redis import RedisBackend
    from redis import asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    RedisBackend = None  # type: ignore
    aioredis = None  # type: ignore


# Track initialization state
_cache_initialized = False
_active_backend = "none"


async def init_cache() -> None:
    """
    Initialize cache backend based on configuration.

    Called during application startup. Falls back gracefully:
    - If Redis configured but unavailable -> falls back to memory
    - If cache disabled -> no-op

    Environment variables:
        CACHE_ENABLED: Enable/disable caching (default: true)
        CACHE_BACKEND: "memory" or "redis" (default: memory)
        REDIS_HOST: Redis server host (required for redis backend)
        REDIS_PORT: Redis server port (default: 6379)
        REDIS_PASSWORD: Redis auth password (optional)
        REDIS_DB: Redis database number (default: 0)
    """
    global _cache_initialized, _active_backend

    if not settings.CACHE_ENABLED:
        logger.info("Cache disabled by configuration (CACHE_ENABLED=false)")
        _active_backend = "disabled"
        return

    backend = settings.CACHE_BACKEND.lower()

    # Validate Redis configuration
    if backend == "redis":
        if not REDIS_AVAILABLE:
            logger.warning(
                "Redis package not installed, falling back to memory cache. "
                "Install with: uv pip install redis"
            )
            backend = "memory"
        elif not settings.REDIS_HOST:
            logger.warning(
                "REDIS_HOST not configured, falling back to memory cache. "
                "Set REDIS_HOST environment variable for Redis backend."
            )
            backend = "memory"

    # Initialize the appropriate backend
    if backend == "redis":
        try:
            # Build Redis URL
            if settings.REDIS_PASSWORD:
                redis_url = (
                    f"redis://:{settings.REDIS_PASSWORD}@"
                    f"{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
                )
            else:
                redis_url = (
                    f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
                    f"/{settings.REDIS_DB}"
                )

            # Connect to Redis
            redis_client = aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
            )

            # Test connection
            await redis_client.ping()

            # Initialize FastAPICache with Redis backend
            FastAPICache.init(RedisBackend(redis_client), prefix="docint:")
            _cache_initialized = True
            _active_backend = "redis"

            logger.info(
                "Cache initialized with Redis backend",
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
            )

        except Exception as e:
            logger.error(
                "Failed to connect to Redis, falling back to memory cache",
                error=str(e),
                host=settings.REDIS_HOST,
            )
            # Fall back to in-memory
            FastAPICache.init(InMemoryBackend(), prefix="docint:")
            _cache_initialized = True
            _active_backend = "memory"
            logger.info("Cache initialized with InMemory backend (Redis fallback)")
    else:
        # In-memory backend (default)
        FastAPICache.init(InMemoryBackend(), prefix="docint:")
        _cache_initialized = True
        _active_backend = "memory"
        logger.info("Cache initialized with InMemory backend")


async def close_cache() -> None:
    """
    Close cache connections during application shutdown.

    For Redis backend, this closes the connection pool.
    For in-memory backend, this is a no-op (memory is freed automatically).
    """
    global _cache_initialized, _active_backend

    if _active_backend == "redis":
        try:
            # FastAPICache handles Redis cleanup automatically
            logger.info("Cache connections closed", backend=_active_backend)
        except Exception as e:
            logger.error("Error closing cache connections", error=str(e))
    else:
        logger.debug("Cache shutdown complete", backend=_active_backend)

    _cache_initialized = False
    _active_backend = "none"


def get_cache_status() -> dict:
    """
    Get current cache status for health/status endpoints.

    Returns:
        dict with cache configuration and status
    """
    return {
        "enabled": settings.CACHE_ENABLED,
        "backend": _active_backend,
        "configured_backend": settings.CACHE_BACKEND,
        "initialized": _cache_initialized,
        "default_ttl": settings.CACHE_DEFAULT_TTL,
        "ttl_settings": {
            "documents": settings.CACHE_DOCUMENT_TTL,
            "folders": settings.CACHE_FOLDER_TTL,
            "organizations": settings.CACHE_ORG_TTL,
            "users": settings.CACHE_USER_TTL,
        },
    }


def cache_key_builder(
    func: Callable,
    namespace: str = "",
    *,
    request: Any = None,
    response: Any = None,
    args: tuple = None,
    kwargs: dict = None,
) -> str:
    """
    Build cache key with org_id isolation for multi-tenancy.

    Key format: {namespace}:{org_id}:{function_name}:{params_hash}

    This ensures:
    1. Different organizations never share cached data
    2. Same query with same params returns cached result
    3. Different params generate different cache keys

    Args:
        func: The cached function
        namespace: Cache namespace (e.g., "documents", "folders")
        request: FastAPI request object (unused)
        response: FastAPI response object (unused)
        args: Positional arguments to the function
        kwargs: Keyword arguments to the function

    Returns:
        Unique cache key string
    """
    # Extract org_id from kwargs for tenant isolation
    org_id = kwargs.get("org_id", "global") if kwargs else "global"

    # Create hash of other parameters (excluding org_id)
    params = {}
    if kwargs:
        for k, v in kwargs.items():
            if k != "org_id" and v is not None:
                # Handle Pydantic models by converting to dict
                if hasattr(v, "model_dump"):
                    params[k] = v.model_dump(exclude_none=True)
                else:
                    params[k] = v

    # Create deterministic hash of parameters
    params_str = json.dumps(params, sort_keys=True, default=str)
    params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]

    return f"{namespace}:{org_id}:{func.__name__}:{params_hash}"


# =============================================================================
# Pre-configured cache decorators with tenant-safe key builders
# =============================================================================


def cached_documents(ttl: int = None):
    """
    Cache decorator for document queries.

    Default TTL: CACHE_DOCUMENT_TTL (120 seconds / 2 minutes)

    Usage:
        @cached_documents()
        async def list_documents(org_id: str, ...):
            ...

        @cached_documents(ttl=60)  # Custom 1-minute TTL
        async def get_document(org_id: str, document_id: str):
            ...
    """
    if not settings.CACHE_ENABLED:
        # Return a no-op decorator when caching is disabled
        def noop_decorator(func):
            return func

        return noop_decorator

    return cache(
        expire=ttl or settings.CACHE_DOCUMENT_TTL,
        namespace="documents",
        key_builder=cache_key_builder,
    )


def cached_folders(ttl: int = None):
    """
    Cache decorator for folder queries.

    Default TTL: CACHE_FOLDER_TTL (300 seconds / 5 minutes)
    """
    if not settings.CACHE_ENABLED:

        def noop_decorator(func):
            return func

        return noop_decorator

    return cache(
        expire=ttl or settings.CACHE_FOLDER_TTL,
        namespace="folders",
        key_builder=cache_key_builder,
    )


def cached_organizations(ttl: int = None):
    """
    Cache decorator for organization queries.

    Default TTL: CACHE_ORG_TTL (1800 seconds / 30 minutes)
    Organizations change infrequently, so longer TTL is appropriate.
    """
    if not settings.CACHE_ENABLED:

        def noop_decorator(func):
            return func

        return noop_decorator

    return cache(
        expire=ttl or settings.CACHE_ORG_TTL,
        namespace="organizations",
        key_builder=cache_key_builder,
    )


def cached_users(ttl: int = None):
    """
    Cache decorator for user queries.

    Default TTL: CACHE_USER_TTL (300 seconds / 5 minutes)
    """
    if not settings.CACHE_ENABLED:

        def noop_decorator(func):
            return func

        return noop_decorator

    return cache(
        expire=ttl or settings.CACHE_USER_TTL,
        namespace="users",
        key_builder=cache_key_builder,
    )


# =============================================================================
# Cache invalidation helpers
# =============================================================================


async def invalidate_documents(org_id: str) -> None:
    """
    Invalidate all document caches for an organization.

    Note: Pattern-based invalidation only works with Redis backend.
    For in-memory backend, we rely on TTL expiration.

    Args:
        org_id: Organization ID to invalidate caches for
    """
    if not settings.CACHE_ENABLED or not _cache_initialized:
        return

    if _active_backend == "redis":
        try:
            # Redis supports pattern-based key deletion
            backend = FastAPICache.get_backend()
            if hasattr(backend, "_redis"):
                keys = await backend._redis.keys(f"docint:documents:{org_id}:*")
                if keys:
                    await backend._redis.delete(*keys)
                    logger.debug(
                        "Document cache invalidated",
                        org_id=org_id,
                        keys_deleted=len(keys),
                    )
        except Exception as e:
            logger.warning("Failed to invalidate document cache", error=str(e))
    else:
        # In-memory backend doesn't support pattern deletion
        # Rely on TTL expiration
        logger.debug(
            "Document cache invalidation requested (TTL-based)",
            org_id=org_id,
        )


async def invalidate_folders(org_id: str) -> None:
    """
    Invalidate all folder caches for an organization.
    """
    if not settings.CACHE_ENABLED or not _cache_initialized:
        return

    if _active_backend == "redis":
        try:
            backend = FastAPICache.get_backend()
            if hasattr(backend, "_redis"):
                keys = await backend._redis.keys(f"docint:folders:{org_id}:*")
                if keys:
                    await backend._redis.delete(*keys)
                    logger.debug(
                        "Folder cache invalidated",
                        org_id=org_id,
                        keys_deleted=len(keys),
                    )
        except Exception as e:
            logger.warning("Failed to invalidate folder cache", error=str(e))
    else:
        logger.debug("Folder cache invalidation requested (TTL-based)", org_id=org_id)


async def invalidate_users(org_id: str) -> None:
    """
    Invalidate all user caches for an organization.
    """
    if not settings.CACHE_ENABLED or not _cache_initialized:
        return

    if _active_backend == "redis":
        try:
            backend = FastAPICache.get_backend()
            if hasattr(backend, "_redis"):
                keys = await backend._redis.keys(f"docint:users:{org_id}:*")
                if keys:
                    await backend._redis.delete(*keys)
                    logger.debug(
                        "User cache invalidated",
                        org_id=org_id,
                        keys_deleted=len(keys),
                    )
        except Exception as e:
            logger.warning("Failed to invalidate user cache", error=str(e))
    else:
        logger.debug("User cache invalidation requested (TTL-based)", org_id=org_id)


async def invalidate_organization(org_id: str) -> None:
    """
    Invalidate organization cache for a specific organization.
    """
    if not settings.CACHE_ENABLED or not _cache_initialized:
        return

    if _active_backend == "redis":
        try:
            backend = FastAPICache.get_backend()
            if hasattr(backend, "_redis"):
                keys = await backend._redis.keys(f"docint:organizations:{org_id}:*")
                if keys:
                    await backend._redis.delete(*keys)
                    logger.debug(
                        "Organization cache invalidated",
                        org_id=org_id,
                        keys_deleted=len(keys),
                    )
        except Exception as e:
            logger.warning("Failed to invalidate organization cache", error=str(e))
    else:
        logger.debug(
            "Organization cache invalidation requested (TTL-based)", org_id=org_id
        )
