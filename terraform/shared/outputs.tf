# Shared Infrastructure Module Outputs

output "storage_bucket_name" {
  description = "Name of the GCS storage bucket"
  value       = google_storage_bucket.thoth_storage.name
}

output "storage_bucket_url" {
  description = "URL of the GCS storage bucket"
  value       = google_storage_bucket.thoth_storage.url
}

output "service_account_email" {
  description = "Email of the Cloud Run service account"
  value       = google_service_account.thoth_mcp.email
}

output "gitlab_token_secret_id" {
  description = "ID of the GitLab token secret"
  value       = google_secret_manager_secret.gitlab_token.secret_id
}

output "gitlab_url_secret_id" {
  description = "ID of the GitLab URL secret"
  value       = google_secret_manager_secret.gitlab_url.secret_id
}

output "project_id" {
  description = "GCP Project ID"
  value       = var.project_id
}

output "region" {
  description = "GCP region"
  value       = var.region
}
