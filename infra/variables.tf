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
