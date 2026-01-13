#!/bin/bash
# Terraform Bootstrap Script
# This script creates the GCS bucket for storing Terraform state
# Run this once before using the main Terraform configuration

set -e

# Configuration
PROJECT_ID="thoth-483015"
REGION="us-central1"
STATE_BUCKET="thoth-terraform-state"

echo "🚀 Terraform Bootstrap for Thoth"
echo "=================================="
echo ""

# Check if gcloud is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &>/dev/null; then
    echo "❌ Error: Not authenticated with gcloud"
    echo "   Run: gcloud auth login"
    exit 1
fi

# Set project
echo "📦 Setting project to: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# Check if bucket already exists
if gsutil ls -b "gs://$STATE_BUCKET" &>/dev/null; then
    echo "✅ State bucket already exists: gs://$STATE_BUCKET"
    echo ""
    echo "Checking bucket configuration..."
    
    # Verify versioning
    VERSIONING=$(gsutil versioning get "gs://$STATE_BUCKET" | grep -o "Enabled\|Suspended")
    if [ "$VERSIONING" = "Enabled" ]; then
        echo "  ✅ Versioning: Enabled"
    else
        echo "  ⚠️  Versioning: Disabled (enabling...)"
        gsutil versioning set on "gs://$STATE_BUCKET"
    fi
    
    # Verify uniform bucket-level access
    UBA=$(gsutil uniformbucketlevelaccess get "gs://$STATE_BUCKET" | grep -o "Enabled\|Disabled")
    if [ "$UBA" = "Enabled" ]; then
        echo "  ✅ Uniform bucket-level access: Enabled"
    else
        echo "  ⚠️  Uniform bucket-level access: Disabled (enabling...)"
        gsutil uniformbucketlevelaccess set on "gs://$STATE_BUCKET"
    fi
    
    echo ""
    echo "✅ Bootstrap validation complete!"
    exit 0
fi

echo "📦 Creating state bucket: gs://$STATE_BUCKET"
echo ""

# Navigate to infra directory
cd "$(dirname "$0")/../infra"

# Initialize Terraform without backend (for bootstrap)
echo "1️⃣  Initializing Terraform (local state)..."
terraform init -backend=false

# Apply bootstrap configuration
echo ""
echo "2️⃣  Creating state bucket with Terraform..."
terraform apply -auto-approve \
    -target=google_storage_bucket.terraform_state \
    -target=google_storage_bucket_iam_member.github_actions_state_access \
    -var="project_id=$PROJECT_ID" \
    -var="region=$REGION"

# Verify bucket was created
if ! gsutil ls -b "gs://$STATE_BUCKET" &>/dev/null; then
    echo ""
    echo "❌ Error: State bucket was not created successfully"
    exit 1
fi

echo ""
echo "3️⃣  Migrating state to GCS backend..."
# Migrate state to the new bucket
terraform init -migrate-state -force-copy

# Clean up local state files
echo ""
echo "4️⃣  Cleaning up local state files..."
rm -f terraform.tfstate terraform.tfstate.backup

echo ""
echo "✅ Bootstrap complete!"
echo ""
echo "State bucket created: gs://$STATE_BUCKET"
echo "Terraform backend configured: GCS"
echo ""
echo "Next steps:"
echo "  1. Run: cd infra && terraform init"
echo "  2. Run: terraform plan"
echo "  3. Run: terraform apply"
echo ""
