# Bootstrap configuration for Terraform state bucket
# 
# The bootstrap resources have been moved to infra/bootstrap/ directory
# to avoid circular dependencies and validation issues during initial setup.
#
# USAGE:
# ======
# 
# 1. First-time setup (bootstrap):
#    ./scripts/bootstrap_terraform.sh
#
#    OR manually:
#    cd infra/bootstrap
#    terraform init
#    terraform apply -var="project_id=thoth-483015" -var="region=us-central1"
#
# 2. After bootstrap, use the main infra directory:
#    cd infra
#    terraform init
#    terraform plan
#    terraform apply
#
# 3. GitHub Actions automatically handles bootstrap on first run
#
# See docs/TERRAFORM_STATE.md for detailed documentation

# Reference to the Terraform state bucket (created by bootstrap directory)
data "google_storage_bucket" "terraform_state" {
  name = "thoth-terraform-state"
}

output "state_bucket_name" {
  description = "Name of the Terraform state bucket"
  value       = data.google_storage_bucket.terraform_state.name
}

output "state_bucket_url" {
  description = "URL of the Terraform state bucket"
  value       = data.google_storage_bucket.terraform_state.url
}
