terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.8.0"
    }
  }

  # Bootstrap uses local backend initially
  backend "local" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Create the Terraform state bucket
resource "google_storage_bucket" "terraform_state" {
  name     = "thoth-terraform-state"
  location = var.region
  project  = var.project_id

  force_destroy               = false
  public_access_prevention    = "enforced"
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 10
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 30
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    "purpose"    = "terraform-state"
    "managed-by" = "terraform"
    "critical"   = "true"
  }
}

# Grant GitHub Actions service account access to state bucket
resource "google_storage_bucket_iam_member" "github_actions_state_access" {
  bucket = google_storage_bucket.terraform_state.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:github-actions@${var.project_id}.iam.gserviceaccount.com"

  depends_on = [google_storage_bucket.terraform_state]
}

output "state_bucket_name" {
  description = "Name of the Terraform state bucket"
  value       = google_storage_bucket.terraform_state.name
}

output "state_bucket_url" {
  description = "URL of the Terraform state bucket"
  value       = google_storage_bucket.terraform_state.url
}
