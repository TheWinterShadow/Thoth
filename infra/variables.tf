# Variables for Terraform configuration

variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "thoth-483015"
}

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone for resources"
  type        = string
  default     = "us-central1-c"
}

variable "container_image" {
  description = "Container image for Cloud Run deployment"
  type        = string
  default     = "gcr.io/thoth-483015/thoth-mcp:latest"
}

variable "bucket_name" {
  description = "Name of the GCS bucket"
  type        = string
  default     = "thoth-storage-bucket"
}

variable "bucket_location" {
  description = "Location of the GCS bucket"
  type        = string
  default     = "US"
}

# Secret variables (optional, can be set later via gcloud)
variable "gitlab_token" {
  description = "GitLab personal access token (optional, update via gcloud)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "gitlab_url" {
  description = "GitLab base URL (optional, defaults to gitlab.com)"
  type        = string
  default     = ""
}

variable "google_credentials_json" {
  description = "Google service account credentials JSON (optional)"
  type        = string
  default     = ""
  sensitive   = true
}
