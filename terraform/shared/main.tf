# Main Terraform configuration for Thoth MCP Server on GCP Cloud Run
# Uses HashiCorp Cloud (Terraform Cloud) for remote state management
#
# Configuration is split across multiple files:
# - main.tf: Provider and data sources
# - iam.tf: Service account, IAM roles, secrets, and storage
# - cloud_run.tf: Cloud Run service configuration
# - cloud_tasks.tf: Cloud Tasks queue configuration
# - variables.tf: Input variables
# - outputs.tf: Output values

terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Terraform Cloud backend for remote state management
  # Configure with: terraform login
  # Then update the organization and workspace names below
  cloud {
    organization = "TheWinterShadow" # Update with your Terraform Cloud organization

    workspaces {
      name = "thoth-mcp-gcp" # Update with your desired workspace name
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Get current project information
data "google_project" "current" {
  project_id = var.project_id
}
