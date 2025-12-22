# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Document management platform built with FastAPI, featuring file upload, storage, and organization management. Integrates with Google Cloud Platform (Cloud SQL PostgreSQL, Cloud Storage) and includes session-based authentication and modular API architecture.

**Product Requirements**: https://claude.ai/public/artifacts/9ae012dd-ec9b-4547-ab4d-af2e0a10d62b

## Core Commands

```bash
# Setup & Development
uv sync                                           # Install dependencies
./deploy.sh --dev                                 # Start local dev server
DEBUG=True LOG_LEVEL=DEBUG ./deploy.sh --dev     # Debug mode

# IMPORTANT: Always use --reload-dir to prevent reload loops
uv run uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000

# Code Quality
uv run black app/                                 # Format
uv run ruff check app/ --fix                     # Lint
uv run mypy app/                                 # Type check

# Testing
uv run pytest tests/ -v                          # All tests
uv run pytest tests/unit/ -v                     # Unit tests only
uv run pytest tests/integration/ -v              # Integration tests only
uv run pytest tests/ -k "test_login" -v          # Pattern match
uv run pytest tests/ --cov=app --cov-report=html # Coverage

# Database & Infrastructure (via biz2bricks_infra)
biz2bricks provision full-setup --env-file .env.production  # Full GCP setup
biz2bricks db init --env-file .env                          # Initialize tables only
biz2bricks db status --env-file .env                        # Check table status
biz2bricks status --env-file .env.production                # Show all resource status

# Deployment
./deploy.sh --test                               # Smoke tests
./deploy.sh --deploy                             # Deploy (development)
./deploy.sh --deploy --env production            # Deploy (production)
./deploy.sh --fast --skip-tests                  # Quick deploy

# Client Generation (TypeScript types from OpenAPI)
uv run python scripts/generate_client.py                    # Generate TS types to Next.js app
uv run python scripts/generate_client.py --output ./types   # Custom output path
uv run python scripts/generate_client.py --dry-run          # Preview without generating
```

## Architecture Overview

**Stack**: FastAPI 0.124.0 | PostgreSQL (Cloud SQL) | SQLAlchemy 2.0 async | GCS | Pydantic v2

```
app/
├── main.py                 # FastAPI entry point
├── api/v1/                 # API endpoints (routers)
│   ├── auth.py            # Session-based JWT auth
│   ├── organizations.py   # Multi-tenant org management
│   ├── users.py           # User CRUD
│   ├── folders.py         # Folder hierarchy
│   ├── audit.py           # Audit log endpoints
│   └── documents_modules/ # Document endpoints (modular)
├── services/               # Business logic layer
│   ├── audit_service.py   # Non-blocking audit logging
│   └── document/          # Facade pattern (5 specialized services)
├── core/                   # Infrastructure
│   ├── db_client.py       # DatabaseManager singleton
│   ├── gcs_client.py      # GCS singleton
│   └── security.py        # JWT, password hashing
└── models/                 # Pydantic models & schemas
    └── schemas/           # Request/response schemas (modular)
```

### Model Architecture (Shared vs Local)

**SQLAlchemy ORM Models** - Shared via `biz2bricks_core` package (GitHub):
```python
from biz2bricks_core import (
    db,                    # DatabaseManager singleton
    Base,                  # SQLAlchemy DeclarativeBase
    UserModel,             # users table
    OrganizationModel,     # organizations table (+ plan_id, subscription_status)
    FolderModel,           # folders table
    DocumentModel,         # documents table (+ file_hash, parsed_path, parsed_at)
    AuditLogModel,         # audit_logs table (+ event_type, document_hash, file_name, job_id)
    AuditAction,           # Enum: CREATE, UPDATE, DELETE, LOGIN, LOGOUT, UPLOAD, DOWNLOAD, MOVE
    AuditEntityType,       # Enum: ORGANIZATION, USER, FOLDER, DOCUMENT
)
```

**Pydantic Models** - Local to this service (`app/models/`):
- `app/models/user.py` - `User`, `UserRole` (ADMIN, USER, VIEWER)
- `app/models/organization.py` - `Organization`, `PlanType` (FREE, STARTER, PRO, BUSINESS)
  - Includes: `plan_id`, `subscription_status` fields for usage tracking
- `app/models/folder.py` - `Folder`
- `app/models/document.py` - `Document`, `DocumentStatus`, `FileType`
  - Includes: `file_hash` (SHA-256), `parsed_path`, `parsed_at` for AI processing
- `app/models/schemas/` - API request/response schemas
  - `stats.py` - `AuditLogEntry` with AI fields: `event_type`, `document_hash`, `file_name`, `job_id`

This separation follows microservices best practices: SQLAlchemy models (database schema) are shared because all services use the same database, while Pydantic models (API contracts) remain local for independent evolution.

## Critical Patterns

### 1. Document Service Facade

The document service uses **Facade Pattern** with 5 specialized services in `app/services/document/`:

```python
# DocumentService composes specialized services
class DocumentService(DocumentBaseService):
    def __init__(self):
        self.validation_service = DocumentValidationService()
        self.storage_service = DocumentStorageService()
        self.crud_service = DocumentCrudService()
        self.query_service = DocumentQueryService()
        self.download_service = DocumentDownloadService()
```

### 2. Authentication Pattern

All protected endpoints use `get_current_user_dict` dependency:

```python
@router.post("/endpoint")
async def endpoint(current_user: Dict = Depends(get_current_user_dict)):
    org_id = current_user["org_id"]      # Multi-tenant isolation
    user_id = current_user["user_id"]
    session_id = current_user["session_id"]
```

JWT tokens: access (2 hours) + refresh (7 days) with automatic rotation.

### 3. SQLAlchemy Async Pattern

```python
from biz2bricks_core import db, UserModel

# Always use session context manager
async with db.session() as session:
    stmt = select(UserModel).where(UserModel.email == email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

# Insert with flush to get generated values
async with db.session() as session:
    user = UserModel(id=str(uuid4()), email=email)
    session.add(user)
    await session.flush()  # Get ID before commit
```

### 4. Non-Blocking Audit Logging

```python
from app.services.audit_service import audit_service
from biz2bricks_core import AuditAction, AuditEntityType

# Fire-and-forget at end of operations
asyncio.create_task(
    audit_service.log_event(
        org_id=org_id,
        action=AuditAction.CREATE,
        entity_type=AuditEntityType.USER,
        entity_id=user_id,
        user_id=current_user_id,
        details={"new_values": {...}},
    )
)
```

Tracked: Organization, User, Folder, Document (CREATE, UPDATE, DELETE, LOGIN, LOGOUT, UPLOAD, DOWNLOAD, MOVE)

### 5. Caching Pattern

The API includes a caching layer using `fastapi-cache2` with multi-tenant isolation:

```python
from app.core.cache import cached_documents, cached_folders, invalidate_cache

# Use decorators for read operations (TTLs configured per entity)
@cached_documents()  # TTL: 120 seconds
async def get_document(org_id: str, doc_id: str):
    ...

@cached_folders()  # TTL: 300 seconds
async def list_folders(org_id: str):
    ...

# Invalidate cache on mutations
await invalidate_cache(f"documents:{org_id}:*")
```

**Backends**: `memory` (default) or `redis` (GCP Memorystore)
**TTLs**: documents (2 min), folders (5 min), organizations (30 min), users (5 min)
**Multi-tenant**: All cache keys are prefixed with `org_id` for isolation

## Adding New Features

### New API Endpoint

```python
# 1. Create endpoint in app/api/v1/
@router.post("/new-endpoint", response_model=ResponseModel)
async def new_endpoint(
    request: RequestModel,
    current_user: Dict[str, Any] = Depends(get_current_user_dict)
):
    return await service.method_name(org_id=current_user["org_id"], **request.model_dump())

# 2. Add Pydantic models in app/models/schemas/ (choose appropriate domain file)
# 3. Implement service logic in app/services/
# 4. Register router in app/main.py
```

### New Document Service

```python
# 1. Inherit from DocumentBaseService in app/services/document/
class NewService(DocumentBaseService):
    async def specialized_operation(self, org_id: str, doc_id: str):
        pass

# 2. Add to DocumentService facade
self.new_service = NewService()
```

## Common Pitfalls

### JWT Exception Handling
```python
# ✅ Use specific exceptions
except jwt.ExpiredSignatureError:
    logger.debug("Token expired")
except jwt.InvalidSignatureError:
    logger.warning("Invalid signature")

# ❌ Don't use generic jwt.PyJWTError
```

### SQLAlchemy Async
```python
# ✅ Always use async session context manager
async with db.session() as session:
    result = await session.execute(stmt)

# ❌ Don't use sync patterns: session.query(User).all()
```

### Dev Server Reload Loops
```bash
# ✅ Always use --reload-dir app
uv run uvicorn app.main:app --reload --reload-dir app

# ❌ Without --reload-dir, .venv changes trigger reloads
```

## Environment Configuration

See `.env.example` for complete configuration. Key variables:

```bash
# Local Development
DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/doc_intelligence"
USE_CLOUD_SQL_CONNECTOR=false

# Production (Cloud SQL)
CLOUD_SQL_INSTANCE="project:region:instance"
USE_CLOUD_SQL_CONNECTOR=true
CLOUD_SQL_IP_TYPE="PRIVATE"

# Required
GCP_PROJECT_ID="your-project-id"
GCS_BUCKET_NAME="your-bucket-name"
JWT_SECRET_KEY="your-256-bit-secret"

# Cache Configuration
CACHE_ENABLED=true
CACHE_BACKEND="memory"  # or "redis"
CACHE_DEFAULT_TTL=300
# Redis (optional - for production)
REDIS_HOST="localhost"
REDIS_PORT=6379
```

## Coding Standards

```python
# ✅ Absolute imports
from app.core.config import settings
from biz2bricks_core import db

# ✅ Dependency injection for services
@router.post("/endpoint")
async def endpoint(service: DocumentService = Depends(get_document_service)):
    return await service.method()

# ✅ Specific exceptions with context
except SQLAlchemyError as e:
    logger.error("Database operation failed", error=str(e))
    raise HTTPException(status_code=500, detail="Database error")
```

## Testing

```text
tests/
├── conftest.py           # Shared fixtures
├── fixtures/sample_files/  # PDF, XLSX samples
├── unit/                  # Mock-based tests
│   ├── core/             # test_config, test_security, test_db_models
│   └── services/         # test_user_service, test_audit_service, test_document_service
└── integration/           # API tests
    ├── api/              # test_auth, test_health, test_users
    └── workflows/        # test_auth_workflow
```

**Key Fixtures** (tests/conftest.py):

- `mock_db_session`, `mock_gcs_client`, `mock_upload_file` - Mock objects
- `user_data`, `org_data`, `document_data` - Faker-generated test data
- `sample_pdf_content`, `sample_xlsx_content` - Valid file bytes
- `gcs_cleanup` - Auto-cleanup utility for GCS test objects

**Markers**: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.auth`, `@pytest.mark.slow`

## Key Files Reference

| Category | Files |
|----------|-------|
| Entry Point | `app/main.py` |
| Database | `biz2bricks_core` (shared models: OrganizationModel, UserModel, FolderModel, DocumentModel, AuditLogModel) |
| Cache | `app/core/cache.py` |
| Services | `app/services/document/document_service.py` (facade), `app/services/audit_service.py` |
| Auth | `app/api/v1/auth.py`, `app/core/security.py` |
| Scripts | `scripts/generate_client.py` (TypeScript types from OpenAPI) |
| Infra CLI | `biz2bricks provision`, `biz2bricks db init`, `biz2bricks status` (from biz2bricks_infra package) |
| Deploy | `deploy.sh`, `cloudbuild.yaml` |

## GCP Provisioning (via biz2bricks_infra)

Infrastructure is now managed via the `biz2bricks` CLI from the `biz2bricks_infra` package:

```bash
# Install biz2bricks_infra
uv pip install -e ../biz2bricks_infra

# Full setup: Cloud SQL + GCS + Service Account + Secrets
biz2bricks provision full-setup --env-file .env.production

# Individual resources
biz2bricks provision cloud-sql --env-file .env.production
biz2bricks provision gcs-bucket --env-file .env.production
biz2bricks provision service-account --env-file .env.production
biz2bricks provision secrets --env-file .env.production

# Database initialization
biz2bricks db init --env-file .env

# Show status of all resources
biz2bricks status --env-file .env.production

# Delete resources (with confirmation)
biz2bricks delete all --env-file .env.production

# Secrets management
biz2bricks secrets list
biz2bricks secrets get DATABASE_PASSWORD

# Service account key generation
biz2bricks sa create-key -o key.json --env-file .env.production
```

## Health Endpoints

- `/health` - Basic health check
- `/status` - Detailed service status (PostgreSQL, GCS)
- `/ready`, `/live` - Kubernetes probes
- `/docs` - API documentation (development only)
