# Root Module Variables for Thoth MCP Infrastructure

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

variable "mcp_container_image" {
  description = "Container image for MCP server (e.g., gcr.io/project-id/thoth-mcp:latest)"
  type        = string
}

variable "ingestion_container_image" {
  description = "Container image for ingestion worker (e.g., gcr.io/project-id/thoth-ingestion:latest)"
  type        = string
}

variable "mcp_cpu" {
  description = "CPU allocation for MCP server (e.g., '0.25', '0.5', '1')"
  type        = string
  default     = "0.25"
}

variable "mcp_memory" {
  description = "Memory allocation for MCP server (e.g., '256Mi', '512Mi', '1Gi')"
  type        = string
  default     = "256Mi"
}

variable "ingestion_cpu" {
  description = "CPU allocation for ingestion worker (e.g., '1', '2', '4')"
  type        = string
  default     = "1"
}

variable "ingestion_memory" {
  description = "Memory allocation for ingestion worker (e.g., '1Gi', '2Gi', '4Gi')"
  type        = string
  default     = "2Gi"
}

variable "mcp_min_instances" {
  description = "Minimum number of MCP server instances"
  type        = number
  default     = 0
}

variable "mcp_max_instances" {
  description = "Maximum number of MCP server instances"
  type        = number
  default     = 2
}

variable "ingestion_min_instances" {
  description = "Minimum number of ingestion worker instances"
  type        = number
  default     = 0
}

variable "ingestion_max_instances" {
  description = "Maximum number of ingestion worker instances"
  type        = number
  default     = 10
}

variable "log_level" {
  description = "Application log level"
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], var.log_level)
    error_message = "Log level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL."
  }
}

variable "cloud_tasks_max_concurrent" {
  description = "Maximum concurrent Cloud Tasks executions"
  type        = number
  default     = 10
}

variable "cloud_tasks_dispatch_rate" {
  description = "Maximum Cloud Tasks dispatch rate per second"
  type        = number
  default     = 5
}

