# Document Intelligence Backend

A **document management platform** built with FastAPI and PostgreSQL, featuring file upload, storage, and organization management. Integrates with Google Cloud Platform (Cloud SQL PostgreSQL, Cloud Storage) and includes session-based authentication with multi-tenant organization support.

**Product Requirements**: https://claude.ai/public/artifacts/9ae012dd-ec9b-4547-ab4d-af2e0a10d62b

## Key Features

- **Document Management**: Upload, store, and organize PDF and XLSX files
- **Cloud Storage**: Google Cloud Storage integration with signed URLs
- **Multi-Tenant Architecture**: Organization-based isolation and access control
- **Session-Based Authentication**: JWT tokens with automatic refresh token rotation
- **Audit Logging**: Comprehensive audit trail for compliance (PostgreSQL-based)
- **GCP Provisioning**: Automated scripts for Cloud SQL, GCS, Service Accounts, and Secret Manager
- **Cloud-Native Deployment**: Google Cloud Run with PostgreSQL (Cloud SQL)

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Technology Stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [GCP Setup](#gcp-setup)
- [Environment Configuration](#environment-configuration)
- [Development Server](#development-server)
- [API Endpoints](#api-endpoints)
- [Audit Logging](#audit-logging)
- [Deployment](#deployment)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

## Architecture Overview

The system follows a **clean architecture** with service composition patterns:

- **Core Layer**: Configuration, clients (Database, GCS), security, logging, exceptions
- **Service Layer**: Business logic with Facade pattern for document operations
- **API Layer**: FastAPI routers with dependency injection and session-based auth
- **Models Layer**: Pydantic v2 models (local) and SQLAlchemy ORM models (from `biz2bricks_core`)
  - **Plan Types**: FREE, STARTER, PRO, BUSINESS (with usage limits)
  - **Document Fields**: file_hash, parsed_path, parsed_at (for AI processing)

### Document Service Architecture

The document processing system uses a **Facade Pattern** with 5 specialized services:

```
┌───────────────────────────────────────────────────────────────────┐
│                    DocumentService (Facade)                       │
├───────────────────────────────────────────────────────────────────┤
│ ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│ │  Validation     │  │    Storage      │  │     CRUD        │     │
│ │   Service       │  │    Service      │  │    Service      │     │
│ └─────────────────┘  └─────────────────┘  └─────────────────┘     │
│ ┌─────────────────┐  ┌─────────────────┐                          │
│ │     Query       │  │   Download      │                          │
│ │    Service      │  │    Service      │                          │
│ └─────────────────┘  └─────────────────┘                          │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   FastAPI API   │───▶│ Database Client  │───▶│   PostgreSQL    │
│    Endpoints    │    │   (SQLAlchemy)   │    │   (Cloud SQL)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────┐    ┌──────────────────┐
│   GCS Client    │───▶│   Cloud Storage  │
│   (Singleton)   │    │     Bucket       │
└─────────────────┘    └──────────────────┘
```

## Technology Stack

### Core Infrastructure
- **Backend**: FastAPI 0.124.0 with async/await
- **Database**: PostgreSQL via Cloud SQL with SQLAlchemy 2.0 async
- **Shared Core**: `biz2bricks_core` package ([GitHub](https://github.com/cwijay/biz_to_bricks_core_v1.git)) - SQLAlchemy ORM models (User, Organization, Folder, Document, AuditLog), database utilities, usage tracking
- **File Storage**: Google Cloud Storage with signed URLs
- **Caching**: fastapi-cache2 with memory/Redis backends
- **Authentication**: Session-based JWT with refresh token rotation
- **Dependency Management**: uv (ultra-fast Python package installer)
- **Deployment**: Google Cloud Run

### Development & Quality
- **Validation**: Pydantic v2 (2.12.5+) with strict type checking
- **Logging**: Structured JSON logging with Structlog 24.1.0+
- **Code Quality**: Black, Ruff, MyPy
- **Testing**: Pytest with async support

## Prerequisites

- **Python 3.12+** (required for latest dependencies)
- **Google Cloud Account** with billing enabled
- **gcloud CLI** installed and configured
- **uv** (recommended) or **pip** for dependency management
- **Docker** (for Cloud Run deployment)
- **PostgreSQL 15+** (for local development)

## Installation

### Using uv (Recommended)

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
git clone <repository-url>
cd document-intelligence-backend
uv sync  # Creates .venv and installs all dependencies
```

### Using pip (Legacy)

```bash
git clone <repository-url>
cd document-intelligence-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## GCP Setup

This section covers all GCP resource creation - from authentication to database tables.

### Prerequisites

1. **Google Cloud SDK** installed and authenticated
2. **GCP Project** with billing enabled
3. **Required APIs** enabled

```bash
# Install gcloud CLI (macOS)
brew install google-cloud-sdk

# Login to Google Cloud
gcloud auth login

# Set up Application Default Credentials (required for Cloud SQL, GCS)
gcloud auth application-default login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com
```

### Quick Start (Automated)

The fastest way to set up all GCP resources:

```bash
# Full setup: provision + init tables + generate .env (RECOMMENDED)
uv run python scripts/provision_all.py --full-setup --env-file .env.production

# Provision GCP resources only (Cloud SQL, GCS bucket, service account, secrets)
uv run python scripts/provision_all.py --env-file .env.production

# Preview what will be created (dry-run)
uv run python scripts/provision_all.py --full-setup --dry-run

# Provision + initialize database tables
uv run python scripts/provision_all.py --init-tables --env-file .env.production

# Provision + generate .env file from resources
uv run python scripts/provision_all.py --generate-env --env-output .env
```

The script is **idempotent** - it only creates missing resources. Output shows:
- `EXISTS ✓` - Resource already exists
- `CREATED ✓` - Resource was created
- `MISSING ✗` - Resource doesn't exist

### Resources Created

| Resource | Description | Script |
|----------|-------------|--------|
| Cloud SQL Instance | PostgreSQL 15 database | `scripts/setup_cloud_sql.py` |
| Database | `doc_intelligence` database | `scripts/setup_cloud_sql.py` |
| Database User | `postgres` user with password | `scripts/setup_cloud_sql.py` |
| GCS Bucket | Document storage with versioning | `setup_gcp_bucket.py` |
| Service Account | IAM roles for Cloud Run | `scripts/setup_service_account.py` |
| Secrets | `DATABASE_PASSWORD`, `JWT_SECRET_KEY` | `scripts/setup_secrets.py` |
| Database Tables | All application tables | `scripts/init_database.py` |

### Manual Setup (Step-by-Step)

If you prefer manual control or the automated script fails:

#### Step 1: Create Cloud SQL Instance

```bash
# Using the interactive script (recommended)
uv run python scripts/setup_cloud_sql.py

# OR manually via gcloud (takes 5-10 minutes)
gcloud sql instances create doc-intelligence-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --assign-ip

# Create database
gcloud sql databases create doc_intelligence \
  --instance=doc-intelligence-db

# Set postgres password
gcloud sql users set-password postgres \
  --instance=doc-intelligence-db \
  --password=YOUR_SECURE_PASSWORD
```

#### Step 2: Create GCS Bucket

```bash
# Using the interactive script (recommended)
python setup_gcp_bucket.py

# OR manually via gsutil
gsutil mb -p YOUR_PROJECT_ID -c STANDARD -l us-central1 gs://YOUR_BUCKET_NAME
gsutil versioning set on gs://YOUR_BUCKET_NAME
gsutil uniformbucketlevelaccess set on gs://YOUR_BUCKET_NAME
```

#### Step 3: Create Service Account & IAM

```bash
# Using the script
uv run python scripts/setup_service_account.py create

# OR manually
gcloud iam service-accounts create document-intelligence-api-sa \
  --display-name="Document Intelligence API"

# Grant required roles
SA_EMAIL="document-intelligence-api-sa@YOUR_PROJECT.iam.gserviceaccount.com"
for role in roles/cloudsql.client roles/storage.objectAdmin roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$role"
done
```

#### Step 4: Create Secrets

```bash
# Using the script
uv run python scripts/setup_secrets.py create

# OR manually
echo -n "YOUR_DB_PASSWORD" | gcloud secrets create DATABASE_PASSWORD --data-file=-
echo -n "YOUR_JWT_SECRET" | gcloud secrets create JWT_SECRET_KEY --data-file=-
```

#### Step 5: Initialize Database Tables

```bash
# Create all tables
uv run python scripts/init_database.py

# Verify tables were created
uv run python scripts/init_database.py status
```

### Cloud SQL Connection

The application uses the **Cloud SQL Python Connector** for secure database access:

| Setting | Local Development | Cloud Run |
|---------|-------------------|-----------|
| `USE_CLOUD_SQL_CONNECTOR` | `true` | `true` |
| `CLOUD_SQL_IP_TYPE` | `PUBLIC` | `PUBLIC` (or `PRIVATE` with VPC) |

**Security Benefits:**
- No IP whitelisting required
- IAM-based authentication
- Encrypted connections automatically

### Delete Resources

**Warning**: Destructive operations - will delete all data!

```bash
# Delete all and recreate
uv run python scripts/provision_all.py --delete

# Delete only (don't recreate)
uv run python scripts/provision_all.py --delete-only

# Skip confirmation (for CI/CD)
uv run python scripts/provision_all.py --delete --force

# Delete specific resources only
uv run python scripts/provision_all.py --delete --skip-bucket --skip-secrets
```

### Verify Setup

```bash
# Check all resources exist
uv run python scripts/provision_all.py

# Test database connection
uv run python scripts/init_database.py status

# Test GCS access
gsutil ls gs://YOUR_BUCKET_NAME

# Start the server and check health
./deploy.sh --dev
curl http://127.0.0.1:8000/status
```

Expected health response:
```json
{
  "application": {"status": "healthy"},
  "services": {
    "postgresql": {"status": "connected"}
  }
}
```

### Individual Scripts Reference

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/provision_all.py` | Master orchestration (full setup) | `uv run python scripts/provision_all.py --full-setup` |
| `scripts/setup_cloud_sql.py` | Cloud SQL instance | `uv run python scripts/setup_cloud_sql.py` |
| `setup_gcp_bucket.py` | GCS bucket | `python setup_gcp_bucket.py` |
| `scripts/setup_service_account.py` | Service account + IAM | `uv run python scripts/setup_service_account.py create` |
| `scripts/setup_secrets.py` | Secret Manager | `uv run python scripts/setup_secrets.py create` |
| `scripts/init_database.py` | Database tables | `uv run python scripts/init_database.py` |
| `scripts/generate_env.py` | Generate .env files | `uv run python scripts/generate_env.py --env production` |

**provision_all.py flags**:
- `--full-setup` - Run complete setup (provision + init-tables + generate-env)
- `--init-tables` - Initialize database tables after provisioning
- `--generate-env` - Generate .env file from provisioned resources
- `--env-output FILE` - Output path for generated .env file (default: .env)
- `--dry-run` - Preview actions without executing
- `--skip-cloudsql`, `--skip-bucket`, etc. - Skip specific steps

## Environment Configuration

Create `.env` file from `.env.example`:

```bash
# Application Settings
ENVIRONMENT="development"
DEBUG=true
LOG_LEVEL="INFO"
LOG_FORMAT="json"

# =============================================================================
# PostgreSQL Cloud SQL Configuration
# =============================================================================
# Instance connection name: <project>:<region>:<instance>
CLOUD_SQL_INSTANCE="your-project:us-central1:your-instance"
DATABASE_NAME="doc_intelligence"
DATABASE_USER="postgres"
DATABASE_PASSWORD="your-secure-password"

# Use Cloud SQL Connector (recommended)
USE_CLOUD_SQL_CONNECTOR=true

# Cloud SQL IP type: PUBLIC for local dev, PRIVATE for production (in VPC)
CLOUD_SQL_IP_TYPE=PUBLIC

# PostgreSQL - Local Development (alternative)
# DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/doc_intelligence"
# USE_CLOUD_SQL_CONNECTOR=false

# PostgreSQL - Production (Cloud SQL with VPC)
# CLOUD_SQL_IP_TYPE="PRIVATE"

# Connection Pool Settings
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800

# Google Cloud Configuration
GCP_PROJECT_ID="your-gcp-project-id"
GCS_BUCKET_NAME="your-gcs-bucket-name"

# Session-Based Authentication
JWT_SECRET_KEY="your-256-bit-secret-key"
JWT_ALGORITHM="HS256"
SESSION_DURATION_HOURS=2
REFRESH_SESSION_DURATION_DAYS=7

# CORS Configuration
CORS_ORIGINS="http://127.0.0.1:3000,https://your-frontend-domain.com"
CORS_CREDENTIALS=true

# Document Processing
MAX_FILE_SIZE=52428800  # 50MB
ALLOWED_FILE_TYPES='["pdf", "xlsx"]'
SIGNED_URL_EXPIRATION_MINUTES=60

# GCP Authentication (choose one):
# Option 1: Service Account Key File
# GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
# Option 2: Application Default Credentials (Cloud Run)
# Leave GOOGLE_APPLICATION_CREDENTIALS unset
```

### Cache Configuration

The API includes an optional caching layer for improved performance:

```bash
# Enable/disable caching (default: true)
CACHE_ENABLED=true

# Backend: "memory" (default) or "redis" (GCP Memorystore)
CACHE_BACKEND=memory

# Default TTL in seconds (default: 300)
CACHE_DEFAULT_TTL=300

# Redis configuration (optional - for production)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=  # optional
REDIS_DB=0

# TTL settings per entity type (seconds)
CACHE_DOCUMENT_TTL=120   # 2 minutes
CACHE_FOLDER_TTL=300     # 5 minutes
CACHE_ORG_TTL=1800       # 30 minutes
CACHE_USER_TTL=300       # 5 minutes
```

**Note**: The cache automatically falls back to memory backend if Redis is unavailable.

### Local Development with Docker PostgreSQL

For local development without Cloud SQL:

```bash
# Start PostgreSQL via Docker
docker run -d \
  --name postgres-dev \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=doc_intelligence \
  -p 5432:5432 \
  postgres:15

# Configure .env for local database
DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/doc_intelligence"
USE_CLOUD_SQL_CONNECTOR=false

# Initialize tables
uv run python scripts/init_database.py
```

## Development Server

### Using deploy.sh (Recommended)

```bash
./deploy.sh --dev
```

### Manual Start

```bash
# IMPORTANT: Use --reload-dir to prevent reload loops
uv run uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000
```

### Debug Mode

```bash
DEBUG=True LOG_LEVEL=DEBUG ./deploy.sh --dev
```

### Server Endpoints

- **API**: http://127.0.0.1:8000
- **Health Check**: http://127.0.0.1:8000/health
- **API Docs**: http://127.0.0.1:8000/docs (development only)
- **ReDoc**: http://127.0.0.1:8000/redoc (development only)

## API Endpoints

### Health & Status
- `GET /` - Root endpoint with API information
- `GET /health` - Basic health check
- `GET /status` - Detailed status with service health
- `GET /ready` - Kubernetes readiness probe
- `GET /live` - Kubernetes liveness probe

### Authentication (Session-Based)
- `GET /api/v1/auth/organizations` - List available organizations
- `POST /api/v1/auth/login` - User login with session + refresh tokens
- `POST /api/v1/auth/refresh-session` - Refresh session token
- `GET /api/v1/auth/validate` - Validate session token
- `POST /api/v1/auth/logout` - Logout current session
- `POST /api/v1/auth/register` - User registration

### Organizations
- `GET /api/v1/organizations` - List organizations
- `POST /api/v1/organizations` - Create organization
- `GET /api/v1/organizations/{org_id}` - Get organization
- `PUT /api/v1/organizations/{org_id}` - Update organization
- `DELETE /api/v1/organizations/{org_id}` - Delete organization

### Users
- `GET /api/v1/users` - List users in organization
- `GET /api/v1/users/{user_id}` - Get user by ID
- `PUT /api/v1/users/{user_id}` - Update user profile

### Documents
- `POST /api/v1/documents/upload` - Upload document
- `GET /api/v1/documents` - List documents with filtering
- `GET /api/v1/documents/{doc_id}` - Get document details
- `GET /api/v1/documents/{doc_id}/download` - Get signed download URL
- `PUT /api/v1/documents/{doc_id}/status` - Update document status
- `DELETE /api/v1/documents/{doc_id}` - Delete document

### Database Query Endpoints
- `GET /api/v1/documents/database/by-filename/{filename}` - Search by filename
- `GET /api/v1/documents/database/by-folder-name/{folder_name}` - List by folder

### Folders
- `GET /api/v1/folders` - List folders
- `POST /api/v1/folders` - Create folder
- `GET /api/v1/folders/{folder_id}` - Get folder
- `PUT /api/v1/folders/{folder_id}` - Update folder
- `DELETE /api/v1/folders/{folder_id}` - Delete folder

### Audit Logs
- `GET /api/v1/audit/` - List audit logs (admins see all, users see own)
- `GET /api/v1/audit/my-activity` - Get current user's activity
- `GET /api/v1/audit/entity/{entity_type}/{entity_id}` - Get entity history (admin only)

### Example API Usage

**User Login**:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'
```

**Upload Document**:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/documents/upload" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -F "file=@invoice.pdf" \
  -F "target_path=invoices/invoice-2025-001.pdf"
```

**List Documents**:
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/documents?page=1&per_page=20" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"
```

## Audit Logging

The system includes comprehensive audit logging for compliance and debugging.

### Tracked Events

| Entity | Actions |
|--------|---------|
| Organization | CREATE, UPDATE, DELETE |
| User | CREATE, UPDATE, DELETE, LOGIN, LOGOUT |
| Folder | CREATE, DELETE, MOVE |
| Document | CREATE, UPDATE, DELETE, UPLOAD, DOWNLOAD, MOVE |

### Audit Log Structure

Each audit log entry contains:
- **Organization ID**: Multi-tenant isolation
- **User ID**: Who performed the action
- **Action**: CREATE, UPDATE, DELETE, LOGIN, LOGOUT, UPLOAD, DOWNLOAD, MOVE
- **Entity Type**: ORGANIZATION, USER, FOLDER, DOCUMENT
- **Entity ID**: ID of the affected entity
- **Details**: JSONB field with old/new values
- **IP Address**: Client IP address
- **Session ID**: Session identifier
- **User Agent**: Browser/client info
- **Timestamp**: When the action occurred

**AI Processing Fields** (optional):
- **Event Type**: AI event (e.g., `document_parsed`, `summary_generated`)
- **Document Hash**: SHA-256 hash of processed document
- **File Name**: Filename for display
- **Job ID**: Reference to processing job

### API Access Control

- **Regular Users**: Can view their own activity only
- **Admin Users**: Can view all audit logs for their organization

### Example Usage

```bash
# Get my activity
curl -X GET "http://127.0.0.1:8000/api/v1/audit/my-activity" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"

# Get all audit logs (admin only)
curl -X GET "http://127.0.0.1:8000/api/v1/audit/?page=1&per_page=50" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"

# Get entity history (admin only)
curl -X GET "http://127.0.0.1:8000/api/v1/audit/entity/DOCUMENT/doc-uuid" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"
```

## Deployment

All deployment modes are consolidated into a single `deploy.sh` script.

### Deployment Modes

```
┌─────────────────────────────────────────────────────────────┐
│ DEPLOYMENT MODES                                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Local development  → ./deploy.sh --dev        (instant)     │
│ Test only          → ./deploy.sh --test       (15-25 sec)   │
│ Quick deploy       → ./deploy.sh --fast       (3-5 min)     │
│ Full deploy        → ./deploy.sh --deploy     (6-9 min)     │
│ CI/CD              → cloudbuild.yaml          (5-7 min)     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Quick Commands

```bash
# Local development
./deploy.sh --dev

# Test deployed service
./deploy.sh --test https://your-service.run.app

# Deploy to development
./deploy.sh --deploy --project-id my-project

# Deploy to production
./deploy.sh --deploy --project-id my-project --env production

# Quick deploy (skip infrastructure checks)
./deploy.sh --fast --project-id my-project
```

### Full Deploy Options

```bash
./deploy.sh --deploy \
  --project-id biz2bricks-dev-v1 \
  --region us-central1 \
  --bucket biz2bricks-dev-v1-document-store
```

### Cloud Build (CI/CD)

Single `cloudbuild.yaml` for all environments:

```bash
# Manual deployment (development)
gcloud builds submit --config cloudbuild.yaml

# Production deployment
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_ENVIRONMENT=production,_SERVICE_NAME=document-intelligence-api,_SECRET_SUFFIX=-prod
```

**Automatic Triggers**:
- `develop` branch → development environment
- `master` branch → production environment

### Post-Deployment Verification

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe document-intelligence-api \
  --region=us-central1 \
  --format="value(status.url)")

# Health check
curl "$SERVICE_URL/health"

# View logs
gcloud run services logs read document-intelligence-api \
  --region=us-central1 \
  --limit=50
```

### Cloud Run Service Details

#### Live Service URLs

| Environment | Service Name | URL |
|-------------|--------------|-----|
| Development | `document-intelligence-api-dev` | https://document-intelligence-api-dev-726919062103.us-central1.run.app |
| Production | `document-intelligence-api` | *(configured via production trigger)* |

#### Health Endpoints

```bash
# Check if service is healthy (includes database connectivity)
curl https://document-intelligence-api-dev-726919062103.us-central1.run.app/health

# Detailed status with all service health
curl https://document-intelligence-api-dev-726919062103.us-central1.run.app/status

# Liveness probe (app is running)
curl https://document-intelligence-api-dev-726919062103.us-central1.run.app/live

# Readiness probe (ready to serve traffic)
curl https://document-intelligence-api-dev-726919062103.us-central1.run.app/ready
```

#### Configuration Files

| File | Purpose |
|------|---------|
| `development-env.yaml` | Environment variables for development deployment |
| `production-env.yaml` | Environment variables for production deployment |
| `cloudbuild.yaml` | Cloud Build CI/CD configuration |
| `deploy.sh` | Manual deployment script |

#### Cloud SQL Connection

The service connects to Cloud SQL PostgreSQL using the **Cloud SQL Auth Proxy**:

```yaml
# Key environment variables (set in development-env.yaml)
CLOUD_SQL_INSTANCE: "biz2bricks-dev-v1:us-central1:doc-intelligence-db"
USE_CLOUD_SQL_CONNECTOR: "true"
CLOUD_SQL_IP_TYPE: "PUBLIC"  # Use PUBLIC for Auth Proxy, PRIVATE requires VPC
DATABASE_NAME: "doc_intelligence"
DATABASE_USER: "postgres"
```

**Required IAM Roles** for the Cloud Run service account:
- `roles/cloudsql.client` - Connect to Cloud SQL
- `roles/storage.objectAdmin` - Access GCS bucket
- `roles/logging.logWriter` - Write logs

#### Monitoring & Logs

```bash
# Stream logs in real-time
gcloud run services logs tail document-intelligence-api-dev \
  --region=us-central1

# View recent logs
gcloud run services logs read document-intelligence-api-dev \
  --region=us-central1 \
  --limit=100

# View logs in Cloud Console
# https://console.cloud.google.com/run/detail/us-central1/document-intelligence-api-dev/logs

# Check service revisions
gcloud run revisions list \
  --service=document-intelligence-api-dev \
  --region=us-central1
```

#### Troubleshooting Cloud Run

**Health check failing (503)?**
```bash
# Check database connectivity settings
# Ensure CLOUD_SQL_IP_TYPE=PUBLIC (not PRIVATE) unless using VPC Connector
# Verify Cloud SQL instance name is correct

# Check service account has cloudsql.client role
gcloud projects get-iam-policy PROJECT_ID \
  --filter="bindings.members:SERVICE_ACCOUNT" \
  --format="table(bindings.role)"
```

**Container not starting?**
```bash
# Check container logs for startup errors
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=document-intelligence-api-dev" \
  --limit=50 \
  --format="table(timestamp,textPayload)"
```

## Project Structure

```
doc_intelligence_backend_api_v2.0/
├── app/                                    # Main application package
│   ├── main.py                            # FastAPI application entry point
│   │
│   ├── api/                               # API routes
│   │   └── v1/
│   │       ├── auth.py                   # Authentication endpoints
│   │       ├── organizations.py          # Organization management
│   │       ├── users.py                  # User management
│   │       ├── folders.py                # Folder management
│   │       ├── audit.py                  # Audit log endpoints
│   │       ├── audit_context.py          # Audit context utilities
│   │       ├── documents_main.py         # Document router aggregator
│   │       └── documents_modules/        # Modular document endpoints
│   │           ├── common.py            # Shared utilities and error handlers
│   │           ├── document_upload.py
│   │           ├── document_management.py
│   │           └── document_download.py
│   │
│   ├── core/                              # Core functionality
│   │   ├── config.py                     # Pydantic settings
│   │   ├── cache.py                      # Caching infrastructure (memory/Redis)
│   │   ├── db_client.py                  # PostgreSQL DatabaseManager
│   │   ├── gcs_client.py                 # GCS client singleton
│   │   ├── security.py                   # JWT and password handling
│   │   ├── logging.py                    # Structured logging
│   │   └── exceptions.py                 # Custom exceptions
│   │
│   ├── models/                            # Data models
│   │   ├── user.py                       # User Pydantic models
│   │   ├── organization.py               # Organization models
│   │   ├── document.py                   # Document models
│   │   ├── folder.py                     # Folder models
│   │   └── schemas/                      # Request/response schemas
│   │       ├── __init__.py              # Re-exports all schemas
│   │       ├── base.py                  # Pagination models
│   │       ├── organization.py          # Organization schemas
│   │       ├── user.py                  # User schemas
│   │       ├── folder.py                # Folder schemas
│   │       ├── document.py              # Document schemas
│   │       ├── errors.py                # Error responses
│   │       ├── stats.py                 # Stats & audit schemas
│   │       └── validators.py            # Shared validators
│   │
│   ├── services/                          # Business logic
│   │   ├── auth_service.py               # Authentication logic
│   │   ├── user_service.py               # User management (with audit)
│   │   ├── org_service.py                # Organization management (with audit)
│   │   ├── folder_service.py             # Folder management (with audit)
│   │   ├── audit_service.py              # Audit logging service
│   │   └── document/                     # Document service facade (5 specialized services)
│   │       ├── document_service.py           # Main facade
│   │       ├── document_base_service.py
│   │       ├── document_validation_service.py
│   │       ├── document_storage_service.py
│   │       ├── document_crud_service.py      # (with audit)
│   │       ├── document_query_service.py
│   │       └── document_download_service.py
│   │
│   └── utils/                             # Utility functions
│       └── validators.py
│
├── scripts/                               # Utility & provisioning scripts
│   ├── provision_all.py                  # Master GCP provisioning orchestrator
│   ├── setup_service_account.py          # Service account + IAM setup
│   ├── setup_cloud_sql.py                # Cloud SQL instance setup
│   ├── setup_secrets.py                  # Secret Manager setup
│   ├── generate_env.py                   # Environment file generator
│   ├── generate_client.py                # TypeScript type generator
│   ├── init_database.py                  # Database table initialization
│   └── provision_config.yaml             # Example provisioning config
│
├── deploy.sh                             # Unified deployment script
├── cloudbuild.yaml                       # Cloud Build configuration
├── setup_gcp_bucket.py                   # GCS bucket setup
│
├── Dockerfile                            # Container image definition
├── pyproject.toml                        # Python project config (uv)
├── uv.lock                               # Locked dependencies
│
├── .env.example                          # Environment template
├── api-types.ts                          # TypeScript type definitions
│
├── CLAUDE.md                             # Claude Code instructions
├── README.md                             # This file
│
└── tests/                                # Test suite
    ├── conftest.py                      # Shared fixtures and configuration
    ├── fixtures/                        # Test fixtures and sample data
    │   └── sample_files/               # Sample test files (PDF, XLSX)
    ├── utils/                           # Test utilities
    ├── unit/                            # Unit tests
    │   ├── core/                       # Core module tests
    │   │   ├── test_config.py         # Configuration tests
    │   │   ├── test_security.py       # Security/JWT tests
    │   │   └── test_db_models.py      # SQLAlchemy model tests
    │   └── services/                   # Service layer tests
    │       ├── test_user_service.py
    │       ├── test_audit_service.py
    │       └── test_document_service.py
    └── integration/                     # Integration tests
        ├── api/                        # API endpoint tests
        │   ├── test_auth.py
        │   ├── test_health.py
        │   └── test_users.py
        └── workflows/                  # End-to-end workflow tests
            └── test_auth_workflow.py
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run only unit tests
uv run pytest tests/unit/ -v

# Run only integration tests
uv run pytest tests/integration/ -v

# Run with coverage
uv run pytest tests/ --cov=app --cov-report=html

# Run specific test file
uv run pytest tests/unit/core/test_security.py -v

# Run tests matching pattern
uv run pytest tests/ -k "test_login" -v
```

### Test Structure

- **Unit Tests** (`tests/unit/`): Test individual components in isolation using mocks
- **Integration Tests** (`tests/integration/`): Test API endpoints and workflows

### Test Fixtures

Key fixtures in `tests/conftest.py`:
- `async_client` - AsyncClient for API testing
- `mock_db_session` - Mock database session
- `mock_gcs_client` - Mock GCS client
- `sample_pdf_content` - Valid PDF bytes for testing
- `gcs_cleanup` - Automatic GCS cleanup utility

## Troubleshooting

### Common Issues

**1. Database Connection Failed**
```
Error: Cannot connect to PostgreSQL
```
**Solutions**:
- Check `DATABASE_URL` format: `postgresql+asyncpg://user:pass@host:port/db`
- Verify PostgreSQL is running: `docker ps` or `pg_isready`
- For Cloud SQL: Verify `CLOUD_SQL_INSTANCE` and connector settings

**2. GCS Upload/Download Failures**
```
Error: 403 Forbidden
```
**Solutions**:
- Verify `GCS_BUCKET_NAME` environment variable
- Check service account permissions (`roles/storage.admin`)
- Verify CORS configuration on bucket

**3. JWT Token Issues**
```
Error: Invalid signature or Token expired
```
**Solutions**:
- Ensure `JWT_SECRET_KEY` is consistent across environments
- Check system clock synchronization
- Validate token expiry settings

**4. Reload Loops in Development**
```
WARNING: WatchFiles detected changes in '.venv/...'
```
**Solution**: Always use `--reload-dir app`:
```bash
uv run uvicorn app.main:app --reload --reload-dir app
```

### Debug Mode

Enable verbose logging:
```bash
DEBUG=True LOG_LEVEL=DEBUG ./deploy.sh --dev
```

### Health Check

```bash
curl -X GET "http://127.0.0.1:8000/status" | python -m json.tool
```

Expected response:
```json
{
  "application": {
    "name": "Document Intelligence API",
    "version": "1.0.0",
    "environment": "development",
    "status": "healthy"
  },
  "services": {
    "postgresql": {
      "status": "connected"
    }
  }
}
```

## Production Checklist

- [ ] PostgreSQL Cloud SQL instance created
- [ ] GCS bucket created with CORS configuration
- [ ] Service account with appropriate IAM roles
- [ ] JWT_SECRET_KEY changed from default (256-bit)
- [ ] CORS origins configured for production domain
- [ ] Environment variables set in Cloud Run
- [ ] Health endpoints responding (`/health`, `/status`)
- [ ] Authentication flow tested end-to-end
- [ ] Document upload/download working

---

**Need help?** Check the troubleshooting section or review logs with `DEBUG=True`.
