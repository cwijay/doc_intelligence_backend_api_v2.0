# Document Intelligence Backend

A comprehensive **AI-powered document intelligence platform** built with FastAPI, featuring advanced document processing, analysis, and content generation capabilities. The system integrates with Google Cloud Platform (Firebase/Firestore, Cloud Storage) and includes sophisticated AI services for document summarization, FAQ generation, and question extraction with intelligent caching.

**Product Requirements**: https://claude.ai/public/artifacts/9ae012dd-ec9b-4547-ab4d-af2e0a10d62b

## 🎯 **Key Features**

- **🤖 AI Content Generation**: Automated document summaries, FAQ, and questions with smart caching
- **📊 Advanced Document Processing**: LlamaParse integration for PDF, XLSX, and more
- **🏗️ Sophisticated Architecture**: Facade pattern with 7 specialized document services
- **🔐 Enterprise Authentication**: Session-based JWT with automatic refresh token rotation
- **☁️ Cloud-Native**: Google Cloud Run deployment with Firestore named database support
- **⚡ High Performance**: Firestore-first APIs with optimized caching strategies

## 📋 Table of Contents

- [Architecture Overview](#architecture-overview)
- [Technology Stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Environment Configuration](#environment-configuration)
- [Firebase & GCP Setup](#firebase--gcp-setup)
- [Cloud Storage Setup](#cloud-storage-setup)
- [Firestore Indexes](#firestore-indexes)
- [Development Server](#development-server)
- [API Endpoints](#api-endpoints)
- [Testing](#testing)
- [Cloud Run Deployment](#cloud-run-deployment)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

## 🏗️ Architecture Overview

The system follows a **sophisticated clean architecture** with advanced service composition patterns:

- **Core Layer**: Configuration, clients (Firebase, GCS), security, logging, exceptions
- **Service Layer**: **Facade pattern** with specialized microservices for document processing
- **API Layer**: FastAPI routers with dependency injection and session-based auth
- **Models Layer**: Pydantic v2 models with comprehensive validation

### 🚀 Advanced Document Service Architecture

The document processing system uses a **Facade Pattern** with 7 specialized services:

```
┌─────────────────────────────────────────────────────────────┐
│                    DocumentService (Facade)                 │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│ │  Validation     │  │    Storage      │  │     CRUD        │ │
│ │   Service       │  │    Service      │  │    Service      │ │
│ └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│ ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│ │     Query       │  │      AI         │  │     Sync        │ │
│ │    Service      │  │    Service      │  │    Service      │ │
│ └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│ ┌─────────────────┐                                           │
│ │   Download      │                                           │
│ │   Service       │                                           │
│ └─────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   FastAPI API   │───▶│  Firebase Client │───▶│ Firestore Named │
│    Endpoints    │    │    (Singleton)   │    │    Database     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                                              
         ▼                                              
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   GCS Client    │───▶│   Cloud Storage  │───▶│   AI Services   │
│   (Singleton)   │    │     Bucket       │    │ OpenAI/LlamaParse│
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🛠️ Technology Stack

### **Core Infrastructure**
- **Backend**: FastAPI 0.115.7 with async/await and advanced dependency injection
- **Database**: Google Cloud Firestore with **named database** support (`biz2bricks-docdb-v1`)
- **File Storage**: Google Cloud Storage with signed URLs and CORS configuration
- **Authentication**: **Session-based JWT** with automatic refresh token rotation
- **Dependency Management**: **uv** (ultra-fast Python package installer - 10-100x faster than pip)
- **Deployment**: Google Cloud Run with automated CI/CD via Cloud Build

### **AI & LLM Integration**
- **Language Models**: OpenAI GPT-5-mini (configurable) via OpenAI 1.86.0
- **AI Orchestration**: LangChain 0.3.18 + LangChain-OpenAI 0.3.29 for robust AI workflows
- **Document Parsing**: LlamaParse 0.5.20 with LlamaIndex Core 0.13.3 (Pydantic v2 compatible)
- **Vector Database**: Pinecone 5.4.0 with gRPC support for semantic search
- **Intelligent Caching**: Firestore-based AI content caching for performance optimization

### **Development & Quality**
- **Validation**: Pydantic v2 (2.11.0+) with strict type checking
- **Logging**: Structured JSON logging with Structlog 24.1.0+ and request middleware
- **Code Quality**: Black, Ruff, MyPy, Pre-commit hooks
- **Testing**: Pytest with async support and comprehensive coverage
- **File Processing**: Pandas 2.2.3, OpenPyXL 3.1.5 for data extraction

## 📋 Prerequisites

- **Python 3.12+** (required for latest dependencies and type hints)
- **Google Cloud Account** with billing enabled
- **gcloud CLI** installed and configured
- **uv** (recommended) or **pip** for dependency management
- **Docker** (for Cloud Run deployment)
- **Git** for version control

### AI Services (Optional)
- **OpenAI API Key** (for document summarization and AI features)
- **LlamaParse API Key** (for advanced document parsing)
- **Pinecone API Key** (for vector search capabilities)

## 🚀 Installation

### Option 1: Using uv (Recommended)

`uv` provides superior dependency resolution and faster installation compared to pip.

1. **Install uv** (if not already installed):
   ```bash
   # macOS/Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Windows
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   
   # Alternative: pipx install uv
   ```

2. **Clone and setup with uv**:
   ```bash
   git clone <repository-url>
   cd document-intelligence-backend
   uv sync  # Creates .venv and installs all dependencies
   ```

3. **Activate environment**:
   ```bash
   source .venv/bin/activate  # macOS/Linux
   # Or use: uv run <command> to run commands directly
   ```

### Option 2: Using pip (Legacy)

1. **Clone and setup environment**
   ```bash
   git clone <repository-url>
   cd document-intelligence-backend
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

### Managing Dependencies

**With uv (Recommended)**:
```bash
# Add new dependency
uv add package-name

# Add development dependency  
uv add --dev package-name

# Update all dependencies
uv sync --upgrade

# Run commands in the environment
uv run uvicorn app.main:app --reload

# Activate shell (optional)
source .venv/bin/activate
```

**With pip (Legacy)**:
```bash
# Install dependencies
pip install -r requirements.txt

# Add new package
pip install package-name
pip freeze > requirements.txt

# Always activate environment first
source .venv/bin/activate
```

## ⚙️ Environment Configuration

### Required Environment Variables

Create `.env` file from `.env.example`:

```bash
# Application Settings
ENVIRONMENT="development"  # or "production"
DEBUG=true
LOG_LEVEL="INFO"
LOG_FORMAT="json"

# Google Cloud Configuration  
FIREBASE_PROJECT_ID="your-gcp-project-id"
FIREBASE_DATABASE_ID="your-firestore-database-name"  # Important: Use named database
GCP_PROJECT_ID="your-gcp-project-id"
GCS_BUCKET_NAME="your-gcs-bucket-name"

# Session-Based Authentication & Security
JWT_SECRET_KEY="your-256-bit-secret-key-change-in-production"
JWT_ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
SESSION_DURATION_HOURS=2
REFRESH_SESSION_DURATION_DAYS=7

# AI/ML Services Configuration
OPENAI_API_KEY="your-openai-api-key"
OPENAI_MODEL="gpt-5-mini"  # Configurable model - used across all AI services (summary, FAQ, questions)
OPENAI_MAX_TOKENS=4000     # Maximum tokens for AI responses
OPENAI_TEMPERATURE=0.0     # Temperature for deterministic responses

# Document Processing AI
LLAMAPARSE_API_KEY="your-llamaparse-api-key"  # For advanced document parsing

# Vector Search (Optional)
PINECONE_API_KEY="your-pinecone-api-key"
PINECONE_ENVIRONMENT="your-pinecone-environment"
PINECONE_INDEX_NAME="document-intelligence"

# AI Caching Configuration
AI_CONTENT_CACHING=true   # Enable Firestore caching for AI content (recommended)
AI_CACHE_TTL_HOURS=168    # Cache TTL in hours (default: 1 week)

# CORS Configuration
CORS_ORIGINS="http://127.0.0.1:3000,https://your-frontend-domain.com"
CORS_CREDENTIALS=true

# Document Processing Configuration
MAX_FILE_SIZE=52428800  # 50MB
ALLOWED_FILE_TYPES='["pdf", "xlsx"]'
SIGNED_URL_EXPIRATION_MINUTES=60
DOCUMENT_UPLOAD_TIMEOUT=300

# Authentication Methods (choose one):
# Option 1: Service Account Key File
# GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
# 
# Option 2: Service Account JSON String  
# FIREBASE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
#
# Option 3: Application Default Credentials (recommended for development)
# Leave both above options commented
```

### Production Environment

For production (`.env.production`):

```bash
ENVIRONMENT="production"
DEBUG=false
LOG_LEVEL="INFO"
LOG_FORMAT="json"

# Use your actual production values
FIREBASE_PROJECT_ID="your-prod-project"
FIREBASE_DATABASE_ID="your-prod-database"
GCS_BUCKET_NAME="your-prod-bucket"
JWT_SECRET_KEY="your-production-secret-key"
PRODUCTION_CORS_ORIGINS='["https://your-app.com"]'
```

## 🔥 Firebase & GCP Setup

### Step 1: Google Cloud Project Setup

```bash
# Create or select project
gcloud projects create your-project-id
gcloud config set project your-project-id

# Enable required APIs
gcloud services enable firestore.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

### Step 2: Create Firestore Database

**Important**: Use a named database, not the default database.

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project
3. Navigate to **Firestore Database**
4. Click **Create database**
5. **Choose a database ID** (e.g., `biz2bricks-docdb-v1`)
6. Select location closest to users
7. Configure security rules (start in test mode for development)

### Step 3: Authentication Setup

**Development (Application Default Credentials)**:
```bash
gcloud auth application-default login
```

**Production (Service Account)**:
```bash
# Create service account
gcloud iam service-accounts create firestore-admin \
    --display-name="Firestore Admin Service Account"

# Grant permissions
gcloud projects add-iam-policy-binding your-project-id \
    --member="serviceAccount:firestore-admin@your-project-id.iam.gserviceaccount.com" \
    --role="roles/datastore.user"

gcloud projects add-iam-policy-binding your-project-id \
    --member="serviceAccount:firestore-admin@your-project-id.iam.gserviceaccount.com" \
    --role="roles/storage.admin"

# Create key file
gcloud iam service-accounts keys create firebase-key.json \
    --iam-account=firestore-admin@your-project-id.iam.gserviceaccount.com
```

### Step 4: Verify Firebase Connection

```bash
# Test Firebase connectivity
python -c "
import asyncio
from app.core.firebase_client import init_firebase
async def test():
    await init_firebase()
    print('✅ Firebase connected successfully')
asyncio.run(test())
"
```

## 🗄️ Cloud Storage Setup

### Automated Setup (Recommended)

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
# Create bucket
gsutil mb -p your-project-id -c STANDARD -l us-central1 gs://your-bucket-name

# Set lifecycle policy for temp files
gsutil lifecycle set bucket-lifecycle.json gs://your-bucket-name

# Configure CORS for web uploads
gsutil cors set cors.json gs://your-bucket-name

# Set uniform bucket-level access
gsutil uniformbucketlevelaccess set on gs://your-bucket-name
```

### Verify GCS Setup

```bash
python scripts/verify_gcs_setup.py
```

## 📊 Firestore Indexes

The application requires composite indexes for efficient querying.

### Automated Index Creation

```bash
python create_firestore_indexes.py
```

This will display URLs to automatically create required indexes:

**Required Indexes:**

1. **Organizations Index**:
   - Collection: `organizations`
   - Fields: `is_active` (Ascending), `created_at` (Descending)

2. **Organizations with Plan Type Filter**:
   - Collection: `organizations`
   - Fields: `is_active` (Ascending), `plan_type` (Ascending), `created_at` (Descending)

3. **Documents Index**:
   - Collection group: `documents`
   - Fields: `organization_id` (Ascending), `is_active` (Ascending), `created_at` (Descending)

4. **Folders Index**:
   - Collection group: `folders`  
   - Fields: `organization_id` (Ascending), `parent_id` (Ascending), `name` (Ascending)

### Manual Index Creation

Alternatively, create these in [Firebase Console](https://console.firebase.google.com/) → **Firestore Database** → **Indexes** → **Composite**.

## 🏃‍♂️ Development Server

### Using the Optimized Development Script (Recommended)

The project includes a **production-ready development script** that prevents reload loops and maximizes performance:

```bash
# Make the script executable (first time only)
chmod +x run_dev.sh

# Start the development server with all optimizations
./run_dev.sh
```

**🚀 Script Features:**
- ✅ **Smart File Watching**: Only monitors the `app` directory (prevents .venv reload loops)
- ✅ **Performance Optimized**: Excludes cache, pyc, and temporary files
- ✅ **Environment Validation**: Checks for required .env file before starting
- ✅ **UV Integration**: Uses UV for faster dependency resolution
- ✅ **Clear Feedback**: Provides startup status and helpful links
- ✅ **Comprehensive Excludes**: Filters out `.git`, `node_modules`, build artifacts

**Console Output:**
```
🚀 Starting Document Intelligence Backend (Development Mode)
📁 Working Directory: /path/to/document-intelligence-backend
🐍 Using UV for dependency management

🔄 Starting server with optimized file watching...
📡 Server will be available at: http://127.0.0.1:8000
📚 API docs will be available at: http://127.0.0.1:8000/docs
```

### Manual Development Server

**With uv (Alternative)**:
```bash
# IMPORTANT: Use --reload-dir to prevent reload loops
uv run uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000

# Or with activated environment
source .venv/bin/activate
uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000
```

**⚠️ Common Issue: Reload Loops**

If you experience constant server restarts with messages like:
```
WARNING: WatchFiles detected changes in '.venv/lib/python3.12/...'
```

**Solution**: Always use `--reload-dir app` to limit file watching to the application directory only.

### Debug Mode

**With uv**:
```bash
# With detailed logging
DEBUG=True LOG_LEVEL=DEBUG uv run uvicorn app.main:app --reload --reload-dir app
```

**With pip**:
```bash
# With detailed logging
DEBUG=True LOG_LEVEL=DEBUG uvicorn app.main:app --reload --reload-dir app
```

### Server Endpoints

- **API**: http://127.0.0.1:8000
- **Health Check**: http://127.0.0.1:8000/health
- **API Docs**: http://127.0.0.1:8000/docs (development only)
- **ReDoc**: http://127.0.0.1:8000/redoc (development only)

## 🔗 API Endpoints

### Health & Status
- `GET /` - Root endpoint with API information
- `GET /health` - Basic health check
- `GET /status` - Detailed status with service health
- `GET /ready` - Kubernetes readiness probe
- `GET /live` - Kubernetes liveness probe

### Authentication (Session-Based)
- `GET /api/v1/auth/organizations` - List available organizations for registration
- `POST /api/v1/auth/login` - User login with session + refresh tokens
- `POST /api/v1/auth/refresh-session` - Refresh session token (with automatic rotation)
- `GET /api/v1/auth/validate` - Validate session token and check expiry
- `POST /api/v1/auth/logout` - Logout and invalidate current session
- `POST /api/v1/auth/logout-all` - Logout all sessions for user (security feature)
- `POST /api/v1/auth/register` - User registration with organization selection

### Organizations
- `GET /api/v1/organizations` - List organizations (paginated)
- `POST /api/v1/organizations` - Create organization
- `GET /api/v1/organizations/{org_id}` - Get organization by ID
- `PUT /api/v1/organizations/{org_id}` - Update organization
- `DELETE /api/v1/organizations/{org_id}` - Soft delete organization

### Users  
- `GET /api/v1/users` - List users in organization
- `GET /api/v1/users/{user_id}` - Get user by ID
- `PUT /api/v1/users/{user_id}` - Update user profile
- `POST /api/v1/users/invite` - Send user invitation

### Documents
**Standard Document Operations:**
- `POST /api/v1/documents/upload` - Upload document with target_path or folder_id
- `GET /api/v1/documents` - List documents with advanced filtering (folder_path, folder_id, file_type)
- `GET /api/v1/documents/{doc_id}` - Get document details with AI content (summary, FAQ, questions)
- `GET /api/v1/documents/{doc_id}/download` - Get signed download URL
- `PUT /api/v1/documents/{doc_id}/status` - Update document processing status
- `DELETE /api/v1/documents/{doc_id}` - Delete document (soft delete in Firestore, hard delete in GCS)

**🔥 Firestore-First APIs** (Better Performance):
- `GET /api/v1/documents/firestore/by-filename/{filename}` - Search documents by filename with relationship data
- `GET /api/v1/documents/firestore/by-folder-name/{folder_name}` - List documents by folder name with rich metadata

**🤖 AI-Powered Document Processing:**
- `POST /api/v1/documents/parse` - Parse documents using LlamaParse (PDF, XLSX, XLS, CSV)
- `GET /api/v1/documents/parse/{storage_path:path}` - Get existing parsed content
- `POST /api/v1/documents/save-parsed` - Save parsed content directly to GCS with metadata

**🧠 AI Content Generation (with Intelligent Caching):**

#### Document Summarization
- `POST /api/v1/documents/summarize?file_name={filename}` - Generate AI summary with optional custom prompt
- `GET /api/v1/documents/summarize?file_name={filename}` - Retrieve existing summary from cache
- `PUT /api/v1/documents/summarize?file_name={filename}` - Update/regenerate summary with new prompt

#### Document Questions
- `POST /api/v1/documents/questions?file_name={filename}` - Generate AI questions (1-20 count, custom prompts)
- `GET /api/v1/documents/questions?file_name={filename}` - Retrieve existing questions from cache
- `PUT /api/v1/documents/questions?file_name={filename}` - Update/regenerate questions

#### Document FAQ
- `POST /api/v1/documents/faq?file_name={filename}` - Generate AI FAQ (1-20 count, custom prompts)
- `GET /api/v1/documents/faq?file_name={filename}` - Retrieve existing FAQ from cache
- `PUT /api/v1/documents/faq?file_name={filename}` - Update/regenerate FAQ

**💡 AI Caching Strategy:**
- ✅ **First Generation**: Content generated via OpenAI and stored in Firestore
- ✅ **Subsequent Requests**: Cached content returned instantly (no OpenAI API calls)
- ✅ **Smart Regeneration**: Custom prompts trigger fresh generation with cache update
- ✅ **Cost Optimization**: Significant reduction in OpenAI API usage

**🔄 Recent API Changes:**
- ~~`GET /api/v1/documents/{document_id}/ai-content`~~ - **REMOVED** (use document fields directly)
- ~~`PATCH /api/v1/documents/{document_id}/ai-content`~~ - **REMOVED** (use save-parsed endpoint instead)

**Data Management:**
- `GET /api/v1/documents/sync/validate` - Validate sync between Firestore and GCS

### Folders
- `GET /api/v1/folders` - List folders in organization
- `POST /api/v1/folders` - Create new folder
- `GET /api/v1/folders/{folder_id}` - Get folder details
- `PUT /api/v1/folders/{folder_id}` - Update folder
- `DELETE /api/v1/folders/{folder_id}` - Delete folder

### Example API Usage

**Get Available Organizations**:
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/auth/organizations"
```

**User Login** (Session-Based):
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'
```

**Upload Document with Target Path** (Recommended):
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/documents/upload" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -F "file=@invoice.pdf" \
  -F "target_path=Google/original/invoices/invoice-2025-001.pdf" \
  -F "metadata={\"source\":\"web_upload\",\"category\":\"invoice\"}"
```

**Search Documents by Folder Name** (Firestore-First):
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/documents/firestore/by-folder-name/invoices" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"
```

**Parse Document with AI**:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/documents/parse" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"storage_path": "Google/original/invoices/invoice-2025-001.pdf"}'
```

**Save Parsed Content**:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/documents/save-parsed" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_path": "Tech Innovations Corp/parsed/control-docs",
    "content": "# Sample Document\n\nThis is the parsed content...",
    "original_filename": "Sample2.pdf"
  }'
```

### 🧠 **AI Content Generation Examples**

#### **Generate Document Summary**:
```bash
# Generate summary with default settings
curl -X POST "http://127.0.0.1:8000/api/v1/documents/summarize?file_name=Sample2.pdf" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json"

# Generate summary with custom prompt
curl -X POST "http://127.0.0.1:8000/api/v1/documents/summarize?file_name=Sample2.pdf" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create a brief executive summary highlighting key business insights"}'
```

#### **Generate Document Questions**:
```bash
# Generate 5 questions (default)
curl -X POST "http://127.0.0.1:8000/api/v1/documents/questions?file_name=Sample2.pdf" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"

# Generate 10 custom questions
curl -X POST "http://127.0.0.1:8000/api/v1/documents/questions?file_name=Sample2.pdf" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Focus on technical implementation details and system requirements",
    "question_count": 10
  }'
```

#### **Generate Document FAQ**:
```bash
# Generate 5 FAQ items (default)
curl -X POST "http://127.0.0.1:8000/api/v1/documents/faq?file_name=Sample2.pdf" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"

# Generate 8 custom FAQ items
curl -X POST "http://127.0.0.1:8000/api/v1/documents/faq?file_name=Sample2.pdf" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create FAQ focusing on common user questions and troubleshooting",
    "faq_count": 8
  }'
```

#### **Retrieve Cached AI Content**:
```bash
# Get existing summary (instant response from cache)
curl -X GET "http://127.0.0.1:8000/api/v1/documents/summarize?file_name=Sample2.pdf" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"

# Get existing questions
curl -X GET "http://127.0.0.1:8000/api/v1/documents/questions?file_name=Sample2.pdf" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"

# Get existing FAQ
curl -X GET "http://127.0.0.1:8000/api/v1/documents/faq?file_name=Sample2.pdf" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN"
```

#### **Update/Regenerate AI Content**:
```bash
# Update summary with new content
curl -X PUT "http://127.0.0.1:8000/api/v1/documents/summarize?file_name=Sample2.pdf" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"summary": "This updated summary provides a comprehensive overview..."}'

# Regenerate questions with new prompt
curl -X PUT "http://127.0.0.1:8000/api/v1/documents/questions?file_name=Sample2.pdf" \
  -H "Authorization: Bearer YOUR_SESSION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Generate questions suitable for training purposes",
    "question_count": 15
  }'
```

**📊 Example AI Response**:
```json
{
  "success": true,
  "document_id": "abc123",
  "filename": "Sample2.pdf",
  "ai_summary": "# Document Summary: Sample2.pdf\n\n## Executive Summary\nThis document outlines...",
  "summary_metadata": {
    "generated_at": "2025-09-21T10:30:00Z",
    "model": "gpt-5-mini",
    "content_length": 15420,
    "summary_length": 892
  },
  "timestamp": "2025-09-21T10:30:00Z"
}
```

## 🧪 Testing

### Automated Testing

```bash
# Run all tests with async support
uv run pytest tests/ -v --asyncio-mode=auto

# Run specific test file
uv run pytest tests/test_document_service.py -v

# Run tests with coverage report
uv run pytest tests/ --cov=app --cov-report=html --cov-report=term

# Test specific function
uv run pytest tests/test_document_service.py::test_upload_document -v
```

### Code Quality & Formatting

```bash
# Format code
uv run black app/ tests/

# Lint and fix issues
uv run ruff check app/ tests/ --fix

# Type checking
uv run mypy app/

# Run all pre-commit hooks
uv run pre-commit run --all-files
```

### Manual API Testing

```bash
# Health checks
curl -X GET "http://127.0.0.1:8000/health"
curl -X GET "http://127.0.0.1:8000/status" | python -m json.tool

# Test session-based authentication
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password"}'
```

### GCP Setup Testing

```bash
# Test Firebase/Firestore connection
python -c "import asyncio; from app.core.firebase_client import init_firebase; asyncio.run(init_firebase())"

# Verify GCS setup and permissions  
python scripts/verify_gcs_setup.py

# Check GCP authentication
python scripts/gcp_auth_helper.py
```

### Integration Testing

```bash
# Test complete document upload flow
python -c "
import asyncio
from app.services.document_service import DocumentService
async def test():
    service = DocumentService()
    url = await service.generate_upload_url('test.pdf', 'application/pdf')
    print(f'Generated upload URL: {url[:50]}...')
asyncio.run(test())
"
```

## ☁️ Cloud Run Deployment

### Prerequisites

- `gcloud`, `docker`, and `uv` installed locally
- Authenticated to the target project: `gcloud auth login && gcloud config set project <PROJECT_ID>`
- Application Default Credentials if running from a workstation: `gcloud auth application-default login`
- A named Firestore database (for example `biz2bricks-docdb-v1`) and a GCS bucket (for example `biz2bricksv1-document-store`)

### Unified Deployment Script (Recommended)

The repository ships with `deploy_full.sh`, a one-stop deployment workflow that:

- Enables required APIs (`run`, `cloudbuild`, `firestore`, `storage`, `iam`)
- Reuses or creates a Cloud Run service account and applies IAM bindings
- Confirms or creates the target GCS bucket with lifecycle/ACL configuration
- Loads environment variables from a YAML/KEY=VALUE file and writes a temporary `--env-vars-file`
- Builds and pushes both `latest` and timestamped docker tags to Container Registry
- Deploys/updates the Cloud Run service and runs a health probe
- Optionally seeds Firestore composite indexes via the helper scripts

Typical usage:

```bash
chmod +x deploy_full.sh                      # one time
./deploy_full.sh \
  --project-id biz2bricksv1 \
  --region us-central1 \
  --env-file production-env.yaml \
  --bucket biz2bricksv1-document-store
```

Useful flags:
- `--service-account <email>` to pin a specific deployment/runtime identity
- `--bucket <name>` to supply a pre-created bucket (script verifies instead of recreating)
- `--skip-indexes` to speed up subsequent redeploys once Firestore indexes exist
- `--memory`, `--cpu`, `--concurrency`, `--max-instances`, `--timeout` to override defaults

The script expects `FIREBASE_DATABASE_ID` inside your env file. For the default setup use:

```yaml
FIREBASE_DATABASE_ID: biz2bricks-docdb-v1
```

### Alternative Paths

- **Cloud Build**: `gcloud builds submit --config cloudbuild.yaml .`
- **Python Automation**: `python deploy_to_cloudrun.py --project-id <PROJECT_ID>`
- **Manual gcloud Flow**:
  1. `docker build -t gcr.io/<PROJECT_ID>/document-intelligence-api .`
  2. `docker push gcr.io/<PROJECT_ID>/document-intelligence-api`
  3. `gcloud run deploy document-intelligence-api ... --set-env-vars ENVIRONMENT=production,FIREBASE_DATABASE_ID=biz2bricks-docdb-v1`

### Post-Deployment Verification

```bash
# Fetch the live service URL
gcloud run services describe document-intelligence-api \
  --region us-central1 \
  --format="value(status.url)"

# Smoke check
SERVICE_URL=$(gcloud run services describe document-intelligence-api --region us-central1 --format="value(status.url)")
curl -fsS "$SERVICE_URL/health"
curl -fsS "$SERVICE_URL/status" | python -m json.tool
```

## 📁 Project Structure

```
document-intelligence-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI application entry point
│   ├── dependencies.py            # Global dependencies
│   │
│   ├── ai/                        # AI/ML integration
│   │   ├── __init__.py
│   │   └── file_parser.py        # LlamaParse file parsing utilities
│   │
│   ├── api/                       # API routes
│   │   ├── __init__.py
│   │   ├── deps.py               # API-specific dependencies
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── auth.py           # Authentication endpoints
│   │       ├── organizations.py  # Organization management
│   │       ├── users.py          # User management
│   │       ├── documents.py      # Document processing
│   │       ├── folders.py        # Folder management
│   │       ├── debug.py          # Debug endpoints (dev only)
│   │       └── documents_modules/  # 🧠 Modular AI-powered document endpoints
│   │           ├── __init__.py
│   │           ├── common.py              # Shared utilities for document modules
│   │           ├── document_ai_content.py  # AI content management
│   │           ├── document_download.py    # Download management
│   │           ├── document_faq.py         # AI FAQ generation & retrieval
│   │           ├── document_management.py  # Document CRUD operations
│   │           ├── document_processing.py  # Document parsing & processing
│   │           ├── document_questions.py   # AI questions generation & retrieval
│   │           ├── document_summarization.py # AI summarization & retrieval
│   │           ├── document_sync.py        # GCS/Firestore synchronization
│   │           └── document_upload.py      # Document upload handling
│   │
│   ├── core/                     # Core functionality
│   │   ├── __init__.py
│   │   ├── config.py             # Settings management
│   │   ├── firebase_client.py    # Firebase/Firestore client
│   │   ├── gcs_client.py         # Google Cloud Storage client
│   │   ├── security.py           # JWT and security utilities
│   │   ├── logging.py            # Structured logging setup
│   │   └── exceptions.py         # Custom exceptions
│   │
│   ├── models/                   # Data models
│   │   ├── __init__.py
│   │   ├── user.py              # User models
│   │   ├── organization.py      # Organization models
│   │   ├── document.py          # Document models
│   │   ├── folder.py            # Folder models
│   │   └── schemas.py           # Request/response schemas
│   │
│   ├── services/                # Business logic
│   │   ├── __init__.py
│   │   ├── auth_service.py      # Session-based authentication logic
│   │   ├── user_service.py      # User management logic
│   │   ├── org_service.py       # Organization management
│   │   ├── folder_service.py    # Folder management logic
│   │   ├── document_service.py  # Legacy document service (maintained for compatibility)
│   │   └── document/            # 🚀 Advanced Document Service Architecture
│   │       ├── __init__.py
│   │       ├── document_service.py           # Main facade service
│   │       ├── document_base_service.py      # Base service with common functionality
│   │       ├── document_validation_service.py # File validation, virus scanning
│   │       ├── document_storage_service.py   # GCS operations, path management
│   │       ├── document_crud_service.py      # CRUD operations, Firestore lifecycle
│   │       ├── document_query_service.py     # Complex queries, search operations
│   │       ├── document_ai_service.py        # AI content generation (summary, FAQ)
│   │       ├── document_sync_service.py      # GCS/Firestore sync validation
│   │       ├── document_download_service.py  # Signed URLs, download management
│   │       ├── document_parsing_service.py   # LlamaParse integration
│   │       └── document_summarization_service.py # AI summarization workflows
│   │
│   └── utils/                   # Utilities
│       ├── __init__.py
│       ├── helpers.py           # Helper functions
│       └── validators.py        # Input validators
│
├── scripts/                     # Utility scripts
│   ├── gcp_auth_helper.py       # GCP authentication helper
│   └── verify_gcs_setup.py      # GCS setup verification
│
├── docs/                        # Sample documents for testing
├── tests/                       # Test files (when added)
│
├── requirements.txt             # Python dependencies (pip)
├── pyproject.toml              # Python project config (uv)
├── uv.lock                     # Locked dependencies (uv)
├── .env                        # Environment variables (development)  
├── .env.production             # Production environment variables
├── .env.example                # Environment template
├── cloudbuild.yaml             # Cloud Build configuration
├── Dockerfile                  # Container image definition
├── firestore.indexes.json      # Optional: Firestore index definitions (if exported)
├── create_firestore_indexes.py # Index creation utility
├── setup_gcp_bucket.py         # GCS bucket setup utility
├── deploy_full.sh              # Unified Cloud Run deployment script
├── deploy_to_cloudrun.py       # Deployment automation
└── README.md                   # This documentation
```

## 🔧 Troubleshooting

### Common Issues

**1. Firebase Connection Failed**
```
Error: Failed to initialize Firebase
```
**Solutions**:
- Verify `FIREBASE_PROJECT_ID` and `FIREBASE_DATABASE_ID` are correct
- Check authentication: `gcloud auth list`
- Ensure Firestore API is enabled: `gcloud services list --enabled | grep firestore`

**2. Database Not Found Error**
```
Error: Database projects/PROJECT_ID/databases/DATABASE_ID not found
```
**Solutions**:
- Verify the Firestore database name in `FIREBASE_DATABASE_ID`
- Create the named database in Firebase Console
- Don't use "(default)" - create a named database

**3. Composite Index Required**
```
400 The query requires an index. You can create it here: https://console.firebase.google.com/...
```
**Solutions**:
- Click the provided URL to auto-create the index
- Run `python create_firestore_indexes.py` for all required indexes
- Wait 2-3 minutes for index creation to complete

**4. Permission Denied**
```
Error: Permission denied on resource project
```
**Solutions**:
- Grant required IAM roles: `roles/datastore.user`, `roles/storage.admin`
- Verify service account configuration
- Check `gcloud config get-value account`

**5. GCS Upload/Download Failures**
```
Error: 403 Forbidden or SignatureDoesNotMatch
```
**Solutions**:
- Verify `GCS_BUCKET_NAME` environment variable
- Check bucket CORS configuration
- Ensure service account has `roles/storage.admin`

**6. JWT Token Issues**
```
Error: Invalid signature or Token expired
```
**Solutions**:
- Verify `JWT_SECRET_KEY` is consistent across environments
- Check system clock synchronization
- Validate token expiry settings

**7. Cloud Run Deployment Failures**
```
Error: Service deployment failed
```
**Solutions**:
- Check Cloud Run logs: `gcloud run services logs read document-intelligence-api --region=us-central1`
- Verify all environment variables are set correctly
- Ensure service account permissions for Cloud Run
- Check memory and CPU limits

### Debug Mode

Enable verbose logging:
```bash
export DEBUG=True
export LOG_LEVEL=DEBUG
uvicorn app.main:app --reload
```

### Health Check Debugging

Get detailed system status:
```bash
curl -X GET "http://127.0.0.1:8000/status" | python -m json.tool
```

Expected healthy response:
```json
{
  "status": "healthy",
  "timestamp": "2025-08-19T12:00:00.000Z",
  "environment": "development",
  "debug": true,
  "firebase": {
    "status": "connected",
    "project_id": "your-project-id",
    "database_id": "your-database-name"
  },
  "gcs": {
    "status": "connected",
    "bucket": "your-bucket-name"
  }
}
```

### Production Deployment Checklist

- [ ] Environment variables configured correctly
- [ ] Firestore database created with proper name
- [ ] Composite indexes created and ready
- [ ] GCS bucket configured with CORS
- [ ] Service account permissions granted
- [ ] JWT secret key changed from default
- [ ] CORS origins configured for production domain
- [ ] Health endpoints responding correctly
- [ ] Authentication flow working end-to-end
- [ ] File upload/download working
- [ ] Cloud Run logs showing no errors

---

## 📦 Dependency Management Migration

### Migrating from pip to uv

If you have an existing pip-based setup and want to migrate to uv:

1. **Backup existing environment**:
   ```bash
   pip freeze > requirements-backup.txt
   ```

2. **Initialize uv project**:
   ```bash
   uv init --no-readme  # Creates pyproject.toml
   uv add $(cat requirements.txt | grep -v "^#" | grep -v "^$")
   ```

3. **Verify migration**:
   ```bash
   uv sync
   uv run uvicorn app.main:app --reload
   ```

4. **Clean up old environment** (optional):
   ```bash
   # Remove old pip environment after verifying uv works
   rm -rf old-venv-directory/
   ```

### Why uv is Recommended

- **Superior Dependency Resolution**: Handles complex conflicts that pip cannot resolve
- **Faster Installation**: Significantly faster than pip for dependency resolution
- **Lock File Support**: `uv.lock` ensures reproducible builds across environments
- **Modern Tooling**: Built in Rust, more reliable and performant
- **Direct Execution**: `uv run` eliminates need to activate virtual environments

---

**Need help?** Check the troubleshooting section above or review the detailed logs with `DEBUG=True` for specific error information.
