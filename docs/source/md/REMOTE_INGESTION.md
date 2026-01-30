# Remote Ingestion Guide

This guide explains how to trigger the handbook ingestion pipeline remotely on your Cloud Run deployment.

## Overview

The Thoth MCP server running on Cloud Run now includes an HTTP endpoint `/ingest` that triggers the handbook ingestion pipeline remotely, eliminating the need to run ingestion locally.

## Manual Trigger

### Using curl

```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://thoth-mcp-server-kp5w37kooa-uc.a.run.app/ingest
```

### Response Format

**Success Response (200 OK):**
```json
{
  "status": "success",
  "message": "Ingestion completed",
  "stats": {
    "processed_files": 1234,
    "failed_files": 5,
    "total_chunks": 5678,
    "duration_seconds": 45.2
  }
}
```

**Error Response (500 Internal Server Error):**
```json
{
  "status": "error",
  "message": "Error description here"
}
```

## Scheduled Ingestion with Cloud Scheduler

You can automate ingestion by setting up Cloud Scheduler to call the endpoint periodically.

### Create a Cloud Scheduler Job

```bash
# Create a service account for the scheduler
gcloud iam service-accounts create thoth-scheduler \
  --display-name="Thoth Scheduler" \
  --project=thoth-dev-485501

# Grant it permission to invoke Cloud Run
gcloud run services add-iam-policy-binding thoth-mcp-server \
  --region=us-central1 \
  --member="serviceAccount:thoth-scheduler@thoth-dev-485501.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --project=thoth-dev-485501

# Create the scheduler job (runs daily at 2 AM UTC)
gcloud scheduler jobs create http thoth-ingest-daily \
  --location=us-central1 \
  --schedule="0 2 * * *" \
  --uri="https://thoth-mcp-server-kp5w37kooa-uc.a.run.app/ingest" \
  --http-method=POST \
  --oidc-service-account-email="thoth-scheduler@thoth-dev-485501.iam.gserviceaccount.com" \
  --oidc-token-audience="https://thoth-mcp-server-kp5w37kooa-uc.a.run.app" \
  --project=thoth-dev-485501
```

### Schedule Examples

- **Daily at 2 AM UTC**: `0 2 * * *`
- **Every 6 hours**: `0 */6 * * *`
- **Weekly on Sunday at 3 AM**: `0 3 * * 0`
- **Every hour**: `0 * * * *`

### Test the Scheduler

```bash
# Manually trigger the scheduled job
gcloud scheduler jobs run thoth-ingest-daily \
  --location=us-central1 \
  --project=thoth-dev-485501
```

## Monitoring

### View Cloud Run Logs

```bash
# Stream logs from Cloud Run
gcloud run services logs read thoth-mcp-server \
  --region=us-central1 \
  --project=thoth-dev-485501 \
  --limit=100
```

### Check Scheduler Job History

```bash
gcloud scheduler jobs describe thoth-ingest-daily \
  --location=us-central1 \
  --project=thoth-dev-485501
```

## Benefits of Remote Ingestion

- ✅ **No local resources**: Runs entirely in Google Cloud
- ✅ **Persistent storage**: Vector database stored in GCS
- ✅ **Scalable**: Cloud Run automatically allocates resources
- ✅ **Automated**: Set up once, runs on schedule
- ✅ **Secure**: IAM-protected endpoint
- ✅ **Monitored**: All logs in Cloud Logging

## Troubleshooting

### Endpoint Returns 403 Forbidden

Ensure you're using a valid identity token:
```bash
gcloud auth print-identity-token
```

### Ingestion Times Out

Cloud Run requests have a maximum timeout. For large handbooks:
1. Increase Cloud Run timeout in terraform (default: 300s)
2. Use incremental ingestion (only processes changed files)

### Check Vector Database

Verify documents were ingested:
```bash
# Use the MCP server's search tool
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  https://thoth-mcp-server-kp5w37kooa-uc.a.run.app/messages \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_handbook","arguments":{"query":"test"}}}'
```

## Next Steps

- Set up Cloud Scheduler for automated daily ingestion
- Configure alerts for ingestion failures
- Monitor vector database size in GCS
