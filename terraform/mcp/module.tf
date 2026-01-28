# MCP Server Module  
# Contains Cloud Run service for MCP query server

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

variable "log_level" {
  description = "Log level"
  type        = string
  default     = "INFO"
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

# Data source for project information
data "google_project" "current" {
  project_id = var.project_id
}

# Outputs
output "service_url" {
  description = "URL of the MCP Server Cloud Run service"
  value       = google_cloud_run_v2_service.thoth_mcp.uri
}
