# GCP Service Account Setup for GitHub Actions

This guide walks you through creating a Google Cloud Platform (GCP) service account with the necessary permissions for GitHub Actions to deploy your Document Intelligence Backend to Cloud Run.

## Prerequisites

- GCP account with billing enabled
- `gcloud` CLI installed and authenticated
- Project ID: `biz2bricksv1` (or your project ID)
- Owner or Project IAM Admin role on the project

## Quick Setup (Automated Script)

Run this script to create the service account with all required permissions:

```bash
#!/bin/bash
# Setup script for GitHub Actions service account

PROJECT_ID="biz2bricksv1"
SERVICE_ACCOUNT_NAME="github-actions-deployer"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
KEY_FILE="github-actions-sa-key.json"

# Set the project
gcloud config set project ${PROJECT_ID}

echo "📦 Creating service account: ${SERVICE_ACCOUNT_EMAIL}"
gcloud iam service-accounts create ${SERVICE_ACCOUNT_NAME} \
    --display-name="GitHub Actions Deployer" \
    --description="Service account for automated deployments from GitHub Actions"

echo "🔑 Granting required IAM roles..."

# Cloud Run permissions
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/run.admin"

# Cloud Build permissions
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/cloudbuild.builds.editor"

# Container Registry permissions
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/storage.admin"

# Firestore permissions
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/datastore.user"

# Service account user (to deploy as another service account)
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/iam.serviceAccountUser"

# Logging permissions
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/logging.logWriter"

echo "🔐 Creating and downloading service account key..."
gcloud iam service-accounts keys create ${KEY_FILE} \
    --iam-account=${SERVICE_ACCOUNT_EMAIL}

echo ""
echo "✅ Service account created successfully!"
echo "📄 Key file saved to: ${KEY_FILE}"
echo ""
echo "⚠️  IMPORTANT: Keep this key file secure!"
echo "   - Do NOT commit it to Git"
echo "   - Store it as a GitHub Secret"
echo ""
echo "Next steps:"
echo "1. Base64 encode the key file:"
echo "   cat ${KEY_FILE} | base64 > ${KEY_FILE}.base64"
echo ""
echo "2. Copy the base64 content and add it to GitHub:"
echo "   - Go to your repository Settings > Secrets and variables > Actions"
echo "   - Create a new secret named: GCP_SA_KEY"
echo "   - Paste the base64-encoded content"
echo ""
echo "3. Delete the local key files after adding to GitHub:"
echo "   rm ${KEY_FILE} ${KEY_FILE}.base64"
```

Save this script as `setup_github_actions_sa.sh` and run:

```bash
chmod +x setup_github_actions_sa.sh
./setup_github_actions_sa.sh
```

## Manual Setup (Step-by-Step)

### Step 1: Create the Service Account

```bash
# Set your project ID
PROJECT_ID="biz2bricksv1"
SERVICE_ACCOUNT_NAME="github-actions-deployer"

# Set active project
gcloud config set project ${PROJECT_ID}

# Create service account
gcloud iam service-accounts create ${SERVICE_ACCOUNT_NAME} \
    --display-name="GitHub Actions Deployer" \
    --description="Service account for automated deployments from GitHub Actions"
```

### Step 2: Grant Required IAM Roles

#### Cloud Run Admin
Allows creating, updating, and managing Cloud Run services:

```bash
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/run.admin"
```

#### Cloud Build Editor
Allows submitting and managing Cloud Build jobs:

```bash
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/cloudbuild.builds.editor"
```

#### Storage Admin
Allows managing Container Registry images and GCS buckets:

```bash
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/storage.admin"
```

#### Firestore User
Allows reading and writing Firestore data:

```bash
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/datastore.user"
```

#### Service Account User
Allows the service account to act as Cloud Run runtime service account:

```bash
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"
```

#### Log Writer
Allows writing logs to Cloud Logging:

```bash
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/logging.logWriter"
```

### Step 3: Create and Download Service Account Key

```bash
# Create key file
gcloud iam service-accounts keys create github-actions-sa-key.json \
    --iam-account=${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com

# Verify key was created
ls -lh github-actions-sa-key.json
```

### Step 4: Verify Permissions

```bash
# List all roles granted to the service account
gcloud projects get-iam-policy ${PROJECT_ID} \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --format="table(bindings.role)"
```

You should see:
- `roles/run.admin`
- `roles/cloudbuild.builds.editor`
- `roles/storage.admin`
- `roles/datastore.user`
- `roles/iam.serviceAccountUser`
- `roles/logging.logWriter`

## Step 5: Add to GitHub Secrets

### 5.1 Base64 Encode the Key

**On macOS/Linux:**
```bash
cat github-actions-sa-key.json | base64 > github-actions-sa-key.json.base64
```

**On Windows (PowerShell):**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("github-actions-sa-key.json")) | Out-File -Encoding ASCII github-actions-sa-key.json.base64
```

### 5.2 Add Secret to GitHub

1. Go to your GitHub repository
2. Navigate to **Settings** > **Secrets and variables** > **Actions**
3. Click **New repository secret**
4. Name: `GCP_SA_KEY`
5. Value: Paste the entire content of `github-actions-sa-key.json.base64`
6. Click **Add secret**

### 5.3 Add Additional Required Secrets

Add these secrets following the same process:

**GCP Configuration:**
- `GCP_PROJECT_ID`: `biz2bricksv1`
- `GCP_REGION`: `us-central1`

**Firebase/Firestore:**
- `FIREBASE_PROJECT_ID`: `biz2bricksv1`
- `FIREBASE_DATABASE_ID`: `biz2bricks-docdb-v1`
- `GCS_BUCKET_NAME`: `biz2bricksv1-document-store`

**Security:**
- `JWT_SECRET_KEY`: Your production JWT secret (generate a secure 256-bit key)

**AI Services:**
- `OPENAI_API_KEY`: Your OpenAI API key
- `OPENAI_MODEL`: `gpt-5-mini` (or your preferred model)
- `LLAMAPARSE_API_KEY`: Your LlamaParse API key
- `PINECONE_API_KEY`: Your Pinecone API key
- `PINECONE_ENVIRONMENT`: Your Pinecone environment
- `PINECONE_INDEX_NAME`: `document-intelligence`

**CORS Configuration:**
- `PRODUCTION_CORS_ORIGINS`: `["https://yourdomain.com","https://www.yourdomain.com"]`
- `FRONTEND_DOMAIN`: `biztobricks.com`

**Staging-Specific (if different from production):**
- `STAGING_CORS_ORIGINS`: Staging frontend URLs
- `STAGING_GCS_BUCKET_NAME`: Staging bucket (if different)
- `STAGING_FIREBASE_DATABASE_ID`: Staging database (if different)

### 5.4 Secure Your Key Files

After adding secrets to GitHub, **delete the local key files**:

```bash
# Securely delete the key files
rm -f github-actions-sa-key.json
rm -f github-actions-sa-key.json.base64

# Verify deletion
ls -la github-actions-sa-key.*
```

## Step 6: Setup GitHub Environments

### 6.1 Create Staging Environment

1. Go to **Settings** > **Environments**
2. Click **New environment**
3. Name: `staging`
4. Click **Configure environment**
5. **Environment protection rules**: None (auto-deploy)
6. Add environment-specific secrets if needed

### 6.2 Create Production Environment

1. Click **New environment**
2. Name: `production`
3. Click **Configure environment**
4. **Environment protection rules**:
   - ✅ **Required reviewers**: Add yourself and/or team members
   - ✅ **Wait timer**: Optional (e.g., 5 minutes minimum wait)
   - ✅ **Deployment branches**: Only `main` branch
5. Add production-specific secrets if needed

## Verification

Test your service account authentication:

```bash
# Activate the service account locally (for testing)
gcloud auth activate-service-account \
    --key-file=github-actions-sa-key.json

# Try listing Cloud Run services
gcloud run services list --project=${PROJECT_ID}

# Try listing Firestore databases
gcloud firestore databases list --project=${PROJECT_ID}

# Switch back to your user account
gcloud config set account YOUR_EMAIL@gmail.com
```

## Security Best Practices

1. **Never commit service account keys to Git**
   - Add `*-sa-key.json` to `.gitignore`
   - Add `*.json.base64` to `.gitignore`

2. **Rotate keys regularly**
   - Create new keys every 90 days
   - Delete old keys after rotation

3. **Use least privilege principle**
   - Only grant the minimum required roles
   - Use separate service accounts for different environments

4. **Monitor service account usage**
   - Enable Cloud Audit Logs
   - Set up alerts for suspicious activity

5. **Consider Workload Identity Federation**
   - For enhanced security, use keyless authentication
   - See: https://cloud.google.com/blog/products/identity-security/enabling-keyless-authentication-from-github-actions

## Troubleshooting

### Permission Denied Errors

If you see "Permission Denied" errors during deployment:

1. Verify all IAM roles are granted:
```bash
gcloud projects get-iam-policy ${PROJECT_ID} \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:github-actions-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
```

2. Check if roles need time to propagate (wait 1-2 minutes)

3. Verify the service account email is correct in your workflow

### Invalid Key Format

If GitHub Actions reports invalid credentials:

1. Ensure you base64 encoded the JSON file correctly
2. Verify no extra whitespace was added when copying
3. Try re-encoding: `cat key.json | base64 -w 0` (Linux) or `cat key.json | base64` (macOS)

### Cloud Build Failures

If Cloud Build fails to authenticate:

1. Ensure `cloudbuild.googleapis.com` API is enabled:
```bash
gcloud services enable cloudbuild.googleapis.com --project=${PROJECT_ID}
```

2. Grant Cloud Build service account access to Cloud Run:
```bash
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)")
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
    --role="roles/run.admin"
```

## Next Steps

After completing this setup:

1. ✅ Service account created with proper permissions
2. ✅ Key added to GitHub Secrets
3. ✅ GitHub environments configured
4. → Test the CI/CD pipeline by pushing to `develop` branch
5. → Verify staging deployment
6. → Test production deployment with manual approval

## Additional Resources

- [GitHub Actions for GCP](https://github.com/google-github-actions)
- [Cloud Run IAM Roles](https://cloud.google.com/run/docs/reference/iam/roles)
- [Service Account Best Practices](https://cloud.google.com/iam/docs/best-practices-service-accounts)
- [Workload Identity Federation Setup](https://github.com/google-github-actions/auth#setup)
