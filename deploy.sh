#!/bin/bash

# ===========================================
# Quick Cloud Run Deployment Script
# Document Intelligence API
# ===========================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
DEFAULT_REGION="us-central1"
DEFAULT_SERVICE_NAME="document-intelligence-api"
DEFAULT_MEMORY="1Gi"
DEFAULT_CPU="1"

# Function to print colored output
print_status() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --project-id)
            PROJECT_ID="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --service-name)
            SERVICE_NAME="$2"
            shift 2
            ;;
        --memory)
            MEMORY="$2"
            shift 2
            ;;
        --cpu)
            CPU="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 --project-id PROJECT_ID [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --project-id     Google Cloud Project ID (required)"
            echo "  --region         Cloud Run region (default: $DEFAULT_REGION)"
            echo "  --service-name   Service name (default: $DEFAULT_SERVICE_NAME)"
            echo "  --memory         Memory allocation (default: $DEFAULT_MEMORY)"
            echo "  --cpu            CPU allocation (default: $DEFAULT_CPU)"
            echo "  --help           Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --project-id my-project-123"
            echo "  $0 --project-id my-project-123 --region us-west1 --memory 2Gi"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Set defaults if not provided
REGION=${REGION:-$DEFAULT_REGION}
SERVICE_NAME=${SERVICE_NAME:-$DEFAULT_SERVICE_NAME}
MEMORY=${MEMORY:-$DEFAULT_MEMORY}
CPU=${CPU:-$DEFAULT_CPU}

# Validate required parameters
if [ -z "$PROJECT_ID" ]; then
    print_error "Project ID is required. Use --project-id YOUR_PROJECT_ID"
    exit 1
fi

echo "🚀 Document Intelligence API - Cloud Run Deployment"
echo "================================================="
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Service Name: $SERVICE_NAME"
echo "Memory: $MEMORY"
echo "CPU: $CPU"
echo ""

# Check prerequisites
print_status "Checking prerequisites..."

if ! command_exists gcloud; then
    print_error "gcloud CLI is not installed"
    print_status "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

if ! command_exists docker; then
    print_error "Docker is not installed"
    print_status "Install from: https://docs.docker.com/get-docker/"
    exit 1
fi

if [ ! -f "Dockerfile" ]; then
    print_error "Dockerfile not found in current directory"
    exit 1
fi

if [ ! -f "pyproject.toml" ]; then
    print_error "pyproject.toml not found"
    print_status "This project uses UV dependency management. Please ensure pyproject.toml exists."
    exit 1
fi

print_success "Prerequisites check passed"

# Set project
print_status "Setting Google Cloud project..."
gcloud config set project "$PROJECT_ID"

# Enable required APIs
print_status "Enabling required APIs..."
gcloud services enable run.googleapis.com \
    cloudbuild.googleapis.com \
    containerregistry.googleapis.com \
    firestore.googleapis.com \
    storage-component.googleapis.com

print_success "APIs enabled"

# Configure Docker auth
print_status "Configuring Docker authentication..."
gcloud auth configure-docker --quiet

# Build and push image
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
TIMESTAMP=$(date +%s)

print_status "Building Docker image for linux/amd64 platform (Cloud Run compatibility)..."
docker build --platform linux/amd64 -t "$IMAGE_NAME:latest" -t "$IMAGE_NAME:$TIMESTAMP" .

print_status "Pushing image to Google Container Registry..."
docker push "$IMAGE_NAME:latest"
docker push "$IMAGE_NAME:$TIMESTAMP"

print_success "Image built and pushed successfully"

# Environment variables
print_status "Preparing environment variables..."

ENV_VARS="ENVIRONMENT=production"
ENV_VARS="$ENV_VARS,FIREBASE_PROJECT_ID=$PROJECT_ID"
ENV_VARS="$ENV_VARS,GCP_PROJECT_ID=$PROJECT_ID"
ENV_VARS="$ENV_VARS,LOG_LEVEL=INFO"
ENV_VARS="$ENV_VARS,LOG_FORMAT=json"

# Optional environment variables with prompts
echo ""
print_status "Optional Configuration (press Enter to skip):"

read -p "GCS Bucket Name: " GCS_BUCKET
if [ ! -z "$GCS_BUCKET" ]; then
    ENV_VARS="$ENV_VARS,GCS_BUCKET_NAME=$GCS_BUCKET"
fi

read -p "JWT Secret Key: " JWT_SECRET
if [ ! -z "$JWT_SECRET" ]; then
    ENV_VARS="$ENV_VARS,JWT_SECRET_KEY=$JWT_SECRET"
fi

read -p "Frontend Domain (e.g., yourdomain.com): " FRONTEND_DOMAIN
if [ ! -z "$FRONTEND_DOMAIN" ]; then
    ENV_VARS="$ENV_VARS,FRONTEND_DOMAIN=$FRONTEND_DOMAIN"
fi

read -p "Production CORS Origins (JSON array): " CORS_ORIGINS
if [ ! -z "$CORS_ORIGINS" ]; then
    # Escape special characters for shell safety
    ESCAPED_CORS_ORIGINS=$(printf '%s\n' "$CORS_ORIGINS" | sed 's/\\/\\\\/g; s/"/\\"/g')
    ENV_VARS="$ENV_VARS,PRODUCTION_CORS_ORIGINS=\"$ESCAPED_CORS_ORIGINS\""
fi

# Deploy to Cloud Run
print_status "Deploying to Cloud Run..."

gcloud run deploy "$SERVICE_NAME" \
    --image "$IMAGE_NAME:latest" \
    --platform managed \
    --region "$REGION" \
    --allow-unauthenticated \
    --memory "$MEMORY" \
    --cpu "$CPU" \
    --concurrency 80 \
    --max-instances 10 \
    --timeout 300 \
    --set-env-vars "$ENV_VARS"

# Get service URL
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --platform managed \
    --region "$REGION" \
    --format "value(status.url)")

print_success "Deployment completed successfully!"

# Display deployment information
echo ""
echo "🎉 Deployment Information"
echo "========================"
echo "Service Name: $SERVICE_NAME"
echo "Region: $REGION"
echo "Service URL: $SERVICE_URL"
echo ""
echo "🔗 API Endpoints:"
echo "• Health Check: $SERVICE_URL/health"
echo "• API Status: $SERVICE_URL/status"
echo "• Documentation: $SERVICE_URL/docs"
echo ""
echo "📚 Next Steps:"
echo "• Test the deployment: curl $SERVICE_URL/health"
echo "• View logs: gcloud run services logs tail $SERVICE_NAME --region=$REGION"
echo "• Update service: gcloud run services update $SERVICE_NAME --region=$REGION"
echo ""

# Test deployment
print_status "Testing deployment..."
if command_exists curl; then
    if curl -f -s "$SERVICE_URL/health" > /dev/null; then
        print_success "Health check passed"
    else
        print_warning "Health check failed - service may still be starting"
    fi
else
    print_warning "curl not found - skipping health check"
fi

print_success "Deployment script completed!"