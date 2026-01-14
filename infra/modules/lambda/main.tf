# Lambda function module

resource "aws_lambda_function" "this" {
  function_name = var.function_name
  description    = var.description
  role          = var.iam_role_arn
  handler       = var.handler
  runtime       = var.runtime
  memory_size   = var.memory_size
  timeout       = var.timeout

  # Package type: Zip or Image
  package_type = var.package_type

  # For ZIP packages
  filename         = var.package_type == "Zip" ? var.filename : null
  source_code_hash = var.package_type == "Zip" && var.filename != null ? filebase64sha256(var.filename) : null

  # For Image packages
  image_uri = var.package_type == "Image" ? var.image_uri : null

  # Layers
  layers = var.layers

  # Environment variables
  environment {
    variables = var.environment_variables
  }

  # Dead letter queue
  dead_letter_config {
    target_arn = var.dead_letter_queue_arn != "" ? var.dead_letter_queue_arn : null
  }

  # VPC configuration (optional)
  dynamic "vpc_config" {
    for_each = var.vpc_config != null ? [var.vpc_config] : []
    content {
      subnet_ids         = vpc_config.value.subnet_ids
      security_group_ids = vpc_config.value.security_group_ids
    }
  }

  # Tracing
  tracing_config {
    mode = var.enable_xray ? "Active" : "PassThrough"
  }

  tags = merge(
    var.tags,
    {
      Name        = var.function_name
      Environment = var.environment
    }
  )
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days

  tags = merge(
    var.tags,
    {
      Name        = "${var.function_name}-logs"
      Environment = var.environment
    }
  )
}

# Alias for versioning (optional)
resource "aws_lambda_alias" "this" {
  count            = var.create_alias ? 1 : 0
  name             = var.alias_name
  description      = "Alias for ${var.function_name}"
  function_name    = aws_lambda_function.this.function_name
  function_version = "$LATEST"
}

