# Secret Manager configuration for secure credential storage

# Enable Secret Manager API
resource "google_project_service" "secret_manager" {
  project = var.project_id
  service = "secretmanager.googleapis.com"

  disable_on_destroy = false
}

# GitLab token secret
resource "google_secret_manager_secret" "gitlab_token" {
  secret_id = "gitlab-token"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.secret_manager]
}

# GitLab token secret version (initially empty, must be set manually or via CLI)
resource "google_secret_manager_secret_version" "gitlab_token" {
  secret      = google_secret_manager_secret.gitlab_token.id
  secret_data = var.gitlab_token != "" ? var.gitlab_token : "PLACEHOLDER_UPDATE_ME"

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# GitLab base URL secret (optional, defaults to gitlab.com)
resource "google_secret_manager_secret" "gitlab_url" {
  secret_id = "gitlab-url"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.secret_manager]
}

resource "google_secret_manager_secret_version" "gitlab_url" {
  secret      = google_secret_manager_secret.gitlab_url.id
  secret_data = var.gitlab_url != "" ? var.gitlab_url : "https://gitlab.com"

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# Google Cloud credentials secret (for service account keys if needed)
resource "google_secret_manager_secret" "google_credentials" {
  secret_id = "google-application-credentials"
  project   = var.project_id

  replication {
    auto {}
  }

  depends_on = [google_project_service.secret_manager]
}

resource "google_secret_manager_secret_version" "google_credentials" {
  secret      = google_secret_manager_secret.google_credentials.id
  secret_data = var.google_credentials_json != "" ? var.google_credentials_json : "{}"

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# Grant the Cloud Run service account access to read secrets
resource "google_secret_manager_secret_iam_member" "thoth_mcp_gitlab_token_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.gitlab_token.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.thoth_mcp.email}"
}

resource "google_secret_manager_secret_iam_member" "thoth_mcp_gitlab_url_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.gitlab_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.thoth_mcp.email}"
}

resource "google_secret_manager_secret_iam_member" "thoth_mcp_google_credentials_access" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.google_credentials.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.thoth_mcp.email}"
}

# Outputs
output "gitlab_token_secret_name" {
  description = "Name of the GitLab token secret"
  value       = google_secret_manager_secret.gitlab_token.secret_id
}

output "gitlab_url_secret_name" {
  description = "Name of the GitLab URL secret"
  value       = google_secret_manager_secret.gitlab_url.secret_id
}

output "google_credentials_secret_name" {
  description = "Name of the Google credentials secret"
  value       = google_secret_manager_secret.google_credentials.secret_id
}

output "secret_manager_instructions" {
  description = "Instructions for updating secrets"
  value       = <<-EOT
    To update secrets, use the following commands:
    
    # Update GitLab token
    echo -n "YOUR_GITLAB_TOKEN" | gcloud secrets versions add gitlab-token --data-file=- --project=${var.project_id}
    
    # Update GitLab URL (if using self-hosted)
    echo -n "https://your-gitlab-instance.com" | gcloud secrets versions add gitlab-url --data-file=- --project=${var.project_id}
    
    # Update Google credentials (if needed)
    gcloud secrets versions add google-application-credentials --data-file=path/to/credentials.json --project=${var.project_id}
  EOT
}
