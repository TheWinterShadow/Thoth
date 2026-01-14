variable "function_name" {
  description = "Name of the Lambda function"
  type        = string
}

variable "description" {
  description = "Description of the Lambda function"
  type        = string
  default     = ""
}

variable "handler" {
  description = "Lambda handler (for ZIP packages)"
  type        = string
  default     = ""
}

variable "runtime" {
  description = "Lambda runtime (for ZIP packages)"
  type        = string
  default     = "python3.11"
}

variable "package_type" {
  description = "Package type: Zip or Image"
  type        = string
  default     = "Zip"

  validation {
    condition     = contains(["Zip", "Image"], var.package_type)
    error_message = "Package type must be either 'Zip' or 'Image'."
  }
}

variable "filename" {
  description = "Path to the deployment package (for ZIP packages)"
  type        = string
  default     = null
}

variable "image_uri" {
  description = "URI of the container image (for Image packages)"
  type        = string
  default     = null
}

variable "memory_size" {
  description = "Memory size in MB"
  type        = number
  default     = 512

  validation {
    condition     = var.memory_size >= 128 && var.memory_size <= 10240 && var.memory_size % 64 == 0
    error_message = "Memory size must be between 128 and 10240 MB, in 64 MB increments."
  }
}

variable "timeout" {
  description = "Timeout in seconds"
  type        = number
  default     = 3

  validation {
    condition     = var.timeout >= 1 && var.timeout <= 900
    error_message = "Timeout must be between 1 and 900 seconds."
  }
}

variable "iam_role_arn" {
  description = "IAM role ARN for the Lambda function"
  type        = string
}

variable "environment_variables" {
  description = "Environment variables for the Lambda function"
  type        = map(string)
  default     = {}
}

variable "layers" {
  description = "List of Lambda layer ARNs"
  type        = list(string)
  default     = []
}

variable "dead_letter_queue_arn" {
  description = "ARN of the dead letter queue (optional)"
  type        = string
  default     = ""
}

variable "vpc_config" {
  description = "VPC configuration (optional)"
  type = object({
    subnet_ids         = list(string)
    security_group_ids = list(string)
  })
  default = null
}

variable "enable_xray" {
  description = "Enable X-Ray tracing"
  type        = bool
  default     = false
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 7
}

variable "create_alias" {
  description = "Create a Lambda alias"
  type        = bool
  default     = false
}

variable "alias_name" {
  description = "Name of the alias"
  type        = string
  default     = "live"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "tags" {
  description = "Additional tags to apply"
  type        = map(string)
  default     = {}
}

