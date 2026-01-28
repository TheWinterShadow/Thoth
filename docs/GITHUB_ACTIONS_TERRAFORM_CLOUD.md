# GitHub Actions Setup for Terraform Cloud

Quick reference for setting up GitHub Actions to work with Terraform Cloud.

## Required GitHub Secrets

Go to: **Repository Settings > Secrets and variables > Actions**

### 1. TF_API_TOKEN

**Description**: Terraform Cloud API token for authentication

**How to generate**:
```bash
# Visit Terraform Cloud
open https://app.terraform.io/app/settings/tokens

# Or use CLI
terraform login
# Then extract from ~/.terraform.d/credentials.tfrc.json
```

**Value**: Your Terraform Cloud user API token (starts with `TF...`)

### 2. GOOGLE_APPLICATION_CREDENTIALS

**Description**: GCP service account credentials for Cloud Run deployment

**How to generate**:
```bash
# Minify the existing service account key
cat ./auth/terraform-key.json | jq -c .
```

**Value**: Single-line JSON of the service account key

## Workflow Configuration

The workflow is configured to:

1. **Build & Push Docker Image** → `gcr.io/thoth-dev-485501/thoth-mcp`
2. **Run Terraform** via Terraform Cloud
   - Uses remote execution in Terraform Cloud
   - State managed remotely
   - Plan and apply via GitHub Actions
3. **Deploy to Cloud Run** using the built image

## Environment Variables in Workflow

These are set in [`.github/workflows/infra-deploy.yml`](../.github/workflows/infra-deploy.yml):

```yaml
env:
  TF_WORKING_DIR: ./terraform
  GCP_PROJECT_ID: thoth-dev-485501
  GCP_REGION: us-central1
  SERVICE_NAME: thoth-mcp-server
  IMAGE_NAME: thoth-mcp
  TF_CLOUD_ORGANIZATION: TheWinterShadow
  TF_WORKSPACE: thoth-mcp-gcp
```

## Terraform Cloud Integration

The workflow uses the official HashiCorp Terraform GitHub Action:

```yaml
- name: Setup Terraform
  uses: hashicorp/setup-terraform@v3
  with:
    cli_config_credentials_token: ${{ secrets.TF_API_TOKEN }}
    terraform_version: 1.5.7
```

This automatically:
- Installs Terraform CLI
- Configures authentication with Terraform Cloud
- Enables remote operations

## Triggering Deployments

### Automatic (Push to main)

```bash
git add .
git commit -m "feat: your changes"
git push origin main
```

### Manual (Workflow Dispatch)

1. Go to **Actions** tab in GitHub
2. Select **Infrastructure & Cloud Run Deploy** workflow
3. Click **Run workflow**
4. Optionally skip Terraform or Cloud Run steps

## Workflow Jobs

### 1. build_image

- Authenticates to GCP
- Builds Docker image with caching
- Pushes to GCR with SHA and latest tags

### 2. terraform

- Sets up Terraform with Cloud authentication
- Initializes Terraform (connects to Terraform Cloud)
- Validates configuration
- Runs plan (visible in Terraform Cloud UI)
- Applies changes (on main branch only)

### 3. deploy_cloud_run

- Deploys the built image to Cloud Run
- Configures environment variables
- Verifies deployment health
- Checks logs and infrastructure components

## Viewing Runs

### GitHub Actions

View workflow runs: https://github.com/TheWinterShadow/Thoth/actions

### Terraform Cloud

View Terraform runs: https://app.terraform.io/app/TheWinterShadow/thoth-mcp-gcp

## Debugging

### Check GitHub Actions Logs

1. Go to **Actions** tab
2. Click on the failed run
3. Expand the failed step to see logs

### Check Terraform Cloud Logs

1. Go to workspace runs
2. Click on the run
3. View plan/apply output
4. Check for credential or permission errors

### Common Issues

**"Error: Invalid credentials"**
- Check `TF_API_TOKEN` is set correctly in GitHub Secrets
- Ensure token hasn't expired

**"Error: No credentials loaded"**
- Check `GOOGLE_CREDENTIALS` in Terraform Cloud workspace
- Verify it's set as an Environment Variable (not Terraform Variable)

**"Working directory not found"**
- Ensure `TF_WORKING_DIR: ./terraform` matches your directory structure

## Security Notes

- Never commit API tokens or service account keys
- All secrets are masked in GitHub Actions logs
- Terraform Cloud encrypts state at rest
- Use separate service accounts for CI/CD vs. production

## Next Steps

After setup:

1. Test with a small change to trigger the workflow
2. Verify the run completes in both GitHub Actions and Terraform Cloud
3. Check that Cloud Run service is deployed
4. Monitor for any errors or warnings

## Related Documentation

- [Terraform Cloud Setup](./TERRAFORM_CLOUD_SETUP.md) - Full Terraform Cloud configuration
- [GitHub Actions CI/CD](./GITHUB_ACTIONS.md) - General GitHub Actions documentation
