"""
Regression test for the Redis cache backend decode bug.

Bug: app/core/cache.py passed decode_responses=True to aioredis.from_url().
fastapi-cache2's RedisBackend uses JsonCoder, whose decode() calls
value.decode() expecting bytes from the Redis client. With
decode_responses=True the client hands back str, so JsonCoder.decode()
raises AttributeError: 'str' object has no attribute 'decode' on every
cache HIT (the first call for a key always succeeds because it's a MISS
that falls through to the wrapped function; the SECOND call for the same
key is what explodes).

This is invisible with CACHE_BACKEND=memory because InMemoryBackend stores
Python objects by reference and never serializes/deserializes through
JsonCoder.

This test exercises a real cache round trip against a live Redis instance:
write (miss) then read (hit). The second call is the one that reproduces
the AttributeError before the fix.
"""

import os
import uuid

import pytest
import pytest_asyncio

# A Redis instance is expected on the host at 127.0.0.1:6379. It belongs to
# another project on this machine (a `--requirepass` protected container),
# so this test uses a distinct key prefix and a dedicated logical DB (15)
# and only ever deletes the keys it created itself. It must never call
# FLUSHALL/FLUSHDB.
TEST_REDIS_HOST = os.environ.get("TEST_REDIS_HOST", "127.0.0.1")
TEST_REDIS_PORT = int(os.environ.get("TEST_REDIS_PORT", "6379"))
TEST_REDIS_PASSWORD = os.environ.get("TEST_REDIS_PASSWORD", "myredissecret")
TEST_REDIS_DB = int(os.environ.get("TEST_REDIS_DB", "15"))

redis = pytest.importorskip("redis", reason="redis package not installed")


def _redis_available() -> bool:
    """Best-effort synchronous check so we can skip cleanly, not fail."""
    try:
        client = redis.Redis(
            host=TEST_REDIS_HOST,
            port=TEST_REDIS_PORT,
            password=TEST_REDIS_PASSWORD,
            db=TEST_REDIS_DB,
            socket_connect_timeout=1,
        )
        client.ping()
        client.close()
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _redis_available(),
        reason=(
            f"No live Redis reachable at {TEST_REDIS_HOST}:{TEST_REDIS_PORT} "
            "(db=TEST_REDIS_DB) - skipping Redis cache round-trip test"
        ),
    ),
]


@pytest_asyncio.fixture
async def redis_cache_env(monkeypatch):
    """
    Point the app's cache layer at the test Redis DB/prefix, initialize a
    real RedisBackend-backed FastAPICache, and tear everything down
    (including only the keys this test created) afterwards.
    """
    from app.core import cache as cache_module
    from fastapi_cache import FastAPICache

    monkeypatch.setattr(cache_module.settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(cache_module.settings, "CACHE_BACKEND", "redis")
    monkeypatch.setattr(cache_module.settings, "REDIS_HOST", TEST_REDIS_HOST)
    monkeypatch.setattr(cache_module.settings, "REDIS_PORT", TEST_REDIS_PORT)
    monkeypatch.setattr(cache_module.settings, "REDIS_PASSWORD", TEST_REDIS_PASSWORD)
    monkeypatch.setattr(cache_module.settings, "REDIS_DB", TEST_REDIS_DB)

    # Unique prefix per test run so runs never collide with each other or
    # with anything else living in this shared Redis instance.
    test_prefix = f"docint-test:{uuid.uuid4().hex}:"
    monkeypatch.setattr(FastAPICache, "_prefix", test_prefix, raising=False)

    await cache_module.init_cache()
    assert cache_module.get_cache_status()["backend"] == "redis", (
        "Test setup failed to reach the live Redis instance - "
        "cache fell back to memory backend"
    )

    yield cache_module

    # Cleanup: delete only keys created under this test's unique prefix.
    backend = FastAPICache.get_backend()
    redis_client = getattr(backend, "redis", None)
    if redis_client is not None:
        cursor = b"0"
        while True:
            cursor, keys = await redis_client.scan(
                cursor=cursor, match=f"{test_prefix}*", count=100
            )
            if keys:
                await redis_client.delete(*keys)
            if cursor in (b"0", 0):
                break

    await cache_module.close_cache()


@pytest.mark.asyncio
async def test_redis_cache_round_trip_survives_a_hit(redis_cache_env):
    """
    Decorate a trivial async function with the project's real caching
    decorator, call it twice with identical arguments, and confirm both
    calls return equal, correctly-typed results.

    Before the fix: the first call (MISS) succeeds and populates Redis;
    the second call (HIT) raises AttributeError from JsonCoder.decode()
    because decode_responses=True made the Redis client return str instead
    of the bytes JsonCoder expects.
    """
    cache_module = redis_cache_env
    call_count = 0

    @cache_module.cached_organizations(ttl=60)
    async def get_fake_org(org_id: str):
        nonlocal call_count
        call_count += 1
        return {"org_id": org_id, "name": "Bootstrap Test", "calls": call_count}

    org_id = f"test-org-{uuid.uuid4().hex[:8]}"

    first = await get_fake_org(org_id=org_id)
    assert first["org_id"] == org_id
    assert first["calls"] == 1

    # This second, identical call is a cache HIT. Pre-fix, RedisBackend's
    # JsonCoder.decode() raises AttributeError here because the client
    # returned a str, not bytes.
    second = await get_fake_org(org_id=org_id)

    assert second == first, "Cache HIT should return the exact cached value"
    assert call_count == 1, (
        "Wrapped function ran twice - the cache HIT did not return the "
        "cached value (or silently fell through after failing to decode it)"
    )
