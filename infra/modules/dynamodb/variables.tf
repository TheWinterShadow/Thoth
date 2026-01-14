variable "table_name" {
  description = "Name of the DynamoDB table"
  type        = string
}

variable "hash_key" {
  description = "Name of the hash key attribute"
  type        = string
  default     = "id"
}

variable "hash_key_type" {
  description = "Type of the hash key (S, N, B)"
  type        = string
  default     = "S"
}

variable "range_key" {
  description = "Name of the range key attribute (optional)"
  type        = string
  default     = ""
}

variable "range_key_type" {
  description = "Type of the range key (S, N, B)"
  type        = string
  default     = "S"
}

variable "global_secondary_indexes" {
  description = "List of global secondary indexes"
  type = list(object({
    name            = string
    hash_key        = string
    range_key       = optional(string)
    projection_type = string
  }))
  default = []
}

variable "enable_point_in_time_recovery" {
  description = "Enable point-in-time recovery"
  type        = bool
  default     = true
}

variable "ttl_attribute" {
  description = "Name of the TTL attribute (optional)"
  type        = string
  default     = "ttl"
}

variable "kms_key_id" {
  description = "KMS key ID for encryption (optional)"
  type        = string
  default     = ""
}

variable "prevent_destroy" {
  description = "Prevent accidental deletion"
  type        = bool
  default     = false
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "project_name" {
  description = "Project name for tagging"
  type        = string
}

variable "tags" {
  description = "Additional tags to apply"
  type        = map(string)
  default     = {}
}

