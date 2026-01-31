# Ingestion Worker Module
# Contains Cloud Run service for ingestion worker and Cloud Tasks queue

# Variables
variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "service_account_email" {
  description = "Service account email from shared module"
  type        = string
}

variable "storage_bucket_name" {
  description = "Storage bucket name from shared module"
  type        = string
}

variable "gitlab_token_secret_id" {
  description = "GitLab token secret ID"
  type        = string
}

variable "gitlab_url_secret_id" {
  description = "GitLab URL secret ID"
  type        = string
}

variable "huggingface_token_secret_id" {
  description = "HuggingFace token secret ID"
  type        = string
}

variable "container_image" {
  description = "Container image for ingestion worker (e.g., gcr.io/project-id/thoth-ingestion:abc123)"
  type        = string
}

# Data source for project information
data "google_project" "current" {
  project_id = var.project_id
}

# Outputs
output "worker_url" {
  description = "URL of the Ingestion Worker Cloud Run service"
  value       = google_cloud_run_v2_service.thoth_ingestion_worker.uri
}


output "cloud_tasks_queue_name" {
  description = "Name of the Cloud Tasks queue"
  value       = google_cloud_tasks_queue.thoth_ingestion.name
}
