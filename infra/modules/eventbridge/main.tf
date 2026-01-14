# EventBridge rules module for scheduled jobs

# EventBridge rule
resource "aws_cloudwatch_event_rule" "this" {
  for_each = { for rule in var.rules : rule.name => rule }

  name                = "${var.project_name}-${var.environment}-${each.value.name}"
  description         = each.value.description
  schedule_expression = each.value.schedule_expression
  state               = lookup(each.value, "enabled", true) ? "ENABLED" : "DISABLED"

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-${var.environment}-${each.value.name}"
      Environment = var.environment
      Purpose     = "scheduled-job"
    }
  )
}

# EventBridge target (Lambda)
resource "aws_cloudwatch_event_target" "lambda" {
  for_each = { for rule in var.rules : rule.name => rule }

  rule      = aws_cloudwatch_event_rule.this[each.key].name
  target_id = "${each.value.name}-target"
  arn       = each.value.lambda_function_arn

  input = lookup(each.value, "input", null)
}

# Lambda permission for EventBridge
resource "aws_lambda_permission" "eventbridge" {
  for_each = { for rule in var.rules : rule.name => rule }

  statement_id  = "AllowExecutionFromEventBridge-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = each.value.lambda_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.this[each.key].arn
}

# Dead letter queue (optional)
resource "aws_sqs_queue" "dlq" {
  count = var.create_dlq ? 1 : 0

  name                      = "${var.project_name}-${var.environment}-eventbridge-dlq"
  message_retention_seconds = var.dlq_message_retention_seconds

  tags = merge(
    var.tags,
    {
      Name        = "${var.project_name}-${var.environment}-eventbridge-dlq"
      Environment = var.environment
      Purpose     = "dead-letter-queue"
    }
  )
}

