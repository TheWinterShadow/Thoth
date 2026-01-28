# Thoth MCP Server - Terraform Configuration
# Main entry point that references modularized infrastructure

terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  cloud {
    organization = "TheWinterShadow"
    workspaces {
      name = "thoth-mcp-gcp"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Data source for project information
data "google_project" "current" {
  project_id = var.project_id
}

# Module: Shared Infrastructure (IAM, Secrets, Storage, APIs)
module "shared" {
  source = "./shared"

  project_id         = var.project_id
  region             = var.region
  environment        = var.environment
  gitlab_token       = var.gitlab_token
  gitlab_url         = var.gitlab_url
  huggingface_token  = var.huggingface_token
}

# Module: MCP Server
module "mcp" {
  source = "./mcp"

  project_id                = var.project_id
  region                    = var.region
  log_level                 = var.log_level
  
  # Dependencies from shared module
  service_account_email     = module.shared.service_account_email
  storage_bucket_name       = module.shared.storage_bucket_name
  gitlab_token_secret_id    = module.shared.gitlab_token_secret_id
  gitlab_url_secret_id      = module.shared.gitlab_url_secret_id
  huggingface_token_secret_id = module.shared.huggingface_token_secret_id

  depends_on = [module.shared]
}

# Module: Ingestion Worker
module "ingestion" {
  source = "./ingestion"

  project_id            = var.project_id
  region                = var.region

  # Dependencies from shared module
  service_account_email           = module.shared.service_account_email
  storage_bucket_name             = module.shared.storage_bucket_name
  gitlab_token_secret_id          = module.shared.gitlab_token_secret_id
  gitlab_url_secret_id            = module.shared.gitlab_url_secret_id
  huggingface_token_secret_id     = module.shared.huggingface_token_secret_id

  depends_on = [module.shared]
}

# Outputs
output "mcp_service_url" {
  description = "URL of the MCP Server Cloud Run service"
  value       = module.mcp.service_url
}

output "ingestion_worker_url" {
  description = "URL of the Ingestion Worker Cloud Run service"
  value       = module.ingestion.worker_url
}

output "service_account_email" {
  description = "Email of the service account"
  value       = module.shared.service_account_email
}

output "storage_bucket_name" {
  description = "Name of the GCS bucket"
  value       = module.shared.storage_bucket_name
}
