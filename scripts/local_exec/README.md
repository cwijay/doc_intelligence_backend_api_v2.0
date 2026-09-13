# Local execution

Run the backend API **on your machine** against **Docker infrastructure**.

Infrastructure and application are deliberately separate: the containers hold
state you want to keep across restarts, while the API is the thing you edit, so
it runs natively with hot reload.

```bash
./setup_infra.sh     # once — Postgres + Redis, schema, seed data
./start_backend.sh   # every time you want the API
```

---

## What each script does

| Script | Purpose |
|---|---|
| `setup_infra.sh` | Starts Postgres (pgvector) and Redis, waits for health, creates the schema, seeds subscription tiers, inserts a bootstrap organization. Idempotent. |
| `start_backend.sh` | Runs the API with uvicorn on the host, wired to that infrastructure. Hot reload on by default. |
| `stop_infra.sh` | Stops the containers. Data survives unless you pass `--wipe`. |

`setup_infra.sh` generates `.env.local` on first run with a random database
password and JWT secrets. It is gitignored and both scripts read it, so the API
and the database always agree on credentials. Delete it and re-run to rotate.

## Endpoints and ports

```
API        http://127.0.0.1:8000       /docs is live (ENVIRONMENT=development)
Postgres   127.0.0.1:15432             db doc_intelligence
Redis      127.0.0.1:16379
```

Non-default ports are deliberate. Other projects commonly hold 5432 and 6379,
and pointing the API at a stranger's database fails in confusing ways. Override
via `POSTGRES_HOST_PORT` / `REDIS_HOST_PORT` in `.env.local` if these clash too.

This stack uses its own compose project (`b2blocal`), its own volumes and its
own subnet (`10.56.0.0/24`), so it never collides with `../../../biz2bricks_stack`
— the full-platform deployment — or anything else on the same Docker daemon.

## Creating your first user

Registration requires an **existing** `organization_id`, and the organization
endpoints are not usable for bootstrapping a fresh database, so `setup_infra.sh`
inserts one for you. Its ID is `BOOTSTRAP_ORG_ID` in `.env.local`.

```bash
source scripts/local_exec/.env.local

curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"you@example.com\",\"password\":\"DevPass123!\",
       \"full_name\":\"Your Name\",\"username\":\"you\",
       \"organization_id\":\"$BOOTSTRAP_ORG_ID\"}"
```

`full_name` accepts letters, spaces, apostrophes and hyphens only — a digit
produces a generic "Registration failed due to system error", which is easy to
misread as a server problem.

## Useful commands

```bash
./setup_infra.sh --status                # containers + table/org/user counts
./setup_infra.sh --wipe                  # rebuild from empty (asks first)
./stop_infra.sh                          # stop, keep data
docker exec -it b2blocal-postgres psql -U postgres -d doc_intelligence
docker logs -f b2blocal-postgres
./start_backend.sh --port 8080 --no-reload
```

## What does not work locally

- **Document upload and download.** No GCS credentials are configured, so
  `GCSClient` stays inert. The API boots and everything else works; document
  endpoints return errors. Fixed either by configuring GCS or by the planned
  MinIO migration.
- **AI features.** The AI service is a separate application and is not started
  here. It also needs provider API keys.

## Notes

**Redis is real, not a fallback.** `start_backend.sh` runs `uv sync --extra redis`
because `redis` is an optional extra in `pyproject.toml`. Without it the cache
layer silently degrades to in-memory, which hides Redis-specific bugs — one of
which previously broke registration on every second attempt.

**`start_backend.sh` refuses to bind to anything but loopback.** The `users`,
`folders` and `organizations` routers currently carry no authentication
dependency, including their `DELETE` routes, and `org_id` is a plain path
parameter with no tenant check. Until that is fixed, binding this API to a
network interface exposes destructive cross-tenant operations to anyone who can
reach it. `--i-know` overrides the guard; think before using it.
