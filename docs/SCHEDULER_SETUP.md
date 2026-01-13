# Cloud Scheduler Setup

This document explains how to configure Google Cloud Scheduler for automated Thoth synchronization.

## Overview

Thoth uses Cloud Scheduler to automate handbook synchronization:

- **Daily Sync**: Full synchronization at 2 AM UTC
- **Hourly Incremental Sync**: Incremental updates every hour

## Prerequisites

1. Google Cloud Project with billing enabled
2. Cloud Run service deployed
3. gcloud CLI installed and authenticated
4. Appropriate IAM permissions:
   - `cloudscheduler.admin`
   - `run.invoker`
   - `iam.serviceAccountAdmin`

## Automated Setup

Use the provided script for complete setup:

```bash
./scripts/setup_secrets_and_scheduler.sh
```

This handles:
1. Enabling Cloud Scheduler API
2. Creating scheduler service account
3. Granting Cloud Run invoker permissions
4. Creating scheduler jobs

## Manual Setup

### 1. Enable Cloud Scheduler API

```bash
gcloud services enable cloudscheduler.googleapis.com --project=YOUR_PROJECT_ID
```

### 2. Create Service Account

Create a dedicated service account for scheduler:

```bash
gcloud iam service-accounts create thoth-scheduler \
    --display-name="Thoth Cloud Scheduler Service Account" \
    --project=YOUR_PROJECT_ID
```

### 3. Grant Cloud Run Invoker Role

Allow the scheduler to invoke the Cloud Run service:

```bash
SERVICE_NAME="thoth-mcp-server"
REGION="us-central1"
SCHEDULER_SA="thoth-scheduler@YOUR_PROJECT_ID.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding ${SERVICE_NAME} \
    --member="serviceAccount:${SCHEDULER_SA}" \
    --role="roles/run.invoker" \
    --region=${REGION} \
    --project=YOUR_PROJECT_ID
```

### 4. Get Cloud Run Service URL

```bash
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} \
    --region=${REGION} \
    --format="value(status.url)" \
    --project=YOUR_PROJECT_ID)

echo "Service URL: ${SERVICE_URL}"
```

### 5. Create Scheduler Jobs

#### Daily Full Sync Job

Runs at 2 AM UTC every day:

```bash
gcloud scheduler jobs create http thoth-daily-sync \
    --location=${REGION} \
    --schedule="0 2 * * *" \
    --time-zone="UTC" \
    --uri="${SERVICE_URL}/sync" \
    --http-method=POST \
    --message-body='{"scheduled":true,"sync_type":"daily"}' \
    --oidc-service-account-email="${SCHEDULER_SA}" \
    --oidc-token-audience="${SERVICE_URL}" \
    --attempt-deadline=320s \
    --max-retry-attempts=3 \
    --min-backoff=5s \
    --max-backoff=3600s \
    --project=YOUR_PROJECT_ID
```

#### Hourly Incremental Sync Job

Runs every hour:

```bash
gcloud scheduler jobs create http thoth-hourly-incremental-sync \
    --location=${REGION} \
    --schedule="0 * * * *" \
    --time-zone="UTC" \
    --uri="${SERVICE_URL}/sync" \
    --http-method=POST \
    --message-body='{"scheduled":true,"sync_type":"incremental","incremental":true}' \
    --oidc-service-account-email="${SCHEDULER_SA}" \
    --oidc-token-audience="${SERVICE_URL}" \
    --attempt-deadline=180s \
    --max-retry-attempts=2 \
    --min-backoff=5s \
    --max-backoff=1800s \
    --project=YOUR_PROJECT_ID
```

## Terraform Setup

Scheduler jobs are automatically created via Terraform:

```bash
cd infra

terraform init
terraform apply \
    -var="project_id=YOUR_PROJECT_ID" \
    -var="region=us-central1"
```

The configuration is in `infra/scheduler.tf`.

## Managing Scheduler Jobs

### List Jobs

```bash
gcloud scheduler jobs list --location=us-central1 --project=YOUR_PROJECT_ID
```

### View Job Details

```bash
gcloud scheduler jobs describe thoth-daily-sync \
    --location=us-central1 \
    --project=YOUR_PROJECT_ID
```

### Run Job Manually

Test a job by running it immediately:

```bash
gcloud scheduler jobs run thoth-daily-sync \
    --location=us-central1 \
    --project=YOUR_PROJECT_ID
```

### Update Job Schedule

```bash
gcloud scheduler jobs update http thoth-daily-sync \
    --location=us-central1 \
    --schedule="0 3 * * *" \
    --project=YOUR_PROJECT_ID
```

### Pause Job

```bash
gcloud scheduler jobs pause thoth-daily-sync \
    --location=us-central1 \
    --project=YOUR_PROJECT_ID
```

### Resume Job

```bash
gcloud scheduler jobs resume thoth-daily-sync \
    --location=us-central1 \
    --project=YOUR_PROJECT_ID
```

### Delete Job

```bash
gcloud scheduler jobs delete thoth-daily-sync \
    --location=us-central1 \
    --project=YOUR_PROJECT_ID
```

## Schedule Configuration

### Cron Format

Cloud Scheduler uses standard cron format:

```
* * * * *
│ │ │ │ │
│ │ │ │ └── Day of week (0-7, Sunday = 0 or 7)
│ │ │ └──── Month (1-12)
│ │ └────── Day of month (1-31)
│ └──────── Hour (0-23)
└────────── Minute (0-59)
```

### Common Schedules

```bash
# Every 15 minutes
"*/15 * * * *"

# Every hour at minute 0
"0 * * * *"

# Every day at 2 AM
"0 2 * * *"

# Every Monday at 9 AM
"0 9 * * 1"

# First day of every month at midnight
"0 0 1 * *"
```

### Time Zones

Specify time zone for schedules:

```bash
--time-zone="America/New_York"
--time-zone="Europe/London"
--time-zone="UTC"
```

## Monitoring

### View Job Logs

```bash
# Recent scheduler logs
gcloud logging read \
    'resource.type=cloud_scheduler_job' \
    --limit=20 \
    --project=YOUR_PROJECT_ID

# Logs for specific job
gcloud logging read \
    'resource.type=cloud_scheduler_job AND resource.labels.job_id=thoth-daily-sync' \
    --limit=10 \
    --project=YOUR_PROJECT_ID
```

### View Cloud Run Logs

```bash
# View sync endpoint logs
gcloud logging read \
    'resource.type=cloud_run_revision AND resource.labels.service_name=thoth-mcp-server AND textPayload=~"/sync"' \
    --limit=20 \
    --project=YOUR_PROJECT_ID
```

### Job Execution History

View recent executions in Cloud Console:
1. Go to Cloud Scheduler
2. Click on job name
3. View "Execution history" tab

Or use the API:

```bash
gcloud scheduler jobs describe thoth-daily-sync \
    --location=us-central1 \
    --format="table(state,lastAttemptTime,status.code,status.message)" \
    --project=YOUR_PROJECT_ID
```

## Retry Configuration

Jobs are configured with retry policies:

- **Daily Sync**:
  - Max retries: 3
  - Backoff: 5s to 3600s (exponential)
  - Deadline: 320s

- **Hourly Sync**:
  - Max retries: 2
  - Backoff: 5s to 1800s (exponential)
  - Deadline: 180s

### Update Retry Policy

```bash
gcloud scheduler jobs update http thoth-daily-sync \
    --location=us-central1 \
    --max-retry-attempts=5 \
    --min-backoff=10s \
    --max-backoff=7200s \
    --project=YOUR_PROJECT_ID
```

## Troubleshooting

### Job Fails with 403 Forbidden

Check service account has Cloud Run invoker role:

```bash
gcloud run services get-iam-policy thoth-mcp-server \
    --region=us-central1 \
    --project=YOUR_PROJECT_ID
```

### Job Fails with 404 Not Found

Verify Cloud Run service URL:

```bash
gcloud run services describe thoth-mcp-server \
    --region=us-central1 \
    --format="value(status.url)" \
    --project=YOUR_PROJECT_ID
```

### Job Times Out

Increase attempt deadline:

```bash
gcloud scheduler jobs update http thoth-daily-sync \
    --location=us-central1 \
    --attempt-deadline=600s \
    --project=YOUR_PROJECT_ID
```

### Job Not Running

Check job state:

```bash
gcloud scheduler jobs describe thoth-daily-sync \
    --location=us-central1 \
    --format="value(state)" \
    --project=YOUR_PROJECT_ID
```

If paused, resume:

```bash
gcloud scheduler jobs resume thoth-daily-sync \
    --location=us-central1 \
    --project=YOUR_PROJECT_ID
```

## Cost Considerations

Cloud Scheduler pricing:
- **Jobs**: $0.10 per job per month (for jobs up to 3 per month)
- **Executions**: First 3 jobs are free, then $0.10/job/month

For Thoth setup:
- 2 jobs (daily + hourly)
- ~750 executions/month (hourly job)
- **Total**: ~$0.20/month

## Performance Optimization

### Job Scheduling Best Practices

1. **Stagger Jobs**: Avoid scheduling multiple jobs at the same time
2. **Off-Peak Hours**: Schedule heavy jobs during low-traffic periods
3. **Incremental Updates**: Use hourly incremental sync for efficiency
4. **Monitor Execution Time**: Adjust deadlines based on actual execution times

### Example Optimized Schedule

```bash
# Daily full sync at 2 AM (low traffic)
"0 2 * * *"

# Hourly incremental at :00 minutes
"0 * * * *"

# Weekly deep sync on Sundays at 3 AM
"0 3 * * 0"
```

## Related Documentation

- [Google Cloud Scheduler](https://cloud.google.com/scheduler/docs)
- [Cloud Run Authentication](https://cloud.google.com/run/docs/authenticating/service-to-service)
- [Cron Format](https://cloud.google.com/scheduler/docs/configuring/cron-job-schedules)
- [Monitoring Scheduler Jobs](https://cloud.google.com/scheduler/docs/monitoring)
