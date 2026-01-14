output "rule_arns" {
  description = "Map of rule names to ARNs"
  value = {
    for rule in var.rules : rule.name => aws_cloudwatch_event_rule.this[rule.name].arn
  }
}

output "dlq_arn" {
  description = "ARN of the dead letter queue (if created)"
  value       = var.create_dlq ? aws_sqs_queue.dlq[0].arn : null
}

