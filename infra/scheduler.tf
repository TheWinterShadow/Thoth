# Cloud Scheduler configuration for automated sync jobs

# Enable Cloud Scheduler API
resource "google_project_service" "cloud_scheduler" {
  project = var.project_id
  service = "cloudscheduler.googleapis.com"

  disable_on_destroy = false
}

# Service account for Cloud Scheduler
resource "google_service_account" "scheduler" {
  account_id   = "thoth-scheduler"
  display_name = "Thoth Cloud Scheduler Service Account"
  description  = "Service account for Cloud Scheduler to invoke Thoth services"
  project      = var.project_id
}

# Grant the scheduler service account permission to invoke Cloud Run
resource "google_cloud_run_v2_service_iam_member" "scheduler_invoker" {
  project  = google_cloud_run_v2_service.thoth_mcp.project
  location = google_cloud_run_v2_service.thoth_mcp.location
  name     = google_cloud_run_v2_service.thoth_mcp.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

# Daily sync job - runs at 2 AM UTC
resource "google_cloud_scheduler_job" "daily_sync" {
  name             = "thoth-daily-sync"
  description      = "Daily handbook synchronization"
  schedule         = "0 2 * * *"
  time_zone        = "UTC"
  region           = var.region
  project          = var.project_id
  attempt_deadline = "320s"

  retry_config {
    retry_count          = 3
    max_retry_duration   = "0s"
    min_backoff_duration = "5s"
    max_backoff_duration = "3600s"
    max_doublings        = 5
  }

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.thoth_mcp.uri}/sync"
    
    headers = {
      "Content-Type" = "application/json"
    }

    body = base64encode(jsonencode({
      "scheduled" = true
      "sync_type" = "daily"
    }))

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = google_cloud_run_v2_service.thoth_mcp.uri
    }
  }

  depends_on = [
    google_project_service.cloud_scheduler,
    google_cloud_run_v2_service.thoth_mcp,
    google_cloud_run_v2_service_iam_member.scheduler_invoker
  ]
}

# Hourly incremental sync job - runs every hour
resource "google_cloud_scheduler_job" "hourly_incremental_sync" {
  name             = "thoth-hourly-incremental-sync"
  description      = "Hourly incremental handbook synchronization"
  schedule         = "0 * * * *"
  time_zone        = "UTC"
  region           = var.region
  project          = var.project_id
  attempt_deadline = "180s"

  retry_config {
    retry_count          = 2
    max_retry_duration   = "0s"
    min_backoff_duration = "5s"
    max_backoff_duration = "1800s"
    max_doublings        = 3
  }

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.thoth_mcp.uri}/sync"
    
    headers = {
      "Content-Type" = "application/json"
    }

    body = base64encode(jsonencode({
      "scheduled"    = true
      "sync_type"    = "incremental"
      "incremental"  = true
    }))

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = google_cloud_run_v2_service.thoth_mcp.uri
    }
  }

  depends_on = [
    google_project_service.cloud_scheduler,
    google_cloud_run_v2_service.thoth_mcp,
    google_cloud_run_v2_service_iam_member.scheduler_invoker
  ]
}

# Output scheduler job details
output "scheduler_daily_sync_id" {
  description = "ID of the daily sync scheduler job"
  value       = google_cloud_scheduler_job.daily_sync.id
}

output "scheduler_hourly_sync_id" {
  description = "ID of the hourly incremental sync scheduler job"
  value       = google_cloud_scheduler_job.hourly_incremental_sync.id
}

output "scheduler_service_account" {
  description = "Email of the scheduler service account"
  value       = google_service_account.scheduler.email
}
