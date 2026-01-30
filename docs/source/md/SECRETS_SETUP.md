# Secrets Management Setup

This document explains how to configure Google Cloud Secret Manager for Thoth.

## Overview

Thoth uses Google Cloud Secret Manager to securely store and manage sensitive credentials:

- **GitLab Token**: Personal access token for GitLab API access
- **GitLab URL**: Base URL for GitLab instance (defaults to https://gitlab.com)
- **Google Credentials**: Service account credentials (optional)

## Prerequisites

1. Google Cloud Project with billing enabled
2. gcloud CLI installed and authenticated
3. Appropriate IAM permissions:
   - `secretmanager.admin` or `secretmanager.secretAccessor`
   - `iam.serviceAccountAdmin`

## Automated Setup

The easiest way to set up secrets is using the provided script:

```bash
./scripts/setup_secrets_and_scheduler.sh
```

This script will:
1. Enable Secret Manager API
2. Create required secrets
3. Prompt you to add your GitLab token
4. Grant service account access to secrets
5. Set up Cloud Scheduler jobs

## Manual Setup

### 1. Enable Secret Manager API

```bash
gcloud services enable secretmanager.googleapis.com --project=YOUR_PROJECT_ID
```

### 2. Create Secrets

#### GitLab Token

```bash
# Create secret
gcloud secrets create gitlab-token \
    --replication-policy="automatic" \
    --project=YOUR_PROJECT_ID

# Add token value
echo -n "YOUR_GITLAB_TOKEN" | gcloud secrets versions add gitlab-token \
    --data-file=- \
    --project=YOUR_PROJECT_ID
```

#### GitLab URL (Optional)

```bash
# Create secret
gcloud secrets create gitlab-url \
    --replication-policy="automatic" \
    --project=YOUR_PROJECT_ID

# Set default value
echo -n "https://gitlab.com" | gcloud secrets versions add gitlab-url \
    --data-file=- \
    --project=YOUR_PROJECT_ID
```

#### Google Credentials (Optional)

```bash
# Create secret
gcloud secrets create google-application-credentials \
    --replication-policy="automatic" \
    --project=YOUR_PROJECT_ID

# Add credentials from file
gcloud secrets versions add google-application-credentials \
    --data-file=path/to/credentials.json \
    --project=YOUR_PROJECT_ID
```

### 3. Grant Service Account Access

Grant the Cloud Run service account access to secrets:

```bash
SERVICE_ACCOUNT="thoth-mcp-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com"

# GitLab Token
gcloud secrets add-iam-policy-binding gitlab-token \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project=YOUR_PROJECT_ID

# GitLab URL
gcloud secrets add-iam-policy-binding gitlab-url \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project=YOUR_PROJECT_ID

# Google Credentials
gcloud secrets add-iam-policy-binding google-application-credentials \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --project=YOUR_PROJECT_ID
```

## Terraform Setup

If using Terraform, secrets are automatically created but need values:

```bash
cd infra

# Initialize Terraform
terraform init

# Apply with variables
terraform apply \
    -var="project_id=YOUR_PROJECT_ID" \
    -var="gitlab_token=YOUR_TOKEN"
```

Or update secrets after Terraform deployment:

```bash
# Update GitLab token
echo -n "YOUR_TOKEN" | gcloud secrets versions add gitlab-token \
    --data-file=- \
    --project=YOUR_PROJECT_ID
```

## Updating Secrets

To update existing secrets:

```bash
# Update GitLab token
echo -n "NEW_TOKEN" | gcloud secrets versions add gitlab-token \
    --data-file=- \
    --project=YOUR_PROJECT_ID

# Update GitLab URL
echo -n "https://custom-gitlab.com" | gcloud secrets versions add gitlab-url \
    --data-file=- \
    --project=YOUR_PROJECT_ID
```

## Viewing Secrets

List all secrets:

```bash
gcloud secrets list --project=YOUR_PROJECT_ID
```

View secret metadata:

```bash
gcloud secrets describe gitlab-token --project=YOUR_PROJECT_ID
```

Access secret value:

```bash
gcloud secrets versions access latest --secret=gitlab-token --project=YOUR_PROJECT_ID
```

## Application Usage

The application automatically retrieves secrets from Secret Manager:

1. First, it tries to get secrets from Secret Manager
2. If Secret Manager is unavailable, it falls back to environment variables
3. Environment variables follow the pattern: `SECRET_ID` → `SECRET_ID` (uppercase with underscores)

### Environment Variable Fallback

You can still use environment variables for local development:

```bash
export GITLAB_TOKEN="your_token"
export GITLAB_BASE_URL="https://gitlab.com"
```

### Code Example

```python
from thoth.ingestion.gitlab_api import GitLabAPIClient

# Token is automatically retrieved from Secret Manager or environment
client = GitLabAPIClient()
```

## Security Best Practices

1. **Never commit secrets to version control**
2. **Use IAM roles for access control** - Grant least privilege access
3. **Enable secret rotation** - Regularly update tokens
4. **Audit secret access** - Monitor who accesses secrets
5. **Use secret versions** - Keep history of secret changes

## Troubleshooting

### Permission Denied

If you get permission errors:

```bash
# Grant yourself admin access
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="user:YOUR_EMAIL" \
    --role="roles/secretmanager.admin"
```

### Secret Not Found

Verify secret exists:

```bash
gcloud secrets describe SECRET_ID --project=YOUR_PROJECT_ID
```

### Application Cannot Access Secrets

Check service account permissions:

```bash
gcloud secrets get-iam-policy SECRET_ID --project=YOUR_PROJECT_ID
```

Ensure the service account has `roles/secretmanager.secretAccessor` role.

## Cost Considerations

Secret Manager pricing:
- **Active secret versions**: $0.06 per secret version per month
- **Access operations**: $0.03 per 10,000 operations

For typical usage with 3 secrets and hourly sync jobs:
- ~$0.18/month for storage
- ~$0.03/month for access operations
- **Total**: ~$0.21/month

## Related Documentation

- [Google Cloud Secret Manager](https://cloud.google.com/secret-manager/docs)
- [Cloud Run Secrets](https://cloud.google.com/run/docs/configuring/secrets)
- [IAM Roles for Secret Manager](https://cloud.google.com/secret-manager/docs/access-control)
