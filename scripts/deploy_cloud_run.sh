#!/bin/bash
# Deployment script for Thoth MCP Server to Google Cloud Run

set -euo pipefail

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-thoth-483015}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="thoth-mcp-server"
IMAGE_NAME="thoth-mcp"
IMAGE_TAG="${IMAGE_TAG:-latest}"
GCR_IMAGE="gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    echo_info "Checking prerequisites..."
    
    if ! command -v gcloud &> /dev/null; then
        echo_error "gcloud CLI not found. Please install Google Cloud SDK."
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        echo_error "docker not found. Please install Docker."
        exit 1
    fi
    
    if ! command -v terraform &> /dev/null; then
        echo_warn "terraform not found. Skipping infrastructure setup."
        SKIP_TERRAFORM=true
    else
        SKIP_TERRAFORM=false
    fi
    
    echo_info "Prerequisites check passed."
}

# Configure gcloud
configure_gcloud() {
    echo_info "Configuring gcloud..."
    
    gcloud config set project "${PROJECT_ID}"
    gcloud config set run/region "${REGION}"
    
    echo_info "gcloud configured for project: ${PROJECT_ID}, region: ${REGION}"
}

# Build Docker image
build_image() {
    echo_info "Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG}..."
    
    docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" .
    
    if [ $? -eq 0 ]; then
        echo_info "Docker image built successfully."
    else
        echo_error "Failed to build Docker image."
        exit 1
    fi
}

# Push image to Google Container Registry
push_image() {
    echo_info "Pushing image to GCR: ${GCR_IMAGE}..."
    
    # Configure Docker to use gcloud credentials
    gcloud auth configure-docker --quiet
    
    # Tag image for GCR
    docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "${GCR_IMAGE}"
    
    # Push to GCR
    docker push "${GCR_IMAGE}"
    
    if [ $? -eq 0 ]; then
        echo_info "Image pushed successfully to GCR."
    else
        echo_error "Failed to push image to GCR."
        exit 1
    fi
}

# Deploy infrastructure with Terraform
deploy_infrastructure() {
    if [ "${SKIP_TERRAFORM}" = true ]; then
        echo_warn "Skipping infrastructure deployment (terraform not found)."
        return
    fi
    
    echo_info "Deploying infrastructure with Terraform..."
    
    cd infra
    
    # Initialize Terraform
    terraform init
    
    # Plan deployment
    terraform plan \
        -var="project_id=${PROJECT_ID}" \
        -var="region=${REGION}" \
        -var="container_image=${GCR_IMAGE}" \
        -out=tfplan
    
    # Ask for confirmation
    echo_warn "Review the Terraform plan above."
    read -p "Do you want to apply this plan? (yes/no): " -r
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo_warn "Deployment cancelled by user."
        cd ..
        exit 0
    fi
    
    # Apply deployment
    terraform apply tfplan
    
    if [ $? -eq 0 ]; then
        echo_info "Infrastructure deployed successfully."
    else
        echo_error "Failed to deploy infrastructure."
        cd ..
        exit 1
    fi
    
    cd ..
}

# Deploy to Cloud Run directly (alternative to Terraform)
deploy_cloud_run() {
    echo_info "Deploying to Cloud Run: ${SERVICE_NAME}..."
    
    gcloud run deploy "${SERVICE_NAME}" \
        --image="${GCR_IMAGE}" \
        --platform=managed \
        --region="${REGION}" \
        --allow-unauthenticated \
        --memory=4Gi \
        --cpu=2 \
        --timeout=300 \
        --min-instances=0 \
        --max-instances=3 \
        --set-env-vars="PYTHONUNBUFFERED=1,GCP_PROJECT_ID=${PROJECT_ID},LOG_LEVEL=INFO"
    
    if [ $? -eq 0 ]; then
        echo_info "Cloud Run deployment successful."
    else
        echo_error "Failed to deploy to Cloud Run."
        exit 1
    fi
}

# Verify deployment
verify_deployment() {
    echo_info "Verifying deployment..."
    
    # Get service URL
    SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
        --region="${REGION}" \
        --format="value(status.url)")
    
    if [ -z "${SERVICE_URL}" ]; then
        echo_error "Failed to get service URL."
        exit 1
    fi
    
    echo_info "Service URL: ${SERVICE_URL}"
    
    # Check health endpoint (if available)
    echo_info "Checking service health..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${SERVICE_URL}/health" || echo "000")
    
    if [ "${HTTP_CODE}" = "200" ]; then
        echo_info "Health check passed (HTTP ${HTTP_CODE})."
    else
        echo_warn "Health check returned HTTP ${HTTP_CODE} (service may still be starting)."
    fi
    
    # Show logs
    echo_info "Recent logs:"
    gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=${SERVICE_NAME}" \
        --limit=10 \
        --format="table(timestamp,textPayload)" \
        --freshness=1h
}

# Main deployment flow
main() {
    echo_info "Starting Thoth MCP Server deployment to Cloud Run..."
    echo_info "Project: ${PROJECT_ID}"
    echo_info "Region: ${REGION}"
    echo_info "Image: ${GCR_IMAGE}"
    echo ""
    
    check_prerequisites
    configure_gcloud
    build_image
    push_image
    
    # Choose deployment method
    if [ "${SKIP_TERRAFORM}" = false ]; then
        echo_warn "Deploy using Terraform (recommended) or gcloud CLI?"
        echo "1) Terraform (infrastructure as code)"
        echo "2) gcloud CLI (quick deployment)"
        read -p "Choose (1 or 2): " -r DEPLOY_METHOD
        
        if [ "${DEPLOY_METHOD}" = "1" ]; then
            deploy_infrastructure
        else
            deploy_cloud_run
        fi
    else
        deploy_cloud_run
    fi
    
    verify_deployment
    
    echo ""
    echo_info "Deployment complete! ✓"
    echo_info "Service URL: $(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format='value(status.url)')"
}

# Run main function
main "$@"
