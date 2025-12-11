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
- [GCP Resource Provisioning](#gcp-resource-provisioning)
- [Environment Configuration](#environment-configuration)
- [Database Setup](#database-setup)
- [Cloud Storage Setup](#cloud-storage-setup)
- [Development Server](#development-server)
- [API Endpoints](#api-endpoints)
- [Audit Logging](#audit-logging)
- [Deployment](#deployment)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

## Architecture Overview

The system follows a **clean architecture** with service composition patterns:

- **Core Layer**: Configuration, clients (Database, GCS), security, logging, exceptions
- **Service Layer**: Business logic with Facade pattern for document operations
- **API Layer**: FastAPI routers with dependency injection and session-based auth
- **Models Layer**: Pydantic v2 models and SQLAlchemy ORM models

### Document Service Architecture

The document processing system uses a **Facade Pattern** with specialized services:

```
┌─────────────────────────────────────────────────────────────┐
│                    DocumentService (Facade)                 │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│ │  Validation     │  │    Storage      │  │     CRUD        │ │
│ │   Service       │  │    Service      │  │    Service      │ │
│ └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│ ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│ │     Query       │  │     Sync        │  │   Download      │ │
│ │    Service      │  │    Service      │  │    Service      │ │
│ └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
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
- **File Storage**: Google Cloud Storage with signed URLs
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

## GCP Resource Provisioning

Automated scripts to provision all required GCP resources for deployment.

### Quick Start (Interactive)

```bash
# Complete GCP setup with prompts
uv run python scripts/provision_all.py
```

This master script orchestrates:
1. Service Account creation with IAM roles
2. Cloud SQL PostgreSQL instance, database, and user
3. GCS bucket with versioning
4. Secret Manager secrets (DATABASE_PASSWORD, JWT_SECRET_KEY, REFRESH_SECRET_KEY)
5. Database table initialization
6. Environment file generation

### CI/CD (Non-Interactive)

```bash
# Provision using config file
uv run python scripts/provision_all.py \
  --config scripts/provision_config.yaml \
  --non-interactive \
  --output-env .env.production
```

### Individual Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/provision_all.py` | Master orchestration | `uv run python scripts/provision_all.py` |
| `scripts/setup_service_account.py` | Service account + IAM | `uv run python scripts/setup_service_account.py create` |
| `scripts/setup_cloud_sql.py` | Cloud SQL instance | `uv run python scripts/setup_cloud_sql.py` |
| `scripts/setup_secrets.py` | Secret Manager | `uv run python scripts/setup_secrets.py create` |
| `scripts/generate_env.py` | Generate .env files | `uv run python scripts/generate_env.py --env production` |
| `setup_gcp_bucket.py` | GCS bucket | `python setup_gcp_bucket.py` |
| `scripts/init_database.py` | Database tables | `uv run python scripts/init_database.py` |

### Configuration File

Copy and customize `scripts/provision_config.yaml` for your environment:

```yaml
project_id: "your-project-id"
region: "us-central1"

cloud_sql:
  instance_name: "doc-intelligence-db"
  tier: "db-f1-micro"  # or db-custom-1-3840 for production
  database_name: "doc_intelligence"

storage:
  bucket_name: "${project_id}-document-store"

service_account:
  name: "document-intelligence-api-sa"
  roles:
    - "roles/cloudsql.client"
    - "roles/storage.objectAdmin"
    - "roles/secretmanager.secretAccessor"

secrets:
  use_secret_manager: true
```

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
CLOUD_SQL_INSTANCE=biz2bricks-dev-v1:us-central1:biz-2-bricks-intelli-doc-dev
DATABASE_NAME=biz-2-bricks-intelli-doc-dev
DATABASE_USER=postgres
DATABASE_PASSWORD=&e<IK7kq0)N2J/nt

# Use direct connection for local development (bypass Cloud SQL connector)
USE_CLOUD_SQL_CONNECTOR=true

# Cloud SQL IP type: PUBLIC for local dev, PRIVATE for production (in VPC)
CLOUD_SQL_IP_TYPE=PUBLIC

# Direct PostgreSQL connection URL - update PUBLIC_IP with your Cloud SQL public IP
# NOTE: Password is URL-encoded (&=%26, <=%3C, )=%29, /=%2F)
DATABASE_URL=postgresql+asyncpg://postgres:%26e%3CIK7kq0%29N2J%2Fnt@136.112.54.69:5432/biz-2-bricks-intelli-doc-dev

# # PostgreSQL - Local Development
# DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/doc_intelligence"
# USE_CLOUD_SQL_CONNECTOR=false

# PostgreSQL - Production (Cloud SQL)
# DATABASE_NAME="doc_intelligence"
# DATABASE_USER="postgres"
# DATABASE_PASSWORD="your-secure-password"
# CLOUD_SQL_INSTANCE="project:region:instance"
# USE_CLOUD_SQL_CONNECTOR=true
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

## Database Setup

### Local Development with PostgreSQL

1. **Start PostgreSQL** (Docker or native):
```bash
# Using Docker
docker run -d \
  --name postgres-dev \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=doc_intelligence \
  -p 5432:5432 \
  postgres:15
```

2. **Configure environment**:
```bash
DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/doc_intelligence"
USE_CLOUD_SQL_CONNECTOR=false
```

3. **Initialize tables**:
```bash
uv run python scripts/init_database.py
```

4. **Verify setup**:
```bash
uv run python scripts/init_database.py status
```

### Production with Cloud SQL

1. Create Cloud SQL instance via GCP Console or `deploy.sh`
2. Configure `.env.production`:
```bash
DATABASE_NAME="doc_intelligence"
DATABASE_USER="postgres"
DATABASE_PASSWORD="secure-password"
CLOUD_SQL_INSTANCE="project:region:instance"
USE_CLOUD_SQL_CONNECTOR=true
```

## Local Development with Cloud Resources

This section guides you through running the application locally while connecting to cloud resources (Cloud SQL and GCS bucket).

### Prerequisites

1. **Google Cloud SDK** installed and authenticated:
```bash
# Install gcloud CLI (if not installed)
# macOS
brew install google-cloud-sdk

# Login to your Google Cloud account
gcloud auth login

# Set up Application Default Credentials (for Python SDK - Cloud SQL, GCS)
gcloud auth application-default login

# Set your active project
gcloud config set project YOUR_PROJECT_ID

# Verify your configuration
gcloud config list

# Check authentication status
gcloud auth list
```

2. **Required GCP APIs** enabled:
```bash
gcloud services enable sqladmin.googleapis.com
gcloud services enable storage.googleapis.com
```

### Step 1: Create Cloud SQL Instance

Use the automated setup script:
```bash
uv run python scripts/setup_cloud_sql.py
```

This interactive script will:
- Create a Cloud SQL PostgreSQL 15 instance
- Create the database
- Create the database user
- Output the configuration for your `.env` file

**Manual creation** (if preferred):
```bash
# Create instance (takes 5-10 minutes)
# NOTE: No --authorized-networks flag - use Cloud SQL Connector for secure access
gcloud sql instances create doc-intelligence-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --assign-ip

# Create database
gcloud sql databases create doc_intelligence \
  --instance=doc-intelligence-db

# Set postgres user password
gcloud sql users set-password postgres \
  --instance=doc-intelligence-db \
  --password=YOUR_SECURE_PASSWORD
```

### Cloud SQL Connection Methods

This application uses the **Cloud SQL Python Connector** for secure database access. This approach:
- **No IP whitelisting needed** - Authenticates via IAM credentials
- **Encrypted connections** - All traffic is encrypted automatically
- **Works everywhere** - Same method for local dev and production

**Local Development Setup:**
```bash
# 1. Authenticate with Google Cloud
gcloud auth application-default login

# 2. Set environment variables in .env
USE_CLOUD_SQL_CONNECTOR=true
CLOUD_SQL_IP_TYPE=PUBLIC  # Use PUBLIC for local development
```

**Production (Cloud Run):**
```bash
# Environment variables
USE_CLOUD_SQL_CONNECTOR=true
CLOUD_SQL_IP_TYPE=PRIVATE  # Use PRIVATE for Cloud Run (VPC)
```

**Security Note:** The Cloud SQL instance has no authorized networks configured. All access must go through the Cloud SQL Connector, which authenticates via:
- Application Default Credentials (local development)
- Service Account (Cloud Run / production)

### Step 2: Create GCS Bucket

Use the automated setup script:
```bash
python setup_gcp_bucket.py
```

**Manual creation**:
```bash
# Create bucket
gsutil mb -p YOUR_PROJECT_ID -c STANDARD -l us-central1 gs://YOUR_BUCKET_NAME

# Enable versioning
gsutil versioning set on gs://YOUR_BUCKET_NAME
```

### Step 3: Configure Environment

Create your `.env` file with cloud resource configuration:
```bash
# Application Settings
ENVIRONMENT="development"
DEBUG=true
LOG_LEVEL="INFO"
LOG_FORMAT="text"

# =============================================================================
# PostgreSQL Cloud SQL Configuration
# =============================================================================
# Instance connection name: <project>:<region>:<instance>
CLOUD_SQL_INSTANCE=your-project:us-central1:doc-intelligence-db
DATABASE_NAME=doc_intelligence
DATABASE_USER=postgres
DATABASE_PASSWORD=your-secure-password

# Use Cloud SQL connector (set to true for Cloud Run, can be true or false for local)
USE_CLOUD_SQL_CONNECTOR=true

# Cloud SQL IP type: PUBLIC for local dev, PRIVATE for production (in VPC)
CLOUD_SQL_IP_TYPE=PUBLIC

# Direct PostgreSQL connection URL (alternative to Cloud SQL connector)
# NOTE: URL-encode special characters in password: & = %26, < = %3C, > = %3E, etc.
# DATABASE_URL=postgresql+asyncpg://postgres:password@PUBLIC_IP:5432/doc_intelligence

# =============================================================================
# Google Cloud Storage Configuration
# =============================================================================
GCP_PROJECT_ID=your-project-id
GCS_BUCKET_NAME=your-bucket-name

# =============================================================================
# Authentication
# =============================================================================
JWT_SECRET_KEY=your-256-bit-secret-key-here

# =============================================================================
# GCP Authentication (for local development)
# =============================================================================
# Option 1: Use Application Default Credentials (recommended)
# Run: gcloud auth application-default login

# Option 2: Service Account Key File
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

### Step 4: Initialize Database Tables

```bash
uv run python scripts/init_database.py
```

Verify the tables were created:
```bash
uv run python scripts/init_database.py status
```

### Step 5: Start the Development Server

```bash
./deploy.sh --dev
```

Or manually:
```bash
uv run uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000
```

### Step 6: Verify Connection

Check the health endpoint:
```bash
curl http://127.0.0.1:8000/status
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
    "postgresql": {"status": "connected"},
    "gcs": {"status": "connected"}
  }
}
```

### Security Notes

The Cloud SQL instance uses the **Cloud SQL Python Connector** for all access - no IP whitelisting required. This is the recommended secure approach:

1. **No authorized networks** - Instance doesn't accept direct IP connections
2. **IAM-based authentication** - Uses Application Default Credentials or Service Account
3. **Encrypted connections** - All traffic encrypted automatically
4. Never commit `.env` files with credentials

### Troubleshooting

**Cannot connect to Cloud SQL:**
```bash
# Check instance is running
gcloud sql instances describe doc-intelligence-db --format="value(state)"

# Verify you're authenticated
gcloud auth application-default login

# Check Cloud SQL Connector is enabled in .env
USE_CLOUD_SQL_CONNECTOR=true
CLOUD_SQL_IP_TYPE=PUBLIC  # For local development
```

**GCS permission denied:**
```bash
# Ensure you're authenticated
gcloud auth application-default login

# Check bucket exists
gsutil ls gs://YOUR_BUCKET_NAME
```

## Cloud Storage Setup

### Automated Setup

```bash
python setup_gcp_bucket.py
```

This interactive script will:
- Create the GCS bucket with optimal settings
- Configure CORS for direct client uploads
- Set up lifecycle policies
- Test upload/download functionality

### Manual Setup

```bash
gsutil mb -p your-project-id -c STANDARD -l us-central1 gs://your-bucket-name
gsutil cors set cors.json gs://your-bucket-name
gsutil uniformbucketlevelaccess set on gs://your-bucket-name
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
| Document | UPLOAD, UPDATE, DELETE |

### Audit Log Structure

Each audit log entry contains:
- **Organization ID**: Multi-tenant isolation
- **User ID**: Who performed the action
- **Action**: CREATE, UPDATE, DELETE, LOGIN, etc.
- **Entity Type**: ORGANIZATION, USER, FOLDER, DOCUMENT
- **Entity ID**: ID of the affected entity
- **Details**: JSONB field with old/new values
- **IP Address**: Client IP address
- **User Agent**: Browser/client info
- **Timestamp**: When the action occurred

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
│   │           ├── document_upload.py
│   │           ├── document_management.py
│   │           ├── document_download.py
│   │           └── document_sync.py
│   │
│   ├── core/                              # Core functionality
│   │   ├── config.py                     # Pydantic settings
│   │   ├── db_client.py                  # PostgreSQL DatabaseManager
│   │   ├── db_models.py                  # SQLAlchemy ORM models (incl. AuditLogModel)
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
│   │   └── schemas.py                    # Request/response schemas
│   │
│   ├── services/                          # Business logic
│   │   ├── auth_service.py               # Authentication logic
│   │   ├── user_service.py               # User management (with audit)
│   │   ├── org_service.py                # Organization management (with audit)
│   │   ├── folder_service.py             # Folder management (with audit)
│   │   ├── audit_service.py              # Audit logging service
│   │   └── document/                     # Document service facade
│   │       ├── document_service.py           # Main facade
│   │       ├── document_base_service.py
│   │       ├── document_validation_service.py
│   │       ├── document_storage_service.py
│   │       ├── document_crud_service.py      # (with audit)
│   │       ├── document_query_service.py
│   │       ├── document_sync_service.py
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
