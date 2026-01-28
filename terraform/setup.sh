#!/bin/bash
# Quick setup script for Thoth MCP Server on GCP with Terraform Cloud

set -e

echo "🚀 Thoth MCP Server - GCP Terraform Setup"
echo "=========================================="
echo ""

# Check prerequisites
echo "Checking prerequisites..."

if ! command -v terraform &> /dev/null; then
    echo "❌ Terraform is not installed. Please install it from https://www.terraform.io/downloads"
    exit 1
fi
echo "✅ Terraform found: $(terraform version -json | jq -r '.terraform_version')"

if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI is not installed. Please install it from https://cloud.google.com/sdk/docs/install"
    exit 1
fi
echo "✅ gcloud found"

if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install it from https://docs.docker.com/get-docker/"
    exit 1
fi
echo "✅ Docker found"

echo ""

# Get GCP project ID
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "")
if [ -z "$CURRENT_PROJECT" ]; then
    echo "No GCP project is currently set."
    read -p "Enter your GCP Project ID: " PROJECT_ID
    gcloud config set project "$PROJECT_ID"
else
    read -p "Use current GCP project '$CURRENT_PROJECT'? (y/n): " USE_CURRENT
    if [[ "$USE_CURRENT" =~ ^[Yy]$ ]]; then
        PROJECT_ID="$CURRENT_PROJECT"
    else
        read -p "Enter your GCP Project ID: " PROJECT_ID
        gcloud config set project "$PROJECT_ID"
    fi
fi

echo ""
echo "📦 Using GCP Project: $PROJECT_ID"
echo ""

# Enable required APIs
echo "Enabling required GCP APIs..."
gcloud services enable run.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable iam.googleapis.com
gcloud services enable artifactregistry.googleapis.com
echo "✅ APIs enabled"

echo ""

# Build and push container
read -p "Build and push Docker container? (y/n): " BUILD_CONTAINER
if [[ "$BUILD_CONTAINER" =~ ^[Yy]$ ]]; then
    IMAGE_TAG="${IMAGE_TAG:-latest}"
    IMAGE_NAME="gcr.io/${PROJECT_ID}/thoth-mcp:${IMAGE_TAG}"
    
    echo "Building container: $IMAGE_NAME"
    docker build -t "$IMAGE_NAME" .
    
    echo "Configuring Docker for GCR..."
    gcloud auth configure-docker
    
    echo "Pushing container..."
    docker push "$IMAGE_NAME"
    echo "✅ Container pushed: $IMAGE_NAME"
else
    read -p "Enter container image URL (e.g., gcr.io/project/thoth-mcp:latest): " IMAGE_NAME
fi

echo ""

# Create terraform.tfvars
if [ ! -f terraform/terraform.tfvars ]; then
    echo "Creating terraform.tfvars..."
    cat > terraform/terraform.tfvars <<EOF
# Thoth MCP Server Configuration
project_id      = "${PROJECT_ID}"
region          = "us-central1"
environment     = "dev"
container_image = "${IMAGE_NAME}"

# Optional: Set GitLab credentials here or via Secret Manager
# gitlab_token = "your-gitlab-token"
# gitlab_url   = "https://gitlab.com"

# Resource Configuration
log_level        = "INFO"
cloud_run_cpu    = "2"
cloud_run_memory = "2Gi"
min_instances    = 0
max_instances    = 3
EOF
    echo "✅ Created terraform/terraform.tfvars"
else
    echo "⚠️  terraform/terraform.tfvars already exists, skipping creation"
fi

echo ""

# Terraform Cloud setup
echo "🔐 Terraform Cloud Setup"
echo "------------------------"
echo "1. Sign up or log in to Terraform Cloud: https://app.terraform.io"
echo "2. Run 'terraform login' in the terraform/ directory"
echo "3. Edit terraform/main.tf and update the cloud block with:"
echo "   - organization: your Terraform Cloud organization name"
echo "   - workspaces.name: your workspace name (e.g., thoth-mcp-gcp)"
echo ""
read -p "Have you completed Terraform Cloud setup? (y/n): " TF_CLOUD_READY

if [[ "$TF_CLOUD_READY" =~ ^[Yy]$ ]]; then
    echo ""
    echo "Initializing Terraform..."
    cd terraform
    terraform init
    
    echo ""
    echo "Running Terraform plan..."
    terraform plan
    
    echo ""
    read -p "Apply Terraform configuration? (y/n): " APPLY
    if [[ "$APPLY" =~ ^[Yy]$ ]]; then
        terraform apply
        echo ""
        echo "🎉 Deployment complete!"
        echo ""
        echo "Get your service URL:"
        echo "  terraform output service_url"
    fi
else
    echo ""
    echo "Please complete Terraform Cloud setup manually:"
    echo "1. cd terraform"
    echo "2. terraform login"
    echo "3. Edit main.tf to set organization and workspace"
    echo "4. terraform init"
    echo "5. terraform apply"
fi

echo ""
echo "📚 Next steps:"
echo "- View logs: gcloud run services logs read thoth-mcp-server"
echo "- Update secrets: echo -n 'token' | gcloud secrets versions add gitlab-token --data-file=-"
echo "- Grant access: gcloud run services add-iam-policy-binding thoth-mcp-server --region=us-central1 --member='user:email@example.com' --role='roles/run.invoker'"
echo ""
echo "For more information, see terraform/README.md"
