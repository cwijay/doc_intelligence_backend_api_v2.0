# Redis cache decode bug — TDD fix report

## Root cause

`app/core/cache.py:109` (now with a comment) passed `decode_responses=True`
to `aioredis.from_url()`. fastapi-cache2's `RedisBackend` uses `JsonCoder`,
whose `decode()` does `json.loads(value.decode(), ...)` — it requires
`bytes`. With `decode_responses=True` the redis-py client hands back `str`
instead, so every cache HIT raised:

```
AttributeError: 'str' object has no attribute 'decode'
```

at `fastapi_cache/coder.py:110`. The first request for a given key is a
MISS (falls through to the real function, no decode involved) so it always
succeeds; the second and every later request for that key is a HIT and
explodes. In `app/services/auth_service.py` (~lines 756-769) this was
silently rewritten by a bare `except Exception` into
`RegistrationError("Invalid organization selected")`, hiding the real
cause; login failed the same way with "Invalid email or password" for
valid credentials.

This was invisible with `CACHE_BACKEND=memory` because `InMemoryBackend`
stores Python objects by reference and never serializes/deserializes
through `JsonCoder` — there is no decode step to fail.

## Fix

One line, `app/core/cache.py`:

```python
redis_client = aioredis.from_url(
    redis_url,
    encoding="utf-8",
    decode_responses=False,   # was True
)
```

`encoding="utf-8"` is kept as required. No other production code changed.
`CACHE_BACKEND` default remains `memory`.

## Step 1+2: regression test written first, confirmed FAILING

File: `tests/integration/test_cache_redis.py`, marked
`@pytest.mark.integration`, skips cleanly if no Redis is reachable at
`127.0.0.1:6379`/db 15. It decorates a trivial async function with the
real `cached_organizations()` decorator, calls it twice with identical
kwargs against a live Redis (a distinct `docint-test:<uuid>:` prefix per
run, `REDIS_DB=15`), and asserts the second (HIT) call returns the same,
correctly-typed value as the first (MISS) call. Cleanup deletes only keys
matching its own prefix; no FLUSHALL/FLUSHDB is ever called.

Command:
```
TEST_REDIS_PASSWORD=myredissecret uv run pytest tests/integration/test_cache_redis.py -v
```

Output (before the fix):
```
tests/integration/test_cache_redis.py::test_redis_cache_round_trip_survives_a_hit FAILED [100%]
...
    @classmethod
    def decode(cls, value: bytes) -> Any:
>       return json.loads(value.decode(), object_hook=object_hook)
                          ^^^^^^^^^^^^
E       AttributeError: 'str' object has no attribute 'decode'. Did you mean: 'encode'?

.venv/lib/python3.12/site-packages/fastapi_cache/coder.py:110: AttributeError
============================== 1 failed in 0.39s ===============================
```
This reproduces the exact bug from the diagnosis, at the exact library
line, on the second (cache-hit) call.

## Step 3: applied the one-line fix

`decode_responses=True` -> `decode_responses=False` in
`app/core/cache.py`, with an explanatory comment.

## Step 4: regression test re-run, confirmed PASSING

Command:
```
TEST_REDIS_PASSWORD=myredissecret uv run pytest tests/integration/test_cache_redis.py -v
```

Output (after the fix):
```
tests/integration/test_cache_redis.py::test_redis_cache_round_trip_survives_a_hit PASSED [100%]
============================== 1 passed in 3.59s ===============================
```

Verified no leftover keys after the test run:
```
$ python -c "import redis; c=redis.Redis(host='127.0.0.1', port=6379, password='myredissecret', db=15); print(c.keys('docint-test:*'))"
[]
```

## Step 5: existing suite, no regressions

Command: `TEST_REDIS_PASSWORD=myredissecret uv run pytest tests/ -q`

Before the fix (change stashed, new test file excluded so it can't fail
the "before" baseline for unrelated reasons):
```
24 failed, 163 passed, 185 warnings in 5.30s
```

After the fix (with the new test file included):
```
24 failed, 164 passed, 185 warnings in 10.35s
```

The 24 failing tests are byte-for-byte the same test IDs in both runs
(all in `tests/integration/api/test_auth.py`, `test_health.py`,
`test_users.py`, and `tests/integration/workflows/test_auth_workflow.py`)
— pre-existing failures unrelated to this change (not investigated further
per the task's scope; the cache fix introduces zero new failures and adds
exactly one new passing test).

## Step 6: live stack verification

```
cd ../biz2bricks_stack && docker compose up -d --build api
```
Only the `api` service was rebuilt/restarted; `postgres`, `redis`,
`litellm`, `ai`, `frontend`, `caddy` were left untouched (confirmed via
`docker compose up` output showing only `api` as "Recreated"/"Started").
Startup log confirms Redis-backed cache: `Cache initialized with Redis
backend backend=redis host=redis port=6379`.

Registered two users into the same existing org
(`e30cc41c-321a-4437-9ce7-02d3cb761536`, "Bootstrap Test") back to back,
without touching Redis in between:

Registration 1 — HTTP 201:
```
{"access_token":"223d2890-...","user":{"user_id":"5ec31110-5806-4b50-a26d-7f13d9b47fbe","email":"cachefix-test-1-1789282674@example.com","org_id":"e30cc41c-321a-4437-9ce7-02d3cb761536","org_name":"Bootstrap Test",...}}
```

Registration 2 — HTTP 201:
```
{"access_token":"8530aa58-...","user":{"user_id":"0d9a081f-6597-4d4a-8742-d9e00e848b20","email":"cachefix-test-2-1789282674@example.com","org_id":"e30cc41c-321a-4437-9ce7-02d3cb761536","org_name":"Bootstrap Test",...}}
```

Both succeeded. Pre-fix this pattern reproduced "Invalid organization
selected" on the second call (per the original diagnosis); post-fix both
calls succeed against the same live Redis-backed cache, confirming the
fix end to end.

## Notes on Redis instance used for the test

`127.0.0.1:6379` on the host is `infra-redis-1`, a different project's
`--requirepass`-protected container (the biz2bricks project's own Redis
publishes no host port by design). Per the task's explicit instruction to
use this host-reachable Redis with a distinct key prefix, the test
connects to it using its already-running `--requirepass` value
(`myredissecret`, read via `docker inspect`) against logical DB 15, uses a
per-run UUID key prefix, and deletes only the keys it created. No
FLUSHALL/FLUSHDB was called at any point.
