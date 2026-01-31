# Cloud Run service for ingestion worker
# Handles batch processing, Cloud Tasks integration, and GCS repository sync

resource "google_cloud_run_v2_service" "thoth_ingestion_worker" {
  name                = "thoth-ingestion-worker"
  location            = var.region
  project             = var.project_id
  deletion_protection = false

  template {
    service_account = var.service_account_email

    scaling {
      min_instance_count = 0  # Scale to zero when not processing
      max_instance_count = 10 # Allow parallel batch processing
    }

    timeout = "3600s" # 1 hour for batch processing

    containers {
      image = var.container_image

      ports {
        name           = "http1"
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = false
      }

      # Environment variables for ingestion worker
      env {
        name  = "GCS_BUCKET_NAME"
        value = var.storage_bucket_name
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "CLOUD_TASKS_LOCATION"
        value = var.region
      }

      env {
        name  = "CLOUD_TASKS_QUEUE"
        value = google_cloud_tasks_queue.thoth_ingestion.name
      }

      env {
        name  = "SERVICE_ACCOUNT_EMAIL"
        value = var.service_account_email
      }

      env {
        name  = "BATCH_SIZE"
        value = "100"
      }

      # CLOUD_RUN_SERVICE_URL will point to itself for Cloud Tasks callbacks
      env {
        name  = "CLOUD_RUN_SERVICE_URL"
        value = "https://thoth-ingestion-worker-${data.google_project.current.number}.${var.region}.run.app"
      }

      # Secret environment variables
      env {
        name = "GITLAB_TOKEN"
        value_source {
          secret_key_ref {
            secret  = var.gitlab_token_secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "GITLAB_URL"
        value_source {
          secret_key_ref {
            secret  = var.gitlab_url_secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "HF_TOKEN"
        value_source {
          secret_key_ref {
            secret  = var.huggingface_token_secret_id
            version = "latest"
          }
        }
      }

      # Startup probe
      startup_probe {
        initial_delay_seconds = 30
        timeout_seconds       = 10
        period_seconds        = 15
        failure_threshold     = 8

        http_get {
          path = "/health"
          port = 8080
        }
      }

      # Liveness probe
      liveness_probe {
        initial_delay_seconds = 30
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 3

        http_get {
          path = "/health"
          port = 8080
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}

# IAM binding: Allow service account to invoke itself (for Cloud Tasks callbacks)
resource "google_cloud_run_v2_service_iam_member" "ingestion_worker_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.thoth_ingestion_worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.service_account_email}"
}

output "ingestion_worker_url" {
  description = "URL of the ingestion worker Cloud Run service"
  value       = google_cloud_run_v2_service.thoth_ingestion_worker.uri
}
