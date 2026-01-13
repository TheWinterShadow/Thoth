# Thoth Infrastructure as Code

This directory contains Terraform configuration for the Thoth project infrastructure.

## 📁 File Structure

```
infra/
├── main.tf           # Provider configuration and API enablement
├── bootstrap.tf      # State bucket infrastructure (special handling)
├── storage.tf        # Application storage bucket
├── cloud_run.tf      # Cloud Run service deployment
├── secrets.tf        # Secret Manager configuration
├── scheduler.tf      # Cloud Scheduler jobs
├── variables.tf      # Input variables
└── README.md         # This file
```

## 🚀 Quick Start

### First Time Setup (Bootstrap)

Before using Terraform, you must create the state bucket:

```bash
# From project root
./scripts/bootstrap_terraform.sh
```

This creates the GCS bucket that will store Terraform state. This is a one-time operation.

### Regular Usage

After bootstrap:

```bash
cd infra

# Initialize Terraform (uses GCS backend)
terraform init

# Plan changes
terraform plan -var="project_id=thoth-483015" -var="region=us-central1"

# Apply changes
terraform apply -var="project_id=thoth-483015" -var="region=us-central1"
```

## 📋 Resources Managed

### Core Infrastructure
- **GCS Buckets**: Application storage and Terraform state
- **Service Accounts**: Cloud Run service account with IAM roles
- **Cloud Run**: Containerized MCP server deployment

### Security & Secrets
- **Secret Manager**: GitLab credentials and service account keys
- **IAM Policies**: Least-privilege access controls

### Automation
- **Cloud Scheduler**: Daily full sync and hourly incremental sync jobs

## 🔐 Terraform State

State is stored in GCS for:
- ✅ Persistence across runs
- ✅ Team collaboration
- ✅ State locking
- ✅ Version history

**State Bucket**: `gs://thoth-terraform-state/terraform/state`

See [../docs/TERRAFORM_STATE.md](../docs/TERRAFORM_STATE.md) for details.

## 🔧 Variables

Key variables (see [variables.tf](variables.tf)):

| Variable | Default | Description |
|----------|---------|-------------|
| `project_id` | `thoth-483015` | GCP project ID |
| `region` | `us-central1` | GCP region |
| `bucket_name` | `thoth-storage-bucket` | Application storage bucket |
| `container_image` | `gcr.io/thoth-483015/thoth-mcp:latest` | Cloud Run container image |
| `gitlab_token` | `""` | GitLab access token (set via Secret Manager) |
| `gitlab_url` | `""` | GitLab base URL (set via Secret Manager) |

## 📝 Common Commands

```bash
# Initialize/update providers
terraform init

# Format code
terraform fmt -recursive

# Validate configuration
terraform validate

# Plan changes
terraform plan

# Apply changes
terraform apply

# Show current state
terraform state list

# Show specific resource
terraform state show google_storage_bucket.thoth_bucket

# Import existing resource
terraform import google_storage_bucket.thoth_bucket thoth-storage-bucket

# Destroy all resources (dangerous!)
terraform destroy
```

## 🔄 CI/CD Integration

GitHub Actions automatically:
1. ✅ Bootstraps state bucket if needed
2. ✅ Imports existing resources
3. ✅ Plans changes on every push
4. ✅ Applies changes on main branch
5. ✅ Validates infrastructure weekly

See [../.github/workflows/infra-deploy.yml](../.github/workflows/infra-deploy.yml)

## 🐛 Troubleshooting

### "Bucket already exists" Error

Resources already exist in GCP but not in Terraform state. Import them:

```bash
terraform import google_storage_bucket.thoth_bucket thoth-storage-bucket
```

GitHub Actions does this automatically.

### "State bucket not found"

Run the bootstrap script:

```bash
./scripts/bootstrap_terraform.sh
```

### "Permission denied"

Authenticate with GCP:

```bash
gcloud auth application-default login
```

### State Lock Error

Another Terraform process is running. Wait or force unlock (dangerous):

```bash
terraform force-unlock <lock-id>
```

## 📚 Documentation

- [Terraform State Management](../docs/TERRAFORM_STATE.md)
- [Secrets Setup](../docs/SECRETS_SETUP.md)
- [Scheduler Setup](../docs/SCHEDULER_SETUP.md)
- [GitHub Actions](../docs/GITHUB_ACTIONS.md)
- [Cloud Run Deployment](../docs/CLOUD_RUN_DEPLOYMENT.md)

## ⚠️ Important Notes

1. **State Bucket**: Has `prevent_destroy = true` - never delete manually
2. **Secrets**: Secret values must be set manually after creation (see SECRETS_SETUP.md)
3. **Bootstrap**: Must be run once before regular Terraform usage
4. **Backend**: Cannot be changed without state migration
5. **IAM**: Service account permissions are critical - test after changes

## 🤝 Contributing

When adding new infrastructure:

1. Add resource in appropriate `.tf` file
2. Add variables to `variables.tf` if needed
3. Add outputs if needed
4. Update this README
5. Update relevant documentation
6. Test locally before pushing
7. Review `terraform plan` output carefully

## 🔗 External References

- [Terraform GCP Provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [GCS Backend](https://www.terraform.io/docs/backends/types/gcs.html)
- [Cloud Run](https://cloud.google.com/run/docs)
- [Secret Manager](https://cloud.google.com/secret-manager/docs)
- [Cloud Scheduler](https://cloud.google.com/scheduler/docs)
