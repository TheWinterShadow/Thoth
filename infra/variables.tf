# Variables for Terraform configuration

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]+$", var.aws_region))
    error_message = "AWS region must be a valid region identifier."
  }
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

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "thoth"
}

variable "s3_bucket_name" {
  description = "Name of the S3 bucket for vector DB storage"
  type        = string
  default     = "thoth-storage-bucket"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]*[a-z0-9]$", var.s3_bucket_name))
    error_message = "S3 bucket name must be lowercase alphanumeric with hyphens."
  }
}

variable "s3_bucket_location" {
  description = "AWS region for S3 bucket"
  type        = string
  default     = "us-east-1"
}

variable "ecr_repository_name" {
  description = "Name of the ECR repository"
  type        = string
  default     = "thoth-mcp"
}

variable "lambda_memory_size" {
  description = "Memory size for MCP server Lambda function (MB)"
  type        = number
  default     = 512

  validation {
    condition     = var.lambda_memory_size >= 128 && var.lambda_memory_size <= 10240 && var.lambda_memory_size % 64 == 0
    error_message = "Lambda memory size must be between 128 and 10240 MB, in 64 MB increments."
  }
}

variable "lambda_timeout" {
  description = "Timeout for MCP server Lambda function (seconds)"
  type        = number
  default     = 900 # 15 minutes

  validation {
    condition     = var.lambda_timeout >= 1 && var.lambda_timeout <= 900
    error_message = "Lambda timeout must be between 1 and 900 seconds."
  }
}

variable "refresh_lambda_memory_size" {
  description = "Memory size for refresh service Lambda function (MB)"
  type        = number
  default     = 2048

  validation {
    condition     = var.refresh_lambda_memory_size >= 128 && var.refresh_lambda_memory_size <= 10240 && var.refresh_lambda_memory_size % 64 == 0
    error_message = "Lambda memory size must be between 128 and 10240 MB, in 64 MB increments."
  }
}

variable "refresh_lambda_timeout" {
  description = "Timeout for refresh service Lambda function (seconds)"
  type        = number
  default     = 900 # 15 minutes

  validation {
    condition     = var.refresh_lambda_timeout >= 1 && var.refresh_lambda_timeout <= 900
    error_message = "Lambda timeout must be between 1 and 900 seconds."
  }
}

variable "lambda_layers" {
  description = "List of Lambda layer ARNs to attach to MCP server function"
  type        = list(string)
  default     = []
}

variable "kms_key_id" {
  description = "KMS key ID for encryption (optional, uses AWS managed key if not provided)"
  type        = string
  default     = ""
}

variable "api_domain_name" {
  description = "Custom domain name for API Gateway (optional)"
  type        = string
  default     = ""
}

variable "log_level" {
  description = "Log level for Lambda functions"
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], var.log_level)
    error_message = "Log level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL."
  }
}

# Secret variables (optional, should be set via AWS Secrets Manager)
variable "gitlab_token" {
  description = "GitLab personal access token (optional, should be set via Secrets Manager)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "gitlab_url" {
  description = "GitLab base URL (optional, defaults to gitlab.com)"
  type        = string
  default     = "https://gitlab.com"
}

variable "api_key" {
  description = "API key for HTTP endpoint authentication (optional, should be set via Secrets Manager)"
  type        = string
  default     = ""
  sensitive   = true
}
