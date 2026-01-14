variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "rules" {
  description = "List of EventBridge rules"
  type = list(object({
    name                = string
    description         = string
    schedule_expression = string
    lambda_function_arn = string
    lambda_function_name = string
    input               = optional(string)
    enabled             = optional(bool)
  }))
}

variable "create_dlq" {
  description = "Create dead letter queue for failed invocations"
  type        = bool
  default     = true
}

variable "dlq_message_retention_seconds" {
  description = "Message retention in seconds for DLQ"
  type        = number
  default     = 1209600 # 14 days
}

variable "tags" {
  description = "Additional tags to apply"
  type        = map(string)
  default     = {}
}

