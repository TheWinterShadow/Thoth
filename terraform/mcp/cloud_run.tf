# Cloud Run Configuration for Thoth MCP Server (lightweight query service)

# Cloud Run service for Thoth MCP Server
resource "google_cloud_run_v2_service" "thoth_mcp" {
  name                = "thoth-mcp-server"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = var.service_account_email
    timeout         = "300s" # 5 minutes for queries (reduced from 3600s)

    # Force new revision deployment with lazy loading
    annotations = {
      "lazy-loading-enabled" = "v2"
    }

    scaling {
      min_instance_count = 0  # Scale to zero when idle
      max_instance_count = 10 # Scale up for query traffic
    }

    containers {
      image = "gcr.io/${var.project_id}/thoth-mcp:latest"

      ports {
        name           = "http1"
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = false
      }

      env {
        name  = "PYTHONUNBUFFERED"
        value = "1"
      }

      env {
        name  = "GCS_BUCKET_NAME"
        value = var.storage_bucket_name
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "LOG_LEVEL"
        value = var.log_level
      }

      # HuggingFace token for model downloads
      env {
        name = "HF_TOKEN"
        value_source {
          secret_key_ref {
            secret  = var.huggingface_token_secret_id
            version = "latest"
          }
        }
      }

      # Startup probe - allow more time for GCS restoration
      startup_probe {
        initial_delay_seconds = 15
        timeout_seconds       = 10
        period_seconds        = 15
        failure_threshold     = 12  # 15 + (15 * 12) = 195 seconds total

        http_get {
          path = "/health"
          port = 8080
        }
      }

      # Liveness probe
      liveness_probe {
        initial_delay_seconds = 20
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

  labels = {
    app         = "thoth-mcp"
    managed-by  = "terraform"
  }
}

# Note: IAM policy for run.invoker is set manually via gcloud CLI
# due to Terraform Cloud service account lacking run.services.setIamPolicy permission
# Command: gcloud run services add-iam-policy-binding thoth-mcp-server --region=us-central1 --member="allUsers" --role="roles/run.invoker"
