# Terraform State Management

This document explains how Terraform state is managed in the Thoth project.

## State Storage

Terraform state is stored in Google Cloud Storage (GCS) to enable:
- **Persistent state** across GitHub Actions workflow runs
- **State locking** to prevent concurrent modifications
- **Team collaboration** with shared state
- **State versioning** for rollback capability
- **Infrastructure as Code** - State bucket is managed by Terraform itself

### State Bucket Configuration

**Bucket Name**: `thoth-terraform-state`  
**Location**: `us-central1`  
**Backend**: GCS (Google Cloud Storage)  
**Managed By**: Terraform (see [infra/bootstrap.tf](../infra/bootstrap.tf))

The state is stored at: `gs://thoth-terraform-state/terraform/state`

## State Bucket as Code

The state bucket itself is managed as Terraform code in [infra/bootstrap.tf](../infra/bootstrap.tf):

```terraform
resource "google_storage_bucket" "terraform_state" {
  name     = "thoth-terraform-state"
  location = var.region
  
  versioning {
    enabled = true  # Essential for state recovery
  }
  
  lifecycle {
    prevent_destroy = true  # Protection against accidental deletion
  }
}
```

This ensures the state bucket configuration is:
- Version controlled
- Documented
- Reproducible
- Auditable

## Backend Configuration

[infra/main.tf](../infra/main.tf):
```terraform
backend "gcs" {
  bucket = "thoth-terraform-state"
  prefix = "terraform/state"
}
```

## Automatic State Bucket Creation

### GitHub Actions (Automated)

The GitHub Actions workflow automatically bootstraps the state bucket if it doesn't exist:

1. **Check** if state bucket exists
2. **Initialize** Terraform without backend (local state)
3. **Apply** bootstrap configuration to create state bucket
4. **Migrate** state to GCS backend
5. **Continue** with main infrastructure deployment

See [.github/workflows/infra-deploy.yml](../.github/workflows/infra-deploy.yml) for implementation.

### Local Development (Manual)

Run the bootstrap script to create the state bucket:

```bash
./scripts/bootstrap_terraform.sh
```

This script:
1. Authenticates with GCP
2. Runs Terraform bootstrap configuration
3. Creates state bucket with proper settings
4. Migrates local state to GCS
5. Cleans up local state files

**Alternative manual approach**:
```bash
cd infra

# Initialize without backend
terraform init -backend=false

# Create state bucket
terraform apply -auto-approve \
  -target=google_storage_bucket.terraform_state \
  -var="project_id=thoth-483015" \
  -var="region=us-central1"

# Migrate to GCS backend
terraform init -migrate-state -force-copy

# Clean up
rm terraform.tfstate*
```

## Handling Existing Resources

### Problem: Resource Already Exists

When a resource (like the storage bucket) already exists in GCP but not in Terraform state, you'll see:
```
Error: googleapi: Error 409: Your previous request to create the named bucket succeeded and you already own it., conflict
```

### Solution 1: Automatic Import (GitHub Actions)

The workflow automatically imports existing resources before running `terraform plan`:

```bash
terraform import google_storage_bucket.thoth_bucket thoth-storage-bucket
```

### Solution 2: Manual Import (Local Development)

If working locally, import existing resources manually:

```bash
cd infra

# Import storage bucket
terraform import google_storage_bucket.thoth_bucket thoth-storage-bucket

# Import other resources as needed
terraform import google_secret_manager_secret.gitlab_token projects/thoth-483015/secrets/gitlab-token
terraform import google_secret_manager_secret.gitlab_url projects/thoth-483015/secrets/gitlab-url
```

### Solution 3: Lifecycle Protection

Resources include lifecycle blocks to prevent recreation:

```terraform
lifecycle {
  prevent_destroy = false
  ignore_changes = [
    name,  # Don't recreate if name hasn't changed
  ]
}
```

## Local Development Setup

### Bootstrap (First Time Only)

Before using Terraform for the first time:

```bash
# Option 1: Use bootstrap script (recommended)
./scripts/bootstrap_terraform.sh

# Option 2: Manual bootstrap
cd infra
terraform init -backend=false
terraform apply -target=google_storage_bucket.terraform_state
terraform init -migrate-state -force-copy
```

### Regular Usage

After bootstrap is complete:

```bash
cd infra

# Authenticate with GCP (if not already)
gcloud auth application-default login

# Initialize Terraform (will use GCS backend)
terraform init

# Verify state is stored remotely
terraform state list
```

### State Commands

```bash
# List all resources in state
terraform state list

# Show details of a specific resource
terraform state show google_storage_bucket.thoth_bucket

# Remove a resource from state (doesn't delete the resource)
terraform state rm google_storage_bucket.thoth_bucket

# Pull remote state to view
terraform state pull

# Push local state to remote (use with caution)
terraform state push

# Import existing resource
terraform import <resource_address> <resource_id>
```

## State Locking

GCS backend automatically provides state locking to prevent concurrent modifications. If a lock is held, you'll see:

```
Error: Error acquiring the state lock
```

**Solution**:
```bash
# Wait for the lock to be released, or force unlock (use with caution)
terraform force-unlock <lock-id>
```

## State Versioning

The state bucket has versioning enabled. To recover a previous state version:

```bash
# List versions
gsutil ls -a gs://thoth-terraform-state/terraform/state/

# Download a specific version
gsutil cp gs://thoth-terraform-state/terraform/state/default.tfstate#<version> .

# Restore if needed
terraform state push default.tfstate
```

## Troubleshooting

### State Bucket Doesn't Exist

**Problem**: `terraform init` fails with "bucket does not exist"

**Solution**:
```bash
# Run bootstrap script
./scripts/bootstrap_terraform.sh

# Or manually create with Terraform
cd infra
terraform init -backend=false
terraform apply -target=google_storage_bucket.terraform_state
terraform init -migrate-state -force-copy
```

### Permission Denied

**Problem**: Cannot access state bucket

**Solution**: Ensure your service account has `roles/storage.objectAdmin`:
```bash
gcloud projects add-iam-policy-binding thoth-483015 \
  --member="serviceAccount:github-actions@thoth-483015.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

### State Drift

**Problem**: Terraform state doesn't match actual infrastructure

**Solution**:
```bash
# Import missing resources
terraform import <resource_address> <resource_id>

# Or refresh state from actual infrastructure
terraform refresh
```

### Corrupted State

**Problem**: State file is corrupted or inconsistent

**Solution**:
```bash
# Restore from previous version
gsutil ls -a gs://thoth-terraform-state/terraform/state/
gsutil cp gs://thoth-terraform-state/terraform/state/default.tfstate#<version> restored.tfstate
terraform state push restored.tfstate
```

## Best Practices

1. **Never edit state files manually** - Use Terraform commands
2. **Always use remote backend** - Don't commit `.tfstate` files to Git
3. **Enable versioning** - Allows state recovery
4. **Use state locking** - Prevents concurrent modifications
5. **Import existing resources** - Don't let resources drift
6. **Regular backups** - GCS versioning provides automatic backups
7. **Review state changes** - Use `terraform plan` before `apply`
8. **Protect production state** - Use separate workspaces or projects

## Migration from Local State

If you previously used local state:

```bash
cd infra

# Backup local state
cp terraform.tfstate terraform.tfstate.backup

# Update main.tf with backend configuration
# Then re-initialize
terraform init -migrate-state

# Verify migration
terraform state list
gsutil ls gs://thoth-terraform-state/terraform/state/

# Delete local state after verification
rm terraform.tfstate terraform.tfstate.backup
```

## Related Documentation

- [Infrastructure Deployment](CLOUD_RUN_DEPLOYMENT.md)
- [GitHub Actions Workflows](GITHUB_ACTIONS.md)
- [Terraform GCS Backend Documentation](https://www.terraform.io/docs/backends/types/gcs.html)
