# Shared Infrastructure Module
# Contains IAM, Secrets, Storage, and API enablement
# Variables and outputs are defined in variables.tf and outputs.tf

output "huggingface_token_secret_id" {
  description = "ID of the HuggingFace token secret"
  value       = google_secret_manager_secret.huggingface_token.secret_id
}
