# Terraform Cloud Setup Guide

This guide walks through the complete setup for using Terraform Cloud with your Thoth MCP infrastructure on GCP.

## Prerequisites

- Terraform Cloud account (free tier works)
- GCP project with billing enabled
- GitHub repository with admin access
- `gcloud` CLI installed and configured

## 1. Terraform Cloud Setup

### Create Organization & Workspace

1. Go to [Terraform Cloud](https://app.terraform.io)
2. Create or use existing organization: `TheWinterShadow`
3. Create workspace: `thoth-mcp-gcp`
4. Choose "CLI-driven workflow"

### Configure Workspace Settings

1. In your workspace, go to **Settings > General**
2. Set **Execution Mode**: Remote
3. Set **Terraform Version**: 1.5.7
4. Set **Working Directory**: `terraform`

## 2. GCP Service Account Setup

### Create Service Account and Key

```bash
# Create service account
gcloud iam service-accounts create terraform-thoth \
  --display-name="Terraform Cloud Thoth Deployment" \
  --project=thoth-dev-485501

# Grant necessary permissions
gcloud projects add-iam-policy-binding thoth-dev-485501 \
  --member="serviceAccount:terraform-thoth@thoth-dev-485501.iam.gserviceaccount.com" \
  --role="roles/editor"

# Create and download key
gcloud iam service-accounts keys create ./auth/terraform-key.json \
  --iam-account=terraform-thoth@thoth-dev-485501.iam.gserviceaccount.com
```

### Minify JSON for Terraform Cloud

```bash
# Create single-line JSON (required for Terraform Cloud)
cat ./auth/terraform-key.json | jq -c .
```

## 3. Configure Terraform Cloud Variables

### Environment Variables (Sensitive)

Go to your workspace: https://app.terraform.io/app/TheWinterShadow/thoth-mcp-gcp/settings/variables

Add the following **Environment Variables**:

| Key | Value | Sensitive |
|-----|-------|-----------|
| `GOOGLE_CREDENTIALS` | Minified JSON from step 2 | ✓ |

### Terraform Variables

Add these **Terraform Variables** in the same settings page:

| Key | Value | Sensitive | Description |
|-----|-------|-----------|-------------|
| `project_id` | `thoth-dev-485501` | | GCP Project ID |
| `region` | `us-central1` | | GCP Region |
| `environment` | `dev` | | Environment name |
| `container_image` | `gcr.io/thoth-dev-485501/thoth-mcp:latest` | | Container image |
| `gitlab_token` | Leave empty or set your token | ✓ | GitLab PAT (optional) |
| `gitlab_url` | `https://gitlab.com` | | GitLab URL |

**Note**: These can also be set in [environments/dev.tfvars](../terraform/environments/dev.tfvars) file.

## 4. GitHub Actions Setup

### Add GitHub Secrets

Go to your repository settings: **Settings > Secrets and variables > Actions**

Add these **Repository Secrets**:

| Name | Value | Description |
|------|-------|-------------|
| `TF_API_TOKEN` | Your Terraform Cloud API token | Generate from Terraform Cloud |
| `GOOGLE_APPLICATION_CREDENTIALS` | Same as `GOOGLE_CREDENTIALS` above | For GCP authentication |

### Generate Terraform Cloud API Token

1. Go to Terraform Cloud: https://app.terraform.io/app/settings/tokens
2. Click **Create an API token**
3. Give it a description (e.g., "GitHub Actions - Thoth")
4. Copy the token immediately (you won't see it again)
5. Add to GitHub Secrets as `TF_API_TOKEN`

## 5. Local Development Setup

### Authenticate with Terraform Cloud

```bash
terraform login
```

This will open a browser window to generate a token. Paste the token when prompted.

### Initialize Terraform

```bash
cd terraform
terraform init
```

### Run Plan

```bash
terraform plan -var-file=environments/dev.tfvars
```

### Apply Changes

```bash
terraform apply -var-file=environments/dev.tfvars
```

## 6. Verify Setup

### Check Terraform Cloud

1. Go to your workspace: https://app.terraform.io/app/TheWinterShadow/thoth-mcp-gcp
2. You should see successful runs after applying

### Test GitHub Actions

```bash
# Trigger infrastructure deployment
git add .
git commit -m "chore: migrate to Terraform Cloud"
git push origin main
```

Check the Actions tab in your GitHub repository.

## 7. Troubleshooting

### Error: "No credentials loaded"

**Solution**: Ensure `GOOGLE_CREDENTIALS` environment variable is set in Terraform Cloud workspace with the minified JSON.

### Error: "Value cannot contain newlines"

**Solution**: Make sure you used `jq -c .` to minify the JSON to a single line.

### Error: "error unmarshaling credentials"

**Solution**: The variable expects JSON, not base64. Use the raw minified JSON output.

### GitHub Actions: "terraform init failed"

**Solution**: Verify `TF_API_TOKEN` secret is set correctly in GitHub repository settings.

### "Invalid credentials" during apply

**Solution**: Check that the service account has the `roles/editor` role on the project.

## 8. State Management

### View State

```bash
terraform state list
terraform state show <resource_name>
```

### Remote State in Terraform Cloud

All state is now stored in Terraform Cloud. No local state files or GCS buckets are needed.

To view state in the UI:
1. Go to workspace: https://app.terraform.io/app/TheWinterShadow/thoth-mcp-gcp
2. Click **States** tab

## 9. Environment-Specific Configuration

### Development

```bash
terraform plan -var-file=environments/dev.tfvars
terraform apply -var-file=environments/dev.tfvars
```

### Production (Future)

Create `environments/prod.tfvars` with production values and use:

```bash
terraform workspace select prod
terraform plan -var-file=environments/prod.tfvars
```

## 10. Security Best Practices

- ✅ Service account credentials stored only in Terraform Cloud
- ✅ Sensitive variables marked as sensitive
- ✅ Key files excluded from git via `.gitignore`
- ✅ GitHub Actions uses secrets, not hardcoded values
- ✅ State stored remotely in Terraform Cloud (encrypted)

## Resources

- [Terraform Cloud Documentation](https://developer.hashicorp.com/terraform/cloud-docs)
- [GitHub Actions Terraform Setup](https://github.com/hashicorp/setup-terraform)
- [GCP Service Account Best Practices](https://cloud.google.com/iam/docs/best-practices-service-accounts)
