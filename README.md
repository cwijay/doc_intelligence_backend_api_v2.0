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
- **Deployment**: Google Cloud Run with manual deployment scripts (Python, Bash, or Cloud Build)

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

This section provides comprehensive instructions for deploying the Document Intelligence API to Google Cloud Run using manual deployment methods.

### 📋 Prerequisites

Before deploying, ensure you have:

1. **Google Cloud Project Setup**:
   ```bash
   # Install gcloud CLI (if not already installed)
   # Visit: https://cloud.google.com/sdk/docs/install

   # Login and set project
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID

   # Enable required APIs
   gcloud services enable run.googleapis.com
   gcloud services enable cloudbuild.googleapis.com
   gcloud services enable firestore.googleapis.com
   gcloud services enable storage.googleapis.com
   gcloud services enable artifactregistry.googleapis.com
   ```

2. **Local Tools Installed**:
   - `gcloud` CLI (authenticated)
   - `docker` (for building containers)
   - `python` 3.12+ (for Python deployment script)
   - `uv` (optional, for dependency management)

3. **Application Default Credentials**:
   ```bash
   gcloud auth application-default login
   ```

4. **GCP Resources Created**:
   - **Named Firestore Database**: Create via Firebase Console (e.g., `biz2bricks-dev-v1-docdb-v1`)
   - **GCS Bucket**: For document storage (e.g., `biz2bricks-dev-v1-document-store`)
   - **Service Account** (optional): For Cloud Run identity with appropriate IAM roles

### 🚀 Deployment Methods

The project provides **three manual deployment methods**. Choose the one that best fits your workflow:

---

#### **Method 1: Complete Infrastructure Setup** (⭐ Recommended for First Deployment)

The `deploy_full.sh` script is the **ONLY true "one-stop" solution** that creates ALL required GCP resources from scratch.

**🏗️ Infrastructure Creation (Unique to this method):**
- ✅ **Creates GCS bucket** with versioning and lifecycle policies
- ✅ **Creates service account** with automatic detection/reuse
- ✅ **Configures comprehensive IAM permissions** (6 roles):
  - `roles/run.invoker` - Allow service invocation
  - `roles/datastore.user` - Firestore database access
  - `roles/storage.objectAdmin` - GCS bucket full access
  - `roles/logging.logWriter` - Cloud Logging access
  - `roles/cloudtrace.agent` - Cloud Trace access
  - `roles/iam.serviceAccountUser` - Service account usage

**🚀 Deployment Features:**
- ✅ Automatically enables required GCP APIs
- ✅ Loads environment variables from YAML or KEY=VALUE files
- ✅ Builds and pushes Docker images (both `latest` and timestamped tags)
- ✅ Deploys to Cloud Run with configurable resource limits
- ✅ Deploys Firestore composite indexes
- ✅ Runs post-deployment health checks with retries
- ✅ **Idempotent** - safe to run multiple times (reuses existing resources)

**Best for:** First-time deployment, setting up new environments, complete infrastructure provisioning

---

#### **📖 Complete deploy_full.sh Documentation**

##### **What Happens During Deployment**

The `deploy_full.sh` script executes a comprehensive 12-step deployment workflow:

**Phase 1: Prerequisites & Validation**
1. **Verify Required Tools** - Checks for `gcloud`, `docker`, and `python3`
2. **Validate Project Files** - Ensures `Dockerfile`, `pyproject.toml` exist
3. **Check Authentication** - Verifies active gcloud authentication
4. **Set Active Project** - Configures gcloud to use specified project ID
5. **Configure Docker Auth** - Sets up authentication for pushing to GCR

**Phase 2: GCP API Enablement**
6. **Enable Required APIs** (automatically):
   - `run.googleapis.com` - Cloud Run
   - `cloudbuild.googleapis.com` - Container building
   - `containerregistry.googleapis.com` - Image storage
   - `iam.googleapis.com` - Identity & Access Management
   - `firestore.googleapis.com` - Firestore database
   - `storage-component.googleapis.com` - Cloud Storage

**Phase 3: Infrastructure Setup**
7. **Service Account Management**:
   - Detects existing service account from current Cloud Run service (if exists)
   - Falls back to first available service account in project
   - Creates new service account `document-int-run@PROJECT.iam.gserviceaccount.com` if none exist
   - Grants `roles/iam.serviceAccountUser` to current gcloud user

8. **IAM Role Binding** - Grants 5 essential roles to service account:
   - `roles/run.invoker` - Invoke Cloud Run services
   - `roles/datastore.user` - Read/write Firestore data
   - `roles/storage.objectAdmin` - Full GCS bucket access
   - `roles/logging.logWriter` - Write application logs
   - `roles/cloudtrace.agent` - Send trace data

9. **GCS Bucket Creation**:
   - Checks if bucket exists (idempotent)
   - Creates bucket with `--uniform-bucket-level-access`
   - Enables versioning on bucket
   - Configures lifecycle policy (keep last 5 versions, delete older)
   - Uses default name: `{project-id}-document-intelligence` if not specified

**Phase 4: Environment Configuration**
10. **Parse Environment File**:
    - Reads YAML or KEY=VALUE format files
    - Supports both `:` and `=` separators
    - Handles quoted strings and complex values
    - Sets default values for critical variables
    - Creates temporary `.env` file for Cloud Run deployment

**Phase 5: Firestore Indexes**
11. **Deploy Firestore Indexes** (if `--skip-indexes` not set):
    - Attempts `deploy_firestore_indexes.py --method firebase` first
    - Falls back to `--method gcloud` if Firebase CLI fails
    - Falls back to `create_firestore_indexes.py` if automated deployment fails
    - Non-blocking - continues deployment even if index creation fails

**Phase 6: Build & Deploy**
12. **Build Docker Image**:
    - Builds for `linux/amd64` platform (Cloud Run compatible)
    - Tags with both `:latest` and `:timestamp` for rollback capability
    - Pushes both tags to Google Container Registry

13. **Deploy to Cloud Run**:
    - Creates or updates Cloud Run service
    - Attaches service account
    - Configures resource limits (memory, CPU, concurrency, max instances)
    - Sets timeout for long-running requests
    - Loads all environment variables from temporary file
    - Configures `--allow-unauthenticated` for public access

**Phase 7: Verification & Cleanup**
14. **Health Check** - Tests `/health` endpoint with retries (3 attempts)
15. **Display Results** - Shows service URL and next steps
16. **Cleanup** - Removes temporary environment file

---

##### **Command-Line Options Reference**

```bash
./deploy_full.sh [OPTIONS]
```

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--project-id` | **Yes** | - | Google Cloud project ID for deployment |
| `--region` | No | `us-central1` | Cloud Run region (e.g., `us-west1`, `europe-west1`) |
| `--service-name` | No | `document-intelligence-api` | Name of the Cloud Run service |
| `--env-file` | No | `production-env.yaml` | Path to environment configuration file (YAML or KEY=VALUE) |
| `--service-account` | No | Auto-detect | Service account email for Cloud Run runtime identity |
| `--bucket` | No | From env file or auto-generated | GCS bucket name (format: `project-id-document-intelligence`) |
| `--memory` | No | `1Gi` | Memory allocation (e.g., `512Mi`, `2Gi`, `4Gi`) |
| `--cpu` | No | `1` | CPU allocation (e.g., `1`, `2`, `4`) |
| `--concurrency` | No | `80` | Max concurrent requests per instance (1-1000) |
| `--max-instances` | No | `10` | Maximum number of instances for autoscaling (1-1000) |
| `--timeout` | No | `300` | Request timeout in seconds (max 3600) |
| `--skip-indexes` | No | `false` | Skip Firestore index deployment (faster redeployments) |

---

##### **Prerequisites**

Before running `deploy_full.sh`, ensure you have:

**1. Local Tools Installed:**
```bash
# Check gcloud CLI
gcloud --version  # Should be 400.0.0 or newer

# Check Docker
docker --version  # Should be 20.10 or newer

# Check Python
python3 --version  # Should be 3.12 or newer
```

**2. GCP Authentication:**
```bash
# Login to GCP
gcloud auth login

# Set up application default credentials
gcloud auth application-default login

# Verify authentication
gcloud auth list
```

**3. Required Files in Repository:**
- `Dockerfile` - Container image definition
- `pyproject.toml` - Python project configuration
- `uv.lock` - Dependency lock file (optional, warning if missing)
- Environment file (e.g., `production-env.yaml`)

**4. Firestore Database Created:**
- Must be created manually via Firebase Console
- Must be a **named database** (not `(default)`)
- Note: Script does NOT create Firestore database

**5. GCP Project Permissions:**
Your gcloud account must have these roles:
- `roles/run.admin` - Deploy Cloud Run services
- `roles/iam.serviceAccountAdmin` - Create service accounts
- `roles/iam.securityAdmin` - Grant IAM roles
- `roles/storage.admin` - Create and manage GCS buckets
- `roles/serviceusage.serviceUsageAdmin` - Enable APIs

---

##### **Step 1: Prepare Environment File**

Create a `production-env.yaml` file with your configuration:

```yaml
# production-env.yaml
ENVIRONMENT: production
DEBUG: false
LOG_LEVEL: INFO
LOG_FORMAT: json

# Google Cloud Configuration
FIREBASE_PROJECT_ID: biz2bricks-dev-v1
FIREBASE_DATABASE_ID: biz2bricks-dev-v1-docdb-v1
GCP_PROJECT_ID: biz2bricks-dev-v1
GCS_BUCKET_NAME: biz2bricks-dev-v1-document-store

# Authentication & Security
JWT_SECRET_KEY: your-production-secret-key-256-bit
JWT_ALGORITHM: HS256
ACCESS_TOKEN_EXPIRE_MINUTES: 30
SESSION_DURATION_HOURS: 2
REFRESH_SESSION_DURATION_DAYS: 7

# AI Services (Required for AI features)
OPENAI_API_KEY: sk-your-openai-api-key
OPENAI_MODEL: gpt-4o-mini
LLAMAPARSE_API_KEY: your-llamaparse-api-key

# CORS Configuration
PRODUCTION_CORS_ORIGINS: '["https://biztobricks.com","https://www.biztobricks.com"]'
FRONTEND_DOMAIN: biztobricks.com

# Document Processing
MAX_FILE_SIZE: 52428800
ALLOWED_FILE_TYPES: '["pdf", "xlsx", "xls", "csv"]'
SIGNED_URL_EXPIRATION_MINUTES: 60
```

**Step 2: Run Deployment**

```bash
# Make script executable (first time only)
chmod +x deploy_full.sh

# Deploy with all features
./deploy_full.sh \
  --project-id biz2bricks-dev-v1 \
  --region us-central1 \
  --env-file production-env.yaml \
  --bucket biz2bricks-dev-v1-document-store

# Deploy with custom resource limits
./deploy_full.sh \
  --project-id biz2bricks-dev-v1 \
  --region us-central1 \
  --env-file production-env.yaml \
  --bucket biz2bricks-dev-v1-document-store \
  --memory 2Gi \
  --cpu 2 \
  --max-instances 20 \
  --concurrency 100

# Skip index creation for faster redeployments
./deploy_full.sh \
  --project-id biz2bricks-dev-v1 \
  --region us-central1 \
  --env-file production-env.yaml \
  --skip-indexes
```

---

##### **Usage Examples**

**Example 1: First-Time Deployment (Minimal)**
```bash
# Simplest deployment - creates everything with defaults
./deploy_full.sh --project-id my-project-id
```
*Creates: service account, GCS bucket (`my-project-id-document-intelligence`), deploys with 1Gi/1CPU*

**Example 2: Production Deployment (Full Configuration)**
```bash
# Production deployment with custom resources
./deploy_full.sh \
  --project-id biz2bricks-prod \
  --region us-central1 \
  --env-file production-env.yaml \
  --bucket biz2bricks-prod-documents \
  --memory 2Gi \
  --cpu 2 \
  --max-instances 50 \
  --concurrency 100 \
  --timeout 600
```
*Best for: High-traffic production environments with AI workloads*

**Example 3: Multi-Region Deployment**
```bash
# Deploy to Europe region
./deploy_full.sh \
  --project-id my-project \
  --region europe-west1 \
  --env-file production-env.yaml \
  --bucket my-project-eu-documents
```
*Note: Create separate buckets for each region for better performance*

**Example 4: Development Environment**
```bash
# Dev deployment with lower resources
./deploy_full.sh \
  --project-id my-project-dev \
  --region us-central1 \
  --env-file development-env.yaml \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 3
```
*Saves costs in development environments*

**Example 5: Rapid Redeploy (Code Changes Only)**
```bash
# Skip index deployment for faster updates
./deploy_full.sh \
  --project-id my-project \
  --env-file production-env.yaml \
  --skip-indexes
```
*Use this for subsequent deployments when only code has changed*

**Example 6: Custom Service Account**
```bash
# Use specific service account
./deploy_full.sh \
  --project-id my-project \
  --env-file production-env.yaml \
  --service-account custom-sa@my-project.iam.gserviceaccount.com
```
*Useful when you've pre-configured a service account with specific permissions*

---

##### **What Gets Created (Resource Checklist)**

When you run `deploy_full.sh` for the first time, these resources are created:

| Resource | Name Format | Description | Cost Impact |
|----------|-------------|-------------|-------------|
| **Service Account** | `document-int-run@{project}.iam.gserviceaccount.com` | Identity for Cloud Run service | Free |
| **IAM Role Bindings** | 6 roles (run.invoker, datastore.user, etc.) | Permissions for service account | Free |
| **GCS Bucket** | `{project-id}-document-intelligence` or custom | Document storage with versioning | Pay per GB stored |
| **Docker Images** | `gcr.io/{project}/{service}:latest` & `:timestamp` | Container images in GCR | Pay per GB stored |
| **Cloud Run Service** | `document-intelligence-api` or custom | Serverless compute service | Pay per request |
| **Environment Variables** | Set via `--env-file` | Configuration loaded into Cloud Run | Free |
| **Firestore Indexes** | Composite indexes for queries | Required for complex queries | Free |

**Not Created (Must Exist Before Deployment):**
- ❌ Firestore Database - Create manually via Firebase Console
- ❌ GCP Project - Create via Cloud Console
- ❌ Firebase Configuration - Set up via Firebase Console

---

##### **Deployment Output Explained**

When running `deploy_full.sh`, you'll see output like this:

```bash
ℹ️  Setting active GCP project to biz2bricks-dev-v1
ℹ️  Checking required APIs
✅ API enabled: run.googleapis.com
✅ API enabled: cloudbuild.googleapis.com
ℹ️  Attempting to detect existing Cloud Run service for service account reuse
⚠️  No service account provided or detected. Defaulting to new account document-int-run@biz2bricks-dev-v1.iam.gserviceaccount.com
✅ Service account created: document-int-run@biz2bricks-dev-v1.iam.gserviceaccount.com
ℹ️  Granting required project roles to document-int-run@biz2bricks-dev-v1.iam.gserviceaccount.com
✅ Role granted: roles/run.invoker
✅ Role granted: roles/datastore.user
ℹ️  GCS bucket exists: gs://biz2bricks-dev-v1-document-store
ℹ️  Deploying Firestore indexes via deploy_firestore_indexes.py
ℹ️  Building Docker image for Cloud Run (linux/amd64)
✅ Docker image built
ℹ️  Pushing image: gcr.io/biz2bricks-dev-v1/document-intelligence-api:latest
✅ Docker images pushed to Container Registry
ℹ️  Deploying Cloud Run service: document-intelligence-api
✅ Cloud Run service deployed successfully
✅ Service URL: https://document-intelligence-api-abc123-uc.a.run.app
ℹ️  Testing health endpoint...
✅ Health check passed: {"status":"healthy"}
✅ Deployment complete!

Next steps:
 - Review logs: gcloud run services logs tail document-intelligence-api --region=us-central1
 - Validate Firestore indexes if any warnings were emitted
 - Update frontend or clients to use: https://document-intelligence-api-abc123-uc.a.run.app
```

**Key Indicators:**
- ✅ Green checkmark = Success
- ℹ️  Blue info = Informational
- ⚠️  Yellow warning = Non-critical issue (deployment continues)
- ❌ Red X = Critical error (deployment stops)

---

##### **Troubleshooting deploy_full.sh**

**Problem: "No active gcloud account detected"**
```bash
# Solution: Login to gcloud
gcloud auth login
gcloud auth application-default login
```

**Problem: "Permission denied" when creating service account**
```bash
# Solution: Grant yourself required roles
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:YOUR_EMAIL" \
  --role="roles/iam.serviceAccountAdmin"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:YOUR_EMAIL" \
  --role="roles/iam.securityAdmin"
```

**Problem: "Failed to create GCS bucket - name already taken"**
```bash
# Solution: Bucket names are globally unique, use a custom name
./deploy_full.sh \
  --project-id my-project \
  --bucket my-unique-bucket-name-12345
```

**Problem: "Dockerfile not found"**
```bash
# Solution: Run script from repository root
cd /path/to/doc_intelligence_backend_api_v2.0
./deploy_full.sh --project-id my-project
```

**Problem: "API not enabled" errors**
```bash
# Solution: Script auto-enables APIs, but if you see this error:
gcloud services enable run.googleapis.com \
  cloudbuild.googleapis.com \
  containerregistry.googleapis.com \
  iam.googleapis.com \
  firestore.googleapis.com \
  storage-component.googleapis.com
```

**Problem: "Health check failed" after deployment**
```bash
# Solution: Check logs for startup errors
gcloud run services logs read document-intelligence-api \
  --region us-central1 \
  --limit 100

# Common causes:
# 1. Missing environment variables (check production-env.yaml)
# 2. Firestore database not created
# 3. Invalid API keys (OPENAI_API_KEY, JWT_SECRET_KEY)
```

**Problem: Deployment is very slow**
```bash
# Solution: Skip index deployment for faster subsequent deploys
./deploy_full.sh \
  --project-id my-project \
  --env-file production-env.yaml \
  --skip-indexes
```

**Problem: "Docker push failed - unauthorized"**
```bash
# Solution: Reconfigure Docker authentication
gcloud auth configure-docker

# Or login to Docker manually
docker login -u oauth2accesstoken -p "$(gcloud auth print-access-token)" gcr.io
```

**Problem: Out of memory errors in Cloud Run**
```bash
# Solution: Increase memory allocation
./deploy_full.sh \
  --project-id my-project \
  --memory 2Gi \
  --timeout 600  # Also increase timeout for AI operations
```

---

##### **Idempotency & Safe Redeployment**

The `deploy_full.sh` script is **idempotent** - you can run it multiple times safely:

- ✅ **Service Account**: Detects and reuses existing accounts
- ✅ **IAM Roles**: Re-granting roles is safe (no duplicates)
- ✅ **GCS Bucket**: Checks existence before creating
- ✅ **APIs**: Re-enabling already enabled APIs is safe
- ✅ **Cloud Run Service**: Updates existing service instead of failing
- ✅ **Docker Images**: New timestamp tag created each time, `:latest` updated

**Safe to Run Multiple Times:**
```bash
# Run this 5 times - same result every time
./deploy_full.sh --project-id my-project --env-file production-env.yaml
```

**What Changes Each Time:**
- New Docker image with timestamp tag (e.g., `:1699564823`)
- Cloud Run service updated to latest code
- Environment variables refreshed from file
- Health check performed on new deployment

**What Stays the Same:**
- Service account (reused)
- GCS bucket (not recreated)
- IAM permissions (not duplicated)
- Firestore indexes (if `--skip-indexes` used)

---

#### **Method 2: Cloud Build Manual Trigger**

The `cloudbuild.yaml` provides a simple configuration for building and deploying via Cloud Build.

**Features:**
- ✅ Uses Cloud Build for building Docker images
- ✅ Pushes to Google Container Registry (GCR)
- ✅ Deploys to Cloud Run with configurable substitutions
- ⚠️ **Note**: Does NOT include API keys in the build config (must be set separately)

**Step 1: Review cloudbuild.yaml**

The configuration includes default substitutions that you can override:

```yaml
substitutions:
  _REGION: 'us-central1'
  _SERVICE_NAME: 'document-intelligence-api'
  _ENVIRONMENT: 'production'
  _GCP_PROJECT_ID: 'biz2bricks-dev-v1'
  _FIREBASE_DATABASE_ID: 'biz2bricks-dev-v1-docdb-v1'
  _GCS_BUCKET_NAME: 'biz2bricks-dev-v1-document-store'
  _MEMORY: '1Gi'
  _CPU: '1'
  _CONCURRENCY: '80'
  _MAX_INSTANCES: '10'
```

**Step 2: Deploy with Cloud Build**

```bash
# Deploy with default substitutions
gcloud builds submit --config cloudbuild.yaml .

# Deploy with custom substitutions
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_MEMORY=2Gi,_CPU=2,_MAX_INSTANCES=20 \
  .
```

**Step 3: Set API Keys Separately**

Since `cloudbuild.yaml` doesn't include sensitive API keys, set them manually:

```bash
gcloud run services update document-intelligence-api \
  --region us-central1 \
  --update-env-vars="OPENAI_API_KEY=sk-your-key,LLAMAPARSE_API_KEY=your-key,JWT_SECRET_KEY=your-secret"
```

---

### 📊 Deployment Methods Comparison

Use this table to understand what each deployment method creates and when to use it:

| Feature | deploy_full.sh | cloudbuild.yaml |
|---------|----------------|-----------------|
| **Infrastructure Creation** |
| Creates GCS Bucket | ✅ Yes | ❌ No |
| Creates Service Account | ✅ Yes | ❌ No |
| Configures IAM Permissions | ✅ Yes (6 roles) | ❌ No |
| Creates Firestore Database | ⚠️ Manual* | ⚠️ Manual* |
| **Deployment Features** |
| Enables GCP APIs | ✅ Yes | ⚠️ Partial |
| Builds Docker Image | ✅ Yes | ✅ Yes |
| Pushes to Registry | ✅ Yes | ✅ Yes |
| Deploys to Cloud Run | ✅ Yes | ✅ Yes |
| Deploys Firestore Indexes | ✅ Yes | ❌ No |
| **Configuration** |
| Environment Management | Good | Basic |
| .env File Support | ✅ YAML | ⚠️ Substitutions only |
| API Key Handling | ✅ Automated | ⚠️ Manual setup required |
| Health Checks | ✅ With retries | ❌ No |
| **Best Use Case** | Full deployment | Quick manual builds |
| **Lines of Code** | 542 | 90 |

*Firestore database must be created manually via Firebase Console before running any deployment script.

---

### 🎯 When to Use Each Deployment Method

#### **Use `deploy_full.sh` When:**
- ✅ **First-time deployment** to a new GCP project
- ✅ Setting up a **new environment** (staging, production, etc.)
- ✅ You need **complete infrastructure provisioning** from scratch
- ✅ You want **IAM roles automatically configured**
- ✅ Starting with a **blank GCP project** (no resources created yet)
- ✅ Doing **regular updates** to an existing deployment with full validation

**Example Command:**
```bash
./deploy_full.sh --project-id biz2bricks-dev-v1 --env-file production-env.yaml
```

#### **Use `cloudbuild.yaml` When:**
- ✅ Infrastructure **already exists**
- ✅ You need **quick manual builds** without full automation
- ✅ You want to use **Cloud Build UI** for triggering deployments
- ✅ Doing **simple code updates** without environment changes
- ⚠️ You're willing to **manually set API keys** after deployment

**Example Command:**
```bash
gcloud builds submit --config cloudbuild.yaml .
```

---

### 💡 Recommended Workflow

**For New Projects:**
1. **First Time**: Use `deploy_full.sh` to create all infrastructure
2. **Subsequent Deploys**: Use `deploy_full.sh` for full deployment or `cloudbuild.yaml` for quick updates
3. **Quick Updates**: Use `fast_deploy.sh` (wraps deploy_full.sh with smoke tests)

**For Existing Projects:**
- Use `deploy_full.sh` for most deployments (recommended)
- Use `fast_deploy.sh` for quick code changes with validation
- Use `test_only.sh` to validate existing deployments
- Use `cloudbuild.yaml` for simple manual builds via Cloud Build UI

---

### 🔍 Post-Deployment Verification

After deployment, verify the service is running correctly:

**1. Get Service URL**
```bash
SERVICE_URL=$(gcloud run services describe document-intelligence-api \
  --region us-central1 \
  --format="value(status.url)")

echo "Service URL: $SERVICE_URL"
```

**2. Health Check**
```bash
# Basic health check
curl -fsS "$SERVICE_URL/health"

# Expected output: {"status":"healthy"}
```

**3. Detailed Status Check**
```bash
# Detailed service status with Firebase/GCS connectivity
curl -fsS "$SERVICE_URL/status" | python -m json.tool

# Expected output includes:
# {
#   "status": "healthy",
#   "environment": "production",
#   "firebase": {
#     "status": "connected",
#     "project_id": "biz2bricks-dev-v1",
#     "database_id": "biz2bricks-dev-v1-docdb-v1"
#   },
#   "gcs": {
#     "status": "connected",
#     "bucket": "biz2bricks-dev-v1-document-store"
#   }
# }
```

**4. Test Authentication**
```bash
# Test login endpoint
curl -X POST "$SERVICE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpassword"}'
```

**5. View Logs**
```bash
# Stream live logs
gcloud run services logs read document-intelligence-api \
  --region us-central1 \
  --limit 50

# Follow logs in real-time
gcloud run services logs tail document-intelligence-api \
  --region us-central1
```

---

### 🔧 Updating an Existing Deployment

To update a running service with new code or configuration:

**Quick Update (Code Changes Only):**
```bash
# Redeploy with skip-indexes flag (faster)
./deploy_full.sh \
  --project-id biz2bricks-dev-v1 \
  --region us-central1 \
  --env-file production-env.yaml \
  --skip-indexes
```

**Update Environment Variables Only:**
```bash
gcloud run services update document-intelligence-api \
  --region us-central1 \
  --update-env-vars="LOG_LEVEL=DEBUG,MAX_FILE_SIZE=104857600"
```

**Update Resource Limits:**
```bash
gcloud run services update document-intelligence-api \
  --region us-central1 \
  --memory 2Gi \
  --cpu 2 \
  --max-instances 20
```

---

### 🛡️ Production Deployment Checklist

Before deploying to production, ensure:

- [ ] All required environment variables are set in `production-env.yaml` or `.env.production`
- [ ] Named Firestore database is created (not using `(default)`)
- [ ] GCS bucket is created with proper CORS configuration
- [ ] Service account has appropriate IAM roles:
  - `roles/datastore.user` (Firestore access)
  - `roles/storage.objectAdmin` (GCS access)
  - `roles/secretmanager.secretAccessor` (if using Secret Manager)
- [ ] JWT_SECRET_KEY is changed from default and is strong (256-bit)
- [ ] CORS origins are configured for your production domain
- [ ] OpenAI API key is valid and has sufficient credits
- [ ] LlamaParse API key is valid (if using document parsing)
- [ ] Firestore composite indexes are created (run `python create_firestore_indexes.py`)
- [ ] Cloud Run resource limits are appropriate for your load:
  - Memory: At least `1Gi` (recommended: `2Gi` for AI workloads)
  - CPU: At least `1` (recommended: `2` for concurrent requests)
  - Max instances: Set based on expected traffic and budget
  - Timeout: At least `300s` for AI processing operations
- [ ] Health checks pass: `/health`, `/status`
- [ ] Authentication flow tested end-to-end
- [ ] Document upload/download tested with real files
- [ ] AI features tested (summary, FAQ, questions generation)
- [ ] Logs show no errors or warnings
- [ ] Monitoring and alerting configured (Cloud Monitoring)

---

### 🚨 Troubleshooting Deployment Issues

**Issue: Cloud Build Permission Denied**
```bash
# Grant Cloud Build service account permissions
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)")
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud iam service-accounts add-iam-policy-binding \
  ${PROJECT_NUMBER}-compute@developer.gserviceaccount.com \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

**Issue: Service Not Responding**
```bash
# Check service status
gcloud run services describe document-intelligence-api \
  --region us-central1

# Check recent logs for errors
gcloud run services logs read document-intelligence-api \
  --region us-central1 \
  --limit 100 | grep ERROR
```

**Issue: Firebase Connection Failed**
```bash
# Verify Firestore database exists
gcloud firestore databases list

# Verify service account permissions
gcloud projects get-iam-policy YOUR_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:YOUR_SA_EMAIL"
```

**Issue: GCS Upload/Download Failures**
```bash
# Verify bucket exists and permissions
gsutil ls -L gs://your-bucket-name

# Check CORS configuration
gsutil cors get gs://your-bucket-name

# Test upload from Cloud Run service account
gcloud run services proxy document-intelligence-api --region us-central1
```

**Issue: Environment Variables Not Loading**
```bash
# List current environment variables
gcloud run services describe document-intelligence-api \
  --region us-central1 \
  --format="json" | jq '.spec.template.spec.containers[0].env'

# Update missing variables
gcloud run services update document-intelligence-api \
  --region us-central1 \
  --update-env-vars="MISSING_VAR=value"
```

---

### 📊 Monitoring and Maintenance

**View Service Metrics:**
```bash
# Open Cloud Console for metrics
gcloud run services describe document-intelligence-api \
  --region us-central1 \
  --format="value(status.url)"

# Visit: https://console.cloud.google.com/run
```

**Set Up Alerting:**
```bash
# Example: Alert on high error rate
gcloud alpha monitoring policies create \
  --notification-channels=YOUR_CHANNEL_ID \
  --display-name="Cloud Run Error Rate Alert" \
  --condition-display-name="Error rate > 5%" \
  --condition-threshold-value=5 \
  --condition-threshold-duration=300s
```

**Regular Maintenance Tasks:**
- Review logs weekly for errors or warnings
- Monitor Cloud Run costs and adjust scaling limits
- Update dependencies monthly: `uv sync --upgrade`
- Rotate JWT secrets quarterly
- Review and optimize Firestore queries
- Clean up old Cloud Build artifacts
- Test disaster recovery procedures

## 📁 Project Structure

```
doc_intelligence_backend_api_v2.0/
├── app/                                    # Main application package
│   ├── __init__.py
│   ├── main.py                            # FastAPI application entry point
│   ├── config.py                          # Legacy config (use app.core.config instead)
│   ├── dependencies.py                    # Global dependencies and DI setup
│   │
│   ├── ai/                                # AI/ML integration layer
│   │   ├── __init__.py
│   │   └── file_parser.py                # LlamaParse document parsing utilities
│   │
│   ├── api/                               # API routes and endpoints
│   │   ├── __init__.py
│   │   ├── deps.py                       # API-specific dependencies
│   │   └── v1/                           # API version 1
│   │       ├── __init__.py
│   │       ├── auth.py                   # Session-based authentication endpoints
│   │       ├── organizations.py          # Organization management endpoints
│   │       ├── users.py                  # User management endpoints
│   │       ├── documents.py              # Legacy document endpoints (maintained)
│   │       ├── documents_main.py         # Main document router aggregator
│   │       ├── folders.py                # Folder management endpoints
│   │       ├── password.py               # Password reset/change endpoints
│   │       ├── debug.py                  # Debug endpoints (development only)
│   │       └── documents_modules/        # 🧠 Modular AI-powered document endpoints
│   │           ├── __init__.py
│   │           ├── common.py              # Shared utilities for document modules
│   │           ├── document_ai_content.py  # AI content management endpoints
│   │           ├── document_download.py    # Download management endpoints
│   │           ├── document_faq.py         # AI FAQ generation & retrieval
│   │           ├── document_management.py  # Document CRUD operations
│   │           ├── document_processing.py  # Document parsing & processing
│   │           ├── document_questions.py   # AI questions generation & retrieval
│   │           ├── document_summarization.py # AI summarization & retrieval
│   │           ├── document_sync.py        # GCS/Firestore synchronization
│   │           └── document_upload.py      # Document upload handling
│   │
│   ├── core/                              # Core functionality layer
│   │   ├── __init__.py
│   │   ├── config.py                     # Pydantic settings & environment config
│   │   ├── firebase_client.py            # Firebase/Firestore singleton client
│   │   ├── gcs_client.py                 # Google Cloud Storage singleton client
│   │   ├── security.py                   # JWT, password hashing, session management
│   │   ├── simple_auth.py                # Simplified auth utilities
│   │   ├── logging.py                    # Structured logging with middleware
│   │   └── exceptions.py                 # Custom exception hierarchy
│   │
│   ├── models/                            # Data models and schemas
│   │   ├── __init__.py
│   │   ├── user.py                       # User Pydantic models
│   │   ├── organization.py               # Organization Pydantic models
│   │   ├── document.py                   # Document Pydantic models with AI fields
│   │   ├── folder.py                     # Folder Pydantic models
│   │   └── schemas.py                    # Request/response schemas
│   │
│   ├── services/                          # Business logic layer
│   │   ├── __init__.py
│   │   ├── auth_service.py               # Session-based authentication logic
│   │   ├── user_service.py               # User management service
│   │   ├── org_service.py                # Organization management service
│   │   ├── folder_service.py             # Folder management service
│   │   ├── vector_indexing_service.py    # Pinecone vector indexing service
│   │   ├── document_service.py           # Legacy document service (compatibility)
│   │   ├── document_service_original.py  # Original backup (reference only)
│   │   └── document/                     # 🚀 Advanced Document Service Architecture
│   │       ├── __init__.py
│   │       ├── document_service.py           # Main facade service (composition)
│   │       ├── document_base_service.py      # Base service with shared functionality
│   │       ├── document_validation_service.py # File validation & type checking
│   │       ├── document_storage_service.py   # GCS operations & path management
│   │       ├── document_crud_service.py      # CRUD ops & Firestore lifecycle
│   │       ├── document_query_service.py     # Complex queries & search
│   │       ├── document_ai_service.py        # AI content generation (summary, FAQ)
│   │       ├── document_sync_service.py      # GCS/Firestore sync validation
│   │       ├── document_download_service.py  # Signed URLs & download mgmt
│   │       ├── document_parsing_service.py   # LlamaParse integration
│   │       └── document_summarization_service.py # AI summarization workflows
│   │
│   └── utils/                             # Utility functions
│       ├── __init__.py
│       ├── helpers.py                    # General helper functions
│       └── validators.py                 # Input validation utilities
│
├── scripts/                               # Utility and setup scripts
│   ├── gcp_auth_helper.py                # GCP authentication verification helper
│   └── verify_gcs_setup.py               # GCS bucket setup verification
│
├── docs/                                  # Sample documents for testing
├── tests/                                 # Test suite (pytest with async support)
│
├── .github/                               # GitHub configuration (not used for CI/CD)
│   └── workflows/                        # Archived workflows (reference only)
│
├── requirements.txt                       # Python dependencies (pip/legacy)
├── pyproject.toml                        # Python project config (uv-managed)
├── uv.lock                               # Locked dependencies (uv)
│
├── .env                                  # Local development environment variables
├── .env.dev                              # Development environment (alternative)
├── .env.test                             # Test environment variables
├── .env.production                       # Production environment variables
├── .env.example                          # Environment variable template
├── production-env.yaml                   # Production config (YAML format)
├── development-env.yaml                  # Development config (YAML format)
│
├── Dockerfile                            # Multi-stage container image definition
├── cloudbuild.yaml                       # Cloud Build manual deployment config
├── .dockerignore                         # Docker build exclusions
│
├── firestore.indexes.json                # Firestore composite index definitions
├── create_firestore_indexes.py           # Firestore index creation utility
├── deploy_firestore_indexes.py           # Firestore index deployment utility
│
├── setup_gcp_bucket.py                   # Interactive GCS bucket setup
├── create_test_user.py                   # Test user creation utility
│
├── deploy_full.sh                        # ⭐ Comprehensive deployment script (recommended)
├── fast_deploy.sh                        # Quick deployment with smoke tests
├── test_only.sh                          # Rapid deployment validation
├── run_dev.sh                            # Optimized development server script
│
├── CLAUDE.md                             # Claude Code instructions (codebase guide)
├── AGENTS.md                             # AI agents documentation
├── README.md                             # This comprehensive documentation
├── LICENSE                               # Project license
└── .gitignore                            # Git exclusions
```

### 📝 Key File Descriptions

**Configuration Files:**
- `app/core/config.py` - **Primary** configuration using Pydantic settings
- `.env` files - Environment-specific variables (never commit `.env`, only `.env.example`)
- `*-env.yaml` - YAML format environment configs for deployment scripts

**Deployment Files:**
- `deploy_full.sh` - **Recommended** comprehensive deployment with full automation
- `fast_deploy.sh` - Quick deployment with smoke test validation
- `test_only.sh` - Rapid smoke test validation for existing deployments
- `cloudbuild.yaml` - Cloud Build configuration for manual triggers
- `cloudbuild.develop.yaml` - Automated deployment for develop branch
- `cloudbuild.production.yaml` - Production deployment with gradual rollout
- `Dockerfile` - Multi-stage build optimized for Cloud Run

**Maintenance Scripts** (scripts/maintenance/):
- `cleanup_duplicate_documents.py` - Clean duplicate Firestore documents
- `cleanup_duplicate_storage_paths.py` - Clean duplicate GCS storage paths
- `diagnose_document_sync.py` - Troubleshoot document synchronization issues

**Service Architecture:**
- `app/services/document/` - Modular document services following Facade pattern
- `app/services/document/document_service.py` - Main orchestrator (composes specialized services)
- Each specialized service handles one domain (validation, storage, AI, etc.)

**API Architecture:**
- `app/api/v1/documents_modules/` - Modular AI endpoints with intelligent caching
- `app/api/v1/auth.py` - Session-based JWT authentication with refresh tokens
- Each module is self-contained with GET/POST/PUT operations

**AI Integration:**
- `app/services/document/document_ai_service.py` - AI content generation
- `app/ai/file_parser.py` - LlamaParse document parsing
- AI content cached in Firestore for cost optimization

**Development Tools:**
- `run_dev.sh` - Prevents reload loops, smart file watching
- `scripts/gcp_auth_helper.py` - Verifies GCP authentication
- `scripts/verify_gcs_setup.py` - Validates GCS configuration
- `create_test_user.py` - Creates test users for development

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
