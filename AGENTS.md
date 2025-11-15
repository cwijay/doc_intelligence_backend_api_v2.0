# Repository Guidelines

## Project Structure & Module Organization
The backend lives in `document-intelligence-backend/` with FastAPI entrypoints in `app/main.py` and router packages under `app/api/`. Domain logic sits in `app/services/` and `app/models/`, with shared helpers in `app/utils/` and `app/core/` for config, logging, and clients. Acceptance docs and diagrams reside in `docs/`, while automated tests mirror the service layout in `tests/`. Deployment assets (Dockerfile, Cloud Build config, GCP scripts) stay alongside the code to keep infrastructure versioned with the API.

## Build, Test, and Development Commands
Install dependencies with `uv sync` (creates `.venv/`). Start the local API via `uv run uvicorn app.main:app --reload` or by executing `./run_dev.sh` to load `.env` defaults. Run the full test suite with `uv run pytest` and add `--cov` to capture coverage data. For linting and style checks, execute `uv run ruff check app tests` and `uv run black --check app tests` before pushing. Use `./deploy_full.sh` to build and push the Cloud Run image once CI has passed.

## Coding Style & Naming Conventions
Follow the default formatters: Black for auto-formatting (88-char line width) and Ruff for linting; fix issues with `uv run black app tests` and `uv run ruff --fix`. Prefer full type hints on function signatures and Pydantic models. Use UpperCamelCase for Pydantic models, snake_case for modules, functions, and async coroutine names, and UPPER_SNAKE_CASE for constants and environment variables. Co-locate API routes with their dependencies inside feature folders to keep imports explicit.

## Testing Guidelines
Write `pytest` tests under `tests/` that mirror the package path (e.g., `tests/services/test_document_service.py`). Name async tests with `async def test_*` and use `pytest.mark.asyncio` when required. Aim for meaningful coverage on service facades and Firestore integrations; mock Google clients via fixtures in `tests/conftest.py`. Run `uv run pytest -k "document"` for focused suites, and ensure smoke tests pass before requesting review.

## Commit & Pull Request Guidelines
Use concise, present-tense commit subjects similar to `Clean up localhost configuration` seen in history; group related changes per commit. Reference relevant issues in the commit body when applicable. Pull requests should include a short summary, testing notes (`uv run pytest`, linting results), and deployment considerations if Cloud Run configs change. Attach screenshots or API response samples when updating endpoints. Request at least one review and wait for CI green checks before merging.

## Security & Configuration Tips
Copy `deployment-config.example.json` and `production-env.yaml` when provisioning new environments; never commit secrets or service account keys. Update `cors-update.env` and `cloudbuild.yaml` in tandem with domain or bucket changes. Use Google IAM roles scoped by project and verify Cloud Run permissions via `python check_cloudrun_permissions.py` before deploying.
