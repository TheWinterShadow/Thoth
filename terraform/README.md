# Thoth MCP Server - GCP Terraform with Terraform Cloud

This directory contains Terraform configuration for deploying Thoth MCP Server to Google Cloud Platform (GCP) using Cloud Run with **Terraform Cloud** for remote state management.

## Architecture

- **Cloud Run**: Serverless container platform hosting the MCP server
- **Cloud Storage**: Vector database storage (GCS bucket)
- **Secret Manager**: Secure storage for GitLab credentials
- **Service Account**: Least-privilege IAM for Cloud Run
- **Terraform Cloud**: Remote state management and execution

## Quick Start

### Prerequisites

1. GCP project with billing enabled
2. Terraform Cloud account (free tier works)
3. Docker image built and pushed to GCR
4. `gcloud` CLI authenticated

### Setup Steps

```bash
# 1. Authenticate with Terraform Cloud
terraform login

# 2. Initialize Terraform
terraform init

# 3. Plan with environment-specific variables
terraform plan -var-file=environments/dev.tfvars

# 4. Apply changes
terraform apply -var-file=environments/dev.tfvars
```

## Detailed Setup

For complete setup instructions including:
- Terraform Cloud workspace configuration
- GCP service account creation
- GitHub Actions integration
- Environment variables setup

See: **[Terraform Cloud Setup Guide](../docs/TERRAFORM_CLOUD_SETUP.md)**

## Configuration

### Terraform Cloud Backend

Configured in [main.tf](main.tf):

```hcl
terraform {
  cloud {
    organization = "TheWinterShadow"
    workspaces {
      name = "thoth-mcp-gcp"
    }
  }
}
```

### Environment Variables

Set these in your Terraform Cloud workspace at:
https://app.terraform.io/app/TheWinterShadow/thoth-mcp-gcp/settings/variables

**Environment Variables** (for provider authentication):
- `GOOGLE_CREDENTIALS` - Minified JSON service account key (sensitive)

**Terraform Variables** (or use tfvars files):
- `project_id` - Your GCP project ID
- `region` - GCP region (default: us-central1)
- `container_image` - Full container image path
- `environment` - Environment name (dev/staging/prod)
- `gitlab_token` - GitLab PAT (optional, sensitive)
- `gitlab_url` - GitLab URL (default: https://gitlab.com)

### Environment-Specific Configuration

Use tfvars files for different environments:

```bash
# Development
terraform plan -var-file=environments/dev.tfvars

# Production (future)
terraform plan -var-file=environments/prod.tfvars
```
# Build the container
docker build -t gcr.io/YOUR_PROJECT_ID/thoth-mcp:latest .

# Configure Docker for GCR
gcloud auth configure-docker

# Push the image
docker push gcr.io/YOUR_PROJECT_ID/thoth-mcp:latest
```

### 5. Initialize and Deploy

```bash
# Initialize Terraform (connects to Terraform Cloud)
terraform init

# Review the plan
terraform plan

# Deploy
terraform apply
```

## Configuration Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `project_id` | GCP Project ID | - | Yes |
| `region` | GCP region | `us-central1` | No |
| `environment` | Environment (dev/staging/prod) | `dev` | No |
| `container_image` | Docker image URL | - | Yes |
| `gitlab_token` | GitLab PAT (or set in Secret Manager) | `""` | No |
| `gitlab_url` | GitLab base URL | `https://gitlab.com` | No |
| `log_level` | Application log level | `INFO` | No |
| `cloud_run_cpu` | CPU allocation | `"2"` | No |
| `cloud_run_memory` | Memory allocation | `"2Gi"` | No |
| `min_instances` | Min Cloud Run instances | `0` | No |
| `max_instances` | Max Cloud Run instances | `3` | No |

## Outputs

After deployment, Terraform outputs:
- `service_url`: Cloud Run service URL
- `service_name`: Cloud Run service name
- `storage_bucket_name`: GCS bucket name
- `service_account_email`: Service account email

## Managing Secrets

### Option 1: Via Terraform (Initial Setup)

Set in `terraform.tfvars`:
```hcl
gitlab_token = "your-token-here"
```

### Option 2: Via GCP Console/CLI (Recommended for Production)

```bash
# Update GitLab token
echo -n "your-token" | gcloud secrets versions add gitlab-token --data-file=-

# Update GitLab URL
echo -n "https://gitlab.com" | gcloud secrets versions add gitlab-url --data-file=-
```

## Authentication & Access

By default, Cloud Run requires authentication. To allow public access, uncomment the resource in [main.tf](main.tf#L279-L284).

To grant access to specific users/services:
```bash
gcloud run services add-iam-policy-binding thoth-mcp-server \
  --region=us-central1 \
  --member="user:email@example.com" \
  --role="roles/run.invoker"
```

## Terraform Cloud Configuration

### Workspace Settings

In your Terraform Cloud workspace:
1. Set execution mode to "Remote"
2. Configure auto-apply (optional)
3. Add environment variables if using secrets via TF Cloud

### Variable Sets (Optional)

For managing multiple environments, create variable sets in Terraform Cloud:
- Development variables
- Staging variables
- Production variables

## Cleanup

To destroy all resources:
```bash
terraform destroy
```

**Note**: This will delete:
- Cloud Run service
- GCS bucket and all data
- Secrets (but not their versions)
- Service account

## Migration from AWS

If migrating from AWS Lambda to GCP Cloud Run:
1. Update application code to use GCS instead of S3
2. Update environment variables
3. Build new container image
4. Deploy with this Terraform configuration

Backup files from previous AWS configuration are saved with `.backup` extension.

## Troubleshooting

### Terraform Cloud Connection Issues
```bash
# Re-authenticate
terraform login

# Verify workspace exists
terraform workspace list
```

### GCP API Issues
```bash
# Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable storage.googleapis.com
```

### Container Build Issues
```bash
# Test container locally
docker run -p 8080:8080 gcr.io/YOUR_PROJECT_ID/thoth-mcp:latest
```

## Support

For issues or questions:
- Check Cloud Run logs: `gcloud run services logs read thoth-mcp-server`
- Review Terraform state: `terraform show`
- Validate configuration: `terraform validate`
