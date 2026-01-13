# GitHub Actions CI/CD Setup

This document describes the automated deployment workflows for Thoth.

## Workflows Overview

### 1. Infrastructure & Cloud Run Deploy
**File**: `.github/workflows/infra-deploy.yml`

Automatically provisions GCP infrastructure and deploys the application to Cloud Run.

**Triggers**:
- Push to `main` branch when these paths change:
  - `infra/**` (Terraform files)
  - `thoth/**` (Application code)
  - `Dockerfile`
  - Workflow file itself
- Manual workflow dispatch with optional flags

**Jobs**:

#### Job 1: Provision Infrastructure
- Sets up Terraform
- Authenticates to GCP
- Validates and plans infrastructure changes
- Applies changes on main branch
- Outputs bucket name for Cloud Run deployment

#### Job 2: Deploy to Cloud Run
- Builds Docker image with caching
- Pushes to Google Container Registry
- Deploys to Cloud Run with proper configuration
- Verifies deployment with health check
- Outputs service URL and recent logs

**Environment Variables**:
```yaml
GCP_PROJECT_ID: thoth-483015
GCP_REGION: us-central1
SERVICE_NAME: thoth-mcp-server
IMAGE_NAME: thoth-mcp
```

**Manual Trigger Options**:
- `skip_terraform`: Skip infrastructure provisioning
- `skip_cloud_run`: Skip Cloud Run deployment

### 2. Continuous Delivery (CD)
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

### GCP_SA_KEY
Service account key JSON with the following roles:
- `roles/run.admin` - Deploy to Cloud Run
- `roles/storage.admin` - Manage GCS buckets
- `roles/iam.serviceAccountUser` - Use service accounts
- `roles/artifactregistry.writer` - Push Docker images

**Setup**:
```bash
# 1. Create service account
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions Deployment" \
  --project=thoth-483015

# 2. Grant roles
for role in run.admin storage.admin iam.serviceAccountUser artifactregistry.writer; do
  gcloud projects add-iam-policy-binding thoth-483015 \
    --member="serviceAccount:github-actions@thoth-483015.iam.gserviceaccount.com" \
    --role="roles/${role}"
done

# 3. Create key
gcloud iam service-accounts keys create github-actions-key.json \
  --iam-account=github-actions@thoth-483015.iam.gserviceaccount.com

# 4. Add to GitHub Secrets
# Copy contents of github-actions-key.json to GCP_SA_KEY secret
cat github-actions-key.json | pbcopy  # macOS
cat github-actions-key.json | xclip -selection clipboard  # Linux

# 5. Delete local key file for security
rm github-actions-key.json
```

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

### Release Deployment

When publishing a new release:
1. Create and push a git tag: `git tag v1.0.0 && git push origin v1.0.0`
2. Create GitHub release from the tag
3. CD workflow automatically:
   - Builds and publishes to PyPI
   - Deploys infrastructure and Cloud Run

## Monitoring Deployments

### GitHub Actions UI
- View real-time workflow progress
- Check deployment summary with service URL
- Review health check status
- See recent logs

### GCP Console
- **Cloud Run**: [console.cloud.google.com/run](https://console.cloud.google.com/run)
- **Cloud Storage**: [console.cloud.google.com/storage](https://console.cloud.google.com/storage)
- **Logs**: [console.cloud.google.com/logs](https://console.cloud.google.com/logs)

### Command Line
```bash
# Check Cloud Run service
gcloud run services describe thoth-mcp-server --region=us-central1

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
6. **Keep secrets updated**: Rotate service account keys periodically
7. **Test in dev first**: Use manual workflow triggers to test changes before merging

## Troubleshooting

### Workflow Fails at Authentication
- Verify `GCP_SA_KEY` secret is correctly set
- Check service account has required permissions
- Ensure service account key is valid (keys expire after 10 years)

### Docker Build Fails
- Check Dockerfile syntax
- Verify all dependencies are available
- Review build logs for specific errors
- Test build locally: `docker build -t test .`

### Terraform Apply Fails
- Review Terraform plan output
- Check for state conflicts
- Verify GCP APIs are enabled
- Ensure no manual changes were made to resources

### Cloud Run Deployment Fails
- Verify image was pushed successfully
- Check Cloud Run quotas in your project
- Review service account permissions
- Check for port conflicts or configuration errors

### Health Check Fails
- Service may still be starting (wait 30 seconds)
- Check application logs for startup errors
- Verify health endpoint is working: `/health`
- Check environment variables are set correctly

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
  --member="serviceAccount:thoth-mcp-sa@thoth-483015.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Update workflow to use secret
--set-secrets="MY_SECRET=my-secret:latest"
```

## Related Documentation

- [Cloud Run Deployment Guide](CLOUD_RUN_DEPLOYMENT.md)
- [Environment Configuration](ENVIRONMENT_CONFIG.md)
- [GitHub Actions Documentation](https://docs.github.com/actions)
- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Terraform GCP Provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
