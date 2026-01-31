#!/bin/bash
# Local deployment script for Thoth MCP Server and Ingestion Worker
# This script builds Docker images and deploys to GCP using Terraform

set -e  # Exit on error

PROJECT_ID="thoth-dev-485501"
REGION="us-central1"

echo "═══════════════════════════════════════════"
echo "  Thoth Local Deployment Script"
echo "═══════════════════════════════════════════"
echo ""
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Step 1: Build Docker images
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Building Docker Images"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "Building MCP Server image..."
docker build -f Dockerfile.mcp \
    -t gcr.io/${PROJECT_ID}/thoth-mcp:latest \
    .
echo "✓ MCP Server image built"
echo ""

echo "Building Ingestion Worker image..."
docker build -f Dockerfile.ingestion \
    -t gcr.io/${PROJECT_ID}/thoth-ingestion:latest \
    .
echo "✓ Ingestion Worker image built"
echo ""

# Step 2: Configure Docker for GCR
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Configuring Docker for GCR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

gcloud auth configure-docker --quiet
echo "✓ Docker configured for GCR"
echo ""

# Step 3: Push images to GCR
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Pushing Images to Google Container Registry"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "Pushing MCP Server image..."
docker push gcr.io/${PROJECT_ID}/thoth-mcp:latest
echo "✓ MCP Server image pushed"
echo ""

echo "Pushing Ingestion Worker image..."
docker push gcr.io/${PROJECT_ID}/thoth-ingestion:latest
echo "✓ Ingestion Worker image pushed"
echo ""

# Step 4: Deploy with Terraform
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: Deploying with Terraform"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd terraform

echo "Initializing Terraform..."
terraform init
echo "✓ Terraform initialized"
echo ""

echo "Planning deployment..."
terraform plan -var-file=environments/dev.tfvars
echo ""

read -p "Apply changes? (y/n): " CONFIRM
if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Applying Terraform configuration..."
    terraform apply -var-file=environments/dev.tfvars -auto-approve
    echo ""
    echo "═══════════════════════════════════════════"
    echo "  Deployment Complete! ✓"
    echo "═══════════════════════════════════════════"
    echo ""
    echo "Service URLs:"
    terraform output -raw mcp_service_url 2>/dev/null && echo "" || echo "MCP service URL not yet available"
    terraform output -raw ingestion_service_url 2>/dev/null && echo "" || echo "Ingestion service URL not yet available"
else
    echo "Deployment cancelled."
    exit 0
fi
