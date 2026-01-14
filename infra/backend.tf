# Backend configuration for Terraform state
# This should be configured after running bootstrap
# Example: terraform init -backend-config="bucket=thoth-terraform-state" -backend-config="dynamodb_table=thoth-terraform-state-lock"

terraform {
  backend "s3" {
    # These values should be provided via backend config or environment variables
    # bucket         = "thoth-terraform-state"
    # key            = "terraform/state"
    # region         = "us-east-1"
    # dynamodb_table = "thoth-terraform-state-lock"
    # encrypt        = true
  }
}

