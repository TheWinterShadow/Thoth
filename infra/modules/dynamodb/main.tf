# DynamoDB table module for connection state/cache

resource "aws_dynamodb_table" "this" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = var.hash_key

  attribute {
    name = var.hash_key
    type = var.hash_key_type
  }

  # Range key (optional)
  dynamic "attribute" {
    for_each = var.range_key != "" ? [1] : []
    content {
      name = var.range_key
      type = var.range_key_type
    }
  }

  dynamic "range_key" {
    for_each = var.range_key != "" ? [1] : []
    content {
      name = var.range_key
    }
  }

  # Global secondary indexes (optional)
  dynamic "global_secondary_index" {
    for_each = var.global_secondary_indexes
    content {
      name            = global_secondary_index.value.name
      hash_key        = global_secondary_index.value.hash_key
      range_key       = lookup(global_secondary_index.value, "range_key", null)
      projection_type = global_secondary_index.value.projection_type
    }
  }

  # Server-side encryption
  server_side_encryption {
    enabled     = true
    kms_key_id  = var.kms_key_id != "" ? var.kms_key_id : null
  }

  # Point-in-time recovery
  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  # TTL
  dynamic "ttl" {
    for_each = var.ttl_attribute != "" ? [1] : []
    content {
      enabled        = true
      attribute_name = var.ttl_attribute
    }
  }

  tags = merge(
    var.tags,
    {
      Name        = var.table_name
      Environment = var.environment
      Purpose     = "mcp-state-cache"
    }
  )

  lifecycle {
    prevent_destroy = var.prevent_destroy
  }
}

