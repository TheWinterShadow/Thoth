variable "role_name" {
  description = "Name of the IAM role"
  type        = string
}

variable "role_description" {
  description = "Description of the IAM role"
  type        = string
  default     = ""
}

variable "service_name" {
  description = "Name of the service using this role"
  type        = string
  default     = ""
}

variable "service_principal" {
  description = "Service principal for assume role policy"
  type        = string
  default     = "lambda.amazonaws.com"
}

variable "policies" {
  description = "List of IAM policies to attach"
  type = list(object({
    name       = string
    statements = list(object({
      effect    = string
      actions   = list(string)
      resources = list(string)
      condition = optional(map(any))
    }))
  }))
  default = []
}

variable "add_cloudwatch_logs_policy" {
  description = "Add CloudWatch Logs policy (for Lambda)"
  type        = bool
  default     = true
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

