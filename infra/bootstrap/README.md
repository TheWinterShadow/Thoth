# Terraform State Bucket Bootstrap

This directory contains the bootstrap configuration for creating the Terraform state bucket.

## Why a Separate Bootstrap?

The main infrastructure configuration (`infra/`) uses a GCS backend to store its Terraform state. However, we need to create that GCS bucket first, which creates a chicken-and-egg problem. This bootstrap configuration solves that by:

1. Using a **local backend** (stores state on disk)
2. Creating **only the state bucket** without dependencies on other infrastructure
3. Running **before** the main infrastructure deployment

## Usage

### Automated (Recommended)

The GitHub Actions workflow automatically runs bootstrap when needed:
```bash
git push  # Triggers infra-deploy.yml workflow
```

### Manual Bootstrap

```bash
cd infra/bootstrap
terraform init
terraform apply -var="project_id=thoth-483015" -var="region=us-central1"
```

### Using the Script

```bash
./scripts/bootstrap_terraform.sh
```

## IAM Requirements

The service account or user running the bootstrap must have these permissions:

- `storage.buckets.create`
- `storage.buckets.get`
- `storage.buckets.update`

Typically granted by roles:
- `roles/storage.admin`
- `roles/editor`
- `roles/owner`

## After Bootstrap

Once the bucket is created:

1. The main infrastructure (`infra/`) can initialize with the GCS backend
2. All Terraform state will be stored in `gs://thoth-terraform-state`
3. The local state file in this directory can be kept for reference

## State Management

- **Bootstrap state**: Stored locally in `infra/bootstrap/terraform.tfstate`
- **Main infra state**: Stored in GCS at `gs://thoth-terraform-state/terraform/state`

## Bucket Configuration

The bucket is created with:
- **Versioning enabled**: For state recovery
- **Uniform bucket-level access**: For security
- **Public access prevention**: Enforced
- **Lifecycle rules**: Cleans up old versions after 30 days, keeps last 10 versions

## Troubleshooting

**Error: "bucket already exists"**
- The bucket name is globally unique
- If it exists, skip bootstrap and run `terraform init` in the main `infra/` directory

**Error: "permission denied"**
- Ensure your service account has storage admin permissions
- For GitHub Actions, verify `GOOGLE_APPLICATION_CREDENTIALS` secret is set correctly
