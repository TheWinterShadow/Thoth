# Bootstrap configuration for Terraform state bucket
# This creates the bucket that will store Terraform state
# 
# USAGE:
# ======
# 
# This configuration manages the state bucket itself, creating a chicken-and-egg
# situation. To resolve this:
#
# 1. First-time setup (bootstrap):
#    ./scripts/bootstrap_terraform.sh
#
#    OR manually:
#    terraform init -backend=false
#    terraform apply -target=google_storage_bucket.terraform_state
#    terraform init -migrate-state -force-copy
#
# 2. After bootstrap, normal Terraform commands will use GCS backend:
#    terraform init
#    terraform plan
#    terraform apply
#
# 3. GitHub Actions automatically handles bootstrap on first run
#
# IMPORTANT:
# ==========
# - The state bucket has `prevent_destroy = true` for safety
# - Never delete this bucket manually - it contains all infrastructure state
# - State bucket has versioning enabled for recovery
# - Lifecycle rules clean up old versions to manage costs
#
# See docs/TERRAFORM_STATE.md for detailed documentation

resource "google_storage_bucket" "terraform_state" {
  name     = "thoth-terraform-state"
  location = var.region
  project  = var.project_id

  force_destroy               = false  # Protect state bucket from accidental deletion
  public_access_prevention    = "enforced"
  uniform_bucket_level_access = true

  versioning {
    enabled = true  # Essential for state recovery
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 10  # Keep last 10 versions
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 30  # Delete versions older than 30 days
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

  lifecycle {
    prevent_destroy = true  # Extra protection against accidental deletion
  }
}

# Grant GitHub Actions service account access to state bucket
resource "google_storage_bucket_iam_member" "github_actions_state_access" {
  bucket = google_storage_bucket.terraform_state.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:github-actions@${var.project_id}.iam.gserviceaccount.com"

  depends_on = [google_storage_bucket.terraform_state]
}

# Grant Thoth service account read access to state (for debugging)
resource "google_storage_bucket_iam_member" "thoth_state_viewer" {
  bucket = google_storage_bucket.terraform_state.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:thoth-mcp-sa@${var.project_id}.iam.gserviceaccount.com"

  depends_on = [
    google_storage_bucket.terraform_state,
    google_service_account.thoth_mcp
  ]
}

output "state_bucket_name" {
  description = "Name of the Terraform state bucket"
  value       = google_storage_bucket.terraform_state.name
}

output "state_bucket_url" {
  description = "URL of the Terraform state bucket"
  value       = google_storage_bucket.terraform_state.url
}

output "bootstrap_complete" {
  description = "Bootstrap completion message"
  value       = "Terraform state bucket created. You can now use 'terraform init' with the GCS backend."
}
