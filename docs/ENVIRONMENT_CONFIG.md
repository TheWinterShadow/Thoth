# Environment Configuration for Thoth

This document describes the environment variables used by the Thoth application.

## Required Environment Variables

### Python Configuration
- `PYTHONUNBUFFERED=1` - Disable Python output buffering for real-time logging
- `PYTHONDONTWRITEBYTECODE=1` - Prevent Python from writing .pyc files

### Google Cloud Platform
- `GCP_PROJECT_ID` - Your GCP project ID (e.g., `thoth-483015`)
- `GCS_BUCKET_NAME` - Name of GCS bucket for vector DB persistence (e.g., `thoth-storage-bucket`)

### Application Settings
- `CHROMA_PERSIST_DIRECTORY` - Path for ChromaDB persistence (default: `./chroma_db`)
- `LOG_LEVEL` - Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: `INFO`)

## Optional Environment Variables

### GitLab Integration
- `GITLAB_URL` - GitLab instance URL (default: `https://gitlab.com`)
- `GITLAB_TOKEN` - Personal access token for GitLab API
- `GITLAB_PROJECT_ID` - GitLab project ID to sync

### Repository Configuration
- `REPO_LOCAL_PATH` - Local path for cloning repositories (default: `./handbook_repo`)
- `SYNC_SCHEDULE` - Cron schedule for automatic syncing (default: `0 */6 * * *` - every 6 hours)

### Model Configuration
- `EMBEDDING_MODEL` - Sentence transformer model name (default: `all-MiniLM-L6-v2`)
- `CHUNK_SIZE` - Document chunk size in characters (default: `1000`)
- `CHUNK_OVERLAP` - Chunk overlap in characters (default: `200`)

### GCS Backup
- `GCS_AUTO_BACKUP` - Enable automatic backups to GCS (default: `false`)
- `GCS_BACKUP_SCHEDULE` - Cron schedule for backups (default: `0 0 * * *` - daily at midnight)

## Cloud Run Configuration

When deploying to Google Cloud Run, set these environment variables in the service configuration:

```bash
gcloud run services update thoth-mcp-server \
  --region=us-central1 \
  --set-env-vars="PYTHONUNBUFFERED=1,GCP_PROJECT_ID=thoth-483015,GCS_BUCKET_NAME=thoth-storage-bucket,LOG_LEVEL=INFO"
```

Or use the Cloud Console:
1. Navigate to Cloud Run → Select service → Edit & Deploy New Revision
2. Go to "Variables & Secrets" tab
3. Add environment variables as key-value pairs

## Terraform Configuration

Environment variables are set in `infra/cloud_run.tf`:

```hcl
env {
  name  = "GCS_BUCKET_NAME"
  value = google_storage_bucket.thoth_bucket.name
}
```

To update:
1. Modify `cloud_run.tf`
2. Run `terraform plan` to preview changes
3. Run `terraform apply` to deploy

## Local Development

Create a `.env` file in the project root:

```bash
# .env
GCP_PROJECT_ID=thoth-483015
GCS_BUCKET_NAME=thoth-storage-bucket
CHROMA_PERSIST_DIRECTORY=./chroma_db
LOG_LEVEL=DEBUG
GITLAB_TOKEN=your_gitlab_token_here
```

Load environment variables:

```bash
# Using direnv
direnv allow

# Or manually with bash
export $(cat .env | xargs)

# Or with Python dotenv
# Already configured in the application
```

## Service Account Credentials

For local development with GCS:

1. Create a service account in GCP Console
2. Grant roles:
   - `roles/storage.objectAdmin` - For GCS bucket access
   - `roles/logging.logWriter` - For Cloud Logging
3. Download JSON key file
4. Set environment variable:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
   ```

For Cloud Run deployment:
- Service account is automatically configured via Terraform
- Uses workload identity (no key file needed)

## Verification

Check environment configuration:

```bash
# Run health check
python -c "from thoth.health import health_check_cli; health_check_cli()"

# Verify GCS access
python -c "from google.cloud import storage; client = storage.Client(); print([b.name for b in client.list_buckets()])"
```

## Security Best Practices

1. **Never commit secrets** to version control
2. Use `.env` files for local development (add to `.gitignore`)
3. Use Secret Manager for sensitive values in production
4. Rotate credentials regularly
5. Use least-privilege service accounts
6. Enable audit logging for GCS access

## Troubleshooting

### GCS Access Issues
```bash
# Check credentials
gcloud auth application-default login

# Verify bucket access
gsutil ls gs://thoth-storage-bucket/
```

### Cloud Run Environment
```bash
# View current environment variables
gcloud run services describe thoth-mcp-server \
  --region=us-central1 \
  --format="value(spec.template.spec.containers[0].env)"

# Check logs for startup errors
gcloud logging read "resource.type=cloud_run_revision" --limit=50
```

### Missing Variables
The application will log warnings for missing optional variables but will fail for required ones. Check logs:

```bash
# Local
python -m thoth.mcp_server.server

# Cloud Run
gcloud logging read "resource.labels.service_name=thoth-mcp-server" --limit=100
```
