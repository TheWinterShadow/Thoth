# Shared Infrastructure Module Variables

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "gitlab_token" {
  description = "GitLab personal access token (sensitive)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "gitlab_url" {
  description = "GitLab base URL"
  type        = string
  default     = "https://gitlab.com"
}

variable "huggingface_token" {
  description = "HuggingFace API token for downloading models (sensitive)"
  type        = string
  default     = ""
  sensitive   = true
}

