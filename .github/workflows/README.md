# GitHub Actions Workflows Documentation

This directory contains automated CI/CD workflows for the Document Intelligence Backend. The workflows handle continuous integration, automated testing, and deployment to Google Cloud Run with staging and production environments.

## 📋 Table of Contents

- [Workflow Overview](#workflow-overview)
- [Quick Start](#quick-start)
- [Workflow Details](#workflow-details)
- [Environment Configuration](#environment-configuration)
- [Deployment Process](#deployment-process)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

## 🎯 Workflow Overview

### CI Workflow (`ci.yml`)

**Purpose**: Validates code quality, runs tests, and performs security scans.

**Triggers**:
- Pull requests to any branch
- Push to `main` or `develop` branches
- Manual trigger via workflow_dispatch

**Jobs**:
1. **Code Quality Checks**: Black formatting, Ruff linting, MyPy type checking
2. **Tests**: Run pytest with coverage reports
3. **Security Scanning**: pip-audit for vulnerabilities, TruffleHog for secrets
4. **Docker Build Validation**: Ensure Docker image builds successfully
5. **CI Summary**: Aggregate results and post PR comments

### CD Workflow (`deploy.yml`)

**Purpose**: Automated deployment to Google Cloud Run with staging and production environments.

**Triggers**:
- Push to `develop` → Deploys to **staging** (automatic)
- Push to `main` → Deploys to **production** (requires manual approval)
- Manual trigger with environment selection

**Jobs**:
1. **Pre-Deployment CI**: Run all CI checks
2. **Determine Environment**: Identify target environment based on branch
3. **Build Image**: Build and push Docker image to Google Container Registry
4. **Deploy to Staging**: Automatic deployment (no approval needed)
5. **Deploy to Production**: Manual approval required, comprehensive health checks
6. **Rollback**: Automatic rollback on deployment failure

## 🚀 Quick Start

### Prerequisites

1. **Complete GCP Setup** (see `GCP_SERVICE_ACCOUNT_SETUP.md`)
   - Service account created with proper permissions
   - Service account key added to GitHub Secrets as `GCP_SA_KEY`

2. **Configure GitHub Secrets** (see [Environment Configuration](#environment-configuration))

3. **Set up GitHub Environments**:
   - `staging`: No protection rules (auto-deploy)
   - `production`: Require reviewer approval, restrict to `main` branch

### First Deployment

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/test-cicd
   # Make a small change
   git commit -m "Test CI/CD pipeline"
   git push origin feature/test-cicd
   ```

2. **Open a Pull Request**:
   - CI workflow will run automatically
   - Review CI results in PR checks

3. **Merge to `develop` (Staging Deployment)**:
   ```bash
   git checkout develop
   git merge feature/test-cicd
   git push origin develop
   ```
   - Staging deployment will trigger automatically
   - Check deployment status in Actions tab

4. **Merge to `main` (Production Deployment)**:
   ```bash
   git checkout main
   git merge develop
   git push origin main
   ```
   - Production deployment will wait for manual approval
   - Designated reviewer approves deployment
   - Production deployment proceeds

## 📖 Workflow Details

### CI Workflow Structure

```
CI Workflow
├── lint-and-format
│   ├── Setup Python 3.12 + UV
│   ├── Install dependencies
│   ├── Run Black formatting check
│   ├── Run Ruff linting
│   └── Run MyPy type checking
├── test
│   ├── Setup Python 3.12 + UV
│   ├── Run pytest with async support
│   └── Generate coverage reports
├── security-scan
│   ├── Run pip-audit for vulnerabilities
│   └── Run TruffleHog for secret detection
├── build-validation
│   ├── Build Docker image
│   ├── Start container
│   └── Test health endpoint
└── ci-summary
    ├── Aggregate all results
    └── Post comment on PR (if applicable)
```

### CD Workflow Structure

```
CD Workflow
├── ci-checks (reuse ci.yml)
├── determine-environment
│   ├── Identify target environment
│   └── Generate image tag
├── build-image
│   ├── Authenticate with GCP
│   ├── Build with Cloud Build
│   └── Tag and push to GCR
├── deploy-staging (if develop branch)
│   ├── Create .env.staging
│   ├── Deploy to Cloud Run
│   ├── Run health checks
│   └── Post deployment summary
├── deploy-production (if main branch)
│   ├── Wait for manual approval
│   ├── Create .env.production
│   ├── Deploy to Cloud Run
│   ├── Run comprehensive health checks
│   ├── Create GitHub release
│   └── Post deployment summary
└── rollback (on failure)
    └── Rollback to previous revision
```

## ⚙️ Environment Configuration

### Required GitHub Secrets

Navigate to **Repository Settings > Secrets and variables > Actions**

#### GCP Authentication
- `GCP_SA_KEY`: Base64-encoded service account JSON key
- `GCP_PROJECT_ID`: `biz2bricksv1`
- `GCP_REGION`: `us-central1`

#### Firebase/Firestore
- `FIREBASE_PROJECT_ID`: `biz2bricksv1`
- `FIREBASE_DATABASE_ID`: `biz2bricks-docdb-v1`
- `GCS_BUCKET_NAME`: `biz2bricksv1-document-store`

#### Security
- `JWT_SECRET_KEY`: Production JWT secret (256-bit)

#### AI Services
- `OPENAI_API_KEY`: OpenAI API key
- `OPENAI_MODEL`: `gpt-5-mini` (optional)
- `LLAMAPARSE_API_KEY`: LlamaParse API key
- `PINECONE_API_KEY`: Pinecone API key
- `PINECONE_ENVIRONMENT`: Pinecone environment
- `PINECONE_INDEX_NAME`: `document-intelligence` (optional)

#### CORS Configuration
- `PRODUCTION_CORS_ORIGINS`: JSON array of production domains
- `FRONTEND_DOMAIN`: `biztobricks.com`

#### Optional Staging-Specific Secrets
- `STAGING_FIREBASE_DATABASE_ID`: Separate staging database
- `STAGING_GCS_BUCKET_NAME`: Separate staging bucket
- `STAGING_CORS_ORIGINS`: Staging frontend URLs

### GitHub Environments Setup

#### 1. Create Staging Environment

1. Go to **Settings > Environments**
2. Click **New environment**
3. Name: `staging`
4. **No protection rules** (allows automatic deployment)

#### 2. Create Production Environment

1. Click **New environment**
2. Name: `production`
3. Configure protection rules:
   - ✅ **Required reviewers**: Add 1+ reviewers
   - ✅ **Deployment branches**: Only `main`
   - ⚡ **Wait timer**: Optional (e.g., 5 minutes)
4. Click **Save protection rules**

## 🚢 Deployment Process

### Staging Deployment (Automatic)

**Trigger**: Push to `develop` branch

```bash
# Make changes and test locally
git checkout develop
git pull origin develop

# Merge feature branch
git merge feature/my-feature

# Push to trigger deployment
git push origin develop
```

**What Happens**:
1. CI checks run (linting, tests, security)
2. Docker image built with tag: `staging-YYYYMMDD-HHMMSS-SHA`
3. Image pushed to GCR
4. Deployed to `document-intelligence-api-staging`
5. Health checks run automatically
6. Deployment summary posted to commit

**Monitoring**:
- View workflow: **Actions** tab → **CD - Deploy to Cloud Run**
- Check logs: Click on the workflow run
- View service: [Cloud Run Console](https://console.cloud.google.com/run)

### Production Deployment (Manual Approval)

**Trigger**: Push to `main` branch

```bash
# Ensure staging is working correctly
# Then merge to main
git checkout main
git pull origin main
git merge develop

# Push to trigger production deployment workflow
git push origin main
```

**What Happens**:
1. CI checks run (linting, tests, security)
2. Docker image built with tag: `production-YYYYMMDD-HHMMSS-SHA`
3. Image pushed to GCR
4. **⏸ Workflow pauses for manual approval**
5. Designated reviewer approves deployment
6. Deployed to `document-intelligence-api`
7. Comprehensive health checks run
8. GitHub release created automatically
9. Deployment summary posted

**Manual Approval Process**:
1. Go to **Actions** tab
2. Click on the running workflow
3. Click **Review deployments**
4. Select **production** environment
5. Add comment (optional)
6. Click **Approve and deploy**

**Monitoring**:
- View workflow: **Actions** tab → **CD - Deploy to Cloud Run**
- Check health: `https://your-service-url.run.app/status`
- View logs: [Cloud Run Console](https://console.cloud.google.com/run)

### Manual Deployment

Trigger deployment to any environment manually:

1. Go to **Actions** tab
2. Select **CD - Deploy to Cloud Run**
3. Click **Run workflow**
4. Choose branch and environment
5. Click **Run workflow**

## 🔍 Troubleshooting

### CI Failures

#### Linting Errors
```bash
# Run locally to fix
cd document-intelligence-backend
uv run black app/ tests/
uv run ruff check --fix app/ tests/
```

#### Test Failures
```bash
# Run tests locally
cd document-intelligence-backend
uv run pytest tests/ -v --asyncio-mode=auto

# Run specific test
uv run pytest tests/test_specific.py -v
```

#### Docker Build Failures
```bash
# Build locally to debug
cd document-intelligence-backend
docker build -t test-image .

# Check Dockerfile syntax
docker build --no-cache -t test-image .
```

### Deployment Failures

#### Authentication Errors

**Error**: "Permission denied" or "Invalid credentials"

**Solution**:
1. Verify `GCP_SA_KEY` secret is correct
2. Check service account has required roles (see `GCP_SERVICE_ACCOUNT_SETUP.md`)
3. Ensure APIs are enabled:
   ```bash
   gcloud services enable run.googleapis.com
   gcloud services enable cloudbuild.googleapis.com
   gcloud services enable containerregistry.googleapis.com
   ```

#### Environment Variable Errors

**Error**: "Missing required environment variable"

**Solution**:
1. Check all required secrets are configured in GitHub
2. Verify secret names match exactly (case-sensitive)
3. Check environment-specific secrets (staging vs production)

#### Health Check Failures

**Error**: Health check fails after deployment

**Solution**:
1. Check Cloud Run logs:
   ```bash
   gcloud run services logs read document-intelligence-api \
     --region=us-central1 --limit=50
   ```
2. Verify Firestore connectivity
3. Check GCS bucket permissions
4. Validate environment variables

#### Image Build Timeouts

**Error**: Cloud Build timeout

**Solution**:
- Increase timeout in workflow (default: 20 minutes)
- Check for network issues
- Verify Docker layer caching is working

### Rollback

If deployment fails, the workflow automatically rolls back to the previous revision. To manually rollback:

```bash
# List revisions
gcloud run revisions list \
  --service=document-intelligence-api \
  --region=us-central1

# Rollback to specific revision
gcloud run services update-traffic document-intelligence-api \
  --to-revisions=REVISION_NAME=100 \
  --region=us-central1
```

## 📝 Best Practices

### Development Workflow

1. **Feature Development**:
   ```
   feature branch → PR → CI checks → merge to develop
   ```

2. **Staging Testing**:
   ```
   develop branch → auto-deploy to staging → verify functionality
   ```

3. **Production Release**:
   ```
   develop → PR to main → CI checks → merge → manual approval → production
   ```

### Code Quality

- Always run linting locally before pushing: `uv run black app/ && uv run ruff check --fix app/`
- Write tests for new features
- Aim for >80% code coverage
- Keep functions small and focused

### Security

- **Never commit secrets** to the repository
- Rotate service account keys every 90 days
- Use separate secrets for staging and production when possible
- Review security scan results in CI
- Keep dependencies up to date

### Deployment Safety

- **Always test in staging first** before production
- Use semantic versioning for releases
- Write clear commit messages
- Monitor Cloud Run metrics after deployment
- Set up alerting for errors and high latency

### Cost Optimization

- Set appropriate Cloud Run resource limits (memory, CPU)
- Configure max instances to prevent runaway costs
- Use Cloud Build caching for faster builds
- Monitor GCP billing regularly

## 📊 Monitoring & Alerts

### Cloud Run Metrics

View in [Cloud Run Console](https://console.cloud.google.com/run):
- Request count and latency
- Error rate
- Container CPU and memory usage
- Instance count

### Logs

```bash
# View recent logs
gcloud run services logs read document-intelligence-api \
  --region=us-central1 --limit=100

# Follow logs in real-time
gcloud run services logs tail document-intelligence-api \
  --region=us-central1
```

### Alerts

Set up Cloud Monitoring alerts for:
- High error rate (>1%)
- High latency (>2 seconds p95)
- Low request count (service down)
- High memory usage (>80%)

## 🔗 Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Google Cloud Run Documentation](https://cloud.google.com/run/docs)
- [GCP Service Account Setup Guide](../../GCP_SERVICE_ACCOUNT_SETUP.md)
- [Cloud Build Documentation](https://cloud.google.com/build/docs)
- [Workload Identity Federation](https://github.com/google-github-actions/auth#setup) (keyless auth)

## 🆘 Support

If you encounter issues:

1. **Check workflow logs**: Actions tab → Failed workflow → View logs
2. **Review Cloud Run logs**: `gcloud run services logs read SERVICE_NAME`
3. **Verify secrets**: Settings → Secrets and variables → Actions
4. **Test locally**: `./run_dev.sh` to ensure app starts correctly
5. **Check service status**: `curl https://your-service-url/status`

For persistent issues, review the main [README.md](../../README.md) and [CLAUDE.md](../../../CLAUDE.md) documentation.
