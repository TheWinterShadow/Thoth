variable "project_name" {
  description = "Project name for secret naming"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "kms_key_id" {
  description = "KMS key ID for encryption (optional)"
  type        = string
  default     = ""
}

variable "gitlab_token" {
  description = "GitLab token (optional, should be set via AWS CLI)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "gitlab_url" {
  description = "GitLab URL (optional, defaults to gitlab.com)"
  type        = string
  default     = "https://gitlab.com"
}

variable "api_key" {
  description = "API key (optional, should be set via AWS CLI)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "tags" {
  description = "Additional tags to apply to secrets"
  type        = map(string)
  default     = {}
}

