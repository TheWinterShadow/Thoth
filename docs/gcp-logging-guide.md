# GCP Cloud Logging Guide for Thoth

This guide explains how to search, filter, and analyze Thoth logs in Google Cloud Logging. The structured JSON format enables powerful querying and dashboard creation.

## Log Structure

Thoth logs are output as structured JSON with the following fields:

### Standard Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO 8601 timestamp (e.g., `2026-01-30T10:15:30.123456Z`) |
| `severity` | string | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `message` | string | The log message |
| `logger` | string | Logger name (e.g., `thoth.ingestion.worker`) |

### Source Location Fields

| Field | Type | Description |
|-------|------|-------------|
| `pathname` | string | Full file path |
| `filename` | string | File name only |
| `lineno` | integer | Line number |
| `funcName` | string | Function name |
| `module` | string | Module name |
| `logging.googleapis.com/sourceLocation` | object | GCP-specific source location (clickable in console) |

### Job Context Fields

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | Unique job identifier for correlation |
| `source` | string | Data source: `handbook`, `dnd`, `personal` |
| `collection` | string | LanceDB table (collection) name |
| `operation` | string | Current operation: `chunking`, `embedding`, `storing` |
| `batch_id` | string | Batch identifier for parallel processing |

### Metrics Fields

| Field | Type | Description |
|-------|------|-------------|
| `files_processed` | integer | Number of files processed |
| `chunks_created` | integer | Number of chunks created |
| `duration_ms` | integer | Operation duration in milliseconds |
| `total_files` | integer | Total files in batch |
| `successful` | integer | Successful operations count |
| `failed` | integer | Failed operations count |

### GCP Special Fields

| Field | Type | Description |
|-------|------|-------------|
| `logging.googleapis.com/trace` | string | Trace ID for request correlation |
| `logging.googleapis.com/labels` | object | Labels for filtering (`job_id`, `source`, `operation`) |

## Common Queries

### Filter by Job ID

Find all logs for a specific ingestion job:

```
resource.type="cloud_run_revision"
resource.labels.service_name="thoth-ingestion-worker"
jsonPayload.job_id="job_abc123"
```

Or using labels (more efficient):

```
resource.type="cloud_run_revision"
labels."job_id"="job_abc123"
```

### Filter by Source

Find all logs for handbook ingestion:

```
resource.type="cloud_run_revision"
jsonPayload.source="handbook"
```

### Filter by Operation

Find all chunking operations:

```
resource.type="cloud_run_revision"
jsonPayload.operation="chunking"
```

### Find Errors

Find all error logs:

```
resource.type="cloud_run_revision"
resource.labels.service_name="thoth-ingestion-worker"
severity>=ERROR
```

Find errors for a specific job:

```
resource.type="cloud_run_revision"
jsonPayload.job_id="job_abc123"
severity>=ERROR
```

### Find Slow Operations

Find operations taking more than 5 seconds:

```
resource.type="cloud_run_revision"
jsonPayload.duration_ms>5000
```

### Search by File Path

Find logs related to a specific file:

```
resource.type="cloud_run_revision"
jsonPayload.file_path:"handbook/engineering"
```

### Combine Filters

Find failed chunks in handbook ingestion:

```
resource.type="cloud_run_revision"
jsonPayload.source="handbook"
jsonPayload.operation="chunking"
severity>=WARNING
```

## Log Analytics Queries

For more complex analysis, use Log Analytics (SQL-like queries):

### Job Duration Analysis

```sql
SELECT
  jsonPayload.job_id,
  jsonPayload.source,
  MIN(timestamp) as start_time,
  MAX(timestamp) as end_time,
  TIMESTAMP_DIFF(MAX(timestamp), MIN(timestamp), SECOND) as duration_seconds
FROM `your-project.global._Default._Default`
WHERE
  resource.type = "cloud_run_revision"
  AND jsonPayload.job_id IS NOT NULL
  AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY jsonPayload.job_id, jsonPayload.source
ORDER BY start_time DESC
LIMIT 50
```

### Error Rate by Source

```sql
SELECT
  jsonPayload.source,
  COUNTIF(severity = "ERROR") as errors,
  COUNT(*) as total,
  ROUND(COUNTIF(severity = "ERROR") / COUNT(*) * 100, 2) as error_rate
FROM `your-project.global._Default._Default`
WHERE
  resource.type = "cloud_run_revision"
  AND jsonPayload.source IS NOT NULL
  AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY jsonPayload.source
```

### Throughput Analysis

```sql
SELECT
  TIMESTAMP_TRUNC(timestamp, HOUR) as hour,
  jsonPayload.source,
  SUM(jsonPayload.chunks_created) as total_chunks,
  SUM(jsonPayload.files_processed) as total_files,
  AVG(jsonPayload.duration_ms) as avg_duration_ms
FROM `your-project.global._Default._Default`
WHERE
  resource.type = "cloud_run_revision"
  AND jsonPayload.chunks_created IS NOT NULL
  AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY hour, jsonPayload.source
ORDER BY hour DESC
```

## Creating Log-Based Metrics

### Error Count Metric

1. Go to **Logging > Log-based Metrics**
2. Click **Create Metric**
3. Configure:
   - **Metric Type**: Counter
   - **Name**: `thoth_ingestion_errors`
   - **Filter**:
     ```
     resource.type="cloud_run_revision"
     resource.labels.service_name="thoth-ingestion-worker"
     severity>=ERROR
     ```
   - **Labels**: Add `source` from `jsonPayload.source`

### Job Duration Metric

1. Create a **Distribution** metric
2. **Name**: `thoth_job_duration`
3. **Filter**:
   ```
   resource.type="cloud_run_revision"
   jsonPayload.duration_ms>0
   ```
4. **Field name**: `jsonPayload.duration_ms`

### Chunks Created Metric

1. Create a **Counter** metric
2. **Name**: `thoth_chunks_created`
3. **Filter**:
   ```
   resource.type="cloud_run_revision"
   jsonPayload.chunks_created>0
   ```
4. **Field name**: `jsonPayload.chunks_created`

## Creating Dashboards

### Recommended Dashboard Widgets

1. **Job Success Rate** (Pie chart)
   - Use log-based metrics for success/failure counts

2. **Ingestion Throughput** (Line chart)
   - X-axis: Time
   - Y-axis: `chunks_created` summed over time

3. **Error Timeline** (Line chart)
   - Filter: `severity>=ERROR`
   - Group by: `source`

4. **Active Jobs Table**
   - Recent jobs with status, duration, counts

5. **Duration Histogram**
   - Distribution of `duration_ms` values

## Alerting

### Create an Alert for Job Failures

1. Go to **Monitoring > Alerting**
2. **Create Policy**
3. Configure:
   - **Condition**: Log-based metric `thoth_ingestion_errors` > 5 in 5 minutes
   - **Notification**: Email/Slack/PagerDuty

### Create an Alert for Long-Running Jobs

1. **Condition**: `duration_ms` > 300000 (5 minutes)
2. Use the log-based metric created above

## Grafana Loki Integration

If you're using Grafana Loki, the JSON logs are directly compatible. Use LogQL queries:

### Filter by Job ID

```logql
{app="thoth-ingestion-worker"} | json | job_id="job_abc123"
```

### Extract Metrics

```logql
sum by (source) (
  rate({app="thoth-ingestion-worker"} | json | unwrap chunks_created [5m])
)
```

### Error Rate

```logql
sum(rate({app="thoth-ingestion-worker"} | json | severity="ERROR" [5m]))
/
sum(rate({app="thoth-ingestion-worker"} [5m]))
```

## Troubleshooting

### Logs Not Appearing

1. Check Cloud Run service is running: `gcloud run services describe thoth-ingestion-worker`
2. Verify LOG_FORMAT environment variable (optional - JSON is auto-detected in Cloud Run)
3. Check IAM permissions for Cloud Logging

### Job ID Not in Logs

Ensure the job logger adapter is being used:

```python
from thoth.shared.utils.logger import get_job_logger

job_logger = get_job_logger(logger, job_id=job.job_id, source=source_config.name)
job_logger.info("Processing started")
```

### Trace Correlation Not Working

Ensure trace context is extracted at request start:

```python
from thoth.shared.utils.logger import extract_trace_id_from_header, set_trace_context

trace_header = request.headers.get("X-Cloud-Trace-Context")
trace_id = extract_trace_id_from_header(trace_header)
set_trace_context(trace_id, os.getenv("GCP_PROJECT_ID"))
```

## Best Practices

1. **Always use job_id** - Include job_id in all job-related logs for easy correlation
2. **Use appropriate log levels** - DEBUG for detailed info, INFO for milestones, WARNING for issues, ERROR for failures
3. **Include metrics** - Add numeric fields (duration_ms, chunks_created) for dashboarding
4. **Avoid logging sensitive data** - The logger redacts common patterns, but be careful with custom fields
5. **Use structured extra fields** - Pass context via `extra={}` instead of string interpolation

```python
# Good
logger.info("Processed file", extra={"file_path": path, "chunks_created": 15})

# Avoid
logger.info(f"Processed file {path}, created {chunks} chunks")
```
