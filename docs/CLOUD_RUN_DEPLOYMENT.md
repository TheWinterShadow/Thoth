# Cloud Run Deployment Guide

This guide covers deploying the Thoth MCP Server to Google Cloud Run.

## Prerequisites

1. **Google Cloud Platform Account**
   - Active GCP project
   - Billing enabled
   - Required APIs enabled (done automatically by Terraform)

2. **Local Tools**
   ```bash
   # Google Cloud SDK
   curl https://sdk.cloud.google.com | bash
   exec -l $SHELL
   gcloud init
   
   # Docker
   # Install from https://docs.docker.com/get-docker/
   
   # Terraform (optional but recommended)
   # Install from https://www.terraform.io/downloads
   ```

3. **Authentication**
   ```bash
   # Authenticate with GCP
   gcloud auth login
   
   # Set default project
   gcloud config set project thoth-dev-485501
   
   # Enable Docker authentication
   gcloud auth configure-docker
   ```

## Deployment Methods

### Method 1: Automated Deployment Script (Recommended)

The deployment script handles the entire process:

```bash
# Run deployment script
./scripts/deploy_cloud_run.sh

# Or with custom settings
GCP_PROJECT_ID=your-project-id \
GCP_REGION=us-central1 \
IMAGE_TAG=v1.0.0 \
./scripts/deploy_cloud_run.sh
```

The script will:
1. Check prerequisites
2. Build Docker image
3. Push to Google Container Registry
4. Deploy infrastructure (Terraform) or service (gcloud)
5. Verify deployment
6. Show service URL and logs

### Method 2: Terraform (Infrastructure as Code)

```bash
# Navigate to infrastructure directory
cd infra

# Initialize Terraform
terraform init

# Preview changes
terraform plan \
  -var="project_id=thoth-dev-485501" \
  -var="region=us-central1" \
  -var="container_image=gcr.io/thoth-dev-485501/thoth-mcp:latest"

# Apply configuration
terraform apply

# Get outputs
terraform output service_url
```

### Method 3: Manual gcloud CLI

```bash
# Build and push image
docker build -t thoth-mcp:latest .
docker tag thoth-mcp:latest gcr.io/thoth-dev-485501/thoth-mcp:latest
docker push gcr.io/thoth-dev-485501/thoth-mcp:latest

# Deploy to Cloud Run
gcloud run deploy thoth-mcp-server \
  --image=gcr.io/thoth-dev-485501/thoth-mcp:latest \
  --platform=managed \
  --region=us-central1 \
  --allow-unauthenticated \
  --memory=4Gi \
  --cpu=2 \
  --timeout=300 \
  --min-instances=0 \
  --max-instances=3 \
  --set-env-vars="PYTHONUNBUFFERED=1,GCP_PROJECT_ID=thoth-dev-485501,GCS_BUCKET_NAME=thoth-storage-bucket,LOG_LEVEL=INFO"
```

## Configuration

### Environment Variables

See [ENVIRONMENT_CONFIG.md](ENVIRONMENT_CONFIG.md) for complete list.

Key variables for Cloud Run:
- `GCP_PROJECT_ID` - Your GCP project ID
- `GCS_BUCKET_NAME` - Storage bucket name
- `CHROMA_PERSIST_DIRECTORY` - Vector DB path (default: `/app/data/chroma_db`)
- `LOG_LEVEL` - Logging verbosity (INFO, DEBUG, etc.)

### Resource Limits

Configured in `infra/cloud_run.tf`:
- **Memory**: 4 GiB (adjustable based on vector DB size)
- **CPU**: 2 vCPUs
- **Timeout**: 300 seconds
- **Scaling**: 0-3 instances (auto-scales to zero when idle)

### Storage

Vector database is persisted to Google Cloud Storage:
1. Local ChromaDB writes to `/app/data/chroma_db`
2. Periodically synced to GCS bucket
3. Restored from GCS on container restart

## Verification

### Health Check

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe thoth-mcp-server \
  --region=us-central1 \
  --format="value(status.url)")

# Check health endpoint
curl ${SERVICE_URL}/health
```

### View Logs

```bash
# Recent logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=thoth-mcp-server" \
  --limit=50 \
  --format="table(timestamp,severity,textPayload)"

# Tail logs in real-time
gcloud alpha logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=thoth-mcp-server"

# Filter by severity
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=thoth-mcp-server AND severity>=ERROR" \
  --limit=50
```

### Test the Service

```bash
# Test MCP server (if using stdio transport)
echo '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}' | gcloud run services proxy thoth-mcp-server --region=us-central1

# Check vector store
gcloud run services execute thoth-mcp-server \
  --region=us-central1 \
  --command="python -c 'from thoth.ingestion.vector_store import VectorStore; store = VectorStore(); print(f\"Documents: {store.get_document_count()}\")'"
```

## Monitoring

### Cloud Console

1. Navigate to Cloud Run in GCP Console
2. Select `thoth-mcp-server`
3. View:
   - **Metrics**: Request count, latency, instance count
   - **Logs**: Real-time application logs
   - **Revisions**: Deployment history

### Metrics

Key metrics to monitor:
- **Request latency**: Should be < 1s for queries
- **Instance count**: Auto-scales based on load
- **Error rate**: Should be < 1%
- **Memory usage**: Monitor for memory leaks

### Alerts

Set up alerts in Cloud Monitoring:

```bash
# Create alert for high error rate
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="Thoth MCP Server - High Error Rate" \
  --condition-display-name="Error Rate > 5%" \
  --condition-threshold-value=0.05 \
  --condition-threshold-duration=300s
```

## Backup and Restore

### Automated Backups

GCS sync is built into the application:

```python
from thoth.ingestion.vector_store import VectorStore

# Initialize with GCS
store = VectorStore(
    gcs_bucket_name="thoth-storage-bucket",
    gcs_project_id="thoth-dev-485501"
)

# Create backup
backup_name = store.backup_to_gcs()
print(f"Backup created: {backup_name}")

# List backups
backups = store.list_gcs_backups()
print(f"Available backups: {backups}")

# Restore from backup
store.restore_from_gcs(backup_name="backup_20260112_120000")
```

### Manual Backup

```bash
# Download from Cloud Run
gcloud run services execute thoth-mcp-server \
  --region=us-central1 \
  --command="tar -czf /tmp/backup.tar.gz /app/data/chroma_db"

# Or directly from GCS
gsutil -m cp -r gs://thoth-storage-bucket/chroma_db ./backup/
```

## Troubleshooting

### Deployment Fails

```bash
# Check build logs
gcloud builds list --limit=5

# Check service status
gcloud run services describe thoth-mcp-server --region=us-central1

# View deployment events
gcloud run revisions list --service=thoth-mcp-server --region=us-central1
```

### Service Errors

```bash
# Get recent errors
gcloud logging read "resource.type=cloud_run_revision AND severity=ERROR" --limit=20

# Check health
curl $(gcloud run services describe thoth-mcp-server --region=us-central1 --format='value(status.url)')/health
```

### Storage Issues

```bash
# Verify GCS bucket
gsutil ls gs://thoth-storage-bucket/

# Check permissions
gcloud projects get-iam-policy thoth-dev-485501 \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:thoth-mcp-sa@thoth-dev-485501.iam.gserviceaccount.com"

# Test GCS sync
gcloud run services execute thoth-mcp-server \
  --region=us-central1 \
  --command="python -c 'from thoth.ingestion.gcs_sync import GCSSync; sync = GCSSync(\"thoth-storage-bucket\"); print(sync.list_backups())'"
```

### High Latency

1. Check instance count (may need to increase min instances)
2. Review memory/CPU limits
3. Optimize vector DB size
4. Consider using Memorystore for Redis

### Cold Starts

To reduce cold starts:
1. Set `min-instances=1` (keeps one instance warm)
2. Use CPU boost for faster startup
3. Optimize Docker image size
4. Use Cloud Run's always-on CPU allocation

## Updates and Rollbacks

### Deploy New Version

```bash
# Build new image with tag
docker build -t thoth-mcp:v1.1.0 .
docker tag thoth-mcp:v1.1.0 gcr.io/thoth-dev-485501/thoth-mcp:v1.1.0
docker push gcr.io/thoth-dev-485501/thoth-mcp:v1.1.0

# Update service
gcloud run services update thoth-mcp-server \
  --region=us-central1 \
  --image=gcr.io/thoth-dev-485501/thoth-mcp:v1.1.0
```

### Rollback

```bash
# List revisions
gcloud run revisions list --service=thoth-mcp-server --region=us-central1

# Rollback to previous revision
gcloud run services update-traffic thoth-mcp-server \
  --region=us-central1 \
  --to-revisions=thoth-mcp-server-00002-xyz=100
```

## Cost Optimization

1. **Auto-scaling to zero**: Service scales to 0 instances when idle
2. **Right-size resources**: Monitor usage and adjust CPU/memory
3. **Storage lifecycle**: GCS bucket has 90-day retention policy
4. **Request optimization**: Cache frequent queries
5. **Use committed use discounts** for predictable workloads

Estimated costs (low usage):
- Cloud Run: ~$0.10/day (assuming minimal requests)
- GCS Storage: ~$0.01/GB/month
- Network egress: Varies by traffic

## Security

### Service Account

The Cloud Run service uses a dedicated service account with minimal permissions:
- `roles/storage.objectAdmin` - GCS bucket access only
- `roles/logging.logWriter` - Write logs to Cloud Logging
- `roles/monitoring.metricWriter` - Write metrics

### Network Security

- Internal-only ingress (modify in `cloud_run.tf` if public access needed)
- VPC connector can be added for private network access
- IAM authentication for service-to-service calls

### Secrets Management

Use Secret Manager for sensitive values:

```bash
# Create secret
echo -n "your-secret-value" | gcloud secrets create gitlab-token --data-file=-

# Grant access to service account
gcloud secrets add-iam-policy-binding gitlab-token \
  --member="serviceAccount:thoth-mcp-sa@thoth-dev-485501.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Update Cloud Run to use secret
gcloud run services update thoth-mcp-server \
  --region=us-central1 \
  --set-secrets="GITLAB_TOKEN=gitlab-token:latest"
```

## GitHub Actions CI/CD

The repository includes automated deployment workflows for continuous delivery.

### Workflow: Infrastructure & Cloud Run Deploy

**Location**: `.github/workflows/infra-deploy.yml`

**Triggers**:
- Push to `main` branch (when infra or code changes)
- Manual dispatch with optional flags

**Jobs**:
1. **Provision Infrastructure** - Deploys Terraform resources (GCS bucket, IAM, APIs)
2. **Deploy to Cloud Run** - Builds Docker image and deploys service

**Required Secrets**:
```bash
# Repository Settings → Secrets and variables → Actions
GCP_SA_KEY: Service account key JSON with permissions:
  - Storage Admin
  - Cloud Run Admin
  - Service Account User
  - Artifact Registry Writer
```

**To set up**:
```bash
# 1. Create service account for GitHub Actions
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions Deployment"

# 2. Grant necessary roles
gcloud projects add-iam-policy-binding thoth-dev-485501 \
  --member="serviceAccount:github-actions@thoth-dev-485501.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding thoth-dev-485501 \
  --member="serviceAccount:github-actions@thoth-dev-485501.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding thoth-dev-485501 \
  --member="serviceAccount:github-actions@thoth-dev-485501.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# 3. Create and download key
gcloud iam service-accounts keys create github-actions-key.json \
  --iam-account=github-actions@thoth-dev-485501.iam.gserviceaccount.com

# 4. Add to GitHub Secrets
# Copy contents of github-actions-key.json to GCP_SA_KEY secret in repository settings
```

**Manual Trigger**:
```bash
# Via GitHub UI: Actions → Infrastructure & Cloud Run Deploy → Run workflow
# Options:
#   - skip_terraform: Skip Terraform deployment
#   - skip_cloud_run: Skip Cloud Run deployment
```

**Monitoring Deployments**:
- View deployment status in GitHub Actions tab
- Check deployment summary for service URL and health status
- Review logs directly in workflow output

### Workflow: CD (Continuous Delivery)

**Location**: `.github/workflows/cd.yml`

**Triggers**:
- New GitHub release published
- Manual dispatch

**Jobs**:
1. **Publish to PyPI** - Builds and publishes Python package
2. **Deploy Infrastructure** - Automatically triggers infra deployment after release

**Features**:
- Builds optimized PyTorch CPU-only package
- Verifies build artifacts
- Optionally deploys infrastructure after successful publish
- Can skip infrastructure deployment with manual trigger

## Best Practices

1. **Use Terraform** for reproducible deployments
2. **Tag images** with versions (not just `latest`)
3. **Enable Cloud Logging** for debugging
4. **Set up monitoring alerts** for errors and latency
5. **Regular backups** to GCS
6. **Test locally** with Docker before deploying
7. **Use revision tags** for canary deployments
8. **Document changes** in git commits and tags
9. **Automate deployments** with GitHub Actions
10. **Review deployment logs** in GitHub Actions summaries

## Support

- GitHub Issues: https://github.com/TheWinterShadow/Thoth/issues
- Cloud Run Documentation: https://cloud.google.com/run/docs
- GCS Documentation: https://cloud.google.com/storage/docs
- GitHub Actions: https://docs.github.com/actions
