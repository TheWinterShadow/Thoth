# Cloud Run service for Thoth MCP Server
resource "google_cloud_run_v2_service" "thoth_mcp" {
  name                = "thoth-mcp-server"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    containers {
      image = var.container_image

      # Environment variables
      env {
        name  = "PYTHONUNBUFFERED"
        value = "1"
      }

      env {
        name  = "GCS_BUCKET_NAME"
        value = google_storage_bucket.thoth_bucket.name
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "CHROMA_PERSIST_DIRECTORY"
        value = "/app/data/chroma_db"
      }

      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }

      # Secrets from Secret Manager
      env {
        name = "GITLAB_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gitlab_token.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "GITLAB_BASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gitlab_url.secret_id
            version = "latest"
          }
        }
      }

      # Resource limits
      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      # Health checks via HTTP wrapper endpoint
      startup_probe {
        initial_delay_seconds = 10
        timeout_seconds       = 5
        period_seconds        = 10
        failure_threshold     = 3

        http_get {
          path = "/health"
          port = 8080
        }
      }

      liveness_probe {
        timeout_seconds   = 5
        period_seconds    = 30
        failure_threshold = 3

        http_get {
          path = "/health"
          port = 8080
        }
      }
    }

    # Service account
    service_account = google_service_account.thoth_mcp.email

    # Scaling
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    # Timeout
    timeout = "300s"
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  labels = {
    "managed-by" = "terraform"
    "app"        = "thoth-mcp"
  }
}

# Service account for Cloud Run
resource "google_service_account" "thoth_mcp" {
  account_id   = "thoth-mcp-sa"
  display_name = "Thoth MCP Server Service Account"
  description  = "Service account for Thoth MCP Server running on Cloud Run"
}

# Grant storage access to service account
resource "google_storage_bucket_iam_member" "thoth_mcp_storage_admin" {
  bucket = google_storage_bucket.thoth_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.thoth_mcp.email}"
}

# Grant logging permissions
resource "google_project_iam_member" "thoth_mcp_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.thoth_mcp.email}"
}

# Grant monitoring permissions
resource "google_project_iam_member" "thoth_mcp_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.thoth_mcp.email}"
}

# Grant Thoth service account read access to state bucket (for debugging)
resource "google_storage_bucket_iam_member" "thoth_state_viewer" {
  bucket = "thoth-terraform-state"
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.thoth_mcp.email}"

  depends_on = [google_service_account.thoth_mcp]
}

# IAM policy for Cloud Run service
# By default, no public access - callers must authenticate with Google Cloud ID token
# Grant invoker role to specific service accounts or users who need access

# Note: To call this service, users need:
# 1. IAM permission (roles/run.invoker) on the service
# 2. Valid Google Cloud ID token in Authorization header
#
# To add a user: gcloud run services add-iam-policy-binding thoth-mcp-server \
#   --region=us-central1 --member="user:email@example.com" --role="roles/run.invoker"
#
# To add a service account: gcloud run services add-iam-policy-binding thoth-mcp-server \
#   --region=us-central1 --member="serviceAccount:sa@project.iam.gserviceaccount.com" --role="roles/run.invoker"

# Output service URL
output "service_url" {
  description = "URL of the Cloud Run service"
  value       = google_cloud_run_v2_service.thoth_mcp.uri
}

output "service_name" {
  description = "Name of the Cloud Run service"
  value       = google_cloud_run_v2_service.thoth_mcp.name
}
