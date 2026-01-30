# GitHub Actions CI/CD Setup

This document describes the automated deployment workflows for Thoth, including support for Cloud Scheduler and Secret Manager.

## Workflows Overview

### 1. CI (Continuous Integration)
**File**: `.github/workflows/ci.yml`

Runs linting, type checking, and tests across multiple Python versions.

**Triggers**: Push to main, Pull Requests

**Jobs**:
- **Lint & Format**: Runs ruff and black checks
- **Type Check**: Runs mypy for type validation
- **Test**: Runs pytest across Python 3.10-3.13 with environment variables for secrets testing
- **Build**: Creates distribution packages

**Environment Variables for Testing**:
```yaml
GITLAB_TOKEN: "test-token-for-ci"
GITLAB_BASE_URL: "https://gitlab.com"
GCP_PROJECT_ID: "test-project"
```

### 2. Infrastructure & Cloud Run Deploy
**File**: `.github/workflows/infra-deploy.yml`

Automatically provisions GCP infrastructure including Secret Manager and Cloud Scheduler, then deploys the application to Cloud Run.

**Triggers**:
- Push to `main` branch when these paths change:
  - `infra/**` (Terraform files)
  - `thoth/**` (Application code)
  - `Dockerfile`
  - Workflow file itself
- Manual workflow dispatch with optional flags

**Jobs**:

#### Job 1: Provision Infrastructure
- Creates Terraform state bucket if not exists (persistent storage)
- Imports existing resources to prevent conflicts
- Sets up Terraform with GCS backend
- Authenticates to GCP
- Validates and plans infrastructure changes (with secret variables)
- Applies changes on main branch
- Creates Secret Manager secrets (gitlab-token, gitlab-url, google-application-credentials)
- Sets up Cloud Scheduler jobs (daily and hourly sync)
- Outputs bucket name and post-deployment instructions for secrets

**State Management**:
- Terraform state stored in `gs://thoth-terraform-state/terraform/state`
- Automatic resource import prevents "already exists" errors
- See [TERRAFORM_STATE.md](TERRAFORM_STATE.md) for details

#### Job 2: Deploy to Cloud Run
- Builds Docker image with caching
- Pushes to Google Container Registry
- Deploys with secret environment variables from Secret Manager
- Verifies health endpoint
- Validates Secret Manager and Cloud Scheduler configuration
- Outputs service URL and recent logs

**Environment Variables**:
```yaml
GCP_PROJECT_ID: thoth-dev-485501
GCP_REGION: us-central1
SERVICE_NAME: thoth-mcp-server
IMAGE_NAME: thoth-mcp
```

**Manual Trigger Options**:
- `skip_terraform`: Skip infrastructure provisioning
- `skip_cloud_run`: Skip Cloud Run deployment

### 3. Secrets & Scheduler Validation
**File**: `.github/workflows/validate-infrastructure.yml`

Validates Secret Manager and Cloud Scheduler configuration.

**Triggers**:
- Manual workflow dispatch
- Weekly schedule (Mondays 9 AM UTC)

**Jobs**:

#### Job 1: Validate Secrets
- Checks all required secrets exist (gitlab-token, gitlab-url, google-application-credentials)
- Verifies IAM permissions for service account
- Tests secret access without revealing values

#### Job 2: Validate Scheduler
- Checks scheduler jobs exist (daily-sync, hourly-incremental-sync)
- Verifies job configuration and schedules
- Validates scheduler service account permissions

#### Job 3: Integration Test
- Tests Secret Manager API access
- Verifies end-to-end functionality
- Provides comprehensive validation summary

**Manual Trigger Options**:
- `test_secrets`: Test Secret Manager integration (default: true)
- `test_scheduler`: Test Cloud Scheduler jobs (default: true)

### 4. Continuous Delivery (CD)
**File**: `.github/workflows/cd.yml`

Publishes package to PyPI and optionally deploys infrastructure on releases.

**Triggers**:
- GitHub release published
- Manual workflow dispatch

**Jobs**:

#### Job 1: Publish to PyPI
- Builds Python package with optimized PyTorch
- Verifies build artifacts
- Publishes to PyPI (when uncommented)

#### Job 2: Deploy Infrastructure
- Triggers the infrastructure deployment workflow
- Runs after successful PyPI publish
- Can be disabled with manual trigger input

### 3. Continuous Integration (CI)
**File**: `.github/workflows/ci.yml`

Runs tests and quality checks on all pull requests.

### 4. Documentation Build
**File**: `.github/workflows/docs.yml`

Builds and deploys Sphinx documentation.

### 5. CodeQL Security Scanning
**File**: `.github/workflows/codeql.yml`

Performs static security analysis.

## Required Secrets

Configure these in: **Repository Settings → Secrets and variables → Actions**

### GOOGLE_APPLICATION_CREDENTIALS
Service account key JSON with the following roles:
- `roles/run.admin` - Deploy to Cloud Run
- `roles/storage.admin` - Manage GCS buckets
- `roles/iam.serviceAccountUser` - Use service accounts
- `roles/artifactregistry.writer` - Push Docker images
- `roles/secretmanager.admin` - Manage secrets
- `roles/cloudscheduler.admin` - Manage scheduler jobs

**Setup**:
```bash
# 1. Create service account
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions Deployment" \
  --project=thoth-dev-485501

# 2. Grant roles
for role in run.admin storage.admin iam.serviceAccountUser artifactregistry.writer secretmanager.admin cloudscheduler.admin; do
  gcloud projects add-iam-policy-binding thoth-dev-485501 \
    --member="serviceAccount:github-actions@thoth-dev-485501.iam.gserviceaccount.com" \
    --role="roles/${role}"
done

# 3. Create key
gcloud iam service-accounts keys create github-actions-key.json \
  --iam-account=github-actions@thoth-dev-485501.iam.gserviceaccount.com

# 4. Add to GitHub Secrets
# Copy contents of github-actions-key.json to GOOGLE_APPLICATION_CREDENTIALS secret
cat github-actions-key.json | pbcopy  # macOS
cat github-actions-key.json | xclip -selection clipboard  # Linux

# 5. Delete local key file for security
rm github-actions-key.json
```

### Required Secret Manager Secrets
After infrastructure is deployed, you must populate Secret Manager with:

- **gitlab-token**: GitLab personal access token with `read_api` scope
- **gitlab-url**: GitLab base URL (e.g., `https://gitlab.com`)
- **google-application-credentials**: Service account key JSON for Cloud Run

See [SECRETS_SETUP.md](SECRETS_SETUP.md) for detailed setup instructions.

## Usage

### Automatic Deployment on Push

Any push to `main` branch with changes to infrastructure or application code will automatically:
1. Provision/update infrastructure via Terraform
2. Build and deploy Docker image to Cloud Run
3. Verify deployment health

### Manual Deployment

**Via GitHub UI**:
1. Go to **Actions** tab
2. Select **Infrastructure & Cloud Run Deploy**
3. Click **Run workflow**
4. Choose branch (usually `main`)
5. Optionally toggle skip flags
6. Click **Run workflow**

**Via GitHub CLI**:
```bash
# Full deployment
gh workflow run infra-deploy.yml

# Skip Terraform
gh workflow run infra-deploy.yml -f skip_terraform=true

# Skip Cloud Run
gh workflow run infra-deploy.yml -f skip_cloud_run=true
```

### Post-Deployment Secret Setup

After first deployment, populate secrets:
```bash
# See SECRETS_SETUP.md for detailed instructions
./scripts/setup_secrets_and_scheduler.sh
```

### Validating Infrastructure

Run validation workflow to check Secret Manager and Cloud Scheduler:
```bash
# Via GitHub CLI
gh workflow run validate-infrastructure.yml

# Or via GitHub UI: Actions → Secrets & Scheduler Validation → Run workflow
```

## Troubleshooting

### Secret Manager Issues
**Problem**: Tests fail with "Secret not found" errors

**Solution**:
1. Verify secrets exist: `gcloud secrets list --project=thoth-dev-485501`
2. Check IAM permissions: `gcloud secrets get-iam-policy gitlab-token --project=thoth-dev-485501`
3. Ensure service account has `secretmanager.secretAccessor` role
4. Run validation workflow to diagnose issues

**Problem**: Local tests fail without GCP credentials

**Solution**: Tests automatically fallback to environment variables:
```bash
export GITLAB_TOKEN="your-token"
export GITLAB_BASE_URL="https://gitlab.com"
pytest tests/utils/test_secrets.py
```

### Cloud Scheduler Issues
**Problem**: Scheduled jobs not triggering

**Solution**:
1. Check job status: `gcloud scheduler jobs list --project=thoth-dev-485501`
2. Verify job configuration: `gcloud scheduler jobs describe thoth-daily-sync --location=us-central1`
3. Check service account permissions: Scheduler SA needs `roles/run.invoker`
4. View job history: `gcloud scheduler jobs describe thoth-daily-sync --location=us-central1 | grep -A5 status`
5. Run validation workflow for comprehensive checks

**Problem**: Manual trigger fails

**Solution**:
```bash
# Test scheduler job manually
gcloud scheduler jobs run thoth-daily-sync --location=us-central1

# Check Cloud Run logs for errors
gcloud run services logs read thoth-mcp-server --region=us-central1 --limit=50
```

## Monitoring Deployments

### GitHub Actions UI
- View real-time workflow progress
- Check deployment summary with service URL and Secret Manager setup instructions
- Review health check status
- Validate Secret Manager and Cloud Scheduler configuration
- See recent logs

### GCP Console
- **Cloud Run**: [console.cloud.google.com/run](https://console.cloud.google.com/run)
- **Cloud Storage**: [console.cloud.google.com/storage](https://console.cloud.google.com/storage)
- **Secret Manager**: [console.cloud.google.com/security/secret-manager](https://console.cloud.google.com/security/secret-manager)
- **Cloud Scheduler**: [console.cloud.google.com/cloudscheduler](https://console.cloud.google.com/cloudscheduler)
- **Logs**: [console.cloud.google.com/logs](https://console.cloud.google.com/logs)

### Command Line
```bash
# Check Cloud Run service
gcloud run services describe thoth-mcp-server --region=us-central1

# List secrets
gcloud secrets list --project=thoth-dev-485501

# Check scheduler jobs
gcloud scheduler jobs list --project=thoth-dev-485501 --location=us-central1

# View recent logs
gcloud logging read "resource.type=cloud_run_revision AND \
  resource.labels.service_name=thoth-mcp-server" --limit=50

# Test health endpoint
curl https://thoth-mcp-server-<hash>-uc.a.run.app/health
```

## Deployment Best Practices

1. **Always test locally first**: Run `docker build` and test container before pushing
2. **Use semantic versioning**: Tag releases with proper version numbers
3. **Review Terraform plans**: Check the plan output in workflow summary before applying
4. **Monitor after deployment**: Check logs and health status after each deployment
5. **Rollback if needed**: Use Cloud Run revision management for quick rollbacks
6. **Keep secrets updated**: Rotate service account keys and GitLab tokens periodically
7. **Test in dev first**: Use manual workflow triggers to test changes before merging
8. **Validate infrastructure**: Run validation workflow weekly to catch configuration drift
9. **Secure secrets**: Never commit secrets to version control; always use Secret Manager

### Workflow Fails at Authentication
**Problem**: Workflow fails with "authentication failed" or "permission denied"

**Solution**:
- Verify `GOOGLE_APPLICATION_CREDENTIALS` secret is correctly set
- Check service account has required permissions (run.admin, secretmanager.admin, cloudscheduler.admin)
- Ensure service account key is valid (keys expire after 10 years)
- Verify GCP APIs are enabled: `gcloud services list --enabled`

### Docker Build Fails
- Check Dockerfile syntax
- Verify all dependencies are available
- Review build logs for specific errors
- Test build locally: `docker build -t test .`

### Terraform Apply Fails
**Problem**: Terraform operations fail with state or resource conflicts

**Solution**:
- Review Terraform plan output in workflow summary
- Check for state conflicts: `terraform state list`
- Verify GCP APIs are enabled: Secret Manager API, Cloud Scheduler API, Cloud Run API
- Ensure no manual changes were made to resources
- Check Terraform variables are set: `TF_VAR_gitlab_token`, `TF_VAR_gitlab_url`

### Cloud Run Deployment Fails
- Verify image was pushed successfully to Container Registry
- Check Cloud Run quotas in your project
- Review service account permissions
- Ensure secret environment variables are configured
- Check for port conflicts or configuration errors

### Health Check Fails
- Service may still be starting (wait 30 seconds)
- Check application logs for startup errors
- Verify health endpoint is working: `/health`
- Check environment variables are set correctly
- Ensure Secret Manager secrets are populated

### CI Tests Fail with Secret Errors
**Problem**: Tests fail with "Secret not found" or "google.cloud.secretmanager not found"

**Solution**: CI tests use environment variable fallback:
```yaml
# tests/utils/test_secrets.py automatically handles missing library
# Ensure CI workflow has these environment variables:
GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN || 'test-token' }}
GITLAB_BASE_URL: 'https://gitlab.com'
```

## Advanced Configuration

### Custom Deployment Regions
Edit workflow file and change `GCP_REGION` environment variable:
```yaml
env:
  GCP_REGION: europe-west1  # Change region
```

### Modify Resource Limits
Edit Cloud Run deployment command in workflow:
```yaml
--memory 4Gi \      # Increase memory
--cpu 4 \           # Increase CPU
--max-instances 20  # Increase max instances
```

### Add Environment Variables
Edit Cloud Run deployment command:
```yaml
--set-env-vars "KEY1=value1,KEY2=value2"
```

### Enable Secrets
```bash
# Create secret in Secret Manager
gcloud secrets create my-secret --data-file=secret.txt

# Grant access to Cloud Run service account
gcloud secrets add-iam-policy-binding my-secret \
  --member="serviceAccount:thoth-mcp-sa@thoth-dev-485501.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Update workflow to use secret
--set-secrets="MY_SECRET=my-secret:latest"
```

## Related Documentation

- [Secrets Setup Guide](SECRETS_SETUP.md) - Detailed Secret Manager configuration
- [Scheduler Setup Guide](SCHEDULER_SETUP.md) - Cloud Scheduler configuration and management
- [Cloud Run Deployment Guide](CLOUD_RUN_DEPLOYMENT.md) - Cloud Run deployment details
- [Environment Configuration](ENVIRONMENT_CONFIG.md) - Environment variable configuration
- [GitHub Actions Documentation](https://docs.github.com/actions) - GitHub Actions reference
- [Cloud Run Documentation](https://cloud.google.com/run/docs) - Google Cloud Run reference
- [Terraform GCP Provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs) - Terraform Google provider
