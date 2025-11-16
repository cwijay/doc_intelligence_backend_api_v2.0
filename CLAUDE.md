# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
AI-powered document intelligence platform built with FastAPI, featuring advanced document processing, analysis, and AI content generation with intelligent caching. Integrates with Google Cloud Platform (Firebase/Firestore, Cloud Storage) and includes session-based authentication and modular API architecture.

**Product Requirements**: https://claude.ai/public/artifacts/9ae012dd-ec9b-4547-ab4d-af2e0a10d62b

## Core Development Commands

**Environment Setup (using uv)**:
```bash
uv sync                    # Install dependencies (10-100x faster than pip)
./run_dev.sh              # Start optimized development server
```

**Development Server**:
```bash
# Recommended: Use optimized script (prevents reload loops)
./run_dev.sh

# Manual (IMPORTANT: always use --reload-dir app to prevent .venv reload loops)
uv run uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000

# Debug mode
DEBUG=True LOG_LEVEL=DEBUG uv run uvicorn app.main:app --reload --reload-dir app
```

**Testing & Quality**:
```bash
uv run pytest tests/ -v --asyncio-mode=auto          # Run tests
uv run pytest tests/test_document_service.py -v      # Specific test
uv run pytest tests/ --cov=app --cov-report=html     # Coverage

uv run black app/ tests/                             # Format
uv run ruff check app/ tests/ --fix                  # Lint and fix
uv run mypy app/                                     # Type check
```

**Firebase/GCP Setup**:
```bash
# Manual setup utilities (optional - deploy_full.sh automates most of this)
python create_firestore_indexes.py                   # Create required indexes (automated in deploy_full.sh)
python setup_gcp_bucket.py                           # Interactive GCS setup (automated in deploy_full.sh)
python scripts/gcp_auth_helper.py                    # Verify GCP auth
python scripts/verify_gcs_setup.py                   # Verify GCS setup

# Note: deploy_full.sh automatically creates:
#  - Firestore database (native mode)
#  - GCS bucket with versioning
#  - Service accounts and IAM roles
#  - Firestore composite indexes
```

**Cloud Run Deployment**:
```bash
# Recommended: Comprehensive deployment script
./deploy_full.sh --project-id PROJECT_ID --region us-central1 --env-file .env.production

# Alternative: Cloud Build (requires API keys setup separately)
gcloud builds submit --config cloudbuild.yaml

# Check deployment status
gcloud run services describe document-intelligence-api --region=us-central1
gcloud logging read "resource.type=cloud_run_revision" --limit=20
```

## Code Architecture

### Technology Stack
- **Backend**: FastAPI 0.115.7 with async/await
- **Database**: Google Cloud Firestore (named database: `biz2bricks-docdb-v1`)
- **Storage**: Google Cloud Storage with signed URLs
- **Authentication**: Session-based JWT with refresh tokens
- **Dependency Management**: uv (ultra-fast Python package installer)
- **AI/LLM**: OpenAI GPT-5-mini, LangChain 0.3.18, LlamaParse 0.5.20, Pinecone 5.4.0
- **Validation**: Pydantic v2 (2.11.0+)
- **Logging**: Structured JSON logging with Structlog 24.1.0+

### Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application (app/main.py)        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  API Layer (app/api/v1/)                                    │
│  ├─ auth.py              - Session-based authentication     │
│  ├─ organizations.py     - Multi-tenant org management      │
│  ├─ users.py             - User management                  │
│  ├─ folders.py           - Folder hierarchy                 │
│  ├─ documents_main.py    - Main document router             │
│  └─ documents_modules/   - Modular AI endpoints             │
│      ├─ document_upload.py         - Upload handling        │
│      ├─ document_processing.py     - LlamaParse parsing     │
│      ├─ document_summarization.py  - AI summary w/ cache    │
│      ├─ document_questions.py      - AI questions w/ cache  │
│      ├─ document_faq.py            - AI FAQ w/ cache        │
│      ├─ document_download.py       - Signed URLs            │
│      └─ document_sync.py           - GCS/Firestore sync     │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  Service Layer (app/services/)                              │
│  ├─ auth_service.py      - Authentication logic             │
│  ├─ user_service.py      - User management logic            │
│  ├─ org_service.py       - Organization logic               │
│  ├─ folder_service.py    - Folder management                │
│  └─ document/            - Facade pattern (7 services)      │
│      ├─ document_service.py              - Main facade      │
│      ├─ document_validation_service.py   - File validation  │
│      ├─ document_storage_service.py      - GCS operations   │
│      ├─ document_crud_service.py         - CRUD operations  │
│      ├─ document_query_service.py        - Complex queries  │
│      ├─ document_ai_service.py           - AI content       │
│      ├─ document_sync_service.py         - Sync validation  │
│      └─ document_download_service.py     - Download mgmt    │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  Core Layer (app/core/)                                     │
│  ├─ firebase_client.py   - FirebaseManager singleton        │
│  ├─ gcs_client.py        - GCSManager singleton             │
│  ├─ security.py          - JWT, password hashing, blacklist │
│  ├─ config.py            - Pydantic settings                │
│  ├─ logging.py           - Structured logging               │
│  └─ exceptions.py        - Custom exception hierarchy       │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  Models Layer (app/models/)                                 │
│  ├─ user.py              - User models                      │
│  ├─ organization.py      - Organization models              │
│  ├─ document.py          - Document models                  │
│  ├─ folder.py            - Folder models                    │
│  └─ schemas.py           - Request/response schemas         │
└─────────────────────────────────────────────────────────────┘
```

## Critical Architecture Patterns

### 1. Document Service Facade Pattern

The document service uses **Facade Pattern** with 7 specialized services:

```python
# Main facade (app/services/document/document_service.py)
class DocumentService(DocumentBaseService):
    def __init__(self):
        self.validation_service = DocumentValidationService()
        self.storage_service = DocumentStorageService()
        self.crud_service = DocumentCrudService()
        self.query_service = DocumentQueryService()
        self.ai_service = DocumentAIService()
        self.sync_service = DocumentSyncService()
        self.download_service = DocumentDownloadService()
```

**Key Principles**:
- **Single Responsibility**: Each service handles one domain
- **Composition over Inheritance**: Services are composed, not extended
- **Dependency Injection**: Services injected via `Depends()`
- **Async-First**: All I/O operations use async/await

**Service Communication Pattern**:
```python
# API endpoint delegates to facade
@router.post("/upload")
async def upload(file: UploadFile, current_user: Dict = Depends(get_current_user_dict)):
    return await document_service.create_document(
        org_id=current_user["org_id"],
        file=file,
        user_id=current_user["user_id"]
    )

# Facade orchestrates specialized services
async def create_document(self, org_id: str, file: UploadFile, user_id: str):
    file_type, _ = self.validation_service._validate_file_upload(file)
    storage_path = await self.storage_service.upload_document(...)
    document = await self.crud_service.create_document_metadata(...)
    return document
```

### 2. AI Content Caching Architecture

**Intelligent caching** via modular endpoints in `app/api/v1/documents_modules/`:

```python
# Pattern: Generate → Cache → Retrieve → Update

# POST: Generate with caching
@router.post("/summarize")
async def generate_summary():
    if document.has_ai_summary:
        return cached_content
    content = await ai_service.generate_summary(...)
    document.update_ai_summary(content)  # Cache in Firestore
    return content

# GET: Retrieve cached
@router.get("/summarize")
async def get_summary():
    return document.ai_summary or empty_response

# PUT: Update/regenerate
@router.put("/summarize")
async def update_summary():
    content = await ai_service.regenerate_summary(...)
    document.update_ai_summary(content)
    return content
```

**Cost Optimization**:
- First generation: OpenAI call + Firestore cache
- Subsequent requests: Instant return from cache (no OpenAI calls)
- Smart regeneration: Custom prompts trigger fresh generation
- AI content embedded in document responses

**Modules** (`app/api/v1/documents_modules/`):
- `document_summarization.py` - AI document summarization
- `document_questions.py` - AI question generation (1-20 count)
- `document_faq.py` - AI FAQ generation (1-20 count)

### 3. Session-Based Authentication

**JWT tokens with automatic rotation**:

```python
# Login response
{
    "access_token": "uuid-session-token",      # 2 hours
    "refresh_token": "uuid-refresh-token",     # 7 days
    "token_type": "bearer",
    "user": {
        "org_id": "...",      # Organization isolation
        "session_id": "...",  # Session tracking
        "role": "..."         # RBAC
    }
}

# API endpoint pattern
async def protected_endpoint(
    current_user: Dict = Depends(get_current_user_dict)
):
    org_id = current_user["org_id"]      # Multi-tenant isolation
    user_id = current_user["user_id"]    # User tracking
    session_id = current_user["session_id"]  # Session management
```

**Key Features**:
- Session tokens (2 hours) with UUID identifiers
- Refresh tokens (7 days) with automatic rotation
- Token blacklisting for logout (in-memory set for MVP)
- Organization-scoped authentication
- Grace period notifications (10 minutes before expiry)

### 4. Firestore Named Database Pattern

**CRITICAL**: Use **named database**, not default database:

```python
# Configuration (app/core/config.py)
FIREBASE_DATABASE_ID = "biz2bricks-docdb-v1"  # NOT "(default)"

# Client initialization (app/core/firebase_client.py)
client = firestore.AsyncClient(
    project=project_id,
    database=database_id  # Named database
)

# Collection access pattern
async def _get_collection(self, org_id: str):
    if not firebase_manager.is_initialized:
        logger.warning("Firebase not initialized")
        return None
    return firebase_manager.db.collection("organizations")
```

**Always check initialization**:
```python
# ✅ Good
if not firebase_manager.is_initialized:
    logger.warning("Firebase not initialized")
    return []
collection = self._get_collection(org_id)
async for doc in collection.stream():
    results.append(doc.to_dict())

# ❌ Bad
docs = query.stream()  # Could fail if not initialized
async for doc in docs:
    results.append(doc.to_dict())
```

## Important Development Patterns

### Adding New API Endpoints

```python
# 1. Create router endpoint (app/api/v1/)
@router.post("/new-endpoint", response_model=ResponseModel)
async def new_endpoint(
    request: RequestModel,
    current_user: Dict[str, Any] = Depends(get_current_user_dict)
):
    result = await service.method_name(
        org_id=current_user["org_id"],
        **request.model_dump()
    )
    return result

# 2. Add Pydantic models (app/models/schemas.py)
class RequestModel(BaseModel):
    field: str

# 3. Implement service logic (app/services/)
async def method_name(self, org_id: str, **kwargs):
    # Business logic
    pass

# 4. Register router (app/main.py)
app.include_router(router, prefix=f"{settings.API_V1_STR}/path", tags=["Tag"])
```

### Adding Specialized Document Services

```python
# 1. Inherit from DocumentBaseService
class NewService(DocumentBaseService):
    async def specialized_operation(self, org_id: str, doc_id: str):
        # Focused functionality
        pass

# 2. Add to main DocumentService facade
class DocumentService(DocumentBaseService):
    def __init__(self):
        super().__init__()
        self.new_service = NewService()

    async def operation(self, org_id: str, doc_id: str):
        # Delegate to specialized service
        return await self.new_service.specialized_operation(org_id, doc_id)
```

### Working with AI Content Modules

**Always check cache first**:
```python
# Check existing content before generation
if document.has_ai_summary:
    return document.ai_summary

# Generate new content
content = await ai_service.generate_summary(...)

# Cache in Firestore (embedded in document)
document.ai_summary = content
await self.crud_service.update_document(document)
```

**Document model properties** (`app/models/document.py`):
- `has_ai_summary` - Check if summary exists
- `has_ai_questions` - Check if questions exist
- `has_ai_faq` - Check if FAQ exists
- `to_dict()` - Serialize with AI fields included

### OpenAI Model Configuration

**Centralized configuration** (`app/core/config.py`):
```python
OPENAI_MODEL = "gpt-5-mini"  # Default, configurable via env

# ✅ Good: Use settings
from app.core.config import settings
response = await openai.ChatCompletion.create(
    model=settings.OPENAI_MODEL,
    ...
)

# ❌ Bad: Hardcoded model
response = await openai.ChatCompletion.create(
    model="gpt-4o-mini",  # Don't hardcode
    ...
)
```

## Common Development Pitfalls

### 1. JWT Exception Handling

```python
# ✅ Good: Specific exceptions with logging
try:
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
    return payload
except jwt.ExpiredSignatureError:
    logger.debug("Token expired")
    return None
except jwt.InvalidSignatureError:
    logger.warning("Invalid signature")
    return None
except jwt.InvalidTokenError:
    logger.warning("Invalid token format")
    return None

# ❌ Bad: Generic catch-all
try:
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
    return payload
except jwt.PyJWTError:  # Too broad, loses context
    return None
```

### 2. Firestore Async Patterns

```python
# ✅ Good: Proper async iteration with checks
if not firebase_manager.is_initialized:
    logger.warning("Firebase not initialized")
    return []

collection = get_collection("organizations")
query = collection.where(filter=FieldFilter("is_active", "==", True))
docs = query.stream()
results = []

async for doc in docs:
    data = doc.to_dict()
    results.append(Model.from_dict(data, doc.id))
return results

# ❌ Bad: Missing initialization check
docs = query.stream()  # Could fail
async for doc in docs:
    results.append(doc.to_dict())
```

### 3. AI Content Persistence

```python
# ✅ Good: Ensure AI fields in to_dict()
class Document:
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "ai_summary": self.ai_summary,      # Include AI fields
            "ai_questions": self.ai_questions,
            "ai_faq": self.ai_faq,
            ...
        }

# ✅ Good: Check before generating
if document.has_ai_summary:
    return document.ai_summary
else:
    # Generate and cache
    summary = await ai_service.generate_summary(...)
    document.ai_summary = summary
    await crud_service.update_document(document)

# ❌ Bad: Always generate (wastes API calls)
summary = await ai_service.generate_summary(...)  # Ignores cache
```

### 4. Reload Loops in Development

```bash
# ✅ Good: Limit file watching to app directory
uv run uvicorn app.main:app --reload --reload-dir app

# ❌ Bad: Watches entire directory (causes reload loops)
uv run uvicorn app.main:app --reload
# WARNING: WatchFiles detected changes in '.venv/lib/python3.12/...'
```

## Environment Configuration

**Critical Variables**:
```bash
# Firebase/Firestore (CRITICAL: Use named database)
FIREBASE_PROJECT_ID="your-project-id"
FIREBASE_DATABASE_ID="biz2bricks-docdb-v1"  # NOT "(default)"

# GCP
GCP_PROJECT_ID="your-project-id"
GCS_BUCKET_NAME="your-bucket-name"

# Authentication
JWT_SECRET_KEY="your-256-bit-secret"
SESSION_DURATION_HOURS=2
REFRESH_SESSION_DURATION_DAYS=7

# AI Services
OPENAI_API_KEY="your-key"
OPENAI_MODEL="gpt-5-mini"  # Configurable model
LLAMAPARSE_API_KEY="your-key"

# Authentication (choose one):
# Option 1: Service Account Key File
GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
# Option 2: Application Default Credentials (Cloud Run)
# Leave GOOGLE_APPLICATION_CREDENTIALS unset
```

## Firestore Database & Indexes

**Firestore Database Creation:**
- ✅ **Automated by deploy_full.sh** - Creates named database in native mode
- Uses `FIREBASE_DATABASE_ID` from env file (defaults to `PROJECT_ID-docdb-v1`)
- Idempotent - safe to re-run, won't recreate existing database
- For manual creation (if needed): Use Firebase Console or `gcloud firestore databases create`

**⚠️ CRITICAL REQUIREMENT: firestore.indexes.json**

The `firestore.indexes.json` file **MUST exist** in the repository root for deployment to succeed:

- **Without this file**: `deploy_full.sh` will **fail immediately** with a clear error message
- **Purpose**: Defines all 8 required composite indexes for Firestore queries
- **Location**: Repository root (same directory as deploy_full.sh)
- **Format**: Firebase-compatible JSON configuration file

**If the file is missing**:
```bash
# Option 1: View required indexes
python3 create_firestore_indexes.py --project-id YOUR_PROJECT_ID

# Option 2: Use the existing template
# The file should already exist in the repository
# If missing, restore from git history or recreate from the index definitions below
```

**Required Composite Indexes** (defined in `firestore.indexes.json`):

1. **Organizations**: `is_active` (ASC) + `created_at` (DESC)
2. **Organizations with filter**: `is_active` (ASC) + `plan_type` (ASC) + `created_at` (DESC)
3. **Documents**: `organization_id` (ASC) + `is_active` (ASC) + `created_at` (DESC)
4. **Folders**: `organization_id` (ASC) + `parent_id` (ASC) + `name` (ASC)

**Note**: `deploy_full.sh` automatically deploys indexes via `deploy_firestore_indexes.py`

## Coding Standards

### Import Patterns
```python
# ✅ Good: Absolute imports
from app.core.config import settings
from app.core.firebase_client import firebase_manager
from app.models.document import Document

# ❌ Bad: Relative imports at module level
from ..core.config import settings
```

### Service Instantiation
```python
# ✅ Good: Dependency injection
@router.post("/endpoint")
async def endpoint(
    service: DocumentService = Depends(get_document_service)
):
    return await service.method()

# ❌ Bad: Direct instantiation
@router.post("/endpoint")
async def endpoint():
    service = DocumentService()  # Don't instantiate directly
    return await service.method()
```

### Error Handling
```python
# ✅ Good: Specific exceptions with context
try:
    result = await firestore_operation()
except GoogleAPIError as e:
    logger.error("Firestore operation failed", error=str(e))
    raise HTTPException(status_code=500, detail="Database error")

# ❌ Bad: Generic exception
try:
    result = await firestore_operation()
except Exception:  # Too broad
    return None
```

## Testing Best Practices

```python
# Test structure mirrors app structure
tests/
├── services/
│   ├── test_document_service.py
│   └── test_auth_service.py
├── api/
│   └── v1/
│       ├── test_auth.py
│       └── test_documents.py
└── conftest.py  # Shared fixtures

# Async test pattern
@pytest.mark.asyncio
async def test_document_upload():
    service = DocumentService()
    result = await service.upload_document(...)
    assert result.success is True
```

### Smoke Tests for Fast Validation

**Purpose**: Critical tests for rapid deployment validation (15-25 seconds total)

**Smoke Test Suite** (5 tests marked with `@pytest.mark.smoke`):
- User Registration (auth)
- Login & Session (auth)
- Session Validation (auth)
- Organization Create (database write)
- Organization Read (database read)

**Running Smoke Tests**:
```bash
# Run smoke tests only
pytest tests/ -v -m "smoke"

# Using the smoke test script
./scripts/run_smoke_tests.sh

# Test against specific deployment
./test_only.sh https://document-intelligence-api-726919062103.us-central1.run.app

# Test against local server
./test_only.sh http://localhost:8000
```

**Test Markers** (from pytest.ini):
```bash
# Smoke tests - fast validation (15-25 sec)
pytest tests/ -v -m "smoke"

# Skip slow tests (recommended for CI/CD)
pytest tests/ -v -m "not slow"

# Skip AI tests (saves money)
pytest tests/ -v -m "not ai"

# Skip both slow and AI tests
pytest tests/ -v -m "not slow and not ai"

# Integration tests only
pytest tests/ -v -m "integration"
```

**Test Performance**:
- Smoke tests: 15-25 seconds (5 critical tests)
- Full test suite: 2-3 minutes (40+ tests)
- Integration tests: 30-120 seconds per test

## Deployment Notes

### Deployment Decision Tree

```
┌─────────────────────────────────────────────────────────────┐
│ WHEN TO USE WHICH DEPLOYMENT METHOD                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Quick code change → ./fast_deploy.sh          (3-5 min)    │
│ Dependency change → ./deploy_full.sh          (6-9 min)    │
│ Just test service → ./test_only.sh            (15-25 sec)  │
│ CI/CD (develop)   → GitHub Actions/Cloud Build (5-7 min)   │
│ Production deploy → cloudbuild.production.yaml (15-20 min) │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Quick Deployment Commands

**Fastest: Test Only** (15-25 seconds):
```bash
# Validate existing deployment
./test_only.sh https://document-intelligence-api-726919062103.us-central1.run.app
```

**Fast: Quick Deploy** (3-5 minutes):
```bash
# Fast deployment with smoke tests
./fast_deploy.sh

# Ultra-fast (skip all tests)
./fast_deploy.sh --skip-tests
```

**Full: Complete Deploy** (6-9 minutes):
```bash
# Full deployment with all tests
./deploy_full.sh --project-id biz2bricks-dev-v1 \
  --env-file .env.production \
  --timeout 60 \
  --region us-central1 \
  --bucket biz2bricks-dev-v1-document-store
```

### Manual Cloud Run Deployment

**Deployment Options** (in order of recommendation):

**1. Comprehensive Bash Script** (Recommended):
```bash
./deploy_full.sh \
  --project-id PROJECT_ID \
  --region us-central1 \
  --env-file .env.production \
  --bucket BUCKET_NAME
```

**Features**:
- Complete infrastructure setup
- **Automated Firestore database creation** (native mode)
- Service account and IAM management
- GCS bucket creation with versioning and lifecycle policies
- Firestore composite index deployment
- Environment variable parsing

**2. Cloud Build**:
```bash
# Simple Docker build and deploy
gcloud builds submit --config cloudbuild.yaml

# With custom substitutions
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_ENVIRONMENT=staging,_MEMORY=2Gi
```

**Note**: Cloud Build config does NOT include API keys. Set them manually or use the deploy_full.sh script.

**Post-Deployment Health Checks**:
```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe document-intelligence-api \
  --region=us-central1 \
  --format="value(status.url)")

# Test endpoints
curl "$SERVICE_URL/health"
curl "$SERVICE_URL/status"

# View logs
gcloud run services logs read document-intelligence-api \
  --region=us-central1 \
  --limit=50
```

## Key Files

**Application**:
- `app/main.py` - FastAPI application entry point
- `app/core/firebase_client.py` - Firebase singleton (named database)
- `app/core/gcs_client.py` - GCS singleton
- `app/services/document/document_service.py` - Document facade
- `app/api/v1/documents_modules/` - Modular AI endpoints

**Development**:
- `run_dev.sh` - Optimized development server
- `create_firestore_indexes.py` - Index creation utility

**Deployment**:
- `deploy_full.sh` - Comprehensive bash deployment script (recommended)
- `fast_deploy.sh` - Quick deployment script for code changes
- `test_only.sh` - Rapid smoke test validation
- `cloudbuild.yaml` - Simple Cloud Build deployment
- `cloudbuild.develop.yaml` - Automatic deployment for develop branch
- `cloudbuild.production.yaml` - Production deployment config
- `setup_gcp_bucket.py` - GCS bucket setup utility
- `.env.production` - Production environment variables

**Maintenance** (scripts/maintenance/):
- `cleanup_duplicate_documents.py` - Clean duplicate Firestore documents
- `cleanup_duplicate_storage_paths.py` - Clean duplicate GCS paths
- `diagnose_document_sync.py` - Troubleshoot document sync issues

## Recent Changes

**September 2025**:
- **Modular AI Endpoints**: Dedicated modules for summary, FAQ, questions with caching
- **AI Content Caching**: Firestore-based caching (eliminates redundant OpenAI calls)
- **Enhanced Development**: Optimized `run_dev.sh` with smart file watching
- **LangChain Integration**: Robust AI workflows with LangChain
- **Production-Ready AI**: Configurable OpenAI model support (gpt-5-mini default)
- **Removed Endpoints**:
  - ~~`GET /api/v1/documents/{id}/ai-content`~~ - Use document fields directly
  - ~~`PATCH /api/v1/documents/{id}/ai-content`~~ - Use save-parsed endpoint

## Support Resources

- **Health Checks**: `/health`, `/status`, `/ready`, `/live`
- **API Docs**: `/docs` (development only)
- **Logs**: `gcloud run services logs read SERVICE_NAME --region=REGION`
- **Metrics**: `/metrics` (basic implementation)
