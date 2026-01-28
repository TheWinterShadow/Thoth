# Cloud Tasks Configuration for Thoth MCP Server

# Cloud Tasks queue for sequential ingestion
# Note: max_concurrent_dispatches = 1 ensures only one batch runs at a time,
# which is required for ChromaDB to maintain a single unified collection.
# Parallel processing would create multiple collections that can't be merged.
resource "google_cloud_tasks_queue" "thoth_ingestion" {
  name     = "thoth-ingestion-queue-v2"
  location = var.region
  project  = var.project_id

  rate_limits {
    max_concurrent_dispatches = 1  # Sequential processing for unified ChromaDB
    max_dispatches_per_second = 1
  }

  retry_config {
    max_attempts       = 5
    max_retry_duration = "3600s"  # 1 hour max retry duration
    min_backoff        = "30s"
    max_backoff        = "300s"
  }
}
