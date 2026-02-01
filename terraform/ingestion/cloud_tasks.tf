# Cloud Tasks Configuration for Thoth MCP Server

# Cloud Tasks queue for batch ingestion
# Note: LanceDB supports parallel batch processing using isolated table prefixes.
# Each batch writes to gs://bucket/lancedb_batch_X/ then merges to main table.
# Set max_concurrent_dispatches = 1 for sequential, or 10-50 for parallel processing.
resource "google_cloud_tasks_queue" "thoth_ingestion" {
  name     = "thoth-ingestion-queue-v2"
  location = var.region
  project  = var.project_id

  rate_limits {
    max_concurrent_dispatches = 10  # TODO: Increase to 10-50 for parallel batch processing
    max_dispatches_per_second = 1
  }

  retry_config {
    max_attempts       = 5
    max_retry_duration = "3600s"  # 1 hour max retry duration
    min_backoff        = "30s"
    max_backoff        = "300s"
  }
}
