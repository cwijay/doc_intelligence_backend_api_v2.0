# CI/CD Pipeline Documentation
Document Intelligence Backend API - Automated Deployment Pipeline

## 📋 Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Environments](#environments)
- [Deployment Workflows](#deployment-workflows)
- [Setup Instructions](#setup-instructions)
- [Using the Pipeline](#using-the-pipeline)
- [Monitoring & Logs](#monitoring--logs)
- [Rollback Procedures](#rollback-procedures)
- [Secrets Management](#secrets-management)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Overview

This project uses **Google Cloud Build** with **GitHub 2nd generation integration** for automated CI/CD deployments to Cloud Run.

**Key Features:**
- ✅ Automated testing before every deployment
- ✅ Secure secret management via Secret Manager
- ✅ Separate development and production environments
- ✅ Manual approval gate for production deployments
- ✅ Gradual traffic rollout (10% → 50% → 100%)
- ✅ Automated health checks
- ✅ Easy rollback capabilities

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ GitHub Repository: cwijay/doc_intelligence_backend_api_v2.0     │
└───────────────┬─────────────────────────────────┬───────────────┘
                │                                 │
        ┌───────▼────────┐               ┌────────▼────────┐
        │ develop branch │               │  master branch  │
        │  (automatic)   │               │ (with approval) │
        └───────┬────────┘               └────────┬────────┘
                │                                 │
        ┌───────▼────────┐               ┌────────▼────────┐
        │  Cloud Build   │               │  Cloud Build    │
        │   Trigger      │               │    Trigger      │
        │  (immediate)   │               │  (approval req) │
        └───────┬────────┘               └────────┬────────┘
                │                                 │
        ┌───────▼────────┐               ┌────────▼────────┐
        │   Run Tests    │               │   Run Tests     │
        │  Build Docker  │               │  Build Docker   │
        │  Push to GCR   │               │  Push to GCR    │
        │     Deploy     │               │ Deploy (0% →    │
        │  Health Check  │               │  10% → 50% →    │
        │                │               │  100% traffic)  │
        └───────┬────────┘               └────────┬────────┘
                │                                 │
        ┌───────▼────────────────┐       ┌────────▼──────────────────┐
        │ document-intelligence- │       │ document-intelligence-api │
        │       api-dev          │       │      (production)         │
        └────────────────────────┘       └───────────────────────────┘
```

---

## Environments

| Environment | Branch | Service Name | URL | Deployment Type | Approval |
|-------------|--------|--------------|-----|-----------------|----------|
| **Development** | `develop` | `document-intelligence-api-dev` | Auto-generated | Automatic | None |
| **Production** | `master` | `document-intelligence-api` | Auto-generated | Gradual rollout | Required |

### Development Environment
- **Purpose**: Testing and development
- **Deployment**: Automatic on every push to `develop`
- **Timeline**: ~5-7 minutes
- **Resource Limits**: 1Gi memory, 1 CPU, max 5 instances
- **Log Level**: DEBUG

### Production Environment
- **Purpose**: Live production workloads
- **Deployment**: Manual approval required + gradual rollout
- **Timeline**: ~15-20 minutes (including gradual migration)
- **Resource Limits**: 1Gi memory, 1 CPU, max 10 instances
- **Log Level**: INFO
- **Traffic Migration**: 0% → 10% (2 min) → 50% (2 min) → 100%

---

## Deployment Workflows

### Development Deployment (Automatic)

```bash
# 1. Make changes and commit
git checkout develop
git add .
git commit -m "Add new feature"
git push origin develop

# 2. Cloud Build automatically:
#    - Triggers within seconds
#    - Runs pytest tests
#    - Builds Docker image (linux/amd64)
#    - Pushes to GCR with tags: commit SHA, dev-latest, dev-{SHORT_SHA}
#    - Deploys to Cloud Run (document-intelligence-api-dev)
#    - Runs health checks (/health, /status)
#    - Reports success or failure

# 3. Timeline: ~5-7 minutes
```

**What happens:**
1. **Test Phase** (~1-2 min): Installs UV, syncs dependencies, runs pytest
2. **Build Phase** (~2-3 min): Builds Docker image for Cloud Run
3. **Push Phase** (~1 min): Pushes image to Container Registry
4. **Deploy Phase** (~1-2 min): Deploys to Cloud Run with secrets
5. **Verify Phase** (~30 sec): Health checks on deployed service

### Production Deployment (Manual Approval)

```bash
# 1. Merge develop to master
git checkout master
git merge develop
git push origin master

# 2. Cloud Build:
#    - Trigger created but WAITS for approval
#    - Email notification sent to approvers

# 3. Approve in Cloud Console:
#    - Navigate to Cloud Build → Builds
#    - Find pending build
#    - Review build details
#    - Click "Approve"

# 4. After approval, Cloud Build:
#    - Runs comprehensive tests
#    - Builds production Docker image
#    - Deploys new revision with 0% traffic (candidate)
#    - Runs smoke tests on candidate revision
#    - Gradually migrates traffic: 10% → 50% → 100%
#    - Monitors for 2 minutes between each phase
#    - Final health check

# 5. Timeline: ~15-20 minutes after approval
```

**Gradual Rollout Details:**
- **Phase 1 (10%)**: New revision gets 10% of traffic, old revision 90%
  - Wait: 2 minutes for monitoring
  - Purpose: Early detection of issues with minimal impact
- **Phase 2 (50%)**: New revision gets 50% of traffic, old revision 50%
  - Wait: 2 minutes for monitoring
  - Purpose: Validate at higher load
- **Phase 3 (100%)**: New revision gets all traffic
  - Old revision kept for easy rollback

---

## Setup Instructions

### Prerequisites
- Google Cloud Project: `biz2bricks-dev-v1`
- GitHub repository: `https://github.com/cwijay/doc_intelligence_backend_api_v2.0.git`
- Admin access to GitHub repository
- Cloud Run service already deployed once (run `./deploy_full.sh` first)

### Step 1: Set Up Secrets (One-time)

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Migrate secrets to Secret Manager
./scripts/setup_secrets.sh
```

This creates secrets from `.env.dev` and `.env.production`:
- Development secrets: `JWT_SECRET_KEY`, `OPENAI_API_KEY`, etc.
- Production secrets: `JWT_SECRET_KEY-prod`, `OPENAI_API_KEY-prod`, etc.

### Step 2: Grant Cloud Build Permissions (One-time)

```bash
./scripts/setup_cloudbuild_permissions.sh
```

This grants Cloud Build service account:
- `roles/run.admin` - Deploy Cloud Run services
- `roles/iam.serviceAccountUser` - Use service accounts
- `roles/storage.admin` - Manage GCS
- `roles/logging.logWriter` - Write logs

### Step 3: Connect GitHub Repository (One-time)

```bash
./scripts/setup_github_connection.sh
```

Follow the prompts:
1. Script provides authorization URL
2. Open URL in browser
3. Sign in to GitHub
4. Install Google Cloud Build GitHub App
5. Select repository: `cwijay/doc_intelligence_backend_api_v2.0`
6. Authorize access
7. Return to terminal and press Enter

### Step 4: Create Build Triggers (One-time)

```bash
./scripts/create_triggers.sh
```

This creates:
- **deploy-dev-on-push**: Triggers on `develop` branch push (automatic)
- **deploy-prod-on-master**: Triggers on `master` branch push (manual approval)

### Step 5: Test the Pipeline

```bash
# Test development deployment
git checkout develop
echo "# Test CI/CD" >> README.md
git commit -am "Test CI/CD pipeline"
git push origin develop

# Monitor at: https://console.cloud.google.com/cloud-build/builds
```

---

## Using the Pipeline

### Typical Development Workflow

```bash
# 1. Create feature branch
git checkout develop
git pull origin develop
git checkout -b feature/new-feature

# 2. Make changes and test locally
./run_dev.sh

# 3. Commit and push
git add .
git commit -m "Add new feature"
git push origin feature/new-feature

# 4. Create Pull Request to develop
# - Review code
# - Run tests

# 5. Merge PR to develop
# - CI/CD automatically deploys to dev

# 6. Test on dev environment
# - Verify functionality
# - Check logs

# 7. When ready for production:
git checkout master
git pull origin master
git merge develop
git push origin master

# 8. Approve deployment in Cloud Console
# 9. Monitor gradual rollout
```

### Emergency Hotfix Workflow

```bash
# 1. Create hotfix branch from master
git checkout master
git pull origin master
git checkout -b hotfix/critical-fix

# 2. Make fix
# Edit files...

# 3. Test locally
./run_dev.sh

# 4. Commit and push to master
git checkout master
git merge hotfix/critical-fix
git push origin master

# 5. Approve quickly in Cloud Console
# 6. Monitor deployment closely
```

---

## Monitoring & Logs

### View Build Status

```bash
# List recent builds
gcloud builds list --region=us-central1 --limit=10

# View specific build
gcloud builds describe BUILD_ID --region=us-central1

# Stream build logs in real-time
gcloud builds log BUILD_ID --region=us-central1 --stream
```

### View Service Logs

```bash
# Development logs
gcloud run services logs read document-intelligence-api-dev \
  --region=us-central1 \
  --limit=50

# Production logs
gcloud run services logs read document-intelligence-api \
  --region=us-central1 \
  --limit=50

# Follow logs in real-time
gcloud run services logs tail document-intelligence-api \
  --region=us-central1
```

### Check Service Status

```bash
# Get service URL
gcloud run services describe document-intelligence-api \
  --region=us-central1 \
  --format="value(status.url)"

# View traffic split (during gradual rollout)
gcloud run services describe document-intelligence-api \
  --region=us-central1 \
  --format="value(status.traffic)"

# List all revisions
gcloud run revisions list \
  --service=document-intelligence-api \
  --region=us-central1 \
  --limit=5
```

### Cloud Console Links

- **Builds**: https://console.cloud.google.com/cloud-build/builds?project=biz2bricks-dev-v1
- **Triggers**: https://console.cloud.google.com/cloud-build/triggers?project=biz2bricks-dev-v1
- **Cloud Run**: https://console.cloud.google.com/run?project=biz2bricks-dev-v1
- **Secret Manager**: https://console.cloud.google.com/security/secret-manager?project=biz2bricks-dev-v1

---

## Rollback Procedures

### Option 1: Via Cloud Console (Recommended)

1. Go to Cloud Run → Services → `document-intelligence-api`
2. Click "Revisions" tab
3. Find previous healthy revision
4. Click "..." menu → "Manage Traffic"
5. Set 100% traffic to previous revision
6. Click "Save"

### Option 2: Via CLI (Fast)

```bash
# List recent revisions
gcloud run revisions list \
  --service=document-intelligence-api \
  --region=us-central1 \
  --limit=5

# Rollback to specific revision
gcloud run services update-traffic document-intelligence-api \
  --region=us-central1 \
  --to-revisions=PREVIOUS_REVISION_NAME=100
```

### Option 3: Emergency Rollback (Instant)

```bash
# Rollback to second-latest revision (one command)
PREVIOUS_REV=$(gcloud run revisions list \
  --service=document-intelligence-api \
  --region=us-central1 \
  --format="value(metadata.name)" \
  --limit=2 | tail -1)

gcloud run services update-traffic document-intelligence-api \
  --region=us-central1 \
  --to-revisions=$PREVIOUS_REV=100

echo "Rolled back to: $PREVIOUS_REV"
```

### Rollback During Gradual Rollout

If issues detected during 10% or 50% phase:

```bash
# Immediately route all traffic back to stable revision
STABLE_REV=$(gcloud run revisions list \
  --service=document-intelligence-api \
  --region=us-central1 \
  --format="value(metadata.name)" \
  --limit=2 | tail -1)

gcloud run services update-traffic document-intelligence-api \
  --region=us-central1 \
  --to-revisions=$STABLE_REV=100
```

---

## Secrets Management

### View Secrets

```bash
# List all secrets
gcloud secrets list --project=biz2bricks-dev-v1

# View secret metadata
gcloud secrets describe JWT_SECRET_KEY --project=biz2bricks-dev-v1

# View secret versions
gcloud secrets versions list JWT_SECRET_KEY --project=biz2bricks-dev-v1
```

### Update a Secret

```bash
# Add new version
echo -n "new-secret-value" | gcloud secrets versions add JWT_SECRET_KEY \
  --data-file=- \
  --project=biz2bricks-dev-v1

# Update production secret
echo -n "new-prod-secret" | gcloud secrets versions add JWT_SECRET_KEY-prod \
  --data-file=- \
  --project=biz2bricks-dev-v1
```

### Add New Secret

```bash
# Create secret
echo -n "secret-value" | gcloud secrets create NEW_SECRET_NAME \
  --data-file=- \
  --replication-policy=automatic \
  --project=biz2bricks-dev-v1

# Grant Cloud Build access
PROJECT_NUMBER=$(gcloud projects describe biz2bricks-dev-v1 --format="value(projectNumber)")
gcloud secrets add-iam-policy-binding NEW_SECRET_NAME \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=biz2bricks-dev-v1

# Update cloudbuild.yaml to reference new secret:
# availableSecrets:
#   secretManager:
#     - versionName: projects/$PROJECT_ID/secrets/NEW_SECRET_NAME/versions/latest
#       env: NEW_SECRET_NAME
#
# Then add to secretEnv: ['NEW_SECRET_NAME']
# And --update-secrets=NEW_SECRET_NAME=NEW_SECRET_NAME:latest
```

---

## Troubleshooting

### Build Fails During Test Step

**Symptoms**: Build fails with pytest errors

**Solutions**:
```bash
# 1. View test logs
gcloud builds log BUILD_ID --region=us-central1 | grep "test"

# 2. Run tests locally
uv sync
uv run pytest tests/ -v --asyncio-mode=auto

# 3. Fix failing tests and push again
```

### Build Fails During Docker Build

**Symptoms**: Docker build step fails

**Solutions**:
```bash
# 1. Check Dockerfile syntax locally
docker build -t test-image .

# 2. Review build logs for missing files
gcloud builds log BUILD_ID --region=us-central1 | grep "ERROR"

# 3. Ensure all dependencies in requirements.txt or pyproject.toml
```

### Deployment Fails

**Symptoms**: Deploy step fails with permission errors

**Solutions**:
```bash
# 1. Check Cloud Build service account permissions
PROJECT_NUMBER=$(gcloud projects describe biz2bricks-dev-v1 --format="value(projectNumber)")
gcloud projects get-iam-policy biz2bricks-dev-v1 \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

# 2. Re-run permissions script
./scripts/setup_cloudbuild_permissions.sh

# 3. Verify service account exists
gcloud iam service-accounts describe 727735128283-compute@developer.gserviceaccount.com
```

### Health Check Fails

**Symptoms**: Health check step fails after deployment

**Solutions**:
```bash
# 1. Check service logs immediately after deployment
gcloud run services logs read document-intelligence-api-dev \
  --region=us-central1 \
  --limit=100

# 2. Test health endpoint manually
SERVICE_URL=$(gcloud run services describe document-intelligence-api-dev \
  --region=us-central1 \
  --format="value(status.url)")
curl -v $SERVICE_URL/health

# 3. Common causes:
# - Missing environment variables
# - Invalid secrets
# - Firestore database not accessible
# - GCS bucket permissions issues
```

### Secret Not Found

**Symptoms**: Build fails with "secret not found" error

**Solutions**:
```bash
# 1. Verify secret exists
gcloud secrets describe JWT_SECRET_KEY --project=biz2bricks-dev-v1

# 2. Check Cloud Build has access
gcloud secrets get-iam-policy JWT_SECRET_KEY --project=biz2bricks-dev-v1

# 3. Re-run secret setup
./scripts/setup_secrets.sh
```

### Trigger Not Firing

**Symptoms**: Push to branch doesn't trigger build

**Solutions**:
```bash
# 1. Check trigger exists and is enabled
gcloud builds triggers list --region=us-central1 --project=biz2bricks-dev-v1

# 2. Check GitHub connection status
gcloud builds connections describe biz2bricks-github-connection \
  --region=us-central1 \
  --project=biz2bricks-dev-v1

# 3. Manually run trigger
gcloud builds triggers run deploy-dev-on-push \
  --region=us-central1 \
  --branch=develop \
  --project=biz2bricks-dev-v1
```

---

## Best Practices

### Development
1. **Always test on develop first** before merging to master
2. **Run tests locally** before pushing: `uv run pytest tests/ -v`
3. **Monitor build immediately** after pushing to catch issues early
4. **Review logs** for warnings even if deployment succeeds
5. **Test deployed service** before considering it stable

### Production Deployments
1. **Review all changes** before approving production build
2. **Check build logs** for any warnings before approval
3. **Monitor metrics** during gradual rollout (especially 10% phase)
4. **Have rollback plan ready** before starting deployment
5. **Test critical paths** after 100% rollout
6. **Document changes** in commit messages for audit trail

### Secret Management
1. **Never commit secrets** to repository
2. **Rotate secrets quarterly** or after team member changes
3. **Use different secrets** for dev and production
4. **Audit secret access** regularly
5. **Delete unused secrets** promptly

### Monitoring
1. **Check builds daily** for any failures
2. **Review error logs weekly** to catch patterns
3. **Monitor Cloud Run metrics** (latency, errors, resource usage)
4. **Set up alerting** for critical errors
5. **Keep old revisions** for at least 30 days for rollback

### Cost Optimization
1. **Use lower resources for dev** (512Mi memory, 1 CPU, max 3 instances)
2. **Review Cloud Build logs** to optimize build times
3. **Clean up old Docker images** periodically
4. **Monitor Cloud Run costs** and adjust max instances as needed
5. **Use --skip-indexes flag** when redeploying without schema changes

---

## Additional Resources

- **Cloud Build Documentation**: https://cloud.google.com/build/docs
- **Cloud Run Documentation**: https://cloud.google.com/run/docs
- **Secret Manager Documentation**: https://cloud.google.com/secret-manager/docs
- **GitHub App Setup**: https://cloud.google.com/build/docs/automating-builds/github/connect-repo-github

---

## Support & Feedback

For issues or questions:
1. Check this documentation first
2. Review Cloud Build logs
3. Check Cloud Run service logs
4. Search Google Cloud documentation
5. Open GitHub issue if problem persists

---

**Last Updated**: 2025-01-13
**Pipeline Version**: 1.0
