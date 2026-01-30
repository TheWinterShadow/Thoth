# IAM and Permissions Configuration for Thoth MCP Server

# Enable required GCP APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "cloudtasks.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# GCS bucket for vector database storage
resource "google_storage_bucket" "thoth_storage" {
  name          = "${var.project_id}-thoth-storage"
  location      = var.region
  force_destroy = var.environment == "dev" ? true : false

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    app         = "thoth"
    managed-by  = "terraform"
    environment = var.environment
  }

  depends_on = [google_project_service.required_apis]
}

# Secret Manager secrets
resource "google_secret_manager_secret" "gitlab_token" {
  secret_id = "gitlab-token"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret_version" "gitlab_token" {
  secret      = google_secret_manager_secret.gitlab_token.id
  secret_data = var.gitlab_token != "" ? var.gitlab_token : "1234567890abcdef1234567890abcdef"

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret" "gitlab_url" {
  secret_id = "gitlab-url"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret_version" "gitlab_url" {
  secret      = google_secret_manager_secret.gitlab_url.id
  secret_data = var.gitlab_url != "" ? var.gitlab_url : "https://gitlab.com"

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret" "huggingface_token" {
  secret_id = "huggingface-token"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret_version" "huggingface_token" {
  secret      = google_secret_manager_secret.huggingface_token.id
  secret_data = var.huggingface_token != "" ? var.huggingface_token : "dummy-token"

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# Service account for Cloud Run
# Permissions granted:
# - roles/storage.admin: Full GCS bucket access (read, write, metadata)
# - roles/secretmanager.secretAccessor: Read secrets (GitLab token, GitLab URL, HF token)
# - roles/logging.logWriter: Write logs to Cloud Logging
# - roles/monitoring.metricWriter: Write metrics to Cloud Monitoring
# - roles/cloudtasks.enqueuer: Create and manage Cloud Tasks
# - roles/run.invoker: Invoke Cloud Run service (for self-invocation from Cloud Tasks)
resource "google_service_account" "thoth_mcp" {
  account_id   = "thoth-mcp-sa"
  display_name = "Thoth MCP Server Service Account"
  description  = "Service account for Thoth MCP Server on Cloud Run"
}

# Grant storage access
resource "google_storage_bucket_iam_member" "thoth_storage_admin" {
  bucket = google_storage_bucket.thoth_storage.name
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.thoth_mcp.email}"
}

# Grant secret access
resource "google_secret_manager_secret_iam_member" "gitlab_token_accessor" {
  secret_id = google_secret_manager_secret.gitlab_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.thoth_mcp.email}"
}

resource "google_secret_manager_secret_iam_member" "gitlab_url_accessor" {
  secret_id = google_secret_manager_secret.gitlab_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.thoth_mcp.email}"
}

resource "google_secret_manager_secret_iam_member" "huggingface_token_accessor" {
  secret_id = google_secret_manager_secret.huggingface_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.thoth_mcp.email}"
}

# Grant logging and monitoring permissions
resource "google_project_iam_member" "thoth_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.thoth_mcp.email}"
}

resource "google_project_iam_member" "thoth_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.thoth_mcp.email}"
}

# Grant Cloud Tasks permissions
resource "google_project_iam_member" "thoth_cloudtasks_enqueuer" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.thoth_mcp.email}"
}

# Grant IAM Management Permissions
# Custom role with minimal permissions for Terraform to manage Cloud Run IAM
resource "google_project_iam_custom_role" "terraform_cloudrun_iam" {
  role_id     = "terraformCloudRunIAM"
  title       = "Terraform Cloud Run IAM Manager"
  description = "Minimal permissions for Terraform to manage IAM policies on Cloud Run services"
  
  permissions = [
    "run.services.getIamPolicy",
    "run.services.setIamPolicy",
  ]
  
  stage = "GA"
}

# Grant the custom role to Terraform service account
resource "google_project_iam_member" "terraform_cloudrun_iam_manager" {
  project = var.project_id
  role    = google_project_iam_custom_role.terraform_cloudrun_iam.id
  member  = "serviceAccount:${google_service_account.thoth_mcp.email}"
  
  depends_on = [google_project_service.required_apis]
}


# Note: roles/iam.serviceAccountUser is managed via gcloud (TF Cloud lacks setIamPolicy permission)
# gcloud iam service-accounts add-iam-policy-binding thoth-mcp-sa@PROJECT.iam.gserviceaccount.com \
#   --member="serviceAccount:thoth-mcp-sa@PROJECT.iam.gserviceaccount.com" \
#   --role="roles/iam.serviceAccountUser"
